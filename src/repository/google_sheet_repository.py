import os.path
import pickle
from typing import Dict, List
from datetime import datetime

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from src.repository.i_repository import IRepository


# SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
# SAMPLE_SPREADSHEET_ID = '1GkSqLQHR8m88ZktbhJisN2fKg1nqxtt_pcoywnBu2Ow'
# SAMPLE_RANGE_NAME = 'Expenses!C2:F'


class GoogleSheetRepository(IRepository):
    def __init__(
        self,
        scopes,
        spreadsheet_id,
        expenses_sheet_name,
        expenses_start_cell,
        metadata_sheet_name,
        token_path,
        credentials_path,
    ):
        # token_path = 'token.pickle'
        # credentials_path = 'account_transactions_massager/taggers/credentials.json'
        self.spreadsheet_id = spreadsheet_id
        self.expenses_sheet_name = expenses_sheet_name
        self.expenses_start_cell = expenses_start_cell
        self.__start_of_sheet = f"{expenses_sheet_name}!{expenses_start_cell}"
        self.metadata_sheet_name = metadata_sheet_name
        self.scopes = scopes
        self.credentials = self._getOrRefreshCredentials(token_path, credentials_path)
        self.sheet = build("sheets", "v4", credentials=self.credentials).spreadsheets()
        self.last_transaction_date_by_account = None
        self.categories = None

    def _getOrRefreshCredentials(self, token_path, credentials_path) -> Dict:
        creds = None
        # The file token.pickle stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if os.path.exists(token_path):
            with open(token_path, "rb") as token:
                creds = pickle.load(token)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_path, self.scopes
                )
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open(token_path, "wb") as token:
                pickle.dump(creds, token)
        return creds

    def get_transactions(self):
        transactions = self.get_data(f"{self.expenses_sheet_name}")
        # remove header
        transactions.pop(0)
        return transactions

    def get_data(self, data_range, columns_indexes: List[int] = None):
        result = (
            self.sheet.values()
            .get(spreadsheetId=self.spreadsheet_id, range=data_range)
            .execute()
        )
        values = result.get("values", [])
        # validate all entries have 4 cells
        if columns_indexes is None:
            data = values
        else:
            data = []
            for row in values:
                selected_index_fields = list(
                    filter(
                        lambda tuple_index_field: tuple_index_field[0]
                        in columns_indexes,
                        enumerate(row),
                    )
                )
                selected_fields = list(
                    map(
                        lambda tuple_index_field: tuple_index_field[1],
                        selected_index_fields,
                    )
                )
                data.append(selected_fields)

            # data = [map(lambda description_tuple, category_tuple: (description_tuple[1], category_tuple[1]), filter(lambda x: x[0] in columns_indexes, enumerate(row))) for row in values]
        return data

    def batch_insert(self, data: List[List[str]]) -> None:
        self.__append_in_range(
            data, f"{self.expenses_sheet_name}!{self.expenses_start_cell}"
        )

    def sort_transactions(self, column_index_order_by: int):
        data: List[str] = self.get_transactions()
        data.sort(key=lambda key: key[column_index_order_by])

        self.__upsert_range(
            data,
            f"{self.expenses_sheet_name}!"
            f"{self.expenses_start_cell[0]}{int(self.expenses_start_cell[1:]) + 1}",
        )

    def get_last_transaction_date_for_account(self, account_name: str) -> datetime:
        result = (
            self.sheet.values()
            .get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.metadata_sheet_name}!A2:B",
            )
            .execute()
        )
        self.last_transaction_date_by_account = dict(result.get("values", []))
        return self.last_transaction_date_by_account.get(account_name, None)

    def push_categories(self, categories: List[str]) -> None:
        self.__upsert_range(categories, f"{self.metadata_sheet_name}!C2:C")

    def pull_categories(self) -> List[str]:
        result = (
            self.sheet.values()
            .get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.metadata_sheet_name}!C2:C",
            )
            .execute()
        )
        self.categories = result.get("values", [])
        return self.categories

    def add_category(self, category: str):
        if self.categories is None:
            raise Exception("You need to first pull the categories")
        self.categories.append(category)

    def pull_accounts(self):
        result = (
            self.sheet.values()
            .get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.metadata_sheet_name}!A2:A",
            )
            .execute()
        )
        return result.get("values", [])

    def __clear_range(self, sheet_range: str) -> None:
        response = (
            self.sheet.values()
            .clear(spreadsheetId=self.spreadsheet_id, range=sheet_range)
            .execute()
        )
        return response

    def __append_in_range(
        self, values: List[object], sheet_range: str, axis: str = "ROWS"
    ) -> None:
        self.sheet.values().append(
            spreadsheetId=self.spreadsheet_id,
            range=sheet_range,
            insertDataOption="INSERT_ROWS",
            body={"majorDimension": axis, "values": values},
            valueInputOption="USER_ENTERED",
        ).execute()

    def __upsert_range(
        self, values: List[object], update_range: str, axis: str = "ROWS"
    ) -> None:
        self.sheet.values().update(
            spreadsheetId=self.spreadsheet_id,
            range=update_range,
            valueInputOption="USER_ENTERED",
            includeValuesInResponse=True,
            body={"range": update_range, "majorDimension": axis, "values": values},
        ).execute()
