from src.domain.transactions import ITransaction
import numbers
from datetime import datetime


class FromListTransaction(ITransaction):
    def __init__(
        self, date_capture: str, date_auth: str, description: str, amount: float
    ):
        date_capture_datetime = datetime.strptime(date_capture, "%Y/%m/%d")
        date_auth_datetime = datetime.strptime(date_auth, "%Y/%m/%d")

        if not isinstance(amount, numbers.Number):
            raise Exception("Value is not a numeric variable")
        super().__init__(
            auth_date=date_capture_datetime,
            capture_date=date_auth_datetime,
            value=amount,
            description=description,
            is_income=amount >= 0,
        )

    def get_description(self, remove_prefix: bool = False):
        return self.description
