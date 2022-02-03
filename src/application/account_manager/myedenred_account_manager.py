import datetime
from typing import List

from src.application.account_manager.i_account_manager import IAccountManager
from src.application.account_manager.exceptions import AccountNotFoundException
from src.application.password_getter.password_getter import IPasswordGetter
from src.domain.category_taggers.i_tagger import ITagger
from src.domain.transactions import ITransaction, MyEdenredTransaction
from src.infrastructure.bank_account_transactions_fetchers.i_transactions_fetcher import (
    ITransactionsFetcher,
)
from src.infrastructure.bank_account_transactions_fetchers.myedenred_fetcher import (
    MyEdenred,
)


class MyEdenredAccountManager(IAccountManager):
    def __init__(
        self,
        account_id: str,
        username: str,
        password: str,
        remove_transaction_description_prefix: bool,
        taggers: List[ITagger],
        password_getter: IPasswordGetter,
    ):
        self.bank = MyEdenred(
            username,
            password,
            lambda: password_getter.get_password(account_id=account_id),
        )
        self.transactions_fetcher: ITransactionsFetcher = self.bank.get_card(
            int(account_id)
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
                MyEdenredTransaction(
                    transaction_date=raw_transaction["transactionDate"],
                    transaction_name=raw_transaction["transactionName"],
                    amount=raw_transaction["amount"],
                )
            )
        return transactions

    def getCategoryTaggers(self) -> List[ITagger]:
        return self.taggers

    def close(self):
        pass
