"""
Document analyzers.

Responsible for understanding a document before chunking.

The analyzer determines:

- document characteristics
- layout information
- document classification
- recommended chunking strategy (size, overlap, merge/split behavior)
- a confidence score for that recommendation

This information is later consumed by the HybridChunker.
"""
