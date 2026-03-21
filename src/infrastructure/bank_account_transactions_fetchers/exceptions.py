class AuthenticationException(Exception):
    pass


class DownloadTransactionsXlsException(Exception):
    pass


class NordigenAuthExpiredException(Exception):
    """Raised when Nordigen authorization has expired and needs renewal."""

    def __init__(self, account_id: str, message: str = None):
        self.account_id = account_id
        super().__init__(message or f"Authorization expired for account {account_id}")
