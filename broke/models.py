import logging

from datetime import date
from decimal import Decimal
from enum import Enum

logger = logging.getLogger(__name__)


class BankStatement:
    def __init__(self):
        self.active_page = False
        self.page_count = 0
        self.total_balance = Decimal('0')
        self.transactions = []

    def start_page(self, balance):
        if not self.page_count:
            self.total_balance = balance  # Starting balance
        self.check_balance(balance)
        self.page_count += 1
        self.active_page = True

    def finish_page(self, balance=None):
        self.check_balance(balance)
        self.active_page = False

    def add_transaction(self, transaction, balance=None):
        self.transactions.append(transaction)
        amount = transaction.amount
        if transaction.tx_type == TransactionType.DEBIT:
            amount *= -1
        self.adjust_balance(amount)
        self.check_balance(balance)

    def adjust_balance(self, amount):
        self.total_balance += amount

    def check_balance(self, balance):
        # Check that the total balance we've computed matches what's in the
        # statement.
        if balance is not None and balance != self.total_balance:
            logger.warning(
                'Balance mismatch: %s != %s', balance, self.total_balance
            )


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

    OTHER = 'other'


class Transaction:
    def __init__(self, tx_date, tx_type, amount, description, tags=None):
        self.tx_date = tx_date
        self.tx_type = tx_type
        self.amount = amount
        self.description = description
        self.tags = tags or []
        self.details = {}

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
                # item = item[0]
                pass
            elif isinstance(item, dict) and 'en' in item:
                item = item['en']

            dic[field] = item

        return '<{}: {}>'.format(self.__class__.__name__, list(dic.values()))

    def __repr__(self):
        return self._repr([
            'tx_date', 'tx_type', 'amount', 'description', 'tags', 'details'
        ])
