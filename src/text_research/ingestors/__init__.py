"""
Text Ingestors for various data sources.

Each ingestor converts raw data from a source into TextDocument objects
with proper point-in-time timestamps.
"""

from .news import NewsIngestor
from .sec import SECIngestor

__all__ = [
    "NewsIngestor",
    "SECIngestor",
]
