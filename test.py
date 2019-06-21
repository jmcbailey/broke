import logging
import os
import sys

from broke.document_readers.boi import BOIStatementReader
from broke.models import BankStatement


logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'DEBUG'),
    stream=sys.stdout
)


def main():
    pdf_path = 'statement.pdf'
    doc = BankStatement()
    reader = BOIStatementReader(pdf_path, doc)
    reader.read()

if __name__ == '__main__':
    main()
