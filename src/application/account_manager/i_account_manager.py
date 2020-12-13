from abc import ABC, abstractmethod
import datetime
from typing import List
from src.domain.transactions import ITransaction
from src.domain.category_taggers.i_tagger import ITagger


class IAccountManager(ABC):
    @abstractmethod
    def _get_transactions(
        self, date_start: datetime, date_end: datetime
    ) -> List[ITransaction]:
        pass

    @abstractmethod
    def getCategoryTaggers(self) -> List[ITagger]:
        pass

    def get_transactions(
        self, date_start: datetime, date_end: datetime, apply_taggers: bool = False
    ) -> List[ITransaction]:
        transactions = self._get_transactions(date_start, date_end)
        if apply_taggers:
            for transaction in transactions:
                tagger_iterable = iter(self.taggers)
                try:
                    while transaction.get_category() == "":
                        tagger = next(tagger_iterable)
                        transaction.set_category(
                            tagger.get_category(
                                transaction.get_description(
                                    self.remove_transactions_description_prefix
                                )
                            )
                        )
                except StopIteration:
                    continue
        return transactions

    @abstractmethod
    def close(self):
        pass
