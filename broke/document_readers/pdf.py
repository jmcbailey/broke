import tabula

from .base import BaseDocumentReader


class PDFReader(BaseDocumentReader):
    def pdf_to_json(self):
        kwargs = {
            'pages': 'all',
            'stream': True,
            'guess': False
        }

        return tabula.read_pdf(self.path, output_format='json', **kwargs)

    def read(self):
        json_data = self.pdf_to_json()
        for table in json_data:
            for line in table['data']:
                yield self.read_line(line)

    def read_line(self, line):
        return [cell['text'] for cell in line]
