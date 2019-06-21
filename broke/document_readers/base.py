from abc import ABC, abstractmethod


class BaseDocumentReader(ABC):
    def __init__(self, path, document):
        self.path = path
        self.document = document

    @abstractmethod
    def read(self):
        pass

    @abstractmethod
    def read_line(self, line):
        pass
