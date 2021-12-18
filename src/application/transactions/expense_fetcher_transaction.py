from src.domain.transactions import ITransaction, FromListTransaction
import math
from typing import List


class ExpenseFetcherTransaction:
    def __init__(
        self,
        transaction: ITransaction,
        account_name: str,
        debt_description: str,
        income_description: str,
        transfer_description: str,
        date_format: str,
    ):
        self.transaction = transaction
        self.account_name = account_name
        self.transaction_type = (
            debt_description
            if transaction.is_debt()
            else transfer_description
            if transaction.is_transfer()
            else income_description
        )
        self.absolute_value = abs(transaction.get_value())
        self.date_format = date_format

    def to_list(self) -> List[str]:
        return [
            self.transaction.get_capture_date_str(self.date_format),
            self.transaction.get_auth_date_str(self.date_format),
            self.transaction.get_description(),
            self.account_name,
            self.transaction_type,
            self.transaction.get_category(),
            str(self.absolute_value),
            str(self.transaction.get_value()),
        ]

    def __repr__(self):
        return ",".join(self.to_list())

    @staticmethod
    def from_list(
        date_capture: str,
        date_auth: str,
        description: str,
        account_name: str,
        transaction_type: str,
        absolute_transaction_value: float,
        transaction_value: float,
    ):
        flat_transaction = FromListTransaction(
            date_capture, date_auth, description, transaction_value
        )
        return ExpenseFetcherTransaction(flat_transaction, account_name)
