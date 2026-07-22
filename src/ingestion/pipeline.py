# src/ingestion/pipeline.py

from dataclasses import asdict
from pathlib import Path
from time import perf_counter

from langchain_core.documents import Document

from src.ingestion.analysers.models import DocumentAnalysis
from src.ingestion.config import IngestionConfig
from src.ingestion.exceptions import (
    DocumentTooLargeError,
    IngestionError,
    UnsupportedDocumentError,
)
from src.ingestion.models import IngestionReport

from src.ingestion.loaders.factory import LoaderFactory
from src.ingestion.cleaners.factory import CleanerFactory
from src.ingestion.analysers.factory import AnalyzerFactory
from src.ingestion.chunkers.hybrid_chunker import HybridChunker
from src.ingestion.metadata.generator import MetadataGenerator
from src.ingestion.embedders.embedder import Embedder
from src.ingestion.indexers.faiss_indexer import FAISSIndexer

from src.utils.logger import logger


class IngestionPipeline:
    """
    End-to-end document ingestion pipeline.
    """

    def __init__(self):

        # Shared Components
        self.config = IngestionConfig()

        self.cleaner = CleanerFactory.build()

        self.chunker = HybridChunker(self.config)

        self.metadata = MetadataGenerator()

        self.embeddings = Embedder.get(self.config)

        self.indexer = FAISSIndexer()

    def ingest(
        self,
        file_path: str,
        save_index: bool = True,
    ) -> tuple[list[Document], DocumentAnalysis]:

        start = perf_counter()

        logger.info("=" * 80)
        logger.info(f"Ingesting : {file_path}")

        try:
            self._validate_file(file_path)

            # --------------------------------------------------
            # Load Document
            # --------------------------------------------------

            loader = LoaderFactory.build(file_path)
            documents = loader.load(file_path)

            # --------------------------------------------------
            # Clean Document
            # --------------------------------------------------

            documents = self.cleaner.clean(documents)

            # --------------------------------------------------
            # Analyze Document
            # --------------------------------------------------

            analyzer = AnalyzerFactory.build(file_path)
            analysis = analyzer.analyze(documents, file_path)

            logger.info(f"Document Type   : {analysis.document_type}")
            logger.info(f"Confidence      : {analysis.confidence:.2f}")
            logger.info(f"Chunk Strategy  : {analysis.recommendation.strategy}")
            logger.info(f"Chunk Size      : {analysis.recommendation.chunk_size}")

            # --------------------------------------------------
            # Chunk Document
            # --------------------------------------------------

            chunks = self.chunker.chunk(documents, analysis)

            # --------------------------------------------------
            # Metadata Generation
            # --------------------------------------------------

            chunks = self.metadata.generate(chunks, file_path, analysis)

            # --------------------------------------------------
            # Vector Index
            # --------------------------------------------------

            vectorstore = self.indexer.build(chunks, self.embeddings)

            if save_index:
                self.indexer.save(vectorstore, self.config.index_path)

            elapsed = perf_counter() - start

            report = IngestionReport(
                source=Path(file_path).name,
                total_pages=analysis.statistics.page_count,
                total_chunks=len(chunks),
                average_chunk_size=(
                    sum(len(c.page_content) for c in chunks) / max(len(chunks), 1)
                ),
                embedding_model=self.config.embedding_model,
                vector_store=self.config.vector_store,
                processing_time=elapsed,
                document_type=analysis.document_type,
                chunking_strategy=analysis.recommendation.strategy,
                confidence=analysis.confidence,
            )

            analysis.metadata["ingestion_report"] = asdict(report)

            logger.info("=" * 80)
            logger.info(f"Ingestion completed in {elapsed:.2f}s")
            logger.info(
                f"Pages: {report.total_pages} | Chunks: {report.total_chunks} | "
                f"Avg chunk size: {report.average_chunk_size:.0f} chars"
            )

            return chunks, analysis

        except IngestionError:
            # Already a typed, actionable error -- let it propagate as-is.
            raise

        except Exception as exc:
            logger.error(f"Ingestion failed for '{file_path}': {exc}")
            raise IngestionError(
                f"Ingestion failed for '{file_path}': {exc}"
            ) from exc

    # --------------------------------------------------
    # Validation
    # --------------------------------------------------

    def _validate_file(self, file_path: str) -> None:

        path = Path(file_path)

        if not path.exists():
            raise IngestionError(f"File not found: {file_path}")

        extension = path.suffix.lower()

        if extension not in self.config.supported_extensions:
            raise UnsupportedDocumentError(
                f"Unsupported file type '{extension}'. Supported: "
                f"{', '.join(self.config.supported_extensions)}"
            )

        size_mb = path.stat().st_size / (1024 * 1024)

        if size_mb > self.config.max_document_size_mb:
            raise DocumentTooLargeError(
                f"'{path.name}' is {size_mb:.1f}MB, which exceeds the "
                f"{self.config.max_document_size_mb}MB limit."
            )


def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run the ingestion pipeline.")
    parser.add_argument("file_path", help="Path to the document to ingest.")
    parser.add_argument(
        "--no-save-index",
        action="store_true",
        help="Build the index in memory without persisting it to disk.",
    )
    args = parser.parse_args()

    pipeline = IngestionPipeline()
    pipeline.ingest(args.file_path, save_index=not args.no_save_index)


if __name__ == "__main__":
    _main()

