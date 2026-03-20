#!/usr/bin/env python3
"""SEC EDGAR Form 4 insider transaction monitor.

Scans portfolio symbols for insider buy/sell activity directly from SEC filings.
Detects red flags: clustered insider selling near 52-week highs.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from xml.etree import ElementTree

import httpx

from src.core.paths import paths

logger = logging.getLogger(__name__)

SEC_USER_AGENT = "Athena Research athena-research@protonmail.com"
SEC_RATE_LIMIT = 0.15  # 150ms between requests

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


@dataclass
class SECInsiderAlert:
    """Single insider transaction parsed from SEC Form 4."""

    symbol: str
    insider_name: str
    insider_title: str
    transaction_type: str  # "buy" or "sell"
    shares: int
    price_per_share: float
    total_value: float
    filing_date: str
    is_red_flag: bool = False
    red_flag_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "insider_name": self.insider_name,
            "insider_title": self.insider_title,
            "transaction_type": self.transaction_type,
            "shares": self.shares,
            "price_per_share": self.price_per_share,
            "total_value": self.total_value,
            "filing_date": self.filing_date,
            "is_red_flag": self.is_red_flag,
            "red_flag_reason": self.red_flag_reason,
        }


@dataclass
class SECInsiderScanResult:
    """Result of a portfolio-wide SEC insider scan."""

    timestamp: str
    symbols_scanned: int
    transactions_found: int
    red_flags: list[SECInsiderAlert] = field(default_factory=list)
    all_transactions: list[SECInsiderAlert] = field(default_factory=list)
    data_quality: str = "good"

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "symbols_scanned": self.symbols_scanned,
            "transactions_found": self.transactions_found,
            "red_flags": [rf.to_dict() for rf in self.red_flags],
            "all_transactions": [t.to_dict() for t in self.all_transactions],
            "data_quality": self.data_quality,
        }


class SECInsiderMonitor:
    """Monitor SEC EDGAR Form 4 filings for insider transactions.

    Fetches RSS feeds per symbol, parses Form 4 XML for transaction details,
    and detects red flag patterns (clustered selling near highs).
    """

    RSS_URL = (
        "https://www.sec.gov/cgi-bin/browse-edgar"
        "?action=getcompany&CIK={ticker}&type=4&dateb=&owner=include"
        "&count=10&output=atom"
    )

    FORM4_NS = {
        "": "http://www.sec.gov/cgi-bin/viewer?action=view&cik={cik}&type=4",
        "xml": "http://www.w3.org/XML/1998/namespace",
    }

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": SEC_USER_AGENT,
                    "Accept": "application/xml, application/atom+xml, text/xml",
                },
                follow_redirects=True,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def scan_portfolio_symbols(
        self, symbols: list[str]
    ) -> SECInsiderScanResult:
        """Scan a list of symbols for recent insider transactions.

        Args:
            symbols: Ticker symbols to scan.

        Returns:
            SECInsiderScanResult with all transactions and red flags.
        """
        all_transactions: list[SECInsiderAlert] = []
        errors = 0

        for symbol in symbols:
            try:
                txns = await self._fetch_form4_rss(symbol)
                all_transactions.extend(txns)
            except Exception as e:
                logger.warning(f"SEC insider scan failed for {symbol}: {e}")
                errors += 1
            await asyncio.sleep(SEC_RATE_LIMIT)

        red_flags = self.detect_red_flags(all_transactions)
        for rf in red_flags:
            rf.is_red_flag = True

        quality = "good"
        if errors > len(symbols) * 0.5:
            quality = "poor"
        elif errors > 0:
            quality = "partial"

        result = SECInsiderScanResult(
            timestamp=datetime.now().isoformat(),
            symbols_scanned=len(symbols),
            transactions_found=len(all_transactions),
            red_flags=red_flags,
            all_transactions=all_transactions,
            data_quality=quality,
        )

        self._save(result)
        return result

    async def _fetch_form4_rss(self, symbol: str) -> list[SECInsiderAlert]:
        """Fetch Form 4 RSS feed for a symbol and parse filing links.

        For each filing entry, attempts to fetch the actual Form 4 XML
        to extract transaction details (insider, shares, price).
        """
        client = await self._get_client()
        url = self.RSS_URL.format(ticker=symbol)

        resp = await client.get(url)
        if resp.status_code != 200:
            logger.debug(f"SEC RSS returned {resp.status_code} for {symbol}")
            return []

        try:
            root = ElementTree.fromstring(resp.content)
        except ElementTree.ParseError as e:
            logger.debug(f"XML parse error for {symbol} RSS: {e}")
            return []

        entries = root.findall("atom:entry", ATOM_NS)
        transactions: list[SECInsiderAlert] = []

        for entry in entries[:10]:
            title_el = entry.find("atom:title", ATOM_NS)
            updated_el = entry.find("atom:updated", ATOM_NS)
            link_el = entry.find("atom:link", ATOM_NS)

            if title_el is None or updated_el is None:
                continue

            title_text = title_el.text or ""
            filing_date = updated_el.text or ""

            # Extract insider name from title: "4 - Doe, John"
            insider_name = "Unknown"
            if " - " in title_text:
                insider_name = title_text.split(" - ", 1)[-1].strip()

            # Try to get the filing link for detailed XML parsing
            filing_url = None
            if link_el is not None:
                filing_url = link_el.get("href")

            if filing_url:
                await asyncio.sleep(SEC_RATE_LIMIT)
                detail_txns = await self._parse_form4_filing(
                    symbol, filing_url, insider_name, filing_date
                )
                if detail_txns:
                    transactions.extend(detail_txns)
                    continue

            # Fallback: create a basic record from RSS metadata
            transactions.append(
                SECInsiderAlert(
                    symbol=symbol,
                    insider_name=insider_name,
                    insider_title="Officer",
                    transaction_type="unknown",
                    shares=0,
                    price_per_share=0.0,
                    total_value=0.0,
                    filing_date=filing_date[:10] if len(filing_date) >= 10 else filing_date,
                )
            )

        return transactions

    async def _parse_form4_filing(
        self,
        symbol: str,
        filing_url: str,
        fallback_name: str,
        fallback_date: str,
    ) -> list[SECInsiderAlert]:
        """Attempt to parse a Form 4 filing index page to find the XML document.

        SEC filing pages list documents; we look for the primary XML.
        """
        client = await self._get_client()
        transactions: list[SECInsiderAlert] = []

        try:
            # The link from RSS is the filing index page (HTML).
            # We need to find the XML document link within it.
            resp = await client.get(filing_url)
            if resp.status_code != 200:
                return []

            # Look for the primary XML document link in the index page
            content = resp.text
            xml_url = None

            # Pattern: href="/Archives/edgar/data/.../doc4.xml"
            import re

            xml_match = re.search(
                r'href="(/Archives/edgar/data/[^"]+\.xml)"', content
            )
            if xml_match:
                xml_url = f"https://www.sec.gov{xml_match.group(1)}"
            else:
                # Try alternate pattern for direct XML links
                xml_match = re.search(
                    r'href="(https://www\.sec\.gov/Archives/edgar/data/[^"]+\.xml)"',
                    content,
                )
                if xml_match:
                    xml_url = xml_match.group(1)

            if not xml_url:
                return []

            await asyncio.sleep(SEC_RATE_LIMIT)
            xml_resp = await client.get(xml_url)
            if xml_resp.status_code != 200:
                return []

            transactions = self._extract_form4_transactions(
                symbol, xml_resp.content, fallback_name, fallback_date
            )

        except Exception as e:
            logger.debug(f"Form 4 detail parse failed for {symbol}: {e}")

        return transactions

    def _extract_form4_transactions(
        self,
        symbol: str,
        xml_content: bytes,
        fallback_name: str,
        fallback_date: str,
    ) -> list[SECInsiderAlert]:
        """Extract transactions from Form 4 XML content."""
        transactions: list[SECInsiderAlert] = []

        try:
            root = ElementTree.fromstring(xml_content)
        except ElementTree.ParseError:
            return []

        # Extract reporting owner info
        insider_name = fallback_name
        insider_title = "Officer"

        # Form 4 XML uses plain tags (no namespace usually)
        owner_el = root.find(".//reportingOwner")
        if owner_el is not None:
            name_el = owner_el.find(".//rptOwnerName")
            if name_el is not None and name_el.text:
                insider_name = name_el.text.strip()

            title_el = owner_el.find(".//officerTitle")
            if title_el is not None and title_el.text:
                insider_title = title_el.text.strip()

            # Check if director
            is_director_el = owner_el.find(".//isDirector")
            if (
                is_director_el is not None
                and is_director_el.text
                and is_director_el.text.strip() == "1"
                and insider_title == "Officer"
            ):
                insider_title = "Director"

        # Extract non-derivative transactions
        for txn_el in root.findall(".//nonDerivativeTransaction"):
            try:
                shares_el = txn_el.find(
                    ".//transactionAmounts/transactionShares/value"
                )
                price_el = txn_el.find(
                    ".//transactionAmounts/transactionPricePerShare/value"
                )
                code_el = txn_el.find(
                    ".//transactionCoding/transactionCode"
                )
                date_el = txn_el.find(
                    ".//transactionDate/value"
                )

                shares = int(float(shares_el.text)) if shares_el is not None and shares_el.text else 0
                price = float(price_el.text) if price_el is not None and price_el.text else 0.0
                code = code_el.text.strip() if code_el is not None and code_el.text else ""
                txn_date = date_el.text.strip() if date_el is not None and date_el.text else fallback_date[:10]

                # Map transaction code to buy/sell
                if code == "P":
                    txn_type = "buy"
                elif code == "S":
                    txn_type = "sell"
                elif code in ("A", "M", "G", "C", "D"):
                    # Award, exercise, gift, conversion, disposition — skip non-market
                    continue
                else:
                    continue

                transactions.append(
                    SECInsiderAlert(
                        symbol=symbol,
                        insider_name=insider_name,
                        insider_title=insider_title,
                        transaction_type=txn_type,
                        shares=shares,
                        price_per_share=price,
                        total_value=round(shares * price, 2),
                        filing_date=txn_date,
                    )
                )
            except Exception as e:
                logger.debug(f"Error parsing Form 4 transaction: {e}")

        return transactions

    def detect_red_flags(
        self, transactions: list[SECInsiderAlert]
    ) -> list[SECInsiderAlert]:
        """Detect red flag patterns in insider transactions.

        Red flag: 2+ insiders selling the same symbol within 5 days
        while the stock is within 10% of its 52-week high.
        """
        # Group sells by symbol
        sells_by_symbol: dict[str, list[SECInsiderAlert]] = {}
        for txn in transactions:
            if txn.transaction_type == "sell":
                sells_by_symbol.setdefault(txn.symbol, []).append(txn)

        red_flags: list[SECInsiderAlert] = []

        for symbol, sells in sells_by_symbol.items():
            if len(sells) < 2:
                continue

            # Check for clustered selling (2+ unique insiders within 5 days)
            unique_sellers = set()
            dates: list[datetime] = []

            for s in sells:
                unique_sellers.add(s.insider_name)
                try:
                    dt = datetime.strptime(s.filing_date[:10], "%Y-%m-%d")
                    dates.append(dt)
                except (ValueError, IndexError):
                    pass

            if len(unique_sellers) < 2:
                continue

            # Check date clustering
            if dates:
                dates.sort()
                date_span = (dates[-1] - dates[0]).days
                if date_span > 5:
                    continue

            # Check proximity to 52-week high
            near_high = self._check_near_52w_high(symbol)

            if near_high:
                reason = (
                    f"{len(unique_sellers)} insiders sold {symbol} within "
                    f"{date_span if dates else '?'}d while near 52-week high"
                )
                for s in sells:
                    s.is_red_flag = True
                    s.red_flag_reason = reason
                red_flags.extend(sells)
            else:
                # Still flag clustered selling, lower severity
                reason = (
                    f"{len(unique_sellers)} insiders sold {symbol} within "
                    f"{date_span if dates else '?'}d (clustered selling)"
                )
                for s in sells:
                    s.is_red_flag = True
                    s.red_flag_reason = reason
                red_flags.extend(sells)

        return red_flags

    def _check_near_52w_high(self, symbol: str) -> bool:
        """Check if a symbol is within 10% of its 52-week high using yfinance."""
        try:
            import yfinance as yf

            ticker = yf.Ticker(symbol)
            info = ticker.info
            current_price = info.get("currentPrice") or info.get(
                "regularMarketPrice", 0
            )
            high_52w = info.get("fiftyTwoWeekHigh", 0)

            if current_price and high_52w and high_52w > 0:
                pct_from_high = (high_52w - current_price) / high_52w
                return pct_from_high <= 0.10  # Within 10%
        except Exception as e:
            logger.debug(f"yfinance 52w high check failed for {symbol}: {e}")

        return False

    def _save(self, result: SECInsiderScanResult) -> None:
        """Save scan result to disk."""
        out_path = paths.live / "sec_insider_alerts.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(out_path, "w") as f:
                json.dump(result.to_dict(), f, indent=2, default=str)
            logger.info(
                f"Saved SEC insider scan: {result.transactions_found} txns, "
                f"{len(result.red_flags)} red flags -> {out_path}"
            )
        except Exception as e:
            logger.error(f"Failed to save SEC insider alerts: {e}")

    @staticmethod
    def load_latest() -> dict | None:
        """Load the latest saved scan result."""
        path = paths.live / "sec_insider_alerts.json"
        if not path.exists():
            return None
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load SEC insider alerts: {e}")
            return None


async def main():
    """Test SEC insider monitor."""
    monitor = SECInsiderMonitor()
    try:
        result = await monitor.scan_portfolio_symbols(["AAPL", "MSFT", "NVDA"])
        print(json.dumps(result.to_dict(), indent=2))
    finally:
        await monitor.close()


if __name__ == "__main__":
    asyncio.run(main())
