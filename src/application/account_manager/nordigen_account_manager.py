import datetime
from typing import List

from src.application.account_manager.i_account_manager import IAccountManager
from src.application.account_manager.exceptions import AccountNotFoundException
from src.application.password_getter.password_getter import IPasswordGetter
from src.domain.category_taggers.i_tagger import ITagger
from src.domain.transactions import ITransaction, NordigenTransaction
from src.infrastructure.bank_account_transactions_fetchers.i_transactions_fetcher import (
    ITransactionsFetcher,
)
from src.infrastructure.bank_account_transactions_fetchers.nordigen_fetcher import (
    NordigenFetcher,
)
from src.domain.balance import Balance


class NordigenAccountManager(IAccountManager):
    def __init__(
        self,
        secret_id: str,
        secret_key: str,
        account_id: str,
        remove_transaction_description_prefix: bool,
        taggers: List[ITagger],
        account_names: List[
            str
        ] = None,  # this is needed to compare categories agains account names, to identify transfers
    ):
        self.transactions_fetcher: ITransactionsFetcher = NordigenFetcher(
            secret_id, secret_key, account_id
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
        self.account_names = account_names

    def set_accounts(self, account_names: List[str]) -> None:
        self.account_names = account_names

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
                    transaction_name=raw_transaction[
                        "remittanceInformationUnstructured"
                    ],
                    amount=raw_transaction["transactionAmount"],
                )
            )
        return transactions

    def getCategoryTaggers(self) -> List[ITagger]:
        return self.taggers

    def close(self):
        pass

    def get_balance(self) -> Balance:
        raw_balance = self.transactions_fetcher.get_balance()
        if "balances" in raw_balance:
            args = {}
            for balance_type in raw_balance["balances"]:
                if balance_type["balanceType"] == "closingBooked":
                    args["balance_date"] = datetime.datetime.strptime(
                        balance_type["lastChangeDateTime"], "%Y-%m-%dT%H:%M:%SZ"
                    )
                elif balance_type["balanceType"] == "interimAvailable":
                    args["balance"] = float(balance_type["balanceAmount"]["amount"])
                    args["account"] = None

            args["updated_date_time"] = datetime.datetime.now()
            return Balance(**args)
        return None
