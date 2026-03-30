import requests
import json
from datetime import datetime, timedelta, timezone
from datetime import date as datetime_date
from typing import List, Dict, Optional
import logging
from pathlib import Path
from enum import Enum
import os

from src.infrastructure.bank_account_transactions_fetchers.i_transactions_fetcher import (
    ITransactionsFetcher,
)
from src.infrastructure.bank_account_transactions_fetchers.exceptions import (
    NordigenAuthExpiredException,
)
from src.infrastructure.bank_account_transactions_fetchers.nordigen_token_provider import (
    NordigenTokenProvider,
)

log = logging.getLogger(__name__)

DOWNLOAD_DATA_TEMPLATE = (
    "https://bankaccountdata.gocardless.com/api/v2/accounts/{}/transactions/"
)
BALANCE_DATA_TEMPLATE = (
    "https://bankaccountdata.gocardless.com/api/v2/accounts/{}/balances/"
)

INFRA_CACHE_DIR = os.environ.get("INFRA_CACHE_DIR") or "./cache/nordigen/"


class CachePolicy(str, Enum):
    NETWORK_ONLY = "network_only"
    USE_IF_FRESH = "use_if_fresh"


class NordigenFetcher(ITransactionsFetcher):
    def __init__(
        self,
        secret_id: str,
        secret_key: str,
        account: str,
        token_provider: Optional[NordigenTokenProvider] = None,
        cache_dir: Optional[str] = None,
        cache_policy: str = CachePolicy.NETWORK_ONLY.value,
        cache_ttl_hours: int = 3,
    ):
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.account = account
        self.download_data_url = DOWNLOAD_DATA_TEMPLATE.format(account)
        self.balance_data_url = BALANCE_DATA_TEMPLATE.format(account)
        self.token_provider = token_provider or NordigenTokenProvider()
        self.cache_dir = Path(cache_dir or INFRA_CACHE_DIR)
        self.cache_policy = CachePolicy(cache_policy)
        self.cache_ttl = timedelta(hours=cache_ttl_hours)

    def _parse_transaction(self, trx):
        trx["bookingDate"] = datetime.strptime(trx["bookingDate"], "%Y-%m-%d")
        trx["valueDate"] = datetime.strptime(trx["valueDate"], "%Y-%m-%d")
        trx["transactionAmount"] = float(trx["transactionAmount"]["amount"])
        return trx

    def _cache_path(self, resource_name: str) -> Path:
        return self.cache_dir / "{}_{}.json".format(self.account, resource_name)

    def _read_cache_if_fresh(self, resource_name: str) -> Optional[Dict[str, object]]:
        cache_path = self._cache_path(resource_name)
        log.info(f"Reading from {cache_path}")
        if not cache_path.exists():
            log.info("Resources does not exists!")
            return None

        payload = json.loads(cache_path.read_text())
        fetched_at = datetime.fromisoformat(payload["fetched_at"])
        if datetime.now(timezone.utc) - fetched_at > self.cache_ttl:
            log.info(f"Resource exists, but TTL has expired [ttl: {self.cache_ttl}; fetched_at: {fetched_at}; now: {datetime.now(timezone.utc)}]")
            return None

        return payload["data"]

    def _write_cache(self, resource_name: str, data: Dict[str, object]) -> None:
        log.info(f"writing to cache for account {self.account}: {resource_name}")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        log.info(f"wirtting cache into {self._cache_path(resource_name)}")
        self._cache_path(resource_name).write_text(json.dumps(payload))

    def _get_json(self, url: str, resource_name: str) -> Dict[str, object]:
        log.info(f"Fetching transactions for {self.account} with cache policy {self.cache_policy}")
        if self.cache_policy == CachePolicy.USE_IF_FRESH:
            cached = self._read_cache_if_fresh(resource_name)
            if cached is not None:
                log.info(
                    "Using cached Nordigen %s response for account %s",
                    resource_name,
                    self.account,
                )
                return cached
            else:
                log.info(f"reading from resource {resource_name} returned None")

        headers = {
            "accept": "application/json",
            "Authorization": "Bearer {}".format(
                self.token_provider.get_valid_token(self.secret_id, self.secret_key)
            ),
        }
        response = requests.get(url, headers=headers)
        payload = json.loads(response.text)

        self._check_auth_error(payload)
        self._write_cache(resource_name, payload)
        return payload

    def getTransactions(
        self, date_init: datetime = None, date_end: datetime = None, dev: bool = False
    ) -> List[Dict[str, object]]:
        _ = dev
        trxs = self._get_json(self.download_data_url, "transactions")

        try:
            trxs_parsed = [
                self._parse_transaction(trx) for trx in trxs["transactions"]["booked"]
            ]
        except KeyError as e:
            if (
                isinstance(trxs, dict)
                and trxs.get("detail") == "Institution service unavailable"
                and trxs.get("status_code") == 503
                and trxs.get("type") == "ServiceError"
            ):
                log.warning(
                    "Institution service unavailable; skipping transactions fetch "
                    f"for account {self.account}"
                )
                return []
            log.error(f"Error while parsing transactions from account {self.account}")
            log.error(trxs)
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
        return self._get_json(self.balance_data_url, "balances")

    def _check_auth_error(self, response: dict) -> None:
        """Check if API response indicates auth expiration and raise exception if so."""
        if not isinstance(response, dict):
            return

        # Check for various auth expiration patterns from Nordigen/GoCardless API
        summary = response.get("summary", "")
        detail = response.get("detail", "")
        status_code = response.get("status_code")

        auth_expired_indicators = [
            "EUA Expired" in summary,
            "Account has been suspended" in summary,
            status_code == 401,
            status_code == 403 and "expired" in detail.lower(),
            "authentication credentials were not provided" in detail.lower(),
            "access expired" in detail.lower(),
        ]

        if any(auth_expired_indicators):
            log.warning(f"Nordigen auth expired for account {self.account}: {response}")
            raise NordigenAuthExpiredException(
                account_id=self.account,
                message=f"Auth expired: {summary or detail}"
            )
