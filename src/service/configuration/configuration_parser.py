from typing import List, Dict
import os
import importlib

from src.application.account_manager.i_account_manager import IAccountManager
from src.application.account_manager.myedenred_account_manager import (
    MyEdenredAccountManager,
)
from src.application.account_manager.nordigen_account_manager import (
    NordigenAccountManager,
)
from src.domain.category_taggers.historic_tagger import HistoricTagger
from src.domain.category_taggers.i_tagger import ITagger
from src.domain.category_taggers.regex_tagger import RegexTaggerBuilder
from src.repository.google_sheet_repository import GoogleSheetRepository
# Buxfer sink has been removed
from src.repository.i_repository import IRepository


class GeneralAccountInfo:
    def __init__(
        self,
        username: str = None,
        password: str = None,
        remove_transaction_description_prefix: bool = None,
        taggers: List[ITagger] = None,
    ):
        self.username = username
        self.password = password
        self.remove_transaction_description_prefix = (
            remove_transaction_description_prefix
        )
        self.taggers = taggers


def parse_taggers(
    category_taggers, base_repository: IRepository = None
) -> List[ITagger]:

    taggers: List = []

    for tagger_type in category_taggers:
        tagger = category_taggers[tagger_type]
        if tagger_type == "regex":
            regex_tagger_builder = RegexTaggerBuilder()

            for category in tagger:
                regex_tagger_builder.add_category_regex(category, tagger[category][0])

            taggers.append(regex_tagger_builder.build())
        elif tagger_type == "historic_from":
            # To be implemented - accept a list of Account Ids to be selective from where to get historic
            taggers.append(HistoricTagger(base_repository))

    return taggers


def parse_repository(repository, repository_type, password_getter):
    if repository_type == "googlesheet":
        return GoogleSheetRepository(**repository)
    elif repository_type == "buxfer":
        raise Exception(
            "The 'buxfer' repository sink has been removed from the codebase. Please remove it from your configuration."
        )


def parse_remove_transaction_description_prefix(account):
    remove_transaction_description_prefix = False
    if "remove_transaction_description_prefix" in account:
        remove_transaction_description_prefix = account[
            "remove_transaction_description_prefix"
        ]
        if not isinstance(remove_transaction_description_prefix, bool):
            raise Exception(
                "property `remove_transaction_description_prefix` must be bool"
            )
    return remove_transaction_description_prefix


def get_general_account_info(account, account_name, repositories) -> GeneralAccountInfo:
    if "username_env" in account:
        username = os.environ[account["username_env"]]
    elif "username" in account:
        username = account["username"]
    else:
        raise Exception(f"You must define a username for the account {account_name}")

    if "password_env" in account:
        password = os.environ[account["password_env"]]
    elif "password" in account:
        password = account["password"]
    else:
        password = None

    remove_transaction_description_prefix = parse_remove_transaction_description_prefix(
        account
    )

    taggers = parse_taggers(account["category_taggers"], next(iter(repositories)))

    return GeneralAccountInfo(
        username=username,
        password=password,
        remove_transaction_description_prefix=remove_transaction_description_prefix,
        taggers=taggers,
    )


def parse_account(
    account, account_name, repositories, tmp_directory, password_getter
) -> IAccountManager:
    account_type = account["type"].lower().strip()
    if account_type == "activebank-debit" or account_type == "activebank-precard":

        ActiveBankAccountManager = importlib.import_module(
            "src.application.account_manager.active_bank_account_manager",
            package=__package__,
        ).ActiveBankAccountManager
        general_account_info = get_general_account_info(
            account, account_name, repositories
        )

        return ActiveBankAccountManager(
            str(account["card_number"]),
            general_account_info.username,
            general_account_info.password,
            general_account_info.remove_transaction_description_prefix,
            general_account_info.taggers,
            tmp_directory,
            password_getter,
        )
    elif account_type == "myedenred":

        MyEdenredAccountManager = importlib.import_module(
            "src.application.account_manager.myedenred_account_manager",
            package=__package__,
        ).MyEdenredAccountManager

        general_account_info = get_general_account_info(
            account, account_name, repositories
        )

        return MyEdenredAccountManager(
            str(account["card_number"]),
            general_account_info.username,
            general_account_info.password,
            general_account_info.remove_transaction_description_prefix,
            general_account_info.taggers,
            password_getter,
        )
    elif account_type == "nordigen-account":

        NordigenAccountManager = importlib.import_module(
            "src.application.account_manager.nordigen_account_manager",
            package=__package__,
        ).NordigenAccountManager

        return NordigenAccountManager(
            account["secret_id"],
            account["secret_key"],
            account["account"],
            parse_remove_transaction_description_prefix(account),
            parse_taggers(account["category_taggers"], next(iter(repositories))),
        )
