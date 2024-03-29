from datetime import datetime, timedelta
from src.application.account_manager.i_account_manager import IAccountManager
from typing import Iterable, Dict
from enum import Enum

from src.application.transactions.expense_fetcher_transaction import (
    ExpenseFetcherTransaction,
)
from src.repository.i_repository import IRepository

from typing import List
import logging

log = logging.getLogger(__file__)


class OrderBy(Enum):
    AUTH_DATE = 1
    CAPTURE_DATE = 0


class ExpensesFetcher:
    def __init__(
        self,
        repositories: Dict[str, IRepository],
        accounts: Dict[str, IAccountManager],
        debt_description: str = "Debt",
        income_description: str = "Income",
        transfer_description: str = "Transfer",
        date_format: str = "%Y/%M/%D",
    ):
        self.repositories = repositories
        self.accounts = accounts
        self.staged_transactions: List[List[str]] = list()
        self.debt_description = debt_description
        self.income_description = income_description
        self.transfer_description = transfer_description
        self.date_format = date_format
        self.staged_balances: List[List[str]] = list()
        account_names = list(accounts.keys())
        for account_name in account_names:
            self.accounts[account_name].set_accounts(account_names)

    def pull_transactions(
        self,
        date_start: datetime = None,
        date_end: datetime = None,
        account_name: str = None,
        apply_categories: bool = False,
    ):
        if account_name is None:
            accounts_iterator: Iterable[(str, IAccountManager)] = self.accounts.items()
        else:
            accounts_iterator: Iterable[(str, IAccountManager)] = [
                (account_name, self.accounts.get(account_name, None))
            ]

        try:
            for account_name, account_manager in accounts_iterator:

                current_balance = account_manager.get_balance()
                if current_balance is not None:
                    self.staged_balances.append(
                        current_balance.to_list(self.date_format, account_name)
                    )

                if date_start is None:
                    _, pivot_repository = next(iter(self.repositories.items()))
                    date_get_from_repo = pivot_repository.get_last_transaction_date_for_account(
                        account_name
                    )

                    if date_get_from_repo is None:
                        date_start_fetched = datetime.strptime("1970-01-01", "%Y-%m-%d")
                    else:
                        date_start_fetched = date_get_from_repo
                    # date_start_fetched = date_start_fetched + timedelta(days=1)
                    log.debug(
                        f"Reference data for account {account_name} is {date_start_fetched}"
                    )
                else:
                    date_start_fetched = date_start
                if date_end is None:
                    date_end_fetched = datetime.today()
                else:
                    date_end_fetched = date_end
                if date_start_fetched <= date_end_fetched:
                    self.staged_transactions.extend(
                        map(
                            lambda transaction: ExpenseFetcherTransaction(
                                transaction,
                                account_name,
                                self.debt_description,
                                self.income_description,
                                self.transfer_description,
                                self.date_format,
                            ).to_list(),
                            account_manager.get_transactions(
                                date_start_fetched, date_end_fetched, apply_categories
                            ),
                        )
                    )
        except StopIteration:
            pass

    def sort_transactions(
        self, by: int = OrderBy.AUTH_DATE.value, reverse: bool = False
    ):
        self.staged_transactions = sorted(
            self.staged_transactions, key=lambda x: x[by], reverse=reverse
        )

    def get_accounts_iterator(self) -> Iterable[IAccountManager]:
        return iter(self.accounts)

    def get_account(self, account_name) -> IAccountManager:
        return self.accounts.get(account_name, None)

    def pull_transactions_from_repository(self, repository: str):
        if repository not in self.repositories:
            raise Exception("repository unknown")
        repo = self.repositories[repository]
        self.staged_transactions.extend(repo.get_transactions())

    def push_transactions(self, repository_name: str = None):
        if repository_name is None:
            repository_iterator = iter(self.repositories.items())
        else:
            repository_iterator = iter(
                [(repository_name, self.repositories.get(repository_name, None))]
            )

        try:
            for _, repository in repository_iterator:
                repository.batch_insert(self.staged_transactions)
                repository.append_balances(self.staged_balances)
        except StopIteration:
            pass

    def remove_transactions(self, account_name: str = None):
        if account_name is None:
            self.staged_transactions = []
        else:
            self.staged_transactions = list(
                filter(lambda x: x[3] is not account_name, self.staged_transactions)
            )

    def check_duplicates(self, account_name: str = None):
        pass

    def close_all_connections(self):
        for account in self.accounts:
            self.accounts[account].close()


class ExpenseFetcherBuilder:
    def __init__(self):
        self.repositories: Dict[str, IRepository] = dict()
        self.accounts: Dict[str, IAccountManager] = dict()

    def add_repository(self, repository_name: str, repository: IRepository):
        self.repositories[repository_name] = repository

    def add_account(self, account_name: str, account: IAccountManager):
        self.accounts[account_name] = account

    def build(self):
        return ExpensesFetcher(self.repositories, self.accounts)
