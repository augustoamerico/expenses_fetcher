class HistoricTagger:
    SAMPLE_RANGE_NAME = "Expenses!C2:F"

    def __init__(self, repository):
        self.repository = repository
        self.historicExpensesDescriptionCategories = dict(self._get_historical_data())

    def get_category(self, expense_description):
        if len(self.historicExpensesDescriptionCategories) == 0:
            self.historicExpensesDescriptionCategories = self._get_historical_data()

        if expense_description in self.historicExpensesDescriptionCategories:
            return self.historicExpensesDescriptionCategories[expense_description]
        return ""

    def _get_historical_data(self):
        pair_description_category = dict(
            self.repository.get_data(
                data_range=self.SAMPLE_RANGE_NAME, columns_indexes=[0, 3]
            )
        )
        return pair_description_category
