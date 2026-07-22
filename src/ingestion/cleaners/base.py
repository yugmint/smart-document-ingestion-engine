from abc import ABC, abstractmethod

from langchain_core.documents import Document


class BaseCleaner(ABC):
    """
    Base interface for document cleaners.

    A cleaner receives LangChain Documents and returns
    cleaned LangChain Documents.
    """

    @abstractmethod
    def clean(
        self,
        documents: list[Document],
    ) -> list[Document]:
        """
        Clean documents before chunking.
        """

        raise NotImplementedError
