from typing import List, Dict
import os

from src.application.account_manager import ActiveBankAccountManager, IAccountManager
from src.application.account_manager.myedenred_account_manager import (
    MyEdenredAccountManager,
)
from src.domain.category_taggers.historic_tagger import HistoricTagger
from src.domain.category_taggers.i_tagger import ITagger
from src.domain.category_taggers.regex_tagger import RegexTaggerBuilder
from src.repository.google_sheet_repository import GoogleSheetRepository
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


def parse_repository(repository, repository_type):
    if repository_type == "googlesheet":
        return GoogleSheetRepository(
            # scopes,
            repository["scopes"],
            # spreadsheet_id
            repository["spreadsheet_id"],
            # expenses_sheet_name
            repository["expenses_sheet_name"],
            # expenses_start_cell
            repository["expenses_start_cell"],
            # metadata_sheet_name
            repository["metadata_sheet_name"],
            # token_path
            repository["token_cache_path"],
            # credentials_path
            repository["credentials_path"],
        )


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

    remove_transaction_description_prefix = False
    if "remove_transaction_description_prefix" in account:
        remove_transaction_description_prefix = account[
            "remove_transaction_description_prefix"
        ]
        if not isinstance(remove_transaction_description_prefix, bool):
            raise Exception(
                "property `remove_transaction_description_prefix` must be bool"
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
