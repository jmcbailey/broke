import re

from datetime import datetime
from decimal import Decimal


def parse_amount(value):
    if value is None:
        return value
    return Decimal(value.replace(',', ''))


class DateParser:
    def __init__(self, fmt):
        self.fmt = fmt

    def __call__(self, value):
        if not value:
            return value
        return datetime.strptime(value.strip(), self.fmt).date()


class Pattern:
    def __init__(self, regex, processors=None):
        self.regex = re.compile(regex)
        self.processors = processors or {}

    def match(self, value, *args, **kwargs):
        match = self.regex.match(value, *args, **kwargs)
        if not match:
            return None
        match_dict = match.groupdict()
        for key, processor in self.processors.items():
            if key not in match_dict:
                continue
            match_dict[key] = processor(match_dict[key])
        return match_dict


# Common patterns

TX_DATE_REGEX_1 = (
    '[0123][0-9] (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4}'
)

TX_DATE_REGEX_2 = (
    '[0123][0-9](?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)'
)

TX_DATE_REGEX_3 = (
    '[0123][0-9][01][0-9]'
)

AMOUNT_REGEX = '[0-9]{1,3}(,[0-9]{3})*\.[0-9]{2}'
