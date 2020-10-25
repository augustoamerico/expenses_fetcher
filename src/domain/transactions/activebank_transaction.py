from src.domain.transactions import ITransaction
from typing import Dict
import numbers
from datetime import datetime


class ActiveBankTransaction(ITransaction):
    def __init__(
        self,
        auth_date: datetime,
        capture_date: datetime,
        description: str,
        amount: float,
    ):
        if not isinstance(amount, numbers.Number):
            raise Exception("Value is not a numeric variable")
        super().__init__(
            auth_date=auth_date,
            capture_date=capture_date,
            value=amount,
            description=description,
            is_income=amount >= 0,
        )

    def get_description(self, remove_prefix: bool = False):
        processed_description = self.description
        if remove_prefix:
            raise NotImplemented()
        return processed_description
