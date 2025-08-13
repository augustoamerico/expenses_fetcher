from abc import ABC, abstractmethod
import datetime
from typing import List
from src.domain.transactions import ITransaction
from src.domain.balance import Balance
from src.domain.category_taggers.i_tagger import ITagger
import logging

log = logging.getLogger(__file__)


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
                        current_category = tagger.get_category(
                            transaction.get_description(
                                self.remove_transactions_description_prefix
                            )
                        )
                        current_type = tagger.get_type(
                            transaction.get_description(
                                self.remove_transactions_description_prefix
                            )
                        )
                        transaction.set_category(current_category)
                        transaction.set_type(current_type)
                        if self.account_names:
                            log.debug("Account manager is receiving account names:")
                            log.debug(self.account_names)
                            if current_category in self.account_names and transaction.get_type() == "":
                                transaction.set_transfer()
                except StopIteration:
                    continue
        return transactions

    @abstractmethod
    def get_balance() -> Balance:
        pass

    @abstractmethod
    def close(self):
        pass
