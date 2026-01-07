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

    # ================================================================
    # News & Social Ingest Methods
    # ================================================================

    def ingest_news_batch(
        self,
        news_items: list[dict],
        source: str = "news",
    ) -> list[str]:
        """
        Batch ingest news items from news daemon or other sources.

        Args:
            news_items: List of news dictionaries with fields:
                - headline or title: str
                - content or text: str (optional)
                - published_at or timestamp: datetime or str
                - symbols: list[str] (optional)
                - url: str (optional)
                - sentiment: str (optional)
            source: Document source type (default: "news")

        Returns:
            List of added document IDs

        Example:
            news = [
                {
                    "headline": "Apple announces record earnings",
                    "content": "Apple Inc reported...",
                    "published_at": "2026-01-06T08:30:00",
                    "symbols": ["AAPL"],
                }
            ]
            doc_ids = corpus.ingest_news_batch(news)
        """
        doc_ids = []

        for item in news_items:
            try:
                # Extract headline/title
                headline = item.get("headline") or item.get("title", "")

                # Extract content
                content = item.get("content") or item.get("text") or item.get("summary", "")

                # Combine headline and content
                full_text = f"{headline}\n\n{content}".strip() if content else headline

                if not full_text:
                    continue

                # Extract timestamp
                timestamp = item.get("published_at") or item.get("timestamp")
                if isinstance(timestamp, str):
                    timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                elif timestamp is None:
                    timestamp = datetime.now()

                # Extract symbols
                symbols = item.get("symbols") or item.get("tickers") or []
                if isinstance(symbols, str):
                    symbols = [symbols]

                # Build metadata
                metadata = {}
                if item.get("url"):
                    metadata["url"] = item["url"]
                if item.get("sentiment"):
                    metadata["sentiment"] = item["sentiment"]
                if item.get("importance"):
                    metadata["importance"] = item["importance"]
                if item.get("source_name"):
                    metadata["source_name"] = item["source_name"]

                doc = TextDocument(
                    text=full_text,
                    timestamp=timestamp,
                    source=source,
                    symbols=symbols,
                    sector=item.get("sector"),
                    metadata=metadata,
                )

                doc_id = self.add_document(doc)
                doc_ids.append(doc_id)

            except Exception as e:
                logger.warning(f"Failed to ingest news item: {e}")

        logger.info(f"Ingested {len(doc_ids)} news items")
        return doc_ids

    def add_reddit_post(
        self,
        subreddit: str,
        post: dict,
    ) -> str | None:
        """
        Add a Reddit post to the corpus.

        Args:
            subreddit: Subreddit name (e.g., "wallstreetbets")
            post: Post dictionary with fields:
                - title: str
                - selftext: str (post body, optional)
                - created_utc: float or datetime
                - score: int
                - url: str
                - num_comments: int
                - tickers: list[str] (extracted tickers)

        Returns:
            Document ID or None if failed

        Example:
            post = {
                "title": "AAPL to the moon!",
                "selftext": "Just bought 100 shares...",
                "created_utc": 1704538800,
                "score": 500,
                "tickers": ["AAPL"],
            }
            doc_id = corpus.add_reddit_post("wallstreetbets", post)
        """
        try:
            title = post.get("title", "")
            body = post.get("selftext") or post.get("body", "")

            # Combine title and body
            full_text = f"{title}\n\n{body}".strip() if body else title

            if not full_text:
                return None

            # Extract timestamp
            created = post.get("created_utc") or post.get("created")
            if isinstance(created, (int, float)):
                timestamp = datetime.fromtimestamp(created)
            elif isinstance(created, str):
                timestamp = datetime.fromisoformat(created)
            elif isinstance(created, datetime):
                timestamp = created
            else:
                timestamp = datetime.now()

            # Extract tickers
            symbols = post.get("tickers") or post.get("symbols") or []
            if isinstance(symbols, str):
                symbols = [symbols]

            metadata = {
                "subreddit": subreddit,
                "score": post.get("score", 0),
                "num_comments": post.get("num_comments", 0),
                "url": post.get("url", ""),
                "post_id": post.get("id", ""),
            }

            if post.get("sentiment_score") is not None:
                metadata["sentiment_score"] = post["sentiment_score"]

            doc = TextDocument(
                text=full_text,
                timestamp=timestamp,
                source="reddit",
                symbols=symbols,
                metadata=metadata,
            )

            return self.add_document(doc)

        except Exception as e:
            logger.warning(f"Failed to add Reddit post: {e}")
            return None

    def add_twitter_sentiment(
        self,
        symbol: str,
        sentiment_data: dict,
    ) -> str | None:
        """
        Add Twitter/X sentiment data for a symbol.

        Args:
            symbol: Stock ticker
            sentiment_data: Sentiment dictionary with fields:
                - summary: str (overall sentiment summary)
                - tweets: list[dict] (optional, individual tweets)
                - sentiment_score: float (-1 to 1)
                - bullish_count: int
                - bearish_count: int
                - timestamp: datetime or str

        Returns:
            Document ID or None if failed

        Example:
            sentiment = {
                "summary": "Overall bullish on AAPL after earnings...",
                "sentiment_score": 0.65,
                "bullish_count": 150,
                "bearish_count": 50,
            }
            doc_id = corpus.add_twitter_sentiment("AAPL", sentiment)
        """
        try:
            summary = sentiment_data.get("summary", "")
            tweets = sentiment_data.get("tweets", [])

            # Build text from summary and sample tweets
            text_parts = [f"Twitter Sentiment for {symbol}"]
            if summary:
                text_parts.append(f"\n{summary}")

            # Add sample tweets if available
            if tweets:
                text_parts.append("\nSample tweets:")
                for tweet in tweets[:5]:  # Limit to 5 samples
                    tweet_text = tweet.get("text", "")
                    if tweet_text:
                        text_parts.append(f"- {tweet_text[:200]}")

            full_text = "\n".join(text_parts)

            # Extract timestamp
            timestamp = sentiment_data.get("timestamp")
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp)
            elif timestamp is None:
                timestamp = datetime.now()

            metadata = {
                "sentiment_score": sentiment_data.get("sentiment_score", 0),
                "bullish_count": sentiment_data.get("bullish_count", 0),
                "bearish_count": sentiment_data.get("bearish_count", 0),
                "total_tweets": sentiment_data.get("total_tweets", len(tweets)),
            }

            doc = TextDocument(
                text=full_text,
                timestamp=timestamp,
                source="twitter",
                symbols=[symbol],
                metadata=metadata,
            )

            return self.add_document(doc)

        except Exception as e:
            logger.warning(f"Failed to add Twitter sentiment: {e}")
            return None

    def add_earnings_call(
        self,
        symbol: str,
        transcript: str,
        call_date: datetime,
        metadata: dict | None = None,
    ) -> str | None:
        """
        Add an earnings call transcript.

        Args:
            symbol: Company ticker
            transcript: Full transcript text
            call_date: When the call occurred
            metadata: Additional metadata (quarter, fiscal_year, etc.)

        Returns:
            Document ID or None if failed
        """
        try:
            doc = TextDocument(
                text=transcript,
                timestamp=call_date,
                source="earnings_call",
                symbols=[symbol],
                metadata=metadata or {},
            )
            return self.add_document(doc)

        except Exception as e:
            logger.warning(f"Failed to add earnings call: {e}")
            return None

    def add_analyst_report(
        self,
        symbol: str,
        report_text: str,
        report_date: datetime,
        analyst_firm: str | None = None,
        rating: str | None = None,
        price_target: float | None = None,
    ) -> str | None:
        """
        Add an analyst report.

        Args:
            symbol: Company ticker
            report_text: Report content
            report_date: When report was published
            analyst_firm: Name of the firm
            rating: Buy/Hold/Sell rating
            price_target: Target price if provided

        Returns:
            Document ID or None if failed
        """
        try:
            metadata = {}
            if analyst_firm:
                metadata["analyst_firm"] = analyst_firm
            if rating:
                metadata["rating"] = rating
            if price_target:
                metadata["price_target"] = price_target

            doc = TextDocument(
                text=report_text,
                timestamp=report_date,
                source="analyst_report",
                symbols=[symbol],
                metadata=metadata,
            )
            return self.add_document(doc)

        except Exception as e:
            logger.warning(f"Failed to add analyst report: {e}")
            return None

    def get_recent_sentiment(
        self,
        symbol: str,
        hours: int = 24,
        sources: list[str] | None = None,
    ) -> list[TextDocument]:
        """
        Get recent sentiment-related documents for a symbol.

        Args:
            symbol: Stock ticker
            hours: How many hours back to look
            sources: Sources to include (default: reddit, twitter, news)

        Returns:
            List of documents sorted by timestamp (newest first)
        """
        sources = sources or ["reddit", "twitter", "news"]
        cutoff = datetime.now() - timedelta(hours=hours)

        docs = []
        for doc_id, info in self._doc_index.items():
            if info["source"] not in sources:
                continue
            if symbol not in info.get("symbols", []):
                continue

            doc_timestamp = datetime.fromisoformat(info["timestamp"])
            if doc_timestamp >= cutoff:
                doc = self.get_document(doc_id)
                if doc:
                    docs.append(doc)

        docs.sort(key=lambda d: d.timestamp, reverse=True)
        return docs

    def get_sentiment_summary(
        self,
        symbol: str,
        hours: int = 24,
    ) -> dict:
        """
        Get aggregated sentiment summary for a symbol.

        Args:
            symbol: Stock ticker
            hours: How many hours back to look

        Returns:
            Dictionary with sentiment metrics
        """
        docs = self.get_recent_sentiment(symbol, hours)

        if not docs:
            return {
                "symbol": symbol,
                "doc_count": 0,
                "avg_sentiment": None,
                "sources": {},
            }

        # Aggregate by source
        by_source: dict[str, list] = {}
        sentiment_scores = []

        for doc in docs:
            source = doc.source
            if source not in by_source:
                by_source[source] = []
            by_source[source].append(doc)

            # Extract sentiment score if available
            score = doc.metadata.get("sentiment_score")
            if score is not None:
                sentiment_scores.append(score)

        return {
            "symbol": symbol,
            "doc_count": len(docs),
            "avg_sentiment": sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else None,
            "sources": {s: len(d) for s, d in by_source.items()},
            "time_range_hours": hours,
        }
