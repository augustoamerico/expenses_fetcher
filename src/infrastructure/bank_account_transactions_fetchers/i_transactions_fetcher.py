from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict


class ITransactionsFetcher(ABC):
    @abstractmethod
    def getTransactions(
        self, date_init: datetime = None, date_end: datetime = None
    ) -> List[Dict[str, object]]:
        pass
