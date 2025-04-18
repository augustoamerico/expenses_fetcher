import requests
import requests_cache
import json
from datetime import datetime
from random import randint
from time import sleep
from typing import List, Dict

from src.application.password_getter.password_getter import IPasswordGetter

from src.infrastructure.bank_account_transactions_fetchers.i_transactions_fetcher import (
    ITransactionsFetcher,
)

DOWNLOAD_DATA_TEMPLATE = (
    "https://bankaccountdata.gocardless.com/api/v2/accounts/{}/transactions/"
)
GET_TOKEN_URL = "https://bankaccountdata.gocardless.com/api/v2/token/new/"
BALANCE_DATA_TEMPLATE = (
    "https://bankaccountdata.gocardless.com/api/v2/accounts/{}/balances/"
)


requests_cache.install_cache("discogs_cache", backend="sqlite", expire_after=180)


class NordigenFetcher(ITransactionsFetcher):
    def __init__(self, secret_id: str, secret_key: str, account: str):
        self.token = self._generate_token(secret_id, secret_key)
        self.account = account
        self.download_data_url = DOWNLOAD_DATA_TEMPLATE.format(account)
        self.balance_data_url = BALANCE_DATA_TEMPLATE.format(account)

    def _generate_token(self, secret_id: str, secret_key: str):
        headers = {"accept": "application/json", "Content-Type": "application/json"}
        data = {"secret_id": secret_id, "secret_key": secret_key}
        r = requests.post(GET_TOKEN_URL, data=json.dumps(data), headers=headers)
        token_response = json.loads(r.text)
        response = None
        try:
            response = token_response["access"]
        except KeyError as err:
            print(token_response)
            print(secret_id)
            print(secret_key)
        return response

    def _parse_transaction(self, trx):
        trx["bookingDate"] = datetime.strptime(trx["bookingDate"], "%Y-%m-%d")
        trx["valueDate"] = datetime.strptime(trx["valueDate"], "%Y-%m-%d")
        trx["transactionAmount"] = float(trx["transactionAmount"]["amount"])
        return trx

    def getTransactions(
        self, date_init: datetime = None, date_end: datetime = None
    ) -> List[Dict[str, object]]:
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        r = requests.get(self.download_data_url, headers=headers)
        trxs = json.loads(r.text)

        try:
            trxs_parsed = [
                self._parse_transaction(trx) for trx in trxs["transactions"]["booked"]
            ]
        except KeyError as e:
            print(f"Error while parsing transactions from account {self.account}")
            print(trxs)
            raise e

        date_init_query = datetime_date.min if date_init is None else date_init.date()
        date_end_query = datetime_date.max if date_end is None else date_end.date()

        return list(
            filter(
                lambda trx: date_init_query
                <= trx["bookingDate"].date()
                <= date_end_query,
                trxs_parsed,
            )
        )

    def get_balance(self) -> Dict[str, object]:
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        r = requests.get(self.balance_data_url, headers=headers)
        balances_txt = json.loads(r.text)
        return balances_txt
