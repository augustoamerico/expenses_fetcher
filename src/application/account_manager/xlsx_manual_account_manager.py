import datetime
from typing import List, Optional

from src.application.account_manager.i_account_manager import IAccountManager
from src.application.account_manager.exceptions import AccountNotFoundException
from src.domain.category_taggers.i_tagger import ITagger
from src.domain.transactions import ITransaction, FromListTransaction
from src.infrastructure.bank_account_transactions_fetchers.i_transactions_fetcher import (
    ITransactionsFetcher,
)
from src.infrastructure.bank_account_transactions_fetchers.xlsx_transactions_fetcher import (
    XlsxTransactionsFetcher,
)
from src.domain.balance import Balance


class XlsxManualAccountManager(IAccountManager):
    def __init__(
        self,
        account_name: str,
        header_skip_rows: int,
        date_format: str,
        decimal_separator: str,
        thousands_separator: str,
        columns: dict,
        remove_transaction_description_prefix: bool,
        taggers: List[ITagger],
        sheet_name: Optional[str] = None,
        prompt_for_file_path: bool = True,
        file_path: Optional[str] = None,
    ):
        self.account_name = account_name
        self.taggers = taggers
        self.remove_transactions_description_prefix = (
            remove_transaction_description_prefix
        )
        self.prompt_for_file_path = prompt_for_file_path
        self.file_path = file_path
        self.sheet_name = sheet_name
        self.transactions_fetcher: ITransactionsFetcher = XlsxTransactionsFetcher(
            header_skip_rows=header_skip_rows,
            date_format=date_format,
            decimal_separator=decimal_separator,
            thousands_separator=thousands_separator,
            columns=columns,
            sheet_name=sheet_name,
        )
        self._latest_balance_value: Optional[float] = None
        self._latest_balance_date: Optional[datetime.datetime] = None
        self.account_names = None

    def set_accounts(self, account_names: List[str]) -> None:
        self.account_names = account_names

    def _resolve_file_path(self) -> str:
        if self.file_path:
            return self.file_path
        if self.prompt_for_file_path:
            path = input(
                f"Please enter the path to the XLSX file for '{self.account_name}': "
            ).strip()
            if not path:
                raise Exception("No file path provided")
            self.file_path = path
            return path
        raise Exception("file_path not set and prompt_for_file_path is False")

    def _get_transactions(
        self, date_start: datetime, date_end: datetime
    ) -> List[ITransaction]:
        path = self._resolve_file_path()
        raw_rows = self.transactions_fetcher.getTransactions(
            date_init=date_start, date_end=date_end, file_path=path
        )

        # Track latest balance
        self._latest_balance_value = None
        self._latest_balance_date = None

        txs: List[ITransaction] = []
        for row in raw_rows:
            capture = row["captureDate"].strftime("%Y/%m/%d")
            auth = row["authDate"].strftime("%Y/%m/%d")
            desc = row["description"]
            amount = row["amount"]
            txs.append(FromListTransaction(capture, auth, desc, amount))

            if row.get("balance") is not None:
                self._latest_balance_value = row["balance"]
                self._latest_balance_date = row["authDate"] or row["captureDate"]

        return txs

    def getCategoryTaggers(self) -> List[ITagger]:
        return self.taggers

    def close(self):
        pass

    def get_balance(self) -> Balance:
        if self._latest_balance_value is not None:
            return Balance(
                balance_date=self._latest_balance_date,
                updated_date_time=datetime.datetime.now(),
                balance=self._latest_balance_value,
                account=None,
            )
        return None
