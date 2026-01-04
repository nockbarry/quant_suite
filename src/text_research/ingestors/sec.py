"""
SEC Filings Ingestor: Ingest SEC filings into TextCorpus.

Supports:
- 10-K Annual Reports
- 10-Q Quarterly Reports
- 8-K Current Reports

Filings are converted to TextDocuments with proper point-in-time timestamps
based on filing date (not period end date).
"""

import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..corpus import TextCorpus, TextDocument

logger = logging.getLogger(__name__)

# Try to import optional dependencies
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class SECIngestor:
    """
    Ingest SEC filings into TextCorpus.

    Uses SEC EDGAR API to fetch and parse filings. Each filing is stored
    with its filing date as the timestamp (when information became public).

    Example Usage:
        ingestor = SECIngestor(corpus)

        # Ingest recent 10-K filings
        count = ingestor.ingest_10k(symbols=["AAPL", "MSFT"])

        # Ingest 10-Q filings
        count = ingestor.ingest_10q(symbols=["AAPL"])

        # Ingest 8-K filings
        count = ingestor.ingest_8k(symbols=["AAPL"])
    """

    # SEC EDGAR API endpoints
    EDGAR_BASE = "https://www.sec.gov"
    EDGAR_SEARCH = "https://efts.sec.gov/LATEST/search-index"
    COMPANY_SEARCH = "https://www.sec.gov/cgi-bin/browse-edgar"

    # CIK mappings for common symbols
    CIK_MAP = {
        "AAPL": "0000320193",
        "MSFT": "0000789019",
        "GOOGL": "0001652044",
        "AMZN": "0001018724",
        "META": "0001326801",
        "NVDA": "0001045810",
        "AMD": "0000002488",
        "INTC": "0000050863",
        "QCOM": "0000804328",
        "MU": "0000723125",
        "AVGO": "0001730168",
        "TSLA": "0001318605",
        "JPM": "0000019617",
        "BAC": "0000070858",
        "GS": "0000886982",
    }

    # Sector mappings
    SECTOR_MAP = {
        "AAPL": "technology",
        "MSFT": "technology",
        "GOOGL": "technology",
        "AMZN": "technology",
        "META": "technology",
        "NVDA": "semiconductors",
        "AMD": "semiconductors",
        "INTC": "semiconductors",
        "QCOM": "semiconductors",
        "MU": "semiconductors",
        "AVGO": "semiconductors",
        "JPM": "financials",
        "BAC": "financials",
        "GS": "financials",
    }

    def __init__(self, corpus: TextCorpus, user_agent: str | None = None):
        """
        Initialize SECIngestor.

        Args:
            corpus: TextCorpus to add documents to
            user_agent: User agent for SEC requests (required by SEC)
        """
        self.corpus = corpus
        self.user_agent = user_agent or "QuantSuite/1.0 (quant@research.com)"
        self._headers = {"User-Agent": self.user_agent}

    def ingest_10k(
        self,
        symbols: list[str],
        years_back: int = 3,
    ) -> int:
        """
        Ingest 10-K annual reports.

        Args:
            symbols: List of stock symbols
            years_back: How many years of filings to fetch

        Returns:
            Number of documents added
        """
        return self._ingest_filings(symbols, "10-K", years_back * 1)

    def ingest_10q(
        self,
        symbols: list[str],
        quarters_back: int = 8,
    ) -> int:
        """
        Ingest 10-Q quarterly reports.

        Args:
            symbols: List of stock symbols
            quarters_back: How many quarters of filings to fetch

        Returns:
            Number of documents added
        """
        return self._ingest_filings(symbols, "10-Q", quarters_back)

    def ingest_8k(
        self,
        symbols: list[str],
        count: int = 20,
    ) -> int:
        """
        Ingest 8-K current reports.

        Args:
            symbols: List of stock symbols
            count: Number of recent 8-Ks to fetch per symbol

        Returns:
            Number of documents added
        """
        return self._ingest_filings(symbols, "8-K", count)

    def _ingest_filings(
        self,
        symbols: list[str],
        filing_type: str,
        count: int,
    ) -> int:
        """
        Ingest filings of a specific type.

        Args:
            symbols: List of symbols
            filing_type: Filing type (10-K, 10-Q, 8-K)
            count: Number of filings to fetch

        Returns:
            Number of documents added
        """
        if not HAS_REQUESTS:
            logger.warning("requests not available, skipping SEC ingestion")
            return 0

        total_added = 0

        for symbol in symbols:
            cik = self._get_cik(symbol)
            if not cik:
                logger.warning(f"No CIK found for {symbol}")
                continue

            try:
                filings = self._fetch_filings(cik, filing_type, count)

                for filing in filings:
                    doc = self._filing_to_document(filing, symbol, filing_type)
                    if doc:
                        try:
                            self.corpus.add_document(doc)
                            total_added += 1
                        except ValueError:
                            pass

                logger.info(f"Added {len(filings)} {filing_type} filings for {symbol}")

            except Exception as e:
                logger.warning(f"Failed to fetch {filing_type} for {symbol}: {e}")

        return total_added

    def _get_cik(self, symbol: str) -> str | None:
        """Get CIK for a symbol."""
        # Check mapping first
        if symbol in self.CIK_MAP:
            return self.CIK_MAP[symbol]

        # Try to look up from SEC
        try:
            url = f"{self.EDGAR_BASE}/cgi-bin/browse-edgar"
            params = {
                "action": "getcompany",
                "company": symbol,
                "type": "10-K",
                "dateb": "",
                "owner": "include",
                "count": "1",
                "output": "atom",
            }

            response = requests.get(url, params=params, headers=self._headers, timeout=30)

            # Parse CIK from response
            match = re.search(r"CIK=(\d+)", response.text)
            if match:
                cik = match.group(1).zfill(10)
                self.CIK_MAP[symbol] = cik  # Cache it
                return cik

        except Exception as e:
            logger.debug(f"CIK lookup failed for {symbol}: {e}")

        return None

    def _fetch_filings(
        self,
        cik: str,
        filing_type: str,
        count: int,
    ) -> list[dict]:
        """
        Fetch filings from SEC EDGAR.

        Args:
            cik: Company CIK
            filing_type: Filing type
            count: Number of filings to fetch

        Returns:
            List of filing metadata dictionaries
        """
        filings = []

        try:
            # Use SEC submissions API
            url = f"{self.EDGAR_BASE}/cgi-bin/browse-edgar"
            params = {
                "action": "getcompany",
                "CIK": cik,
                "type": filing_type,
                "dateb": "",
                "owner": "include",
                "count": count,
                "output": "atom",
            }

            response = requests.get(url, params=params, headers=self._headers, timeout=30)

            # Parse entries from Atom feed
            entries = re.findall(
                r"<entry>(.*?)</entry>",
                response.text,
                re.DOTALL
            )

            for entry in entries[:count]:
                filing = self._parse_filing_entry(entry)
                if filing:
                    filings.append(filing)

        except Exception as e:
            logger.warning(f"Failed to fetch filings: {e}")

        return filings

    def _parse_filing_entry(self, entry_xml: str) -> dict | None:
        """Parse a filing entry from Atom feed."""
        try:
            # Extract filing date
            date_match = re.search(r"<filing-date>(\d{4}-\d{2}-\d{2})</filing-date>", entry_xml)
            if not date_match:
                date_match = re.search(r"<updated>(\d{4}-\d{2}-\d{2})", entry_xml)

            filing_date = None
            if date_match:
                filing_date = datetime.strptime(date_match.group(1), "%Y-%m-%d")

            # Extract filing URL
            url_match = re.search(r'<link[^>]*href="([^"]+)"', entry_xml)
            filing_url = url_match.group(1) if url_match else None

            # Extract title
            title_match = re.search(r"<title>([^<]+)</title>", entry_xml)
            title = title_match.group(1) if title_match else ""

            # Extract accession number
            acc_match = re.search(r"(\d{10}-\d{2}-\d{6})", entry_xml)
            accession = acc_match.group(1) if acc_match else None

            if not filing_date:
                return None

            return {
                "filing_date": filing_date,
                "url": filing_url,
                "title": title,
                "accession": accession,
            }

        except Exception as e:
            logger.debug(f"Failed to parse filing entry: {e}")
            return None

    def _filing_to_document(
        self,
        filing: dict,
        symbol: str,
        filing_type: str,
    ) -> TextDocument | None:
        """Convert filing metadata to TextDocument."""
        try:
            # Fetch filing text (summary/item section)
            text = self._fetch_filing_text(filing)

            if not text:
                # Use title as fallback
                text = filing.get("title", "")

            if not text.strip():
                return None

            # Determine source type
            source_map = {
                "10-K": "sec_10k",
                "10-Q": "sec_10q",
                "8-K": "sec_8k",
            }
            source = source_map.get(filing_type, "sec")

            return TextDocument(
                text=text,
                timestamp=filing["filing_date"],
                source=source,
                symbols=[symbol],
                sector=self.SECTOR_MAP.get(symbol),
                metadata={
                    "filing_type": filing_type,
                    "accession": filing.get("accession"),
                    "url": filing.get("url"),
                },
            )

        except Exception as e:
            logger.debug(f"Failed to create document from filing: {e}")
            return None

    def _fetch_filing_text(
        self,
        filing: dict,
        max_length: int = 50000,
    ) -> str:
        """
        Fetch and extract text from filing.

        Args:
            filing: Filing metadata
            max_length: Maximum text length to return

        Returns:
            Extracted text from filing
        """
        url = filing.get("url")
        if not url:
            return ""

        try:
            # Add small delay to respect SEC rate limits
            import time
            time.sleep(0.1)

            response = requests.get(url, headers=self._headers, timeout=60)

            # Extract text content
            text = self._extract_text_from_html(response.text)

            # Truncate if needed
            if len(text) > max_length:
                text = text[:max_length] + "..."

            return text

        except Exception as e:
            logger.debug(f"Failed to fetch filing text: {e}")
            return ""

    def _extract_text_from_html(self, html: str) -> str:
        """Extract clean text from HTML filing."""
        # Remove script and style elements
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", html)

        # Decode HTML entities
        text = text.replace("&nbsp;", " ")
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&quot;", '"')

        # Clean up whitespace
        text = re.sub(r"\s+", " ", text)
        text = text.strip()

        return text

    def ingest_from_files(
        self,
        directory: str | Path,
        symbol: str,
        filing_type: str = "sec",
    ) -> int:
        """
        Ingest filings from local files.

        Args:
            directory: Directory containing filing files
            symbol: Stock symbol for all files
            filing_type: Filing type (sec_10k, sec_10q, sec_8k)

        Returns:
            Number of documents added
        """
        directory = Path(directory)
        if not directory.exists():
            logger.warning(f"Directory not found: {directory}")
            return 0

        total_added = 0

        for file_path in directory.glob("*.txt"):
            try:
                text = file_path.read_text()

                # Try to parse date from filename
                date_match = re.search(r"(\d{4}-\d{2}-\d{2})", file_path.name)
                if date_match:
                    timestamp = datetime.strptime(date_match.group(1), "%Y-%m-%d")
                else:
                    # Use file modification time
                    timestamp = datetime.fromtimestamp(file_path.stat().st_mtime)

                doc = TextDocument(
                    text=text,
                    timestamp=timestamp,
                    source=filing_type,
                    symbols=[symbol],
                    sector=self.SECTOR_MAP.get(symbol),
                    metadata={"file": str(file_path)},
                )

                self.corpus.add_document(doc)
                total_added += 1

            except Exception as e:
                logger.warning(f"Failed to ingest {file_path}: {e}")

        return total_added

    def __repr__(self) -> str:
        """String representation."""
        return f"SECIngestor(corpus={self.corpus})"
