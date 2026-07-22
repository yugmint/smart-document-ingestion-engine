# src/ingestion/cleaners/factory.py

from src.ingestion.cleaners.text_cleaner import TextCleaner


class CleanerFactory:
    """
    Factory for document cleaners.
    """

    @staticmethod
    def build():
        return TextCleaner()
