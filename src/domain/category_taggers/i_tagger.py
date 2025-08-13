from abc import ABC


class ITagger(ABC):
    def get_category(self, expense_description: str) -> str:
        pass
    def get_type(self, trx_description: str) -> str:
        pass