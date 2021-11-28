import datetime
from typing import List

from src.application.account_manager import IAccountManager, AccountNotFoundException
from src.application.password_getter.password_getter import IPasswordGetter
from src.domain.category_taggers.i_tagger import ITagger
from src.domain.transactions import ITransaction, NordigenTransaction
from src.infrastructure.bank_account_transactions_fetchers.i_transactions_fetcher import (
    ITransactionsFetcher,
)
from src.infrastructure.bank_account_transactions_fetchers.nordigen_fetcher import (
    NordigenFetcher,
)


class NordigenAccountManager(IAccountManager):
    def __init__(
        self,
        token: str,
        account_id: str,
        remove_transaction_description_prefix: bool,
        taggers: List[ITagger]
    ):
        self.transactions_fetcher: ITransactionsFetcher = NordigenFetcher(
            token,
            account_id
        )
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
                NordigenTransaction(
                    booked_date=raw_transaction["bookingDate"],
                    value_date=raw_transaction["valueDate"],
                    transaction_name=raw_transaction["remittanceInformationUnstructured"],
                    amount=raw_transaction["transactionAmount"],
                )
            )
        return transactions

    def getCategoryTaggers(self) -> List[ITagger]:
        return self.taggers

    def close(self):
        pass
