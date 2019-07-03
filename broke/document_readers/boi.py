import logging

from enum import IntEnum

from broke.models import Transaction, TransactionType, TransactionSubtype
from broke.utils import (
    DateParser, Pattern, parse_amount, TX_DATE_REGEX_1, TX_DATE_REGEX_2,
    TX_DATE_REGEX_3, AMOUNT_REGEX
)
from .pdf import PDFReader


logger = logging.getLogger(__name__)


'''
TODO:
- Save custom tag rules as JSON and apply (?)
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


class BOIStatementReader(PDFReader):
    statement_patterns = {
        StatementLineType.ACCOUNT_NUMBER: Pattern(
            '^%s%sBranch code +(?P<sort_code>\d{2}-\d{2}-\d{2})$' % (SEP, SEP)
        ),
        StatementLineType.BIC_CODE: Pattern(
            r'^%s%sBank Identifier Code (?P<bic_code>[0-9A-Z]{8})$' % (
                SEP, SEP
            )
        ),
        StatementLineType.BALANCE_FORWARD: Pattern(
            r'^(?P<tx_date>%s) BALANCE FORWARD%s%s(?P<balance>%s(?: OD)?)$' % (
                TX_DATE_REGEX_1, SEP, SEP, AMOUNT_REGEX
            ),
            processors={
                'tx_date': DateParser('%d %b %Y'),
                'balance': parse_amount
            }
        ),
        StatementLineType.TRANSACTION: Pattern(
            r'^(?P<tx_date>%s )?(?P<desc>[\d\w*@.&/\-\'+ ]{1,30})%s'
            r'(?P<amount>%s)%s(?P<balance>%s(?: OD)?)?$' % (
                TX_DATE_REGEX_1, SEP, AMOUNT_REGEX, SEP, AMOUNT_REGEX
            ),
            processors={
                'tx_date': DateParser('%d %b %Y'),
                'amount': parse_amount,
                'balance': parse_amount
            }
        ),
        StatementLineType.SUBTOTAL: Pattern(
            '^%s%sSUBTOTAL: +(?P<subtotal>%s)$' % (SEP, SEP, AMOUNT_REGEX),
            processors={'subtotal': parse_amount}
        ),
        StatementLineType.END_STATEMENT: Pattern(
            '^This is an eligible deposit under the Deposit Guarantee.*$'
        ),
    }

    transaction_patterns = {
        TransactionSubtype.PURCHASE: Pattern(
            r'^POSC?(?P<tx_date>%s) (?P<merchant>[\d\w*@.&/\-\'+ ]{2,12})$' %
            TX_DATE_REGEX_2,
            processors={'tx_date': DateParser('%d%b')}
        ),
        TransactionSubtype.ATM_WITHDRAWAL: Pattern(
            r'^ATMD? ?(?P<tx_date>%s) (?P<desc>[\d\w*@.&/\-\'+ ]{2,12})$' %
            TX_DATE_REGEX_2,
            processors={'tx_date': DateParser('%d%b')}
        ),
        TransactionSubtype.DIRECT_DEBIT: Pattern(
            r'^(?P<dest>[\d\w*@.&/\-\'+ ]{2,13}) ?SEPA DD$'
        ),
        TransactionSubtype.STANDING_ORDER: Pattern(
            r'^TO A/C (?P<dest>\d{8})SO$'
        ),
        TransactionSubtype.BANK_TRANSFER: Pattern(
            r'^365 Online ?(?P<dest>[\d\w*@.&/\-\'+ ]{2,10})$'
        ),
        TransactionSubtype.FOREIGN_EXCHANGE: Pattern(
            r'^[CAP](?P<tx_date>%s)[A-Z]{2} {0,2}(?:%s)@[0-9.]{7}$' % (
                TX_DATE_REGEX_3, AMOUNT_REGEX
            ),
            processors={'tx_date': DateParser('%d%m')}
        ),
        TransactionSubtype.FEES: Pattern(r'^NOTIFIED FEES$'),
        TransactionSubtype.INTEREST: Pattern(r'^INTEREST$'),
        TransactionSubtype.OTHER: Pattern(r'.*'),  # catch-all
    }

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
        match = match_dict = None
        line_type = None

        for line_type, regex in self.statement_patterns.items():
            match = regex.match(SEP.join(values))
            if match:
                match_dict = match.match_dict
                break
        if not match:
            line_type = None

        active_page = self.document.active_page
        if line_type == StatementLineType.BALANCE_FORWARD:
            self.document.start_page(match_dict.get('balance'))
        elif line_type == StatementLineType.SUBTOTAL:
            self.document.finish_page(match_dict.get('subtotal'))
        elif line_type == StatementLineType.END_STATEMENT:
            self.document.finish_page()
        elif line_type == StatementLineType.TRANSACTION:
            if not active_page:
                logger.warning('Found unexpected transaction: %s', match)
            self.process_transaction(match_dict, line)
        elif active_page and line_type != StatementLineType.TRANSACTION:
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
        transaction = Transaction(
            self.active_date, tx_type, tx_dict['amount'], tx_dict['desc']
        )
        transaction.tags.append(transaction.tx_type._value_)
        for tx_subtype, pattern in self.transaction_patterns.items():
            match = pattern.match(transaction.description)
            if not match:
                continue
            match_dict = match.match_dict
            tx_date = match_dict.pop('tx_date', None)
            if tx_date:
                # Use the date in the transaction description as it's
                # likely to be the actual transaction date
                transaction.tx_date = self.resolve_date(tx_date)
            transaction.tags.append(tx_subtype._value_)
            transaction.details = match_dict
            break
        logger.info('TX: %s', transaction)
        self.document.add_transaction(transaction, tx_dict.get('balance'))

    def resolve_date(self, dt):
        assert self.active_date
        try:
            new_dt = self.active_date.replace(month=dt.month, day=dt.day)
            if new_dt > self.active_date:
                new_dt = new_dt.replace(year=new_dt.year - 1)
        except ValueError:
            new_dt = self.active_date
        return new_dt
