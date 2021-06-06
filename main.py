import argparse
import os, sys
import yaml
from typing import List
import cmd
from tabulate import tabulate
from datetime import datetime

from src.application.expenses_fetcher.expenses_fetcher import ExpensesFetcher
from src.service.configuration import configuration_parser as cfg_parser
from src.service.password_getter_tty import TTYPasswordGetter

parser = argparse.ArgumentParser(description="ExpenseFetcher")
parser.add_argument(
    "--config-file", dest="config_file", help="expense fetcher config file path"
)

args = parser.parse_args()

print(args.config_file)

password_getter = TTYPasswordGetter("Password for account {} :")
password_getter_repo = TTYPasswordGetter("Password for repository {} :")
config = yaml.load(open(args.config_file), Loader=yaml.FullLoader)


def build_expense_fetcher(config):

    if "expense_fetcher_options" in config:
        if "tmp_dir_path" in config["expense_fetcher_options"]:
            tmp_dir = config["expense_fetcher_options"]["tmp_dir_path"]
        else:
            tmp_dir = os.path.join(os.environ.get("HOME"), ".expense_fetcher_tmp")
        try:
            os.mkdir(tmp_dir)
        except FileExistsError:
            pass

    repositories = dict()
    if "repositories" in config:
        repo_cfg = config["repositories"]
        repositories = dict(
            [
                (
                    repository_name,
                    cfg_parser.parse_repository(
                        config["repositories"][repository_name],
                        repository_name,
                        password_getter_repo,
                    ),
                )
                for repository_name in repo_cfg
            ]
        )
    else:
        raise Exception("No repositories defined")

    accounts = dict()
    if "accounts" in config:
        accounts_cfg = config["accounts"]
        accounts = dict(
            [
                (
                    account_name,
                    cfg_parser.parse_account(
                        accounts_cfg[account_name],
                        account_name,
                        repositories.values(),
                        tmp_dir,
                        password_getter,
                    ),
                )
                for account_name in accounts_cfg
            ]
        )
    else:
        raise Exception("No accounts defined")

    transactions_cfg = {}
    if "transactions" in config:
        transactions_cfg["debt_description"] = (
            None
            if "debt" not in config["transactions"]
            else config["transactions"]["debt"]
        )
        transactions_cfg["income_description"] = (
            None
            if "income" not in config["transactions"]
            else config["transactions"]["income"]
        )
        transactions_cfg["date_format"] = (
            None
            if "date_format" not in config["transactions"]
            else config["transactions"]["date_format"]
        )

    return ExpensesFetcher(repositories, accounts, **transactions_cfg)


class ExpenseFetcherShell(cmd.Cmd):
    intro = "Welcome to the expenses fetcher shell. Type help or ? to list commands.\n"
    prompt = "Expenses Fetcher >> "
    file = None

    def __init__(self, expense_fetcher: ExpensesFetcher):
        super().__init__()
        self.expense_fetcher = expense_fetcher

    @staticmethod
    def _parse_datetime(parameters, parameter_name: str, input_format):
        try:
            return datetime.strptime(
                parameters[parameter_name],
                "%Y-%m-%d" if input_format is None else input_format,
            )
        except Exception:
            raise Exception(
                f"something went wrong while converting the input `{parameter_name}`. "
                f"Unless you have defined `transactions.date_format` otherwise, the default "
                f"format is YYYY-mm-dd"
            )

    @staticmethod
    def _parse_boolean(parameters, parameter_name: str):
        if (
            parameters[parameter_name] == "False"
            or parameters[parameter_name] == "True"
        ):
            return bool(parameters[parameter_name])
        else:
            raise Exception(
                f"parameter `{parameter_name}` must be either True or False"
            )

    # ----- basic turtle commands -----
    def do_pull(self, arg):
        "Pull the transactions from"
        parameters = parse(arg)
        if "apply_categories" in parameters:
            parameters["apply_categories"] = self._parse_boolean(
                parameters, "apply_categories"
            )
        else:
            parameters["apply_categories"] = True
        if "date_start" in parameters:
            parameters["date_start"] = self._parse_datetime(
                parameters, "date_start", self.expense_fetcher.date_format
            )
        if "date_end" in parameters:
            parameters["date_end"] = self._parse_datetime(
                parameters, "date_start", self.expense_fetcher.date_format
            )
        self.expense_fetcher.pull_transactions(**parameters)

    def do_sort(self, arg):
        "Sort transactions. sort_transcations reverse = False"
        parameters = parse(arg)
        if "reverse" in parameters:
            if parameters["reverse"] == "False" or parameters["reverse"] == "True":
                parameters["reverse"] = bool(parameters["reverse"])
            else:
                raise Exception("parameter `reverse` must be either True or False")
        self.expense_fetcher.sort_transactions(**parameters)

    def do_push(self, arg):
        parameters = parse(arg)
        # try:
        self.expense_fetcher.push_transactions(**parameters)
        # except Exception as e:
        #    print(e)

    def do_remove(self, arg):
        parameters = parse(arg)
        self.expense_fetcher.remove_transactions(**parameters)

    def do_list(self, arg):
        parameters = parse(arg)
        print(
            tabulate(
                self.expense_fetcher.staged_transactions,
                headers=[
                    "Date Capture",
                    "Date Auth",
                    "Description",
                    "Account Name",
                    "Type",
                    "Category",
                    "Unsigned Value",
                    "Value",
                ],
            )
        )

    def do_pull_from_sink(self, arg):
        parameters = parse(arg)
        try:
            self.expense_fetcher.pull_transactions_from_repository(**parameters)
        except Exception as e:
            print(e)

    def do_setup_google_api(self):
        """
        1. Acede a https://console.developers.google.com/apis/ e cria um novo projeto
            1.1 - Project name: You can write what you think it suits better. For example, "ExpenseFetcher"
        2. Abrindo o projecto acabado de criar, temos que ativar a API do serviço Google Sheet
        3. Com a API ativa, vamos criar credenciais para a mesma
            - Google Sheet API
            - Other UI (for example, Windows, CLI tool)
            - App Data
        2. Select "Desktop App" as the Oauth client type
        3. Download your credentials. You need to refer these along the process
        """
        print("Not implemented yet")

    def do_exit(self, arg):
        self.expense_fetcher.close_all_connections()
        sys.exit()


def parse(arg):
    "Convert a series of zero or more numbers to an argument tuple"
    parameters = {}
    for key_value in map(str.strip, arg.split(",")):
        if key_value != "":
            key, value = key_value.split("=")
            parameters[key.strip()] = value.strip()
    return parameters


if __name__ == "__main__":
    expense_fetcher = build_expense_fetcher(config)
    ExpenseFetcherShell(expense_fetcher).cmdloop()
