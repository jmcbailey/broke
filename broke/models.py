from enum import Enum


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
    FEES ='fees'
    INTEREST = 'interest'



class Transaction:
    def __init__(self, tx_date, tx_type, amount, description, tags=None):
        self.tx_date = tx_date
        self.tx_type = tx_type
        self.amount = amount
        self.description = description
        self.tags = tags or []
