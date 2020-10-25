from abc import ABC


class ITagger(ABC):
    def get_category(self, expense_description: str) -> str:
        pass
