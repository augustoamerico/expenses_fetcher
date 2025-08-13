from abc import ABC, abstractmethod
from datetime import datetime


class ITransaction(ABC):
    def __init__(
        self,
        auth_date: datetime,
        capture_date: datetime,
        value: float,
        description: str,
        is_income: bool,
        is_transfer: bool,
        is_investment: bool = False
    ):
        self.auth_date = auth_date
        self.capture_date = capture_date
        self.value = value
        self.description = description
        self.is_income_value = is_income
        self.is_debt_value = not is_income
        self.is_transfer_value = is_transfer
        self.is_investment_value = is_investment
        self.type = ""
        self.category = ""

    def get_auth_date_str(self, date_format: str = "%Y/%m/%d") -> str:
        return self.auth_date.strftime(date_format)

    def get_capture_date_str(self, date_format: str = "%Y/%m/%d") -> str:
        return self.capture_date.strftime(date_format)

    def get_value(self) -> float:
        return self.value

    def set_category(self, category: str) -> None:
        self.category = category

    def set_type(self, type: str) -> None:
        self.type = type

    def set_transfer(self, is_transfer: bool = True) -> None:
        self.is_transfer_value = is_transfer
        if is_transfer:
            self.is_debt_value = False
            self.is_income_value = False


    def get_category(self) -> str:
        return self.category

    @abstractmethod
    def get_description(self, remove_prefix: bool = False):
        return self.description
    
    def get_type(self) -> str:
        return self.type

    def is_income(self) -> bool:
        return self.is_income_value

    def is_debt(self) -> bool:
        return not self.is_income_value

    def is_transfer(self) -> bool:
        return self.is_transfer_value
    
    def is_investment(self) -> bool:
        return self.is_investment_value

    def __str__(self):
        # this is here for debugging purposes only
        # return "%s %s %s" % (self.date.isoformat(),self.description,self.value)
        return (
            f"Auth Date: {self.get_auth_date_str()}, Capt Date: {self.get_capture_date_str()}, "
            f"Description: {self.get_description()}, Amount: {self.value}"
        )

    def __repr__(self):
        return self.__str__()
