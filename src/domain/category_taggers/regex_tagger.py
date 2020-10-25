import re

from typing import List, Tuple
from src.domain.category_taggers.i_tagger import ITagger


class RegexTagger(ITagger):
    def __init__(self, category_regex_tuple_list: List[Tuple[str, re.Pattern]]) -> None:
        self.category_regex_tuple_list = category_regex_tuple_list

    def get_category(self, expense_description: str) -> str:
        res = ""
        for category, regex in self.category_regex_tuple_list:
            pattern_matched = regex.search(expense_description)
            if pattern_matched is not None:
                res = category
                break

        return res


class RegexTaggerBuilder:
    def __init__(self):
        self.category_regex_tuple_list: List[Tuple[str, re.Pattern]] = []

    def add_category_regex(self, category: str, regex_pattern_string: str):
        self.category_regex_tuple_list.append(
            (category, re.compile(regex_pattern_string))
        )

    def build(self):
        return RegexTagger(self.category_regex_tuple_list)
