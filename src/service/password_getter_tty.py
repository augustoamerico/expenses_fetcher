from src.application.password_getter.password_getter import IPasswordGetter
import sys
import getpass


class TTYPasswordGetter(IPasswordGetter):
    def get_password(self, account_name: str = None, account_id: str = None):
        if account_name is not None:
            placeholder_value = account_name
        else:
            placeholder_value = account_id
        if placeholder_value is None:
            raise Exception("Please present a context to ask for a password")
        if sys.stdin.isatty():
            password = getpass.getpass(self.placeholder.format(placeholder_value))
        else:
            password = sys.stdin.readline().rstrip()

        return password
