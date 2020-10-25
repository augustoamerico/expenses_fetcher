from abc import ABC, abstractmethod


class IPasswordGetter(ABC):
    def __init__(self, placeholder_message: str):
        """
        A placeholder string is something like this: 'Password for account {}'.
        Latter on, the string is formatted with an input.
        """
        self.placeholder = placeholder_message

    @abstractmethod
    def get_password(self, account_name: str = None, account_id: str = None):
        pass
