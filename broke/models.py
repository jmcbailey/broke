from datetime import date
from enum import Enum
from itertools import chain


class BankStatement:
    def __init__(self):
        self.pages = []
        self.current_page = None

    def start_page(self):
        if self.current_page:
            self.pages.append(self.current_page)
        self.current_page = Page()

    def finish_page(self):
        if self.current_page:
            self.pages.append(self.current_page)
        self.current_page = None

    def add_transaction(self, transaction):
        pass

    @property
    def transactions(self):
        return list(chain.from_iterable([
            page.transactions for page in self.pages
        ]))

    def _filter_transactions(self, fn):
        return list(filter(fn, self.transactions))

    @property
    def credits(self):
        return self._filter_transactions(
            lambda tx: tx.tx_type == TransactionType.CREDIT
        )

    @property
    def debits(self):
        return self._filter_transactions(
            lambda tx: tx.tx_type == TransactionType.DEBIT
        )




class Page:
    def __init__(self):
        self.transactions = []


class TransactionType(Enum):
    CREDIT = 'credit'
    DEBIT = 'debit'


class TransactionSubtype(Enum):
    PURCHASE = 'purchase'
    ATM_WITHDRAWAL = 'atm_withdrawal'
    DIRECT_DEBIT = 'direct_debit'
    STANDING_ORDER = 'standing_order'
    BANK_TRANSFER = 'bank_transfer'
    FOREIGN_EXCHANGE = 'foreign_exchange'
    FEES = 'fees'
    INTEREST = 'interest'


class Transaction:
    def __init__(self, tx_date, tx_type, amount, description, tags=None):
        self.tx_date = tx_date
        self.tx_type = tx_type
        self.amount = amount
        self.description = description
        self.tags = tags or []

    def _repr(self, fields=None):
        dic = {}
        for field in fields:
            field_names = field.split('.')
            item = getattr(self, field_names[0])
            if isinstance(item, date):
                item = item.strftime('%Y-%m-%d')
            elif isinstance(item, list) and len(field_names) > 1:
                item = getattr(item[0], field_names[1])
            elif isinstance(item, list) and item:
                item = item[0]
            elif isinstance(item, dict) and 'en' in item:
                item = item['en']

            dic[field] = item

        return '<{}: {}>'.format(self.__class__.__name__, str(dic))

    def __repr__(self):
        return self._repr(['tx_date', 'tx_type', 'amount', 'description'])
