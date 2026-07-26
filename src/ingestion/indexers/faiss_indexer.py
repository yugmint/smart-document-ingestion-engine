# src/ingestion/indexers/faiss_indexer.py

from pathlib import Path

from langchain_community.vectorstores import FAISS

from src.ingestion.exceptions import IngestionError
from src.utils.logger import logger


class FAISSIndexer:
    """
    Builds and persists a FAISS index.
    """

    def build(self, chunks, embeddings):

        logger.info("=" * 80)
        logger.info("Building FAISS Index")

        if not chunks:
            raise IngestionError(
                "No chunks were produced -- refusing to build an empty "
                "FAISS index. Check the document actually contains text "
                "and that the chunking strategy isn't filtering everything "
                "out."
            )

        vectorstore = FAISS.from_documents(chunks, embeddings)

        logger.info(f"FAISS index created with {len(chunks)} vectors.")

        return vectorstore

    def save(self, vectorstore, path: str):

        output_dir = Path(path)
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Saving index -> {output_dir}")

        vectorstore.save_local(str(output_dir))

    def exists(self, path: str) -> bool:
        """Whether a previously saved index is present at `path`."""
        return (Path(path) / "index.faiss").exists()

    def load(self, path: str, embeddings):
        """
        Load a previously saved index, e.g. to add new documents to
        an existing index (incremental ingestion) instead of always
        rebuilding from scratch.
        """

        output_dir = Path(path)

        if not output_dir.exists():
            raise IngestionError(f"No index found at '{output_dir}'.")

        logger.info(f"Loading index <- {output_dir}")

        # `allow_dangerous_deserialization` is required by recent
        # langchain versions for FAISS pickle loading. Only load
        # indexes you created yourself / trust the source of.
        return FAISS.load_local(
            str(output_dir),
            embeddings,
            allow_dangerous_deserialization=True,
        )

    def add(self, vectorstore, chunks):
        """
        Add chunks to an already-built/loaded vectorstore in place,
        for incremental ingestion without a full rebuild.
        """

        if not chunks:
            logger.warning("add() called with no chunks; nothing to do.")
            return vectorstore

        vectorstore.add_documents(chunks)

        logger.info(f"Added {len(chunks)} vectors to existing index.")

        return vectorstore
