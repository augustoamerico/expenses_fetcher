from datetime import datetime
from typing import List
from dataclasses import dataclass


@dataclass
class Balance:
    balance_date: datetime
    updated_date_time: datetime
    balance: float
    account: str

    def to_list(self, date_format, account) -> List[str]:
        return [
            self.balance_date.strftime(date_format),
            str(self.updated_date_time),
            account,
            str(self.balance),
        ]
