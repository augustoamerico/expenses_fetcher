import os.path
import pickle
from typing import Dict, List, Callable, Optional, Tuple
from datetime import datetime
import requests
import logging
import json

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from src.repository.i_repository import IRepository

LOGIN_URL = "https://www.buxfer.com/api/login"
GET_ACCOUNTS_INFO_URL = "https://www.buxfer.com/api/accounts"
ADD_TRANSACTION = "https://www.buxfer.com/api/add_transaction"
GET_TRANSACTIONS = "https://www.buxfer.com/api/transactions"


class TransferDefinitionMacth:
    def __init__(self, settings: Dict[str, str]):
        self.account_name = settings["account_name"].strip()
        self.description = settings["description"].strip()
        self.category = settings["category"].strip()

    def match(self, account_name: str, description: str, category: str):
        return (
            self.account_name == account_name.strip()
            and self.description == description.strip()
            and self.category == category.strip()
        )


class TransferDefinition:
    def __init__(self, conditions_obj: Dict):
        self.to_definition = TransferDefinitionMacth(conditions_obj["to"])
        self.from_definition = TransferDefinitionMacth(conditions_obj["from"])


class BuxferRepository(IRepository):
    def __init__(
        self,
        username: str,
        password: str = None,
        get_password: Callable = None,
        proxy=None,
        debug=False,
        transfers: List = None,
    ):
        # token_path = 'token.pickle'
        # credentials_path = 'account_transactions_massager/taggers/credentials.json'
        self.session = None
        self.username = username
        self.password = password
        self.get_password = get_password
        self.session_token = None
        self.categories = None
        self.token = None
        self.accounts_accountsId = None
        self.debug = debug
        self._login()
        self._get_accounts()
        self.transfers = list(map(lambda x: TransferDefinition(x), transfers))

    def _login(self) -> Dict:
        self._start()  # load cookies and parameters
        if self.username is None:
            raise AuthenticationException(
                "Need at least the user to access bank account"
            )
        if self.password is None:
            self.password = self.get_password()
        self._authenticate(self.username, self.password)

    def _start(self, cookie_file=None):
        # CURRENTLY NOT SUPPORTING SESSION REUSE
        self._load_session(False)

    def _load_session(self, file_present=True):
        self.session = requests.Session()

    def _authenticate(self, user, password):
        """ Actual authentication. Needs variables previously loaded """
        logging.debug("authenticating...")

        self.login_params = {"email": user, "password": password}
        s = self.session
        r = s.post(url=LOGIN_URL, json=self.login_params, verify=not self.debug)
        # TODO: check if login successful
        try:
            if r.status_code == 200:
                response = json.loads(r.text)
                if "token" in response["response"]:
                    self.token = response["response"]["token"]
                else:
                    raise AuthenticationException(r.text)
        except Exception():
            raise AuthenticationException(r.text)

    def _get_accounts(self):
        response = self.session.get(GET_ACCOUNTS_INFO_URL, params={"token": self.token})
        if response.status_code != 200:
            raise Exception(f"{response.text}")
        accounts = json.loads(response.text)["response"]["accounts"]
        self.accounts_accountsId = dict(
            [(account["name"].strip(), account["id"]) for account in accounts]
        )

    def get_transactions(self):
        """
        Retuns transactions to the application core.
        """
        pass

    def _getCategoryFromTags(self, tags: List[str]):
        if len(tags) == 0:
            return None
        else:
            return tags[0]

    def get_data(self, data_range, columns_indexes: List[int] = None):
        """
        Get pair (description, category) for historic
        """
        total_trx = 1
        fetched_trx = []
        page = 1
        while total_trx - len(fetched_trx) > 0:
            response = self.session.get(
                GET_TRANSACTIONS, params={"token": self.token, "page": page}
            )
            if response.status_code != 200:
                print(response.text)
                raise Exception("Something happened")
            response_obj = json.loads(response.text)
            total_trx = int(response_obj["response"]["numTransactions"])
            fetched_trx.extend(
                [
                    (el["description"], self._getCategoryFromTags(el["tagNames"]))
                    for el in response_obj["response"]["transactions"]
                ]
            )
            page += 1
        return fetched_trx

    def _is_transfer(
        self, trx_account: str, trx_description: str, trx_category: str
    ) -> Tuple[Optional[TransferDefinition], bool, bool]:
        condition_match = None
        for condition in self.transfers:
            is_from = condition.from_definition.match(
                account_name=trx_account,
                description=trx_description,
                category=trx_category,
            )
            is_to = condition.to_definition.match(
                account_name=trx_account,
                description=trx_description,
                category=trx_category,
            )
            if is_from or is_to:
                condition_match = condition

        return condition_match, is_from, is_to

    def batch_insert(self, data: List[List[str]], check_duplicates=True) -> None:
        accounts = {trx[3].strip() for trx in data}
        data.sort(reverse=False, key=lambda x: x[1])
        for account in accounts:
            if account not in self.accounts_accountsId:
                raise Exception(f"Account {account} not recognized")
            current_account_trx = list(filter(lambda x: x[3] == account, data))
            if check_duplicates:
                first_trx_date = datetime.strptime(
                    current_account_trx[0][1], "%Y-%m-%d"
                )
                repository_latest_trx_for_account = self.get_last_transaction_for_account(
                    account
                )
                latest_trx_serielized = set(
                    map(
                        lambda x: f"{x[1]}-{x[3]}-{x[2].strip()}-{x[7]}",
                        repository_latest_trx_for_account,
                    )
                )
                if len(repository_latest_trx_for_account) > 0:
                    latest_datetime = repository_latest_trx_for_account[0][1]
                    if latest_datetime >= first_trx_date:
                        current_account_trx = list(
                            filter(
                                lambda x: f"{datetime.strptime(x[1], '%Y-%m-%d')}-{x[3]}-{x[2].strip()}-{x[7]}"
                                not in latest_trx_serielized
                                and datetime.strptime(x[1], "%Y-%m-%d")
                                >= latest_datetime,
                                current_account_trx,
                            )
                        )
            for trx in current_account_trx:
                description = trx[2].strip()
                trx_category = trx[5].strip()
                transfer_condition, is_from, is_to = self._is_transfer(
                    account, description, trx_category
                )
                if transfer_condition is not None:
                    """
                        This means this is an between-accounts transference.
                        We only want to catch the "from" account trx
                    """
                    if is_from:
                        self._insert_transaction(
                            accountId=self.accounts_accountsId[account],
                            amount=trx[7],
                            description=description,
                            date=trx[1],
                            category=trx_category,
                            trx_type="transfer",
                            from_account_id=self.accounts_accountsId[account],
                            to_account_id=self.accounts_accountsId[
                                transfer_condition.to_definition.account_name
                            ],
                        )
                else:
                    self._insert_transaction(
                        accountId=self.accounts_accountsId[account],
                        amount=trx[7],
                        description=description,
                        date=trx[1],
                        category=trx[5],
                        trx_type=trx[4],
                    )

    def _insert_transaction(
        self,
        accountId,
        amount,
        description,
        date,
        category,
        trx_type,
        from_account_id=None,
        to_account_id=None,
        debug=True,
    ):
        trx_type = trx_type.lower()
        trx_type_bxf = None
        if trx_type == "debt":
            trx_type_bxf = "expense"
        elif trx_type == "income":
            trx_type_bxf = "income"
        elif trx_type == "transfer":
            trx_type_bxf = "transfer"
        else:
            trx_type_bxf = "expense"

        payload = {
            "amount": amount,
            "description": description,
            "accountId": accountId,
            "date": date,
            "tags": category,
            "type": trx_type_bxf,
            "fromAccountId": from_account_id,
            "toAccountId": to_account_id,
        }
        response = self.session.post(
            url=ADD_TRANSACTION, json=payload, params={"token": self.token}
        )
        if response.status_code != 200:
            print(payload)
            print(response.text)
            raise Exception("Failed to add transaction")
        if debug:
            print(f"trx {payload} added")

    def sort_transactions(self, column_index_order_by: int):
        """
        Sort transactions in the repo
        """
        pass

    def get_last_transaction_date_for_account(self, account_name: str) -> datetime:
        response = self.session.get(
            GET_TRANSACTIONS,
            params={
                "token": self.token,
                "accountId": self.accounts_accountsId[account_name],
            },
        )
        if response.status_code != 200:
            return None
        most_recent_transaction = json.loads(response.text)["response"]["transactions"][
            0
        ]
        most_recent_transaction_date = most_recent_transaction["date"]
        last_datetime = datetime.strptime(most_recent_transaction_date, "%Y-%m-%d")
        return last_datetime

    def get_last_transaction_for_account(self, account_name: str) -> List[str]:
        response = self.session.get(
            GET_TRANSACTIONS,
            params={
                "token": self.token,
                "accountId": self.accounts_accountsId[account_name],
            },
        )
        if response.status_code != 200:
            return None
        transactions = json.loads(response.text)["response"]["transactions"]
        if len(transactions) > 0:
            most_recent_transaction_date = transactions[0]["date"]
            most_recent_transactions = list(
                filter(
                    lambda x: x["date"] == most_recent_transaction_date, transactions
                )
            )
            most_recent_transactions_parsed = list(
                map(self._parse_transaction_to_list, most_recent_transactions)
            )
            return most_recent_transactions_parsed
        return []

    def _convert_from_buxfer_type_to_domain_type(
        self, buxfer_type: str, category, account_name, description
    ):
        domain_type = ""
        if buxfer_type == "transfer":
            _, is_from, is_to = self._is_transfer(account_name, description, category)
            if is_from:
                domain_type = "Debt"
            elif is_to:
                domain_type = "Income"
            else:
                raise Exception("unexpected condition")
        elif buxfer_type == "expense":
            domain_type = "Debt"
        elif buxfer_type == "income":
            domain_type = "Income"
        else:
            raise Exception("unexpected condition")
        return domain_type

    def _parse_transaction_to_list(self, buxfer_transaction):
        category = next(iter(buxfer_transaction["tagNames"]))
        if buxfer_transaction["type"] == "transfer":
            account_name = buxfer_transaction["fromAccount"]["name"]
        else:
            account_name = buxfer_transaction["accountName"]
        trx_type = self._convert_from_buxfer_type_to_domain_type(
            buxfer_transaction["type"],
            category,
            account_name,
            buxfer_transaction["description"],
        )
        return [
            datetime.strptime(buxfer_transaction["date"], "%Y-%m-%d"),
            datetime.strptime(buxfer_transaction["date"], "%Y-%m-%d"),
            buxfer_transaction["description"],
            account_name,
            trx_type,
            category,
            abs(buxfer_transaction["amount"]),
            buxfer_transaction["amount"]
            if trx_type == "Income"
            else buxfer_transaction["amount"] * -1,
        ]

    def push_categories(self, categories: List[str]) -> None:
        """
        push categories. In Buxfer, they are called tags
        """

    def pull_categories(self) -> List[str]:
        pass

    def add_category(self, category: str):
        """
        Add a new category to current state
        """
        pass

    def pull_accounts(self):
        self._get_accounts()
