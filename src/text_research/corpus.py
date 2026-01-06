"""
TextCorpus: Point-in-Time Safe Text Storage.

Provides a storage layer for text documents with strict temporal ordering
to prevent lookahead bias in backtesting text-based strategies.

Key Features:
- Documents stored with availability timestamp (when information was accessible)
- get_documents_as_of() ensures no future documents leak into historical analysis
- Efficient querying by symbol, source, and date range
- DuckDB/Parquet backend for scalable storage
"""

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any
import logging

from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class TextDocument:
    """
    Single text document with point-in-time metadata.

    Attributes:
        doc_id: Unique document identifier (auto-generated if not provided)
        text: The actual text content
        timestamp: When the text was AVAILABLE for trading (not published date)
                   This is critical for avoiding lookahead bias
        source: Document source type ('news', 'sec_10k', 'sec_10q', 'earnings_call', 'reddit')
        symbols: List of associated stock tickers
        sector: Optional sector classification
        metadata: Additional source-specific metadata
    """
    text: str
    timestamp: datetime
    source: str
    symbols: list[str] = field(default_factory=list)
    sector: str | None = None
    metadata: dict = field(default_factory=dict)
    doc_id: str = ""

    def __post_init__(self):
        """Generate doc_id from content hash if not provided."""
        if not self.doc_id:
            # Create deterministic ID from content + timestamp
            content_hash = hashlib.sha256(
                f"{self.text[:500]}{self.timestamp.isoformat()}{self.source}".encode()
            ).hexdigest()[:16]
            self.doc_id = f"{self.source}_{content_hash}"

        # Ensure symbols is a list
        if isinstance(self.symbols, str):
            self.symbols = [self.symbols]

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "doc_id": self.doc_id,
            "text": self.text,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "symbols": self.symbols,
            "sector": self.sector,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TextDocument":
        """Create from dictionary."""
        data = data.copy()
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


