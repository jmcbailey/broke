import logging
import re

from datetime import datetime
from decimal import Decimal
from enum import IntEnum

from .pdf import PDFReader


logger = logging.getLogger(__name__)


class StatementLineType(IntEnum):
    ACCOUNT_NUMBER = 1
    BRANCH_CODE = 2
    BIC_CODE = 3
    TRANSACTION = 4
    BALANCE_FORWARD = 5
    SUBTOTAL = 6


SEP = '\x1f'

TX_DATE_REGEX = (
    '[0123][0-9] (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4}'
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
        r'^(?P<tx_date>%s) BALANCE FORWARD%s%s(?P<balance>%s)$' % (
            TX_DATE_REGEX, SEP, SEP, AMOUNT_REGEX
        )
    ),
    StatementLineType.TRANSACTION: re.compile(
        r'^(?P<tx_date>%s )?(?P<desc>[\d\w*@.&+ ]{1,30})%s(?P<amount1>%s)%s('
        r'?P<amount2>%s)?$' % (
            TX_DATE_REGEX, SEP, AMOUNT_REGEX, SEP, AMOUNT_REGEX
        )
    ),
    StatementLineType.SUBTOTAL: re.compile(
        '^%s%sSUBTOTAL: +(?P<subtotal>%s)$' % (SEP, SEP, AMOUNT_REGEX)
    ),
}


def parse_amount(amount):
    return Decimal(amount.replace(',', ''))


def parse_date(dt):
    return datetime.strptime(dt, '%d %b %Y').date()


class BOIStatementReader(PDFReader):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.read_state = None

    def read_line(self, line):
        values = [cell['text'] for cell in line]
        if not any(values):
            return line
        match = None
        line_type = None
        for line_type, regex in STATEMENT_REGEXES.items():
            match = regex.match(SEP.join(values))
            if match:
                break
        if not match:
            print('unmatched: {}'.format('|'.join(values)))
            return

        if line_type == StatementLineType.BALANCE_FORWARD:
            self.document.new_page()
        elif line_type == StatementLineType.SUBTOTAL:
            self.document.end_page()
        elif line_type == StatementLineType.TRANSACTION:
            if not self.document.current_page:
                logger.warning('Found transaction but no current page')
            else:
                #self.document.current_page
                pass
        elif (
            self.document.current_page
            and line_type != StatementLineType.TRANSACTION
        ):
            logger.warning('Expected transaction, found {}'.format(
                '|'.join(values))
            )

        return line

    def process_line(self, line_type, data):
        print('{}: {}'.format(line_type._name_, data))
        #if
