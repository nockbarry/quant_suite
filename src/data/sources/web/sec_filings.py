"""
SEC Filing Scraper

Fetches and parses SEC filings (10-K, 10-Q, 8-K) from EDGAR:
- Recent filings lookup by symbol/CIK
- Section extraction (Risk Factors, MD&A, Business)
- Sentiment analysis of key sections
- Filing comparison for change detection
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

import pandas as pd

from .scraper import WebScraper, DiskCache

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

class FilingType(Enum):
    """SEC filing types."""
    FORM_10K = "10-K"
    FORM_10Q = "10-Q"
    FORM_8K = "8-K"
    FORM_DEF14A = "DEF 14A"
    FORM_S1 = "S-1"
    FORM_4 = "4"  # Insider trading


@dataclass
class Filing:
    """Metadata for an SEC filing."""
    accession_number: str
    filing_type: str
    filed_date: datetime
    cik: str
    company_name: str
    form_url: str
    index_url: str
    description: str = ""


@dataclass
class FilingDocument:
    """A parsed SEC filing document."""
    filing: Filing
    full_text: str
    sections: dict = field(default_factory=dict)
    tables: list = field(default_factory=list)
    exhibits: list = field(default_factory=list)
    fetched_at: datetime = field(default_factory=datetime.now)


@dataclass
class FilingSentiment:
    """Sentiment analysis results for a filing."""
    overall_sentiment: float  # -1 to 1
    section_sentiments: dict  # section -> sentiment
    word_counts: dict  # section -> word count
    key_phrases: list  # Important phrases detected
    risk_indicators: list  # Risk-related phrases
    confidence: float


@dataclass
class FilingComparison:
    """Comparison between two filings."""
    current_filing: Filing
    previous_filing: Filing
    new_risk_factors: list
    removed_risk_factors: list
    sentiment_change: float
    word_count_change: dict
    key_changes: list


# =============================================================================
# CIK LOOKUP
# =============================================================================

# Common ticker -> CIK mappings (expandable)
TICKER_CIK_MAP = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "GOOGL": "0001652044",
    "AMZN": "0001018724",
    "META": "0001326801",
    "TSLA": "0001318605",
    "NVDA": "0001045810",
    "JPM": "0000019617",
    "V": "0001403161",
    "JNJ": "0000200406",
    "WMT": "0000104169",
    "PG": "0000080424",
    "UNH": "0000731766",
    "HD": "0000354950",
    "MA": "0001141391",
    "DIS": "0001744489",
    "PYPL": "0001633917",
    "ADBE": "0000796343",
    "NFLX": "0001065280",
    "CRM": "0001108524",
    "INTC": "0000050863",
    "AMD": "0000002488",
    "QCOM": "0000804328",
    "AVGO": "0001730168",
    "BA": "0000012927",
    "GS": "0000886982",
    "MS": "0000895421",
    "BAC": "0000070858",
    "WFC": "0000072971",
    "C": "0000831001",
    "SPY": "0000884394",
    "QQQ": "0001067839",
}


class CIKLookup:
    """Lookup CIK from ticker symbol."""

    SEC_COMPANY_SEARCH = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={}&type=&dateb=&owner=include&count=40&search_text="
    SEC_TICKER_MAP = "https://www.sec.gov/files/company_tickers.json"

    def __init__(self, scraper: WebScraper):
        self.scraper = scraper
        self._ticker_map: Optional[dict] = None

    async def _load_ticker_map(self) -> dict:
        """Load SEC ticker -> CIK mapping."""
        if self._ticker_map is not None:
            return self._ticker_map

        try:
            result = await self.scraper.fetch(
                self.SEC_TICKER_MAP,
                cache_ttl=timedelta(days=7),
            )

            import json
            data = json.loads(result.content)

            # Build ticker -> CIK map
            self._ticker_map = {}
            for entry in data.values():
                ticker = entry.get("ticker", "").upper()
                cik = str(entry.get("cik_str", "")).zfill(10)
                if ticker and cik:
                    self._ticker_map[ticker] = cik

            logger.info(f"Loaded {len(self._ticker_map)} ticker mappings")
            return self._ticker_map

        except Exception as e:
            logger.error(f"Failed to load ticker map: {e}")
            return TICKER_CIK_MAP

    async def get_cik(self, ticker: str) -> Optional[str]:
        """Get CIK for ticker symbol."""
        ticker = ticker.upper()

        # Check static map first
        if ticker in TICKER_CIK_MAP:
            return TICKER_CIK_MAP[ticker]

        # Load dynamic map
        ticker_map = await self._load_ticker_map()
        return ticker_map.get(ticker)


# =============================================================================
# SEC FILING SCRAPER
# =============================================================================

class SECFilingScraper:
    """
    Scrape and parse SEC filings from EDGAR.

    Usage:
        scraper = SECFilingScraper()
        filings = await scraper.get_recent_filings("AAPL", "10-K", limit=5)
        doc = await scraper.fetch_filing(filings[0].accession_number)
        sections = scraper.extract_sections(doc)
    """

    EDGAR_BASE = "https://www.sec.gov"
    EDGAR_FULL_TEXT = "https://efts.sec.gov/LATEST/search-index"
    EDGAR_FILINGS = "https://data.sec.gov/submissions/CIK{cik}.json"
    EDGAR_FILING_DOC = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"

    # Section patterns for 10-K/10-Q
    SECTION_PATTERNS = {
        "business": r"(?:ITEM\s*1\.?\s*[-–]?\s*BUSINESS|PART\s+I\s*[-–]?\s*ITEM\s*1)",
        "risk_factors": r"(?:ITEM\s*1A\.?\s*[-–]?\s*RISK\s*FACTORS)",
        "mda": r"(?:ITEM\s*7\.?\s*[-–]?\s*MANAGEMENT['\u2019]?S?\s*DISCUSSION)",
        "financial_statements": r"(?:ITEM\s*8\.?\s*[-–]?\s*FINANCIAL\s*STATEMENTS)",
        "controls": r"(?:ITEM\s*9A\.?\s*[-–]?\s*CONTROLS)",
        "legal_proceedings": r"(?:ITEM\s*3\.?\s*[-–]?\s*LEGAL\s*PROCEEDINGS)",
        "properties": r"(?:ITEM\s*2\.?\s*[-–]?\s*PROPERTIES)",
    }

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        rate_limit: float = 0.5,  # SEC rate limit: 10 req/sec, we use conservative 0.5
    ):
        self.scraper = WebScraper(
            cache_dir=cache_dir or Path.home() / ".quant_cache" / "sec",
            rate_limit=rate_limit,
            cache_ttl=timedelta(days=30),  # SEC filings don't change
        )
        self.cik_lookup = CIKLookup(self.scraper)

    async def close(self):
        """Close the scraper session."""
        await self.scraper.close()

    async def get_recent_filings(
        self,
        symbol: str,
        filing_type: str = "10-K",
        limit: int = 10,
    ) -> list[Filing]:
        """
        Get recent filings for a symbol.

        Args:
            symbol: Ticker symbol (e.g., "AAPL")
            filing_type: Filing type (e.g., "10-K", "10-Q", "8-K")
            limit: Maximum number of filings to return

        Returns:
            List of Filing objects
        """
        cik = await self.cik_lookup.get_cik(symbol)
        if not cik:
            logger.error(f"Could not find CIK for {symbol}")
            return []

        # Fetch company submissions
        url = self.EDGAR_FILINGS.format(cik=cik)
        try:
            result = await self.scraper.fetch(url)
            import json
            data = json.loads(result.content)
        except Exception as e:
            logger.error(f"Failed to fetch filings for {symbol}: {e}")
            return []

        # Parse filings
        filings = []
        recent = data.get("filings", {}).get("recent", {})

        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])

        company_name = data.get("name", symbol)

        for i, form in enumerate(forms):
            if len(filings) >= limit:
                break

            # Match filing type (handle variations like "10-K/A")
            if not form.upper().startswith(filing_type.upper()):
                continue

            try:
                accession = accessions[i].replace("-", "")
                filed_date = datetime.strptime(dates[i], "%Y-%m-%d")
                primary_doc = primary_docs[i]

                filing = Filing(
                    accession_number=accessions[i],
                    filing_type=form,
                    filed_date=filed_date,
                    cik=cik,
                    company_name=company_name,
                    form_url=self.EDGAR_FILING_DOC.format(
                        cik=cik.lstrip("0"),
                        accession=accession,
                        document=primary_doc,
                    ),
                    index_url=f"{self.EDGAR_BASE}/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type={filing_type}",
                )
                filings.append(filing)

            except (IndexError, ValueError) as e:
                logger.debug(f"Error parsing filing {i}: {e}")
                continue

        logger.info(f"Found {len(filings)} {filing_type} filings for {symbol}")
        return filings

    async def fetch_filing(self, filing: Filing) -> FilingDocument:
        """
        Fetch the full text of a filing.

        Args:
            filing: Filing object

        Returns:
            FilingDocument with full text and parsed sections
        """
        try:
            result = await self.scraper.fetch(filing.form_url)
            full_text = self.scraper.extract_text(result.content)

            # Parse sections
            sections = self.extract_sections_from_text(full_text)

            # Extract tables
            tables = self.scraper.extract_tables(result.content)

            return FilingDocument(
                filing=filing,
                full_text=full_text,
                sections=sections,
                tables=tables,
            )

        except Exception as e:
            logger.error(f"Failed to fetch filing {filing.accession_number}: {e}")
            return FilingDocument(
                filing=filing,
                full_text="",
                sections={},
            )

    def extract_sections_from_text(self, text: str) -> dict[str, str]:
        """
        Extract key sections from filing text.

        Args:
            text: Full filing text

        Returns:
            Dict mapping section name to content
        """
        sections = {}
        text_upper = text.upper()

        for section_name, pattern in self.SECTION_PATTERNS.items():
            try:
                # Find section start
                match = re.search(pattern, text_upper, re.IGNORECASE)
                if not match:
                    continue

                start_idx = match.end()

                # Find next section (any ITEM header)
                next_section = re.search(
                    r"ITEM\s+\d+[A-Z]?\.?\s*[-–]?",
                    text_upper[start_idx:],
                    re.IGNORECASE,
                )

                if next_section:
                    end_idx = start_idx + next_section.start()
                else:
                    end_idx = min(start_idx + 100000, len(text))  # Cap at 100k chars

                section_text = text[start_idx:end_idx].strip()

                # Clean up
                section_text = re.sub(r"\s+", " ", section_text)
                sections[section_name] = section_text

            except Exception as e:
                logger.debug(f"Error extracting {section_name}: {e}")
                continue

        return sections

    def get_filing_sentiment(
        self,
        doc: FilingDocument,
        use_finbert: bool = True,
    ) -> FilingSentiment:
        """
        Analyze sentiment of filing sections.

        Args:
            doc: FilingDocument to analyze
            use_finbert: Whether to use FinBERT (falls back to lexicon)

        Returns:
            FilingSentiment with scores and analysis
        """
        section_sentiments = {}
        word_counts = {}
        key_phrases = []
        risk_indicators = []

        # Negative financial words
        NEGATIVE_WORDS = {
            "risk", "risks", "uncertainty", "uncertain", "adverse", "decline",
            "decrease", "loss", "losses", "fail", "failure", "failed",
            "lawsuit", "litigation", "liability", "liabilities", "impairment",
            "volatility", "volatile", "downturn", "recession", "default",
            "bankruptcy", "restructuring", "layoff", "terminated",
        }

        # Positive financial words
        POSITIVE_WORDS = {
            "growth", "increase", "increased", "profit", "profitable",
            "revenue", "revenues", "opportunity", "opportunities",
            "innovation", "innovative", "expansion", "expand", "success",
            "successful", "improvement", "improved", "strong", "strength",
            "advantage", "advantages", "leading", "leader",
        }

        for section_name, section_text in doc.sections.items():
            if not section_text:
                continue

            words = section_text.lower().split()
            word_counts[section_name] = len(words)

            # Count sentiment words
            neg_count = sum(1 for w in words if w in NEGATIVE_WORDS)
            pos_count = sum(1 for w in words if w in POSITIVE_WORDS)

            total = neg_count + pos_count
            if total > 0:
                sentiment = (pos_count - neg_count) / total
            else:
                sentiment = 0.0

            section_sentiments[section_name] = sentiment

            # Extract risk indicators from risk_factors section
            if section_name == "risk_factors":
                # Find risk-related sentences
                sentences = re.split(r"[.!?]", section_text)
                for sentence in sentences[:100]:  # First 100 sentences
                    if any(w in sentence.lower() for w in ["may", "could", "might", "risk"]):
                        if len(sentence.split()) > 5:  # Meaningful sentence
                            risk_indicators.append(sentence.strip()[:200])

        # Calculate overall sentiment
        if section_sentiments:
            overall = sum(section_sentiments.values()) / len(section_sentiments)
        else:
            overall = 0.0

        return FilingSentiment(
            overall_sentiment=overall,
            section_sentiments=section_sentiments,
            word_counts=word_counts,
            key_phrases=key_phrases[:20],
            risk_indicators=risk_indicators[:20],
            confidence=0.7,  # Lexicon-based confidence
        )

    def compare_filings(
        self,
        current: FilingDocument,
        previous: FilingDocument,
    ) -> FilingComparison:
        """
        Compare two filings to detect changes.

        Args:
            current: Current filing
            previous: Previous filing to compare against

        Returns:
            FilingComparison with detected changes
        """
        new_risks = []
        removed_risks = []
        key_changes = []

        # Compare risk factors
        current_risks = current.sections.get("risk_factors", "")
        previous_risks = previous.sections.get("risk_factors", "")

        # Simple sentence-level comparison
        current_sentences = set(re.split(r"[.!?]", current_risks.lower()))
        previous_sentences = set(re.split(r"[.!?]", previous_risks.lower()))

        # New sentences in current
        for sentence in current_sentences - previous_sentences:
            if len(sentence.split()) > 10:  # Meaningful sentence
                if any(w in sentence for w in ["risk", "may", "could", "adverse"]):
                    new_risks.append(sentence.strip()[:300])

        # Removed sentences
        for sentence in previous_sentences - current_sentences:
            if len(sentence.split()) > 10:
                if any(w in sentence for w in ["risk", "may", "could", "adverse"]):
                    removed_risks.append(sentence.strip()[:300])

        # Sentiment comparison
        current_sentiment = self.get_filing_sentiment(current)
        previous_sentiment = self.get_filing_sentiment(previous)
        sentiment_change = current_sentiment.overall_sentiment - previous_sentiment.overall_sentiment

        # Word count changes
        word_count_change = {}
        for section in current_sentiment.word_counts:
            current_count = current_sentiment.word_counts.get(section, 0)
            previous_count = previous_sentiment.word_counts.get(section, 0)
            if previous_count > 0:
                change = (current_count - previous_count) / previous_count
                word_count_change[section] = change

        # Key changes summary
        if sentiment_change > 0.1:
            key_changes.append(f"Overall sentiment improved by {sentiment_change:.2%}")
        elif sentiment_change < -0.1:
            key_changes.append(f"Overall sentiment declined by {abs(sentiment_change):.2%}")

        if len(new_risks) > 5:
            key_changes.append(f"Added {len(new_risks)} new risk factors")
        if len(removed_risks) > 5:
            key_changes.append(f"Removed {len(removed_risks)} risk factors")

        return FilingComparison(
            current_filing=current.filing,
            previous_filing=previous.filing,
            new_risk_factors=new_risks[:10],
            removed_risk_factors=removed_risks[:10],
            sentiment_change=sentiment_change,
            word_count_change=word_count_change,
            key_changes=key_changes,
        )

    async def get_filing_with_comparison(
        self,
        symbol: str,
        filing_type: str = "10-K",
    ) -> tuple[FilingDocument, Optional[FilingComparison]]:
        """
        Get most recent filing with comparison to previous.

        Args:
            symbol: Ticker symbol
            filing_type: Filing type

        Returns:
            Tuple of (current_doc, comparison)
        """
        filings = await self.get_recent_filings(symbol, filing_type, limit=2)

        if not filings:
            raise ValueError(f"No {filing_type} filings found for {symbol}")

        current_doc = await self.fetch_filing(filings[0])

        comparison = None
        if len(filings) >= 2:
            previous_doc = await self.fetch_filing(filings[1])
            comparison = self.compare_filings(current_doc, previous_doc)

        return current_doc, comparison


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def get_filing_sentiment(symbol: str, filing_type: str = "10-K") -> FilingSentiment:
    """
    Get sentiment of most recent filing for symbol.

    Args:
        symbol: Ticker symbol
        filing_type: Filing type

    Returns:
        FilingSentiment
    """
    scraper = SECFilingScraper()
    try:
        filings = await scraper.get_recent_filings(symbol, filing_type, limit=1)
        if not filings:
            raise ValueError(f"No {filing_type} found for {symbol}")

        doc = await scraper.fetch_filing(filings[0])
        return scraper.get_filing_sentiment(doc)
    finally:
        await scraper.close()


async def get_risk_factor_changes(symbol: str) -> Optional[FilingComparison]:
    """
    Get risk factor changes between last two 10-Ks.

    Args:
        symbol: Ticker symbol

    Returns:
        FilingComparison or None
    """
    scraper = SECFilingScraper()
    try:
        _, comparison = await scraper.get_filing_with_comparison(symbol, "10-K")
        return comparison
    finally:
        await scraper.close()


async def search_filings_for_text(
    symbol: str,
    search_text: str,
    filing_types: list[str] = None,
    limit: int = 5,
) -> list[tuple[Filing, list[str]]]:
    """
    Search filings for specific text.

    Args:
        symbol: Ticker symbol
        search_text: Text to search for
        filing_types: List of filing types to search
        limit: Max filings to search

    Returns:
        List of (Filing, matching_excerpts) tuples
    """
    if filing_types is None:
        filing_types = ["10-K", "10-Q", "8-K"]

    scraper = SECFilingScraper()
    results = []

    try:
        for filing_type in filing_types:
            filings = await scraper.get_recent_filings(symbol, filing_type, limit=limit)

            for filing in filings:
                doc = await scraper.fetch_filing(filing)
                text_lower = doc.full_text.lower()
                search_lower = search_text.lower()

                if search_lower in text_lower:
                    # Find matching excerpts
                    excerpts = []
                    idx = 0
                    while idx < len(text_lower) and len(excerpts) < 5:
                        pos = text_lower.find(search_lower, idx)
                        if pos == -1:
                            break
                        start = max(0, pos - 100)
                        end = min(len(doc.full_text), pos + len(search_text) + 100)
                        excerpts.append(f"...{doc.full_text[start:end]}...")
                        idx = pos + 1

                    if excerpts:
                        results.append((filing, excerpts))

    finally:
        await scraper.close()

    return results