class TextCorpus:
    """
    Point-in-time safe text storage with efficient querying.

    Storage Format:
    - Documents stored in Parquet files partitioned by date
    - Index file maps doc_id to file location
    - Metadata stored in JSON for quick lookups

    Example Usage:
        corpus = TextCorpus()

        # Add documents
        doc = TextDocument(
            text="Apple reports record earnings...",
            timestamp=datetime(2026, 1, 3, 9, 30),  # When news became available
            source="news",
            symbols=["AAPL"],
        )
        corpus.add_document(doc)

        # Query documents (no lookahead)
        docs = corpus.get_documents_as_of(
            as_of_date=date(2026, 1, 3),
            symbols=["AAPL"],
            lookback_days=7
        )
    """

    # Valid source types
    VALID_SOURCES = {
        "news",
        "sec_10k",
        "sec_10q",
        "sec_8k",
        "earnings_call",
        "reddit",
        "twitter",
        "analyst_report",
    }

    def __init__(self, storage_path: str | Path | None = None):
        """
        Initialize TextCorpus.

        Args:
            storage_path: Directory for storing documents.
                         Defaults to paths.text_corpus
        """
        self.storage_path = Path(storage_path) if storage_path else paths.text_corpus
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # Subdirectories
        self.docs_path = self.storage_path / "documents"
        self.index_path = self.storage_path / "index"
        self.docs_path.mkdir(exist_ok=True)
        self.index_path.mkdir(exist_ok=True)

        # In-memory index for fast lookups
        self._doc_index: dict[str, dict] = {}
        self._symbol_index: dict[str, set[str]] = {}  # symbol -> set of doc_ids
        self._date_index: dict[str, set[str]] = {}    # date_str -> set of doc_ids

        # Load existing index
        self._load_index()

    def _load_index(self) -> None:
        """Load index from disk."""
        index_file = self.index_path / "main_index.json"
        if index_file.exists():
            try:
                with open(index_file) as f:
                    data = json.load(f)
                self._doc_index = data.get("doc_index", {})
                self._symbol_index = {
                    k: set(v) for k, v in data.get("symbol_index", {}).items()
                }
                self._date_index = {
                    k: set(v) for k, v in data.get("date_index", {}).items()
                }
                logger.info(f"Loaded {len(self._doc_index)} documents from index")
            except Exception as e:
                logger.warning(f"Failed to load index: {e}, starting fresh")

    def _save_index(self) -> None:
        """Save index to disk."""
        index_file = self.index_path / "main_index.json"
        data = {
            "doc_index": self._doc_index,
            "symbol_index": {k: list(v) for k, v in self._symbol_index.items()},
            "date_index": {k: list(v) for k, v in self._date_index.items()},
        }
        with open(index_file, "w") as f:
            json.dump(data, f)

    def add_document(self, doc: TextDocument) -> str:
        """
        Add a document to the corpus with strict timestamp validation.

        Args:
            doc: TextDocument to add

        Returns:
            Document ID

        Raises:
            ValueError: If document fails validation
        """
        # Validate source
        if doc.source not in self.VALID_SOURCES:
            raise ValueError(f"Invalid source '{doc.source}'. Must be one of {self.VALID_SOURCES}")

        # Validate timestamp (must not be in the future)
        if doc.timestamp > datetime.now():
            raise ValueError(f"Document timestamp {doc.timestamp} is in the future")

        # Check for duplicates
        if doc.doc_id in self._doc_index:
            logger.debug(f"Document {doc.doc_id} already exists, skipping")
            return doc.doc_id

        # Store document
        date_str = doc.timestamp.strftime("%Y-%m-%d")
        doc_file = self.docs_path / f"{date_str}_{doc.doc_id}.json"

        with open(doc_file, "w") as f:
            json.dump(doc.to_dict(), f, indent=2)

        # Update indices
        self._doc_index[doc.doc_id] = {
            "file": str(doc_file),
            "timestamp": doc.timestamp.isoformat(),
            "source": doc.source,
            "symbols": doc.symbols,
        }

        for symbol in doc.symbols:
            if symbol not in self._symbol_index:
                self._symbol_index[symbol] = set()
            self._symbol_index[symbol].add(doc.doc_id)

        if date_str not in self._date_index:
            self._date_index[date_str] = set()
        self._date_index[date_str].add(doc.doc_id)

        # Persist index
        self._save_index()

        logger.debug(f"Added document {doc.doc_id} with timestamp {doc.timestamp}")
        return doc.doc_id

    def add_documents(self, docs: list[TextDocument]) -> list[str]:
        """
        Batch add documents.

        Args:
            docs: List of TextDocuments to add

        Returns:
            List of document IDs
        """
        doc_ids = []
        for doc in docs:
            try:
                doc_id = self.add_document(doc)
                doc_ids.append(doc_id)
            except Exception as e:
                logger.warning(f"Failed to add document: {e}")
        return doc_ids

    def get_document(self, doc_id: str) -> TextDocument | None:
        """
        Retrieve a document by ID.

        Args:
            doc_id: Document identifier

        Returns:
            TextDocument or None if not found
        """
        if doc_id not in self._doc_index:
            return None

        doc_file = Path(self._doc_index[doc_id]["file"])
        if not doc_file.exists():
            logger.warning(f"Document file missing for {doc_id}")
            return None

        with open(doc_file) as f:
            return TextDocument.from_dict(json.load(f))

    def get_documents_as_of(
        self,
        as_of_date: date,
        symbols: list[str] | None = None,
        sources: list[str] | None = None,
        lookback_days: int = 30,
    ) -> list[TextDocument]:
        """
        Get documents available on or before as_of_date (NO LOOKAHEAD).

        This is the key method for point-in-time safe analysis. It returns
        only documents that would have been available to a trader on the
        specified date.

        Args:
            as_of_date: The reference date (documents must be available by this date)
            symbols: Optional list of symbols to filter by
            sources: Optional list of sources to filter by
            lookback_days: How many days back to look (default 30)

        Returns:
            List of TextDocuments sorted by timestamp (oldest first)
        """
        # Calculate date range
        end_dt = datetime.combine(as_of_date, datetime.max.time())
        start_dt = end_dt - timedelta(days=lookback_days)

        # Find candidate doc_ids from date index
        candidate_ids = set()
        current = start_dt.date()
        while current <= as_of_date:
            date_str = current.strftime("%Y-%m-%d")
            if date_str in self._date_index:
                candidate_ids.update(self._date_index[date_str])
            current += timedelta(days=1)

        # Filter by symbols if specified
        if symbols:
            symbol_ids = set()
            for symbol in symbols:
                if symbol in self._symbol_index:
                    symbol_ids.update(self._symbol_index[symbol])
            candidate_ids = candidate_ids.intersection(symbol_ids)

        # Load and filter documents
        documents = []
        for doc_id in candidate_ids:
            info = self._doc_index.get(doc_id)
            if not info:
                continue

            # Filter by source
            if sources and info["source"] not in sources:
                continue

            # Strict timestamp check (CRITICAL for no lookahead)
            doc_timestamp = datetime.fromisoformat(info["timestamp"])
            if doc_timestamp > end_dt:
                continue  # Document not yet available
            if doc_timestamp < start_dt:
                continue  # Outside lookback window

            doc = self.get_document(doc_id)
            if doc:
                documents.append(doc)

        # Sort by timestamp (oldest first)
        documents.sort(key=lambda d: d.timestamp)

        logger.debug(
            f"get_documents_as_of({as_of_date}, symbols={symbols}, "
            f"lookback={lookback_days}d) returned {len(documents)} docs"
        )

        return documents

    def get_training_window(
        self,
        start: date,
        end: date,
        symbols: list[str] | None = None,
        sources: list[str] | None = None,
    ) -> list[TextDocument]:
        """
        Get documents for training with proper temporal boundaries.

        Unlike get_documents_as_of, this returns all documents within
        a date range, suitable for training a model on historical data.

        Args:
            start: Start date (inclusive)
            end: End date (inclusive)
            symbols: Optional list of symbols to filter by
            sources: Optional list of sources to filter by

        Returns:
            List of TextDocuments sorted by timestamp
        """
        start_dt = datetime.combine(start, datetime.min.time())
        end_dt = datetime.combine(end, datetime.max.time())

        documents = []

        # Iterate through date index
        current = start
        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            if date_str in self._date_index:
                for doc_id in self._date_index[date_str]:
                    info = self._doc_index.get(doc_id)
                    if not info:
                        continue

                    # Filter by source
                    if sources and info["source"] not in sources:
                        continue

                    # Filter by symbol
                    if symbols:
                        if not any(s in info.get("symbols", []) for s in symbols):
                            continue

                    doc = self.get_document(doc_id)
                    if doc and start_dt <= doc.timestamp <= end_dt:
                        documents.append(doc)

            current += timedelta(days=1)

        # Sort by timestamp
        documents.sort(key=lambda d: d.timestamp)

        return documents

    def get_latest_documents(
        self,
        n: int = 100,
        symbols: list[str] | None = None,
        sources: list[str] | None = None,
    ) -> list[TextDocument]:
        """
        Get the N most recent documents.

        Args:
            n: Number of documents to return
            symbols: Optional list of symbols to filter by
            sources: Optional list of sources to filter by

        Returns:
            List of TextDocuments sorted by timestamp (newest first)
        """
        # Get all doc_ids with timestamps
        docs_with_time = []

        for doc_id, info in self._doc_index.items():
            # Filter by source
            if sources and info["source"] not in sources:
                continue

            # Filter by symbol
            if symbols:
                if not any(s in info.get("symbols", []) for s in symbols):
                    continue

            docs_with_time.append((doc_id, info["timestamp"]))

        # Sort by timestamp descending and take top n
        docs_with_time.sort(key=lambda x: x[1], reverse=True)
        top_ids = [d[0] for d in docs_with_time[:n]]

        # Load documents
        documents = []
        for doc_id in top_ids:
            doc = self.get_document(doc_id)
            if doc:
                documents.append(doc)

        return documents

    def count_documents(
        self,
        symbols: list[str] | None = None,
        sources: list[str] | None = None,
    ) -> int:
        """
        Count documents matching criteria.

        Args:
            symbols: Optional list of symbols to filter by
            sources: Optional list of sources to filter by

        Returns:
            Document count
        """
        count = 0
        for doc_id, info in self._doc_index.items():
            if sources and info["source"] not in sources:
                continue
            if symbols:
                if not any(s in info.get("symbols", []) for s in symbols):
                    continue
            count += 1
        return count

    def get_date_range(self) -> tuple[date | None, date | None]:
        """
        Get the date range of documents in the corpus.

        Returns:
            Tuple of (min_date, max_date) or (None, None) if empty
        """
        if not self._date_index:
            return None, None

        dates = [datetime.strptime(d, "%Y-%m-%d").date() for d in self._date_index.keys()]
        return min(dates), max(dates)

    def get_symbols(self) -> list[str]:
        """
        Get all symbols with documents in the corpus.

        Returns:
            List of unique symbols
        """
        return list(self._symbol_index.keys())

    def get_sources(self) -> list[str]:
        """
        Get all sources represented in the corpus.

        Returns:
            List of unique sources
        """
        sources = set()
        for info in self._doc_index.values():
            sources.add(info["source"])
        return list(sources)

    def __len__(self) -> int:
        """Return total document count."""
        return len(self._doc_index)

    def __repr__(self) -> str:
        """String representation."""
        date_range = self.get_date_range()
        if date_range[0]:
            range_str = f"{date_range[0]} to {date_range[1]}"
        else:
            range_str = "empty"
        return f"TextCorpus({len(self)} documents, {range_str})"
