import logging
import re

from datetime import datetime
from decimal import Decimal
from enum import IntEnum

from ..models import Transaction, TransactionType, TransactionSubtype
from .pdf import PDFReader


logger = logging.getLogger(__name__)


'''
TODO:
- check balance as each tx processed
- Update date from matched tx
- Save custom tag rules as JSON and apply
'''


class StatementLineType(IntEnum):
    ACCOUNT_NUMBER = 1
    BRANCH_CODE = 2
    BIC_CODE = 3
    TRANSACTION = 4
    BALANCE_FORWARD = 5
    SUBTOTAL = 6
    END_STATEMENT = 7


SEP = '\x1f'

TX_DATE_REGEX = (
    '[0123][0-9] (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4}'
)

TX_DATE_REGEX_2 = (
    '[0123][0-9](?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)'
)

TX_DATE_REGEX_3 = (
    '[0123][0-9][0123][0-9]'
)

AMOUNT_REGEX = '[0-9]{1,3}(,[0-9]{3})*\.[0-9]{2}'

STATEMENT_REGEXES = {
    StatementLineType.ACCOUNT_NUMBER: re.compile(
        '^%s%sBranch code +(?P<sort_code>\d{2}-\d{2}-\d{2})$' % (SEP, SEP)
    ),
    StatementLineType.BIC_CODE: re.compile(
        r'^%s%sBank Identifier Code (?P<bic_code>[0-9A-Z]{8})$' % (SEP, SEP)
    ),
    StatementLineType.BALANCE_FORWARD: re.compile(
        r'^(?P<tx_date>%s) BALANCE FORWARD%s%s(?P<balance>%s)(?P<od> OD)?$' % (
            TX_DATE_REGEX, SEP, SEP, AMOUNT_REGEX
        )
    ),
    StatementLineType.TRANSACTION: re.compile(
        r'^(?P<tx_date>%s )?(?P<desc>[\d\w*@.&/\-\'+ ]{1,30})%s'
        r'(?P<amount>%s)%s(?P<balance>%s)?(?P<od> OD)?$' % (
            TX_DATE_REGEX, SEP, AMOUNT_REGEX, SEP, AMOUNT_REGEX
        )
    ),
    StatementLineType.SUBTOTAL: re.compile(
        '^%s%sSUBTOTAL: +(?P<subtotal>%s)$' % (SEP, SEP, AMOUNT_REGEX)
    ),
    StatementLineType.END_STATEMENT: re.compile(
        '^This is an eligible deposit under the Deposit Guarantee Scheme..*$'
    ),
}

TRANSACTION_REGEXES = {
    TransactionSubtype.PURCHASE: re.compile(
        r'^POSC?(?P<tx_date>%s) (?P<desc>[\d\w*@.&/\-\'+ ]{2,12})$' %
        TX_DATE_REGEX_2
    ),
    TransactionSubtype.ATM_WITHDRAWAL: re.compile(
        r'^ATMD? ?(?P<tx_date>%s) (?P<desc>[\d\w*@.&/\-\'+ ]{2,12})$' %
        TX_DATE_REGEX_2
    ),
    TransactionSubtype.DIRECT_DEBIT: re.compile(
        r'^(?P<desc>[\d\w*@.&/\-\'+ ]{2,13}) ?SEPA DD$'
    ),
    TransactionSubtype.STANDING_ORDER: re.compile(
        r'^TO A/C (?P<dest>\d{8})SO$'
    ),
    TransactionSubtype.BANK_TRANSFER: re.compile(
        r'^365 Online ?(?P<desc>[\d\w*@.&/\-\'+ ]{2,10})$'
    ),
    TransactionSubtype.FOREIGN_EXCHANGE: re.compile(
        r'^[CAP](?P<tx_date>%s)[A-Z]{2} {0,2}(?:%s)@[0-9.]{7}$' % (
            TX_DATE_REGEX_3, AMOUNT_REGEX
        )
    ),
    TransactionSubtype.FEES: re.compile(r'^NOTIFIED FEES$'),
    TransactionSubtype.INTEREST: re.compile(r'^INTEREST$'),
}


class BOIStatementReader(PDFReader):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.unmatched_transactions = []
        self.active_date = None

    def read(self):
        super().read()
        if self.unmatched_transactions:
            logger.warning(
                'Found %s unmatched transactions: %s',
                len(self.unmatched_transactions),
                self.unmatched_transactions
            )
        else:
            logger.info('Statement read success.')

    def read_line(self, line):
        values = [cell['text'] for cell in line]
        if not any(values):
            return
        match = None
        line_type = None

        for line_type, regex in STATEMENT_REGEXES.items():
            match = regex.match(SEP.join(values))
            if match:
                logger.debug(
                    'MATCHED: %s: %s', line_type._name_, match.groupdict()
                )
                break
        if not match:
            logger.debug('UNMATCHED: %s', '|'.join(values))
            line_type = None

        current_page = self.document.current_page
        if line_type == StatementLineType.BALANCE_FORWARD:
            logger.debug('START PAGE')
            self.document.start_page()
        elif line_type == StatementLineType.SUBTOTAL:
            logger.debug('FINISH PAGE')
            self.document.finish_page()
        elif line_type == StatementLineType.END_STATEMENT:
            logger.debug('END STATEMENT')
            self.document.finish_page()
        elif line_type == StatementLineType.TRANSACTION:
            if not current_page:
                logger.warning(
                    'Found unexpected transaction: %s', match.groupdict()
                )
            self.process_transaction(match.groupdict(), line)
        elif current_page and line_type != StatementLineType.TRANSACTION:
            self.unmatched_transactions.append('|'.join(values))

    def process_transaction(self, tx_dict, raw_line):
        tx_date = tx_dict['tx_date']
        if tx_date:
            self.active_date = self.parse_date(tx_date)
        column_separator_position = 420
        transaction_cell = raw_line[1]
        position = transaction_cell['left'] + transaction_cell['width']
        tx_type = (
            TransactionType.DEBIT
            if position < column_separator_position
            else TransactionType.CREDIT
        )
        amount = self.parse_amount(tx_dict['amount'])
        transaction = Transaction(
            self.active_date, tx_type, amount, tx_dict['desc']
        )
        self.auto_tag(transaction)
        logger.info('TX: %s', transaction.__dict__.values())
        self.document.current_page.transactions.append(transaction)

    def auto_tag(self, transaction):
        match = None
        transaction.tags.append(transaction.tx_type._value_)
        for tx_subtype, regex in TRANSACTION_REGEXES.items():
            match = regex.match(transaction.description)
            if match:
                logger.debug(
                    'TX MATCH: %s: %s', tx_subtype._name_, match.groupdict()
                )
                transaction.tags.append(tx_subtype._value_)
                break
        if not match:
            logger.debug('UNMATCHED TX: %s', transaction.__dict__)

    def parse_amount(self, amount):
        return Decimal(amount.replace(',', ''))

    def parse_date(self, dt):
        return datetime.strptime(dt.strip(), '%d %b %Y').date()
