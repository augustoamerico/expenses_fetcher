from datetime import datetime
from typing import List

from src.application.password_getter.password_getter import IPasswordGetter
from src.application.account_manager.i_account_manager import IAccountManager
from src.domain.category_taggers.i_tagger import ITagger
from src.domain.transactions import ITransaction, ActiveBankTransaction
from src.infrastructure.bank_account_transactions_fetchers.active_bank_fetcher_crawler import (
    ActiveBankCrawler,
    ITransactionsFetcher,
)
from src.repository.google_sheet_repository import GoogleSheetRepository
from src.application.account_manager.exceptions import AccountNotFoundException


class ActiveBankAccountManager(IAccountManager):
    def __init__(
        self,
        account_id: str,
        username: str,
        password: str,
        remove_transaction_description_prefix: bool,
        taggers: List[ITagger],
        tmp_folder: str,
        password_getter: IPasswordGetter,
    ):
        self.bank = ActiveBankCrawler(
            username,
            password,
            tmp_folder,
            lambda: password_getter.get_password(account_id=account_id),
        )
        self.transactions_fetcher: ITransactionsFetcher = self.bank.get_card(account_id)
        if self.transactions_fetcher is None:
            raise AccountNotFoundException(
                f"The account with id {account_id} was not found"
            )
        self.account_id = account_id
        self.taggers = taggers
        self.remove_transactions_description_prefix = (
            remove_transaction_description_prefix
        )

    def _get_transactions(
        self, date_start: datetime, date_end: datetime
    ) -> List[ITransaction]:
        transactions = []
        for raw_transaction in self.transactions_fetcher.getTransactions(
            date_start, date_end
        ):
            transactions.append(
                ActiveBankTransaction(
                    auth_date=raw_transaction["Data Valor"],
                    capture_date=raw_transaction["Data Lanc."],
                    description=raw_transaction["Descrição"],
                    amount=raw_transaction["Valor"],
                )
            )
        return transactions

    def getCategoryTaggers(self) -> List[ITagger]:
        return self.taggers

    def close(self):
        self.bank.driver.quit()
