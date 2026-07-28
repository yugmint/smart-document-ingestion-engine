# src/utils/metrics.py

"""
Prometheus metrics for the ingestion pipeline -- mirrors
RAG_Project_1's src/utils/metrics.py (same library, same shape: a
small fixed set of Histograms/Counters, not one for everything),
requested as a follow-up to that pattern already existing on the
retrieval side.

All recorded from a single hook point, IngestionPipeline.ingest() --
every ingestion (CLI or API) goes through it, so instrumenting there
covers both without touching src/ingestion/api.py.
"""

from prometheus_client import Counter, Histogram

STAGE_DURATION_SECONDS = Histogram(
    "ingestion_stage_duration_seconds",
    "Time spent in each ingestion pipeline stage.",
    ["stage"],
)

INGESTIONS_TOTAL = Counter(
    "ingestion_runs_total",
    "Ingestion runs, by outcome.",
    ["outcome"],
)

CHUNK_COUNT = Histogram(
    "ingestion_chunk_count",
    "Number of chunks produced per ingestion.",
    buckets=(10, 25, 50, 100, 250, 500, 1000, 2500, 5000),
)

AVERAGE_CHUNK_SIZE_CHARS = Histogram(
    "ingestion_average_chunk_size_chars",
    "Average chunk size (characters) per ingestion.",
    buckets=(100, 250, 500, 750, 1000, 1500, 2000, 3000),
)

DUPLICATE_CHUNKS = Histogram(
    "ingestion_duplicate_chunks",
    "Chunks with page_content identical to another chunk from the same ingestion.",
    buckets=(0, 1, 2, 5, 10, 25, 50),
)

# 0-100. Fraction of a document's pages that had at least one repeated
# header/footer line stripped by TextCleaner -- see
# src/ingestion/cleaners/text_cleaner.py.
NOISE_PERCENTAGE = Histogram(
    "ingestion_noise_percentage",
    "Percentage of pages with repeated header/footer noise stripped.",
    buckets=(0, 1, 2, 5, 10, 25, 50, 75, 100),
)
