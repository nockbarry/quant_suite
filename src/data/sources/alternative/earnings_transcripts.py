"""
Earnings Transcript Collector — SEC EDGAR 8-K item 2.02 (Results of Operations).

Fetches earnings press releases from SEC EDGAR. Item 2.02 is the canonical
SEC item code for earnings releases. The press release content lives in
the EX-99.1 (and sometimes EX-99.2 for prepared remarks) exhibit attached
to the 8-K filing.

This is v0 of the document signal pipeline — plumbing only, no LLM extraction.
Stores raw exhibit text via TextCorpus.add_earnings_call() for later use.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from src.data.sources.web.sec_filings import SECFilingScraper

logger = logging.getLogger(__name__)


@dataclass
class EarningsContent:
    """An earnings press release fetched from a SEC 8-K item 2.02 filing."""

    symbol: str
    accession_number: str
    filed_date: str          # ISO YYYY-MM-DD
    period: str              # e.g. "Q4 2024" — best-effort inferred
    exhibit_filename: str
    has_transcript: bool
    full_text: str
    prepared_remarks: str
    qa_section: str
    items: str = ""          # raw EDGAR items field, e.g. "2.02,9.01"
    key_metrics: dict = field(default_factory=dict)  # placeholder, populated in later milestones


# Patterns that typically separate prepared remarks from Q&A in transcripts.
# Press-release-only filings usually have neither — prepared_remarks will hold
# the entire text and qa_section will be empty.
_QA_MARKERS = [
    r"\bquestion[- ]and[- ]answer\b",
    r"\bq\s*&\s*a\b",
    r"\bquestions and answers\b",
]

# Earnings-press-release sanity check — the text must mention at least one of these
# to be treated as a real earnings exhibit (filters out cover sheets and noise).
_EARNINGS_KEYWORDS = [
    "revenue", "earnings per share", "eps", "fiscal", "quarter",
    "results", "guidance", "operating income",
]


class EarningsTranscriptCollector:
    """Collects earnings press releases from SEC 8-K item 2.02 filings.

    Reuses SECFilingScraper for CIK lookup and rate-limited fetching, but
    bypasses get_recent_filings() because we need the EDGAR `items` field
    to filter for 2.02-tagged 8-Ks (which the existing scraper does not expose).
    """

    SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
    INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/index.json"
    DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"

    # SEC EDGAR rejects requests without an identifying User-Agent.
    # Format follows project convention used in src/data/sources/alternative/insider.py.
    SEC_HEADERS = {
        "User-Agent": "QuantSuite/1.0 (research@example.com)",
        "Accept-Encoding": "gzip, deflate",
    }

    # Min byte length for an exhibit to be considered substantive content
    # (excludes XBRL stubs, R-htm tables, etc., but keeps real press releases).
    # Note: MSFT puts the press release as a 60-900KB single file; NVDA uses a
    # 25KB cover sheet + multi-hundred-KB press release. Threshold tuned to
    # capture the real content while filtering boilerplate.
    MIN_EXHIBIT_BYTES = 20000
    # Min char length for extracted text to be considered substantive
    MIN_TEXT_CHARS = 1000
    # Cap on number of .htm exhibits to fetch per filing
    MAX_EXHIBITS_PER_FILING = 3

    # CIKs not in the upstream static TICKER_CIK_MAP. The dynamic SEC ticker
    # map fetcher in CIKLookup is currently broken (no SEC-compliant UA),
    # so we patch in the symbols our pipeline cares about.
    EXTRA_CIKS = {
        "MU":   "0000723125",
        "TSM":  "0001046179",
        "AVGO": "0001730168",
        "ASML": "0000937966",
        "LRCX": "0000707549",
        "AMAT": "0000006951",
        "WDC":  "0000106040",
        "ARM":  "0001973239",
        "MRVL": "0001835632",
        "KLAC": "0000319201",
        "ORCL": "0001341439",
    }

    def __init__(self, scraper: Optional[SECFilingScraper] = None):
        self.scraper = scraper or SECFilingScraper()
        self._owns_scraper = scraper is None

    async def close(self) -> None:
        if self._owns_scraper:
            await self.scraper.close()

    async def get_recent_earnings(self, symbol: str, quarters: int = 4) -> list[EarningsContent]:
        """Fetch up to `quarters` most recent earnings press releases for a symbol."""
        cik = self.EXTRA_CIKS.get(symbol.upper()) or await self.scraper.cik_lookup.get_cik(symbol)
        if not cik:
            logger.warning(f"No CIK for {symbol}, skipping")
            return []

        candidates = await self._list_earnings_filings(cik, limit=quarters * 2)
        if not candidates:
            logger.info(f"{symbol}: no item 2.02 8-Ks found in recent submissions")
            return []

        results: list[EarningsContent] = []
        for cand in candidates:
            if len(results) >= quarters:
                break
            try:
                content = await self._fetch_earnings_content(symbol, cik, cand)
                if content and content.has_transcript:
                    results.append(content)
            except Exception as e:
                logger.warning(f"{symbol} {cand['accession_number']}: {e}")
                continue

        logger.info(f"{symbol}: collected {len(results)} earnings exhibits")
        return results

    async def _list_earnings_filings(self, cik: str, limit: int) -> list[dict]:
        """Read EDGAR submissions JSON, return 8-Ks tagged with item 2.02."""
        url = self.SUBMISSIONS_URL.format(cik=cik)
        result = await self.scraper.scraper.fetch(url, headers=self.SEC_HEADERS)
        try:
            data = json.loads(result.content)
        except json.JSONDecodeError as e:
            logger.error(f"Submissions JSON parse failed for CIK {cik}: {e}")
            return []

        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        items_list = recent.get("items", [])
        accessions = recent.get("accessionNumber", [])
        dates = recent.get("filingDate", [])
        primary_docs = recent.get("primaryDocument", [])

        candidates: list[dict] = []
        for i, form in enumerate(forms):
            if form != "8-K":
                continue
            items = items_list[i] if i < len(items_list) else ""
            if "2.02" not in items:
                continue
            try:
                candidates.append({
                    "accession_number": accessions[i],
                    "filed_date": dates[i],
                    "primary_document": primary_docs[i],
                    "items": items,
                })
            except IndexError:
                continue
            if len(candidates) >= limit:
                break
        return candidates

    async def _fetch_earnings_content(
        self,
        symbol: str,
        cik: str,
        candidate: dict,
    ) -> Optional[EarningsContent]:
        """Walk the filing's index.json, locate EX-99.1 (and optionally EX-99.2),
        fetch and concatenate exhibit text."""
        accession_clean = candidate["accession_number"].replace("-", "")
        cik_int = cik.lstrip("0")

        index_url = self.INDEX_URL.format(cik=cik_int, accession=accession_clean)
        index_result = await self.scraper.scraper.fetch(index_url, headers=self.SEC_HEADERS)
        try:
            index = json.loads(index_result.content)
        except json.JSONDecodeError:
            logger.warning(f"Index.json parse failed for {candidate['accession_number']}")
            return None

        items = index.get("directory", {}).get("item", [])
        exhibit_files = self._select_exhibits(items)
        if not exhibit_files:
            logger.debug(f"No EX-99.x found for {candidate['accession_number']}")
            return None

        # Fetch each exhibit and concatenate
        text_parts: list[str] = []
        primary_filename = exhibit_files[0]["name"]
        for ex in exhibit_files:
            doc_url = self.DOC_URL.format(
                cik=cik_int,
                accession=accession_clean,
                document=ex["name"],
            )
            try:
                doc_result = await self.scraper.scraper.fetch(doc_url, headers=self.SEC_HEADERS)
            except Exception as e:
                logger.warning(f"Fetch failed for {doc_url}: {e}")
                continue
            text = self.scraper.scraper.extract_text(doc_result.content)
            if text:
                text_parts.append(text)

        full_text = "\n\n".join(text_parts).strip()

        if len(full_text) < self.MIN_TEXT_CHARS:
            logger.debug(f"Exhibit text too short ({len(full_text)} chars) for {candidate['accession_number']}")
            return None

        if not self._looks_like_earnings(full_text):
            logger.debug(f"Exhibit text does not look like earnings release for {candidate['accession_number']}")
            return None

        prepared, qa = self._split_remarks_and_qa(full_text)
        period = self._infer_period(candidate["filed_date"], full_text)

        return EarningsContent(
            symbol=symbol.upper(),
            accession_number=candidate["accession_number"],
            filed_date=candidate["filed_date"],
            period=period,
            exhibit_filename=primary_filename,
            has_transcript=True,
            full_text=full_text,
            prepared_remarks=prepared,
            qa_section=qa,
            items=candidate["items"],
        )

    # Filename patterns that are SEC infrastructure, not earnings content.
    # Index files, XBRL viewer tables, FilingSummary, R-tables.
    _INFRA_PATTERNS = re.compile(
        r"(?i)("
        r"-?index(-headers)?\.html?$"   # 0001234567-25-...-index.html
        r"|filingsummary\.xml$"
        r"|metalinks\.json$"
        r"|^r\d+\.htm?$"                # R1.htm, R23.htm — XBRL viewer pages
        r"|show\.js$"
        r"|^report\.css$"
        r"|_(htm|cal|def|lab|pre)\.xml$" # XBRL data files
        r"|\.xsd$"
        r")"
    )

    def _select_exhibits(self, index_items: list[dict]) -> list[dict]:
        """Pick the press release exhibit(s) by size.

        Companies vary wildly in how they name earnings exhibits:
            - MSFT:  msft-ex99_1.htm                (903KB single file)
            - NVDA:  q4fy26pr.htm + cfocommentary.htm (394KB + 260KB)
            - GOOGL: goog-20260204.htm + ex99_1.htm (varies)

        Heuristic: take all .htm/.txt files above MIN_EXHIBIT_BYTES,
        excluding SEC infrastructure files, sorted by size descending.
        """
        candidates: list[tuple[int, dict]] = []
        for item in index_items:
            name = item.get("name", "")
            if not name.lower().endswith((".htm", ".html", ".txt")):
                continue
            if self._INFRA_PATTERNS.search(name):
                continue
            try:
                size = int(item.get("size", 0))
            except (TypeError, ValueError):
                continue
            if size < self.MIN_EXHIBIT_BYTES:
                continue
            candidates.append((size, item))

        candidates.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in candidates[: self.MAX_EXHIBITS_PER_FILING]]

    @staticmethod
    def _looks_like_earnings(text: str) -> bool:
        lower = text.lower()
        hits = sum(1 for kw in _EARNINGS_KEYWORDS if kw in lower)
        return hits >= 3

    @staticmethod
    def _split_remarks_and_qa(text: str) -> tuple[str, str]:
        """Split text on the first Q&A marker. If none found, all text is 'prepared'."""
        for pattern in _QA_MARKERS:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                return text[: m.start()].strip(), text[m.start() :].strip()
        return text.strip(), ""

    @staticmethod
    def _infer_period(filed_date: str, text: str) -> str:
        """Best-effort fiscal period inference. Falls back to filed-date quarter."""
        m = re.search(
            r"(?:fiscal\s+)?(?:first|second|third|fourth|q[1-4])\s*(?:quarter\s*)?(?:of\s*)?(20\d{2})",
            text,
            re.IGNORECASE,
        )
        if m:
            quarter_word = m.group(0).lower()
            year = m.group(1)
            for q_label, q_num in [
                ("first", 1), ("q1", 1),
                ("second", 2), ("q2", 2),
                ("third", 3), ("q3", 3),
                ("fourth", 4), ("q4", 4),
            ]:
                if q_label in quarter_word:
                    return f"Q{q_num} {year}"
        # Fallback: derive from filed date (earnings usually report previous quarter)
        try:
            dt = datetime.strptime(filed_date, "%Y-%m-%d")
            month = dt.month
            year = dt.year
            if month <= 3:
                return f"Q4 {year - 1}"
            elif month <= 6:
                return f"Q1 {year}"
            elif month <= 9:
                return f"Q2 {year}"
            else:
                return f"Q3 {year}"
        except ValueError:
            return "unknown"


async def _smoke_test() -> None:
    """Run as a module to smoke-test against MSFT."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    collector = EarningsTranscriptCollector()
    try:
        results = await collector.get_recent_earnings("MSFT", quarters=2)
        for r in results:
            print(f"\n=== {r.symbol} {r.period} ({r.filed_date}) ===")
            print(f"Accession: {r.accession_number}")
            print(f"Exhibit:   {r.exhibit_filename}")
            print(f"Items:     {r.items}")
            print(f"Length:    {len(r.full_text)} chars (prepared={len(r.prepared_remarks)}, qa={len(r.qa_section)})")
            print(f"Sample:    {r.full_text[:300]}...")
    finally:
        await collector.close()


if __name__ == "__main__":
    asyncio.run(_smoke_test())
