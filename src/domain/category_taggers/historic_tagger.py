from collections import defaultdict
import heapq
from src.domain.category_taggers.i_tagger import ITagger
from functools import partial

class HistoricTagger(ITagger):
    SAMPLE_RANGE_NAME = "Expenses!C2:F"

    def __init__(self, repository):
        self.repository = repository
        self._get_historical_data__init__()

    def get_category(self, trx_description):
        return self._get_metadata(trx_description, 1)

    def get_type(self, trx_description):
        return self._get_metadata(trx_description, 0)
    
    def _get_metadata(self, trx_description, metadata_idx):
        res = ""
        entry = self.historic_trx_description_metadata.get(trx_description, "")
        if entry:
            res = entry[-1][0][metadata_idx] #Tuple((type, category), frequency)
        return res

    #def _get_historical_data(self):
    #    pair_description_category = dict(
    #        self.repository.get_data(
    #            data_range=self.SAMPLE_RANGE_NAME, columns_indexes=[0, 3]
    #        )
    #    )
    #    return pair_description_category

    def _get_historical_data__init__(self):
        trx_descp_trx_to_type_category_count = defaultdict(partial(defaultdict, int))
        tmp_data = self.repository.get_data(
            data_range=self.SAMPLE_RANGE_NAME, columns_indexes=[0, 2, 3]
        )
        for el in tmp_data:
            trx_description = el[0]
            trx_type = el[1]
            trx_category = el[2]

            dict_key = (trx_type, trx_category)

            trx_descp_trx_to_type_category_count[trx_description][dict_key] += 1

        self.historic_trx_description_metadata = {}

        for key, value in trx_descp_trx_to_type_category_count.items():
            self.historic_trx_description_metadata[key] = list(value.items())
            heapq.heapify(
                self.historic_trx_description_metadata[key]
            )
