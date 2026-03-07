"""
Finviz Stock Screener Integration

Pre-built stock screens from Finviz.com for finding trading candidates.

Screens include:
- Momentum leaders (strong earnings + technical momentum)
- Volume breakouts (new highs on volume)
- Oversold bounce candidates (low RSI with reversal)
- Earnings winners (post-earnings momentum)
- Insider buying clusters
- Institutional accumulation

Rate limited to 0.5 req/sec to respect Finviz terms.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    import httpx
except ImportError:
    httpx = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

from src.core.paths import paths

logger = logging.getLogger(__name__)


# Finviz screen parameters (v=111 is the screener view)
# These are URL query strings for different screens
SCREEN_DEFINITIONS = {
    "momentum_leaders": {
        "description": "Strong EPS growth with uptrending price",
        "url_params": "v=111&f=fa_epsqoq_o15,ta_perf_dup,ta_sma20_pa&ft=4",
        "priority": 1,
    },
    "volume_breakouts": {
        "description": "New 52-week highs on above-average volume",
        "url_params": "v=111&f=sh_avgvol_o500,ta_change_u5,ta_highlow52w_nh",
        "priority": 1,
    },
    "oversold_bounce": {
        "description": "Oversold stocks with reversal patterns",
        "url_params": "v=111&f=ta_rsi_os30,ta_perf_ddown,ta_pattern_channelup",
        "priority": 2,
    },
    "earnings_winners": {
        "description": "Post-earnings momentum plays",
        "url_params": "v=111&f=earningsdate_prevweek,ta_change_u,fa_epsqoq_o25",
        "priority": 1,
    },
    "insider_buying": {
        "description": "Recent insider buying activity",
        "url_params": "v=111&f=it_latestbuys,sh_avgvol_o100&o=-change",
        "priority": 2,
    },
    "institutional_accumulation": {
        "description": "Increasing institutional ownership",
        "url_params": "v=111&f=sh_instown_o60,sh_insttrans_pos,ta_sma50_pa&o=-change",
        "priority": 2,
    },
    "high_short_squeeze": {
        "description": "High short interest with upward momentum",
        "url_params": "v=111&f=sh_short_o20,ta_perf_dup,sh_avgvol_o500",
        "priority": 2,
    },
    "dividend_growth": {
        "description": "Dividend stocks with growth momentum",
        "url_params": "v=111&f=fa_div_pos,fa_sales5years_o10,ta_sma200_pa",
        "priority": 3,
    },
}


@dataclass
class ScreenResult:
    """Result from a single Finviz screen."""

    screen_name: str
    description: str
    symbols: list[str]
    timestamp: datetime
    priority: int = 1
    symbol_count: int = 0

    def to_dict(self) -> dict:
        return {
            "screen_name": self.screen_name,
            "description": self.description,
            "symbols": self.symbols,
            "timestamp": self.timestamp.isoformat(),
            "priority": self.priority,
            "symbol_count": self.symbol_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ScreenResult":
        return cls(
            screen_name=d["screen_name"],
            description=d["description"],
            symbols=d["symbols"],
            timestamp=datetime.fromisoformat(d["timestamp"]),
            priority=d.get("priority", 1),
            symbol_count=d.get("symbol_count", len(d["symbols"])),
        )


@dataclass
class FinvizScreens:
    """Collection of all screen results."""

    timestamp: datetime
    screens: dict[str, ScreenResult] = field(default_factory=dict)

    # Convenience accessors
    @property
    def momentum_leaders(self) -> list[str]:
        return self.screens.get("momentum_leaders", ScreenResult("", "", [], datetime.now())).symbols

    @property
    def volume_breakouts(self) -> list[str]:
        return self.screens.get("volume_breakouts", ScreenResult("", "", [], datetime.now())).symbols

    @property
    def oversold_bounce(self) -> list[str]:
        return self.screens.get("oversold_bounce", ScreenResult("", "", [], datetime.now())).symbols

    @property
    def earnings_winners(self) -> list[str]:
        return self.screens.get("earnings_winners", ScreenResult("", "", [], datetime.now())).symbols

    @property
    def insider_buying(self) -> list[str]:
        return self.screens.get("insider_buying", ScreenResult("", "", [], datetime.now())).symbols

    @property
    def institutional_accumulation(self) -> list[str]:
        return self.screens.get("institutional_accumulation", ScreenResult("", "", [], datetime.now())).symbols

    def get_all_symbols(self) -> set[str]:
        """Get all unique symbols across all screens."""
        all_symbols = set()
        for screen in self.screens.values():
            all_symbols.update(screen.symbols)
        return all_symbols

    def get_priority_symbols(self, max_priority: int = 2) -> list[str]:
        """Get symbols from high-priority screens only."""
        symbols = []
        for screen in self.screens.values():
            if screen.priority <= max_priority:
                symbols.extend(screen.symbols)
        return list(set(symbols))

    def get_multi_screen_symbols(self, min_screens: int = 2) -> list[str]:
        """Get symbols that appear in multiple screens."""
        from collections import Counter
        all_symbols = []
        for screen in self.screens.values():
            all_symbols.extend(screen.symbols)
        counts = Counter(all_symbols)
        return [sym for sym, count in counts.items() if count >= min_screens]

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "screens": {k: v.to_dict() for k, v in self.screens.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FinvizScreens":
        screens = {k: ScreenResult.from_dict(v) for k, v in d.get("screens", {}).items()}
        return cls(
            timestamp=datetime.fromisoformat(d["timestamp"]),
            screens=screens,
        )


class FinvizScreener:
    """
    Fetch pre-built stock screens from Finviz.

    Uses respectful rate limiting (0.5 req/sec) and caches results.
    """

    name = "finviz_screens"

    BASE_URL = "https://finviz.com/screener.ashx"

    # User agent to appear as a browser
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    def __init__(
        self,
        cache_ttl_hours: int = 4,
        cache_dir: Optional[Path] = None,
        rate_limit_delay: float = 2.0,  # Seconds between requests
    ):
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.cache_dir = cache_dir or (paths.scraped_data / "finviz")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.rate_limit_delay = rate_limit_delay
        self._cache: Optional[tuple[datetime, FinvizScreens]] = None
        self._last_request_time: datetime = datetime.min

    def _check_cache(self) -> Optional[FinvizScreens]:
        """Check if cached data is still valid."""
        # Check in-memory cache first
        if self._cache:
            timestamp, data = self._cache
            if datetime.now() - timestamp < self.cache_ttl:
                logger.debug("Finviz screens cache hit (memory)")
                return data

        # Check file cache
        cache_file = self.cache_dir / "screens_latest.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                screens = FinvizScreens.from_dict(data)
                if datetime.now() - screens.timestamp < self.cache_ttl:
                    logger.debug("Finviz screens cache hit (file)")
                    self._cache = (screens.timestamp, screens)
                    return screens
            except Exception as e:
                logger.warning(f"Failed to load Finviz cache: {e}")

        return None

    def _update_cache(self, data: FinvizScreens) -> None:
        """Update both memory and file cache."""
        self._cache = (datetime.now(), data)

        cache_file = self.cache_dir / "screens_latest.json"
        try:
            with open(cache_file, "w") as f:
                json.dump(data.to_dict(), f, indent=2)
            logger.info(f"Saved Finviz screens to {cache_file}")
        except Exception as e:
            logger.warning(f"Failed to save Finviz cache: {e}")

    async def _wait_for_rate_limit(self) -> None:
        """Wait if needed to respect rate limit."""
        elapsed = (datetime.now() - self._last_request_time).total_seconds()
        if elapsed < self.rate_limit_delay:
            wait_time = self.rate_limit_delay - elapsed
            logger.debug(f"Rate limiting: waiting {wait_time:.1f}s")
            await asyncio.sleep(wait_time)
        self._last_request_time = datetime.now()

    async def _fetch_screen(self, screen_name: str, url_params: str) -> list[str]:
        """Fetch a single screen from Finviz."""
        if httpx is None:
            raise ImportError("httpx required: pip install httpx")
        if BeautifulSoup is None:
            raise ImportError("beautifulsoup4 required: pip install beautifulsoup4")

        await self._wait_for_rate_limit()

        url = f"{self.BASE_URL}?{url_params}"
        symbols = []

        try:
            async with httpx.AsyncClient(headers=self.HEADERS, timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "html.parser")

                # Strategy 1: Find the screener results table inside #screener-content.
                # Finviz nests the actual data table several levels deep within
                # #screener-content. The data rows use valign="top" to distinguish
                # them from header/layout rows.
                screener_content = soup.find(id="screener-content")
                if screener_content:
                    # Data rows in the screener results have valign="top"
                    for row in screener_content.find_all("tr", attrs={"valign": "top"}):
                        cells = row.find_all("td")
                        if len(cells) >= 2:
                            # Column layout: [No., Ticker, Company, Sector, ...]
                            ticker_cell = cells[1]
                            link = ticker_cell.find("a")
                            if link:
                                symbol = link.text.strip()
                                if symbol and 1 <= len(symbol) <= 5 and symbol.isalpha() and symbol.isupper():
                                    symbols.append(symbol)

                # Strategy 2: Try the styled-table-new class (alternative Finviz layout)
                if not symbols:
                    table = soup.find("table", class_="styled-table-new")
                    if table:
                        for row in table.find_all("tr"):
                            cells = row.find_all("td")
                            if len(cells) >= 2:
                                ticker_cell = cells[1]
                                link = ticker_cell.find("a")
                                if link:
                                    symbol = link.text.strip()
                                    if symbol and 1 <= len(symbol) <= 5 and symbol.isalpha() and symbol.isupper():
                                        symbols.append(symbol)

                # Strategy 3: Look for table-light class (older Finviz layout)
                if not symbols:
                    table = soup.find("table", class_="table-light")
                    if table:
                        for row in table.find_all("tr"):
                            cells = row.find_all("td")
                            if len(cells) >= 2:
                                ticker_cell = cells[1]
                                link = ticker_cell.find("a")
                                if link:
                                    symbol = link.text.strip()
                                    if symbol and 1 <= len(symbol) <= 5 and symbol.isalpha() and symbol.isupper():
                                        symbols.append(symbol)

                # Strategy 4 (last resort): Look for quote.ashx links inside
                # table rows with enough columns to be real results (not nav).
                # Finviz results tables have 10+ columns; navigation tables
                # have 1-2 columns with alphabetical ticker links.
                if not symbols and screener_content:
                    for table in screener_content.find_all("table"):
                        rows = table.find_all("tr")
                        if len(rows) < 2:
                            continue
                        # Check if this table has enough columns to be real results
                        sample_cells = rows[1].find_all("td") if len(rows) > 1 else []
                        if len(sample_cells) < 5:
                            continue  # Skip narrow nav tables
                        for row in rows:
                            cells = row.find_all("td")
                            if len(cells) >= 5:
                                link = cells[1].find("a", href=re.compile(r"quote\.ashx\?t="))
                                if link:
                                    symbol = link.text.strip()
                                    if symbol and 1 <= len(symbol) <= 5 and symbol.isalpha() and symbol.isupper():
                                        symbols.append(symbol)

                if not symbols:
                    logger.warning(
                        f"Screen {screen_name}: no symbols found — Finviz HTML "
                        f"structure may have changed. Check selectors."
                    )
                else:
                    logger.info(f"Screen {screen_name}: found {len(symbols)} symbols")

        except httpx.HTTPError as e:
            logger.warning(f"HTTP error fetching {screen_name}: {e}")
        except Exception as e:
            logger.warning(f"Error fetching {screen_name}: {e}")

        return list(dict.fromkeys(symbols))[:50]  # Dedupe preserving order, limit to 50

    async def get_screens(
        self,
        screen_names: Optional[list[str]] = None,
        force_refresh: bool = False,
    ) -> FinvizScreens:
        """
        Get all screen results.

        Args:
            screen_names: Optional list of specific screens to fetch.
                         If None, fetches all defined screens.
            force_refresh: If True, ignores cache and fetches fresh data.

        Returns:
            FinvizScreens object with all results.
        """
        # Check cache unless forced refresh
        if not force_refresh:
            cached = self._check_cache()
            if cached:
                return cached

        screens_to_fetch = screen_names or list(SCREEN_DEFINITIONS.keys())
        results = FinvizScreens(timestamp=datetime.now())

        for screen_name in screens_to_fetch:
            if screen_name not in SCREEN_DEFINITIONS:
                logger.warning(f"Unknown screen: {screen_name}")
                continue

            screen_def = SCREEN_DEFINITIONS[screen_name]

            try:
                symbols = await self._fetch_screen(screen_name, screen_def["url_params"])

                results.screens[screen_name] = ScreenResult(
                    screen_name=screen_name,
                    description=screen_def["description"],
                    symbols=symbols,
                    timestamp=datetime.now(),
                    priority=screen_def["priority"],
                    symbol_count=len(symbols),
                )
            except Exception as e:
                logger.error(f"Failed to fetch screen {screen_name}: {e}")
                # Add empty result on error
                results.screens[screen_name] = ScreenResult(
                    screen_name=screen_name,
                    description=screen_def["description"],
                    symbols=[],
                    timestamp=datetime.now(),
                    priority=screen_def["priority"],
                    symbol_count=0,
                )

        # Update cache
        self._update_cache(results)

        return results

    async def get_candidates(
        self,
        min_priority: int = 2,
        min_screens: int = 1,
    ) -> list[str]:
        """
        Get trading candidates based on screen criteria.

        Args:
            min_priority: Maximum priority level to include (1 = highest)
            min_screens: Minimum number of screens a symbol must appear in

        Returns:
            List of candidate symbols sorted by relevance.
        """
        screens = await self.get_screens()

        if min_screens > 1:
            return screens.get_multi_screen_symbols(min_screens)
        else:
            return screens.get_priority_symbols(min_priority)

    async def close(self) -> None:
        """Cleanup resources."""
        self._cache = None


# Convenience functions
async def get_finviz_screens() -> FinvizScreens:
    """Get current Finviz screen results."""
    screener = FinvizScreener()
    try:
        return await screener.get_screens()
    finally:
        await screener.close()


async def get_screen_candidates(min_priority: int = 2) -> list[str]:
    """Get trading candidates from Finviz screens."""
    screener = FinvizScreener()
    try:
        return await screener.get_candidates(min_priority=min_priority)
    finally:
        await screener.close()


if __name__ == "__main__":
    # Test the screener
    async def main():
        screener = FinvizScreener()

        print("Fetching Finviz screens...")
        screens = await screener.get_screens()

        print(f"\nTimestamp: {screens.timestamp}")
        print(f"Total unique symbols: {len(screens.get_all_symbols())}")

        for name, result in screens.screens.items():
            print(f"\n{name} (priority {result.priority}):")
            print(f"  Description: {result.description}")
            print(f"  Symbols ({result.symbol_count}): {', '.join(result.symbols[:10])}{'...' if len(result.symbols) > 10 else ''}")

        multi = screens.get_multi_screen_symbols(2)
        if multi:
            print(f"\nSymbols in 2+ screens: {', '.join(multi)}")

        await screener.close()

    asyncio.run(main())
