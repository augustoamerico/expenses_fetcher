import requests
import json
from datetime import datetime
from random import randint
from time import sleep
from typing import List, Dict

from src.application.password_getter.password_getter import IPasswordGetter

from src.infrastructure.bank_account_transactions_fetchers.i_transactions_fetcher import (
    ITransactionsFetcher,
)

DOWNLOAD_DATA_TEMPLATE = "https://ob.nordigen.com/api/accounts/{}/transactions/"


class NordigenFetcher(ITransactionsFetcher):
    def __init__(
        self,
        token: str,
        account: str,
        
    ):
        self.token = token
        self.account = account
        self.download_data_url = DOWNLOAD_DATA_TEMPLATE.format(account)

    def _parse_transaction(self, trx):
        trx["bookingDate"] = datetime.strptime(
                trx["bookingDate"], "%Y-%m-%d"
            ) 
        trx["valueDate"] = datetime.strptime(
                trx["valueDate"], "%Y-%m-%d"
            ) 
        trx["transactionAmount"] = float(trx["transactionAmount"]["amount"])
        return trx

    def getTransactions(
        self, date_init: datetime = None, date_end: datetime = None
    ) -> List[Dict[str, object]]:
        headers = {'accept': 'application/json', 'Authorization': f'Token {self.token}'}
        r = requests.get(self.download_data_url, headers=headers)
        trxs = json.loads(r.text)
        
        trxs_parsed = [self._parse_transaction(trx) for trx in trxs["transactions"]["booked"]]
        
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
        
   
