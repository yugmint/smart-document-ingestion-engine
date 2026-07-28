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
from src.ingestion.cleaners.text_cleaner import noise_page_percentage
from src.ingestion.analysers.factory import AnalyzerFactory
from src.ingestion.chunkers.hybrid_chunker import HybridChunker
from src.ingestion.metadata.generator import MetadataGenerator
from src.ingestion.embedders.embedder import Embedder
from src.ingestion.indexers.faiss_indexer import FAISSIndexer

from src.utils.logger import logger
from src.utils.metrics import (
    AVERAGE_CHUNK_SIZE_CHARS,
    CHUNK_COUNT,
    DUPLICATE_CHUNKS,
    INGESTIONS_TOTAL,
    NOISE_PERCENTAGE,
    STAGE_DURATION_SECONDS,
)


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
        replace: bool = False,
    ) -> tuple[list[Document], DocumentAnalysis]:

        start = perf_counter()

        logger.info("=" * 80)
        logger.info(f"Ingesting : {file_path}")

        try:
            self._validate_file(file_path)

            # --------------------------------------------------
            # Load Document
            # --------------------------------------------------

            stage_start = perf_counter()
            loader = LoaderFactory.build(file_path)
            documents = loader.load(file_path)
            STAGE_DURATION_SECONDS.labels(stage="load").observe(perf_counter() - stage_start)

            # --------------------------------------------------
            # Clean Document
            # --------------------------------------------------

            # Measured on the pre-clean documents -- clean() is about to
            # strip exactly this noise, so measuring after would always
            # read 0%.
            noise_pct = noise_page_percentage(documents)
            NOISE_PERCENTAGE.observe(noise_pct)

            stage_start = perf_counter()
            documents = self.cleaner.clean(documents)
            STAGE_DURATION_SECONDS.labels(stage="clean").observe(perf_counter() - stage_start)

            # --------------------------------------------------
            # Analyze Document
            # --------------------------------------------------

            stage_start = perf_counter()
            analyzer = AnalyzerFactory.build(file_path)
            analysis = analyzer.analyze(documents, file_path)
            STAGE_DURATION_SECONDS.labels(stage="analyze").observe(perf_counter() - stage_start)

            logger.info(f"Document Type   : {analysis.document_type}")
            logger.info(f"Confidence      : {analysis.confidence:.2f}")
            logger.info(f"Chunk Strategy  : {analysis.recommendation.strategy}")
            logger.info(f"Chunk Size      : {analysis.recommendation.chunk_size}")

            # --------------------------------------------------
            # Chunk Document
            # --------------------------------------------------

            stage_start = perf_counter()
            chunks = self.chunker.chunk(documents, analysis)
            STAGE_DURATION_SECONDS.labels(stage="chunk").observe(perf_counter() - stage_start)

            # --------------------------------------------------
            # Metadata Generation
            # --------------------------------------------------

            stage_start = perf_counter()
            chunks = self.metadata.generate(chunks, file_path, analysis)
            STAGE_DURATION_SECONDS.labels(stage="metadata").observe(perf_counter() - stage_start)

            # --------------------------------------------------
            # Vector Index
            # --------------------------------------------------

            stage_start = perf_counter()

            # Accumulate into any existing index rather than always
            # rebuilding from scratch -- a plain `.build()` here on every
            # call silently discarded every previously-ingested document
            # each time a new one came in (each /ingest replaced the
            # whole index with just its own chunks). `replace=True` is
            # the explicit opt-in for the old "start over" behavior.
            # FAISSIndexer.load()/.add() already existed for this; they
            # just weren't wired up here. See docs/05-roadmap.md.
            if save_index and not replace and self.indexer.exists(self.config.index_path):
                existing_vectorstore = self.indexer.load(self.config.index_path, self.embeddings)
                vectorstore = self.indexer.add(existing_vectorstore, chunks)
            else:
                vectorstore = self.indexer.build(chunks, self.embeddings)

            if save_index:
                self.indexer.save(vectorstore, self.config.index_path)

            STAGE_DURATION_SECONDS.labels(stage="index").observe(perf_counter() - stage_start)

            elapsed = perf_counter() - start

            average_chunk_size = (
                sum(len(c.page_content) for c in chunks) / max(len(chunks), 1)
            )
            duplicate_chunks = len(chunks) - len({c.page_content for c in chunks})

            CHUNK_COUNT.observe(len(chunks))
            AVERAGE_CHUNK_SIZE_CHARS.observe(average_chunk_size)
            DUPLICATE_CHUNKS.observe(duplicate_chunks)
            INGESTIONS_TOTAL.labels(outcome="success").inc()

            report = IngestionReport(
                source=Path(file_path).name,
                total_pages=analysis.statistics.page_count,
                total_chunks=len(chunks),
                average_chunk_size=average_chunk_size,
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
            INGESTIONS_TOTAL.labels(outcome="error").inc()
            raise

        except Exception as exc:
            logger.error(f"Ingestion failed for '{file_path}': {exc}")
            INGESTIONS_TOTAL.labels(outcome="error").inc()
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
    parser.add_argument(
        "--replace",
        action="store_true",
        help=(
            "Replace any existing index at the configured path instead of "
            "adding to it (the default is additive/incremental)."
        ),
    )
    args = parser.parse_args()

    pipeline = IngestionPipeline()
    pipeline.ingest(
        args.file_path,
        save_index=not args.no_save_index,
        replace=args.replace,
    )


if __name__ == "__main__":
    _main()

