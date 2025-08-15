from src.domain.transactions import ITransaction
import numbers
from datetime import datetime


class FromListTransaction(ITransaction):
    def __init__(
        self, date_capture: str, date_auth: str, description: str, amount: float, date_format: str = "%Y/%m/%d"
    ):
        capture_dt = datetime.strptime(date_capture, date_format)
        auth_dt = datetime.strptime(date_auth, date_format)

        if not isinstance(amount, numbers.Number):
            raise Exception("Value is not a numeric variable")
        super().__init__(
            auth_date=auth_dt,
            capture_date=capture_dt,
            value=amount,
            description=description,
            is_income=amount >= 0,
            is_transfer=False,
            is_investment=False,
        )

    def get_description(self, remove_prefix: bool = False):
        return self.description
