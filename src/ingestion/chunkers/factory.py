from src.ingestion.config import IngestionConfig
from src.ingestion.analysers.models import ChunkingRecommendation

from src.ingestion.chunkers.recursive_chunker import RecursiveChunker
from src.ingestion.chunkers.structure_chunker import StructureChunker
from src.ingestion.chunkers.semantic_chunker import SemanticChunker
from src.ingestion.chunkers.markdown_chunker import MarkdownChunker

from src.utils.logger import logger


class ChunkerFactory:
    """
    Factory responsible for selecting the appropriate
    chunker based on the analyzer recommendation.
    """

    _CHUNKERS = {
        "recursive": RecursiveChunker,
        "structure": StructureChunker,
        "semantic": SemanticChunker,
        "markdown": MarkdownChunker,
    }

    @staticmethod
    def build(
        recommendation: ChunkingRecommendation,
        config: IngestionConfig,
    ):

        strategy = recommendation.strategy.lower()

        logger.info("=" * 80)
        logger.info(f"Selecting Chunker : {strategy}")

        chunker_cls = ChunkerFactory._CHUNKERS.get(strategy)

        if chunker_cls is None:
            logger.warning(
                f"Unknown strategy '{strategy}'. Falling back to RecursiveChunker."
            )
            chunker_cls = RecursiveChunker

        return chunker_cls(config)
