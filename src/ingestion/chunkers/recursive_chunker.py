from langchain_core.documents import Document

from src.ingestion.chunkers.base import BaseChunker
from src.ingestion.config import IngestionConfig
from src.ingestion.analysers.models import DocumentAnalysis
from src.utils.logger import logger

_DEFAULT_MIN_CHUNK_RATIO = 0.25


class RecursiveChunker(BaseChunker):
    """
    Splits documents by trying separators in priority order
    (paragraph -> line -> sentence -> word -> character),
    recursing into any piece still larger than `chunk_size`,
    then re-joining pieces with a trailing-context overlap.

    Effective chunk_size/chunk_overlap/merge/split behavior comes
    from `analysis.recommendation` when an analysis is provided
    (the normal pipeline path); otherwise it falls back to the
    static `IngestionConfig` values passed at construction time
    (useful for unit tests or ad-hoc use without an analyzer).
    """

    def __init__(self, config: IngestionConfig):
        self.config = config
        self.default_chunk_size = config.chunk_size
        self.default_chunk_overlap = config.chunk_overlap
        self.separators = list(config.separators)

    def chunk(
        self,
        documents: list[Document],
        analysis: DocumentAnalysis | None = None,
    ) -> list[Document]:

        logger.info("Recursive Chunking...")

        params = self._resolve_params(analysis)

        chunks: list[Document] = []

        for document in documents:
            text = document.page_content or ""
            if not text.strip():
                continue

            pieces = self._split(
                text,
                self.separators,
                params["chunk_size"],
                params["split_large_chunks"],
            )

            # `_split` guarantees every piece is <= chunk_size, but
            # says nothing about how far *under* it they are -- a
            # document with lots of short lines/paragraphs would
            # otherwise emit one tiny chunk per fragment. Pack
            # consecutive fragments back together up to chunk_size
            # so chunks actually land near the target size.
            pieces = self._pack(pieces, params["chunk_size"])

            pieces = self._apply_overlap(pieces, params["chunk_overlap"], params["chunk_size"])

            for part in pieces:
                part = part.strip()
                if part:
                    chunks.append(
                        Document(
                            page_content=part,
                            metadata={**document.metadata},
                        )
                    )

        if params["merge_small_chunks"]:
            chunks = self._merge_small_chunks(
                chunks,
                params["min_chunk_size"],
                params["chunk_size"],
            )

        logger.info(f"Chunks Created : {len(chunks)}")
        return chunks

    # --------------------------------------------------
    # Parameter resolution
    # --------------------------------------------------

    def _resolve_params(self, analysis: DocumentAnalysis | None) -> dict:
        if analysis is not None:
            rec = analysis.recommendation
            min_chunk_size = rec.min_chunk_size or max(
                50, int(rec.chunk_size * _DEFAULT_MIN_CHUNK_RATIO)
            )
            return {
                "chunk_size": rec.chunk_size,
                "chunk_overlap": rec.chunk_overlap,
                "merge_small_chunks": rec.merge_small_chunks,
                "split_large_chunks": rec.split_large_chunks,
                "min_chunk_size": min_chunk_size,
            }

        return {
            "chunk_size": self.default_chunk_size,
            "chunk_overlap": self.default_chunk_overlap,
            "merge_small_chunks": True,
            "split_large_chunks": True,
            "min_chunk_size": max(
                50, int(self.default_chunk_size * _DEFAULT_MIN_CHUNK_RATIO)
            ),
        }

    # --------------------------------------------------
    # Recursive splitting
    # --------------------------------------------------

    def _split(
        self,
        text: str,
        separators: list[str],
        chunk_size: int,
        split_large_chunks: bool,
    ) -> list[str]:

        if len(text) <= chunk_size:
            return [text]

        if not separators:
            return self._hard_slice(text, chunk_size) if split_large_chunks else [text]

        separator, *remaining = separators

        # "" is the character-level last resort: guaranteed to shrink.
        if separator == "":
            return self._hard_slice(text, chunk_size) if split_large_chunks else [text]

        if separator not in text:
            return self._split(text, remaining, chunk_size, split_large_chunks)

        fragments = [p for p in text.split(separator) if p != ""]

        pieces: list[str] = []
        for fragment in fragments:
            if len(fragment) <= chunk_size:
                pieces.append(fragment)
            else:
                pieces.extend(
                    self._split(fragment, remaining, chunk_size, split_large_chunks)
                )

        return pieces

    def _pack(self, pieces: list[str], chunk_size: int) -> list[str]:
        """
        Greedily combine consecutive fragments (each already
        <= chunk_size) into chunks as close to chunk_size as
        possible without exceeding it.
        """

        if not pieces:
            return pieces

        packed: list[str] = []
        current = ""

        for piece in pieces:
            candidate = f"{current}\n{piece}" if current else piece

            if len(candidate) <= chunk_size:
                current = candidate
            else:
                if current:
                    packed.append(current)
                current = piece

        if current:
            packed.append(current)

        return packed

    def _hard_slice(self, text: str, chunk_size: int) -> list[str]:
        if chunk_size <= 0:
            return [text]
        slices = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
        return slices or [text]

    # --------------------------------------------------
    # Overlap
    # --------------------------------------------------

    def _apply_overlap(
        self,
        pieces: list[str],
        chunk_overlap: int,
        chunk_size: int,
    ) -> list[str]:
        """
        Prefix each piece (after the first) with the trailing
        `chunk_overlap` characters of the previous *output* piece,
        so consecutive chunks share context instead of cutting
        cleanly at a boundary.

        Skips adding overlap where it would blow the chunk past
        1.5x its target size (e.g. the previous piece was already
        near max size) rather than letting chunks grow unbounded.
        """

        if not pieces or chunk_overlap <= 0:
            return pieces

        result = [pieces[0]]

        for piece in pieces[1:]:
            previous = result[-1]

            overlap_text = (
                previous[-chunk_overlap:]
                if len(previous) > chunk_overlap
                else previous
            )

            if overlap_text and not piece.startswith(overlap_text):
                candidate = f"{overlap_text}\n{piece}"
            else:
                candidate = piece

            if len(candidate) > chunk_size * 1.5:
                candidate = piece

            result.append(candidate)

        return result

    # --------------------------------------------------
    # Small chunk merging
    # --------------------------------------------------

    def _merge_small_chunks(
        self,
        chunks: list[Document],
        min_chunk_size: int,
        chunk_size: int,
    ) -> list[Document]:

        if not chunks:
            return chunks

        merged: list[Document] = []
        max_merged_size = int(chunk_size * 1.2)

        for chunk in chunks:
            if (
                merged
                and len(chunk.page_content) < min_chunk_size
                and len(merged[-1].page_content) + len(chunk.page_content)
                <= max_merged_size
            ):
                previous = merged[-1]
                previous.page_content = (
                    f"{previous.page_content}\n{chunk.page_content}".strip()
                )
            else:
                merged.append(
                    Document(
                        page_content=chunk.page_content,
                        metadata=dict(chunk.metadata),
                    )
                )

        return merged
