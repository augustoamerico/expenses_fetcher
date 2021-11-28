import numbers
from datetime import datetime

from src.domain.transactions import ITransaction


class NordigenTransaction(ITransaction):
    def __init__(
        self, booked_date: datetime, value_date: datetime, transaction_name: str, amount: float
    ):
        if not isinstance(amount, numbers.Number):
            raise Exception("Value is not a numeric variable")
        super().__init__(
            auth_date=booked_date,
            capture_date=value_date,
            value=amount,
            description=transaction_name,
            is_income=amount >= 0,
        )

    def get_description(self, remove_prefix: bool = False):
        processed_description = self.description
        if remove_prefix:
            raise NotImplemented()
        return processed_description
