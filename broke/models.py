from collections import namedtuple
from enum import Enum


class BaseDocument:
    def __init__(self):
        self.elements = []
        self.current_page = None

    def add(self, element):
        self.elements.append(element)

    def new_page(self):
        if self.current_page:
            self.elements.append(self.current_page)
        self.current_page = Page()

    def end_page(self):
        if self.current_page:
            self.pages.append(self.current_page)
        self.current_page = None


class BankStatement(BaseDocument):
    def __pinit__(self):
        self.account_info = {}

    @property
    def transactions(self):
        return


class TransactionDirection(Enum):
    IN = 1
    OUT = 2


Page = namedtuple('Page', ['transactions'], defaults=([]))


Transaction = namedtuple(
    'Transaction',
    ['direction', 'amount', 'description', 'tags']
)
