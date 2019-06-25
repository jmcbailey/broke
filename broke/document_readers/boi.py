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
- Save custom tag rules as JSON and apply
- Reuse description pattern
- Count grouped transaction counts and amounts as each tx is read
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

# TODO: move these into utils module

class parse_date:
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

STATEMENT_PATTERNS = {
    StatementLineType.ACCOUNT_NUMBER: Pattern(
        '^%s%sBranch code +(?P<sort_code>\d{2}-\d{2}-\d{2})$' % (SEP, SEP)
    ),
    StatementLineType.BIC_CODE: Pattern(
        r'^%s%sBank Identifier Code (?P<bic_code>[0-9A-Z]{8})$' % (SEP, SEP)
    ),
    StatementLineType.BALANCE_FORWARD: Pattern(
        r'^(?P<tx_date>%s) BALANCE FORWARD%s%s(?P<balance>%s)(?P<od> OD)?$' % (
            TX_DATE_REGEX_1, SEP, SEP, AMOUNT_REGEX
        ),
        processors={'tx_date': parse_date('%d %b %Y')}
    ),
    StatementLineType.TRANSACTION: Pattern(
        r'^(?P<tx_date>%s )?(?P<desc>[\d\w*@.&/\-\'+ ]{1,30})%s'
        r'(?P<amount>%s)%s(?P<balance>%s)?(?P<od> OD)?$' % (
            TX_DATE_REGEX_1, SEP, AMOUNT_REGEX, SEP, AMOUNT_REGEX
        ),
        processors={'tx_date': parse_date('%d %b %Y')}
    ),
    StatementLineType.SUBTOTAL: Pattern(
        '^%s%sSUBTOTAL: +(?P<subtotal>%s)$' % (SEP, SEP, AMOUNT_REGEX)
    ),
    StatementLineType.END_STATEMENT: Pattern(
        '^This is an eligible deposit under the Deposit Guarantee Scheme..*$'
    ),
}

TRANSACTION_PATTERNS = {
    TransactionSubtype.PURCHASE: Pattern(
        r'^POSC?(?P<tx_date>%s) (?P<desc>[\d\w*@.&/\-\'+ ]{2,12})$' %
        TX_DATE_REGEX_2,
        processors={'tx_date': parse_date('%d%b')}
    ),
    TransactionSubtype.ATM_WITHDRAWAL: Pattern(
        r'^ATMD? ?(?P<tx_date>%s) (?P<desc>[\d\w*@.&/\-\'+ ]{2,12})$' %
        TX_DATE_REGEX_2,
        processors={'tx_date': parse_date('%d%b')}
    ),
    TransactionSubtype.DIRECT_DEBIT: Pattern(
        r'^(?P<desc>[\d\w*@.&/\-\'+ ]{2,13}) ?SEPA DD$'
    ),
    TransactionSubtype.STANDING_ORDER: Pattern(
        r'^TO A/C (?P<dest>\d{8})SO$'
    ),
    TransactionSubtype.BANK_TRANSFER: Pattern(
        r'^365 Online ?(?P<desc>[\d\w*@.&/\-\'+ ]{2,10})$'
    ),
    TransactionSubtype.FOREIGN_EXCHANGE: Pattern(
        r'^[CAP](?P<tx_date>%s)[A-Z]{2} {0,2}(?:%s)@[0-9.]{7}$' % (
            TX_DATE_REGEX_3, AMOUNT_REGEX
        ),
        processors={'tx_date': parse_date('%d%m')}
    ),
    TransactionSubtype.FEES: Pattern(r'^NOTIFIED FEES$'),
    TransactionSubtype.INTEREST: Pattern(r'^INTEREST$'),
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
                'Found %s unmatched transactions:\n\t%s',
                len(self.unmatched_transactions),
                '\n\t'.join([repr(t) for t in self.unmatched_transactions])
            )
        else:
            logger.info('Statement read success.')

    def read_line(self, line):
        values = [cell['text'] for cell in line]
        if not any(values):
            return
        match = None
        line_type = None

        for line_type, regex in STATEMENT_PATTERNS.items():
            match = regex.match(SEP.join(values))
            if match:
                logger.debug('MATCHED: %s: %s', line_type._name_, match)
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
                logger.warning('Found unexpected transaction: %s', match)
            self.process_transaction(match, line)
        elif current_page and line_type != StatementLineType.TRANSACTION:
            self.unmatched_transactions.append('|'.join(values))

    def process_transaction(self, tx_dict, raw_line):
        tx_date = tx_dict['tx_date']
        if tx_date:
            self.active_date = tx_date
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
        for tx_subtype, pattern in TRANSACTION_PATTERNS.items():
            match = pattern.match(transaction.description)
            if match:
                logger.debug('TX MATCH: %s: %s', tx_subtype._name_, match)
                transaction.tags.append(tx_subtype._value_)
                if match.get('tx_date'):
                    # Use the date in the transaction description as it's
                    # likely to be the actual transaction date
                    transaction.tx_date = self.resolve_date(match['tx_date'])
                break
        if not match:
            logger.info('UNMATCHED TX: %s', transaction)
            self.unmatched_transactions.append(transaction)

    def parse_amount(self, amount):
        return Decimal(amount.replace(',', ''))

    def resolve_date(self, dt):
        assert self.active_date
        try:
            new_dt = self.active_date.replace(month=dt.month, day=dt.day)
            if new_dt > self.active_date:
                new_dt = new_dt.replace(year=new_dt.year - 1)
        except ValueError:
            new_dt = self.active_date
        return new_dt
