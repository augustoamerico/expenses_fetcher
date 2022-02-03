from main import ExpenseFetcherShell, build_expense_fetcher
import yaml
import argparse

parser = argparse.ArgumentParser(description="ExpenseFetcher")
parser.add_argument(
    "--config-file", dest="config_file", help="expense fetcher config file path"
)

args = parser.parse_args()

config = yaml.load(open(args.config_file), Loader=yaml.FullLoader)

expense_fetcher = build_expense_fetcher(config)

if __name__ == "__main__":
    expense_fetcher_shell = ExpenseFetcherShell(expense_fetcher)
    expense_fetcher_shell.do_pull("")
    expense_fetcher_shell.do_sort("")
    expense_fetcher_shell.do_list("")
    expense_fetcher_shell.do_push("")
