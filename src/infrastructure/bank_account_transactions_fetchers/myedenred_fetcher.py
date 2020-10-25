# -*- coding: utf-8 -*-
# This code is slightly adapted from https://github.com/ruicovelo/mymoney/blob/master/mymoney/myedenred.py
from typing import List, Dict, Callable

import requests
import json
import time
from datetime import datetime
from datetime import date as datetime_date
import logging
import urllib.request
from src.infrastructure.bank_account_transactions_fetchers.i_transactions_fetcher import (
    ITransactionsFetcher,
)
from src.infrastructure.bank_account_transactions_fetchers.exceptions import (
    AuthenticationException,
)


BASE_URL = "https://www.myedenred.pt/edenred-customer/api/"
LOGIN_URL = BASE_URL + "authenticate/default?appVersion=1.0&appType=PORTAL&channel=WEB"


GETCARD_TRANSACTIONS_URL = (
    BASE_URL
    + "protected/card/<card_id>/accountmovement?_=<timestamp>&appVersion=1.0&appType=PORTAL&channel=WEB"
)  # noqa
GETCARDS_URL = (
    BASE_URL
    + "protected/card/list?_=<timestamp>&appVersion=1.0&appType=PORTAL&channel=WEB"
)  # noqa


class MyEdenred:
    name = "MyEdenred"
    __OSVSTATE = None
    __VIEWSTATE = None

    def __init__(
        self,
        username: str,
        password: str = None,
        get_password: Callable = None,
        proxy=None,
        debug=False,
    ):
        self.username = username
        self.password = password
        self.get_password = get_password
        self.debug = debug
        self.session = None
        self.proxy = None
        self.add_proxy(proxy)
        self.login()

    def add_proxy(self, proxy):  # TODO: maybe this should be moved somewhere
        if proxy:
            # TODO: support other kinds of proxies?
            self.proxy = urllib.request.ProxyHandler({"https": proxy})
        else:
            self.proxy = None

    def login(self):
        self.start()  # load cookies and parameters
        if self.username is None:
            raise AuthenticationException(
                "Need at least the user to access bank account"
            )
        if self.password is None:
            self.password = self.get_password()
        self.authenticate(self.username, self.password)

    def start(self, cookie_file=None):
        # CURRENTLY NOT SUPPORTING SESSION REUSE
        self.load_session(False)

    def load_session(self, file_present=True):
        self.session = requests.Session()

    def authenticate(self, user, password):
        """ Actual authentication. Needs variables previously loaded """
        logging.debug("authenticating...")

        self.login_params = {"userId": user, "password": password, "rememberMe": True}
        s = self.session
        r = s.post(url=LOGIN_URL, json=self.login_params, verify=not self.debug)
        # TODO: check if login successful
        try:
            if r.status_code == 200:
                response = json.loads(r.text)
                if "token" in response["data"]:
                    self.token = response["data"]["token"]
                else:
                    raise AuthenticationException(r.text)
        except Exception():
            raise AuthenticationException(r.text)

    def get_card_list(self):
        s = self.session
        cards = []
        ts = str(time.time()).split(".")[0]
        r = s.get(
            headers={"Authorization": self.token},
            url=GETCARDS_URL.replace("<timestamp>", ts),
        )
        response = json.loads(r.text)
        for card_info in response["data"]:
            card = MyEdenredCard(self, card_info)
            cards.append(card)
        return cards

    def get_card(self, card_id):
        logging.debug("getting card")
        cards = self.get_card_list()
        for card in cards:
            if card.id == card_id:
                return card


class MyEdenredCard(ITransactionsFetcher):
    def __init__(self, bank, card_info):
        self.bank = bank
        self.id = card_info["id"]
        self.number = card_info["number"]
        self.owner_name = card_info["ownerName"]
        self.status = card_info["status"]
        self.full_data = card_info
        self.account_info = None
        self.movement_list = None

    def getTransactions(
        self, date_init: datetime = None, date_end: datetime = None
    ) -> List[Dict[str, object]]:
        date_init_query = datetime_date.min if date_init is None else date_init.date()
        date_end_query = datetime_date.max if date_end is None else date_end.date()
        return list(
            filter(
                lambda trx: date_init_query
                <= trx["transactionDate"].date()
                <= date_end_query,
                self.get_movements(),
            )
        )

    def get_movements(self):
        s = self.bank.session
        transactions = []
        ts = str(time.time()).split(".")[0]
        r = self.bank.session.get(
            headers={"Authorization": self.bank.token},
            url=GETCARD_TRANSACTIONS_URL.replace("<card_id>", str(self.id)).replace(
                "<timestamp>", ts
            ),
        )
        response = json.loads(r.text)
        self.account_info = response["data"]["account"]
        self.movement_list = response["data"]["movementList"]
        for movement in self.movement_list:
            movement["transactionDate"] = datetime.strptime(
                movement["transactionDate"][0:19], "%Y-%m-%dT%H:%M:%S"
            )
            transactions.append(movement)
        return transactions

    def __repr__(self):
        return f"id: {self.id}; number: {self.number}"
