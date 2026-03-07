"""Thesis Keyword Index — extracts searchable keywords from thesis YAMLs for news matching.

Enables the news pipeline to match headlines to theses without relying on $TICKER format.
Instead, matches on company names, thesis concepts, signpost descriptions, and symbols.

Usage:
    from src.intelligence.thesis_keywords import build_keyword_index, match_headline

    index = build_keyword_index()
    matches = match_headline("Schlumberger wins $2B contract in Guyana", index)
    # → {"00a3a58c": MatchResult(thesis_name="Venezuela Energy Recovery", ...)}
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Symbol → company names/aliases for headline matching
SYMBOL_COMPANY_MAP: dict[str, list[str]] = {
    # Energy / Oilfield Services
    "SLB": ["schlumberger"],
    "HAL": ["halliburton"],
    "BKR": ["baker hughes"],
    "OXY": ["occidental"],
    "XOM": ["exxon"],
    "CVX": ["chevron"],
    "COP": ["conocophillips", "conoco"],
    "PBF": ["pbf energy"],
    "VLO": ["valero"],
    "MPC": ["marathon petroleum"],
    "PSX": ["phillips 66"],
    "DVN": ["devon energy"],
    "FANG": ["diamondback"],
    "EOG": ["eog resources"],
    "PXD": ["pioneer natural"],
    # Tankers
    "FRO": ["frontline"],
    "INSW": ["international seaways"],
    "STNG": ["scorpio tankers"],
    "TNK": ["teekay tankers"],
    "EURN": ["euronav"],
    "DHT": ["dht holdings"],
    # Gold / Mining
    "GLD": ["gold etf", "spdr gold"],
    "GOLD": ["barrick"],
    "NEM": ["newmont"],
    "AEM": ["agnico eagle"],
    "WPM": ["wheaton precious"],
    "FNV": ["franco-nevada"],
    # Defense
    "LMT": ["lockheed"],
    "RTX": ["raytheon"],
    "NOC": ["northrop"],
    "GD": ["general dynamics"],
    "BA": ["boeing"],
    "LHX": ["l3harris"],
    "HII": ["huntington ingalls"],
    # Semiconductors
    "MU": ["micron"],
    "NVDA": ["nvidia"],
    "TSM": ["tsmc", "taiwan semi"],
    "INTC": ["intel"],
    "AMD": ["advanced micro"],
    "QCOM": ["qualcomm"],
    # Tech / Payments
    "COIN": ["coinbase"],
    "V": ["visa"],
    "MA": ["mastercard"],
    "PYPL": ["paypal"],
    "SQ": ["block inc", "square"],
    # Homebuilders
    "LEN": ["lennar"],
    "DHI": ["d.r. horton", "dr horton"],
    "TOL": ["toll brothers"],
    "PHM": ["pultegroup"],
    # Biotech / Pharma
    "LLY": ["eli lilly", "lilly"],
    "NVO": ["novo nordisk"],
    # Nuclear
    "CEG": ["constellation energy"],
    "VST": ["vistra"],
    "LEU": ["centrus"],
    # Fertilizer
    "CF": ["cf industries"],
    "MOS": ["mosaic"],
    "NTR": ["nutrien"],
    # European Defense
    "EUAD": ["european defence"],
    # Cyber
    "PANW": ["palo alto"],
    "CRWD": ["crowdstrike"],
    "FTNT": ["fortinet"],
    # Copper
    "FCX": ["freeport"],
    "SCCO": ["southern copper"],
    "TECK": ["teck resources"],
    # Rare Earth
    "MP": ["mp materials"],
    # Brazil
    "EWZ": ["brazil etf"],
    # Shipping
    "ZIM": ["zim integrated"],
    "GOGL": ["golden ocean"],
    "SBLK": ["star bulk"],
}

# Thesis concept keywords (extracted from common thesis names/summaries)
CONCEPT_KEYWORDS: dict[str, list[str]] = {
    "venezuela": ["venezuela", "maduro", "pdvsa", "ofac", "sanctions relief"],
    "iran": ["iran", "hormuz", "khamenei", "tehran", "persian gulf", "strait of hormuz"],
    "gold": ["gold price", "de-dollarization", "gold etf", "bullion", "precious metals"],
    "defense": ["defense spending", "pentagon", "dod budget", "military", "tomahawk", "nato"],
    "european_defense": ["european defense", "eu defense", "european rearm", "eu rearm"],
    "memory": ["hbm", "high bandwidth memory", "dram", "nand"],
    "ai_power": ["hyperscaler", "data center", "nuclear reactor", "ai infrastructure", "power demand"],
    "shipping": ["tanker", "chokepoint", "red sea", "suez", "freight rate", "rerouting"],
    "fertilizer": ["fertilizer", "urea", "potash", "ammonia", "spring planting", "agflation"],
    "stablecoin": ["stablecoin", "genius act", "usdc", "usdt", "crypto regulation"],
    "copper": ["copper deficit", "copper squeeze", "copper demand"],
    "rare_earth": ["rare earth", "tungsten", "antimony", "critical mineral"],
    "cyber": ["cmmc", "cyber defense", "cybersecurity", "zero trust"],
    "nuclear": ["nuclear", "haleu", "uranium", "smr", "small modular reactor"],
    "homebuilder": ["mortgage rate", "housing start", "homebuilder", "home sales"],
    "glp1": ["glp-1", "ozempic", "wegovy", "orforglipron", "obesity drug"],
    "fed": ["fed independence", "federal reserve", "fomc", "rate cut", "rate hike", "powell"],
    "brazil": ["brazil election", "lula", "bolsonaro", "bovespa"],
    "wildfire": ["wildfire rebuild", "la wildfire", "fire rebuild"],
    "small_cap": ["small cap", "russell 2000", "iwm"],
    "deconsolidation": ["defense deconsolidation", "spinoff", "divestitur"],
    "tax_refund": ["tax refund", "consumer spending", "retail sales"],
}


@dataclass
class ThesisKeywordEntry:
    """A keyword entry linking to a thesis."""
    thesis_id: str
    thesis_name: str
    field_source: str  # "symbol", "company", "concept", "signpost", "invalidation"
    direction: str  # "bullish", "bearish", "neutral"


@dataclass
class MatchResult:
    """Result of matching a headline against thesis keywords."""
    thesis_id: str
    thesis_name: str
    relevance: float  # 0.0-1.0
    matched_keywords: list[str]
    directions: list[str]  # directions from matched entries
    field_sources: list[str]  # where keywords matched


# Cache
_cached_index: dict[str, list[ThesisKeywordEntry]] | None = None
_cached_mtime: float = 0.0


def build_keyword_index(
    theses_dir: Path | None = None,
    force: bool = False,
) -> dict[str, list[ThesisKeywordEntry]]:
    """Build a keyword → thesis mapping from all thesis YAML files.

    Cached with mtime check — rebuilds only when YAML files change.
    """
    global _cached_index, _cached_mtime

    if theses_dir is None:
        theses_dir = Path.home() / "quant_results" / "theses"

    if not theses_dir.exists():
        return {}

    # Check if cache is valid
    latest_mtime = max(
        (f.stat().st_mtime for f in theses_dir.glob("*.yaml")),
        default=0.0,
    )

    if not force and _cached_index is not None and latest_mtime <= _cached_mtime:
        return _cached_index

    index: dict[str, list[ThesisKeywordEntry]] = {}

    for thesis_file in theses_dir.glob("*.yaml"):
        try:
            with open(thesis_file) as f:
                thesis = yaml.safe_load(f)
            if not thesis or thesis.get("status") not in ("active", None):
                continue

            tid = thesis.get("id", thesis_file.stem)
            tname = thesis.get("name", "Unknown")

            _index_thesis(index, tid, tname, thesis)

        except Exception as e:
            logger.debug(f"Error indexing thesis {thesis_file}: {e}")

    _cached_index = index
    _cached_mtime = latest_mtime
    logger.info(f"Built thesis keyword index: {len(index)} keywords from {theses_dir}")
    return index


def _index_thesis(
    index: dict[str, list[ThesisKeywordEntry]],
    tid: str,
    tname: str,
    thesis: dict,
) -> None:
    """Extract keywords from a single thesis and add to index."""

    def _add(keyword: str, field_source: str, direction: str = "neutral"):
        kw = keyword.lower().strip()
        if len(kw) < 3:
            return
        entry = ThesisKeywordEntry(tid, tname, field_source, direction)
        index.setdefault(kw, []).append(entry)

    # Thesis name words (skip common words, require 4+ chars)
    name_stopwords = {
        "the", "and", "for", "with", "from", "into", "that", "this", "are", "was",
        "bull", "bear", "play", "wave", "surge", "rally", "cycle", "super",
    }
    for word in re.split(r'[\s/\-]+', tname):
        word_clean = re.sub(r'[^a-z0-9]', '', word.lower())
        if word_clean and word_clean not in name_stopwords and len(word_clean) >= 4:
            _add(word_clean, "thesis_name")

    # Position symbols and their company names
    for sym in thesis.get("positions", []):
        _add(sym.lower(), "symbol")
        for company_name in SYMBOL_COMPANY_MAP.get(sym, []):
            _add(company_name, "company")

    # Signpost descriptions — extract meaningful phrases
    for signpost in thesis.get("signposts", []):
        desc = signpost.get("description", "")
        if desc:
            # Add whole description as keyword (lowered)
            _add(desc, "signpost", "neutral")
            # Also add significant multi-word chunks
            for chunk in _extract_phrases(desc):
                _add(chunk, "signpost", "neutral")

        # Bullish/bearish conditions
        for key, direction in [("bullish_if", "bullish"), ("bearish_if", "bearish")]:
            condition = signpost.get(key, "")
            if condition:
                for chunk in _extract_phrases(condition):
                    _add(chunk, "signpost", direction)

    # Invalidation triggers
    for trigger in thesis.get("invalidation_triggers", []):
        if isinstance(trigger, str):
            for chunk in _extract_phrases(trigger):
                _add(chunk, "invalidation", "bearish")

    # Match against concept keywords
    tname_lower = tname.lower()
    summary_lower = (thesis.get("summary", "") or "").lower()
    combined = tname_lower + " " + summary_lower

    for concept, keywords in CONCEPT_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            for kw in keywords:
                _add(kw, "concept")


def _extract_phrases(text: str) -> list[str]:
    """Extract meaningful phrases from text for keyword matching.

    Aggressively filters common words to prevent false positives.
    Only keeps domain-specific terms and multi-word phrases.
    """
    phrases = []
    text = re.sub(r'[,;()\[\]]', ' ', text)
    words = text.lower().split()

    # Extended stopwords — includes common financial/news words that are too generic
    stopwords = {
        "the", "and", "for", "with", "from", "into", "that", "this", "are", "was",
        "has", "have", "had", "will", "would", "could", "should", "may", "might",
        "is", "be", "been", "being", "or", "not", "no", "if", "of", "in", "on",
        "at", "to", "by", "an", "a", "it", "its", "but", "as", "do", "does",
        "after", "before", "than", "then", "so", "very", "more", "less", "also",
        "new", "high", "low", "up", "down", "over", "under", "out", "all", "any",
        "first", "last", "next", "year", "month", "day", "time", "market", "stock",
        "price", "rate", "growth", "decline", "increase", "decrease", "level",
        "report", "reports", "data", "major", "clear", "key", "win", "loss",
        "hit", "hits", "drop", "drops", "rise", "rises", "move", "moves",
        "strong", "weak", "big", "small", "good", "bad", "old", "long", "short",
        "back", "full", "set", "run", "top", "end", "per", "two", "three",
        "still", "just", "now", "well", "way", "even", "get", "make", "take",
        "see", "use", "try", "come", "keep", "give", "show", "call", "work",
        "change", "need", "start", "turn", "part", "case", "open", "close",
        "revenue", "profit", "company", "sector", "index", "fund", "share",
        "trading", "trade", "buy", "sell", "hold", "position", "investment",
        "capital", "billion", "million", "percent", "guidance", "expansion",
        "contract", "deal", "announces", "announced", "plan", "plans",
        "earnings", "forecast", "outlook", "quarterly", "annual", "beat",
        "beats", "miss", "misses", "expects", "expected", "target", "estimate",
        "analyst", "analysts", "rating", "ratings", "reiterates", "maintains",
        "keeps", "signals", "shows", "record", "demand", "supply", "surge",
        "surges", "higher", "lower", "rising", "falling", "remains", "sees",
        "stocks", "impact", "global", "gains", "falls", "call", "says",
        "transcript", "quarter", "year-over-year", "above", "below",
        # Months and temporal words (leak through signpost descriptions)
        "january", "february", "march", "april", "june", "july",
        "august", "september", "october", "november", "december",
        "week", "weeks", "months", "years", "daily", "weekly", "monthly",
        "today", "tomorrow", "yesterday", "recent", "current", "prior",
        # Common verbs/adjectives that appear in signpost conditions
        "trump", "about", "concern", "concerns", "concerned",
        "dropped", "drops", "dropping", "continuing", "continued", "continues",
        "additional", "significant", "significantly", "potential", "potentially",
        "confirm", "confirmed", "confirms", "indicate", "indicates", "indicated",
        "suggest", "suggests", "suggested", "support", "supports", "supported",
        "pass", "passed", "passes", "reach", "reaches", "reached",
        "fail", "fails", "failed", "failure", "reduce", "reduced", "reduces",
        "issue", "issues", "issued", "form", "forms", "total", "totals",
        "include", "includes", "included", "likely", "unlikely",
        "push", "pulls", "pushes", "approve", "approved", "approves",
        "delay", "delayed", "delays", "extend", "extends", "extended",
        "halt", "halts", "halted", "pause", "paused", "pauses",
        # Countries/regions too generic on their own (keep in CONCEPT_KEYWORDS instead)
        "india", "europe", "japan", "korea", "canada", "mexico", "asia",
        # Generic financial terms that leak through
        "budget", "policy", "program", "project", "system", "group",
        "world", "south", "north", "east", "west", "state", "states",
        "order", "orders", "ordered", "phase", "stage", "point", "points",
        "cost", "costs", "value", "values", "offer", "offers", "offered",
    }

    # Only keep words >= 4 chars that aren't stopwords (more selective)
    for word in words:
        word = re.sub(r'[^a-z0-9\-]', '', word)
        if word and word not in stopwords and len(word) >= 4:
            phrases.append(word)

    # Bigrams (more valuable — keep 3+ char words)
    for i in range(len(words) - 1):
        w1 = re.sub(r'[^a-z0-9]', '', words[i])
        w2 = re.sub(r'[^a-z0-9]', '', words[i + 1])
        if w1 and w2 and w1 not in stopwords and w2 not in stopwords and len(w1) >= 3 and len(w2) >= 3:
            phrases.append(f"{w1} {w2}")

    return phrases


def match_headline(
    headline: str,
    index: dict[str, list[ThesisKeywordEntry]],
) -> dict[str, MatchResult]:
    """Match a news headline against the thesis keyword index.

    Returns dict of thesis_id → MatchResult for all matching theses.
    """
    headline_lower = headline.lower()
    # Also prepare word set for exact word matching
    headline_words = set(re.findall(r'[a-z0-9]+', headline_lower))

    # Track matches per thesis
    thesis_matches: dict[str, dict] = {}

    for keyword, entries in index.items():
        # Check if keyword appears in headline
        matched = False

        if ' ' in keyword:
            # Multi-word: substring match
            if keyword in headline_lower:
                matched = True
        else:
            # Single word: exact word boundary match (avoid partial matches)
            if keyword in headline_words:
                matched = True

        if not matched:
            continue

        for entry in entries:
            if entry.thesis_id not in thesis_matches:
                thesis_matches[entry.thesis_id] = {
                    "thesis_name": entry.thesis_name,
                    "keywords": [],
                    "directions": [],
                    "field_sources": [],
                }

            m = thesis_matches[entry.thesis_id]
            if keyword not in m["keywords"]:
                m["keywords"].append(keyword)
            if entry.direction not in m["directions"]:
                m["directions"].append(entry.direction)
            if entry.field_source not in m["field_sources"]:
                m["field_sources"].append(entry.field_source)

    # Convert to MatchResults with relevance scoring
    results: dict[str, MatchResult] = {}
    for tid, m in thesis_matches.items():
        # Relevance based on number and type of matches
        score = 0.0
        for src in m["field_sources"]:
            score += {
                "symbol": 0.5,
                "company": 0.4,
                "concept": 0.2,
                "signpost": 0.3,
                "invalidation": 0.3,
                "thesis_name": 0.15,
            }.get(src, 0.1)

        # Bonus for multiple keyword matches
        score += min(len(m["keywords"]) * 0.05, 0.3)

        # Cap at 1.0
        relevance = min(score, 1.0)

        results[tid] = MatchResult(
            thesis_id=tid,
            thesis_name=m["thesis_name"],
            relevance=relevance,
            matched_keywords=m["keywords"],
            directions=m["directions"],
            field_sources=m["field_sources"],
        )

    return results


# ---- Symbol Extraction from Headlines ----

_TICKER_RE = re.compile(r'\$([A-Z]{1,5})\b')
_ALLCAPS_RE = re.compile(r'\b([A-Z]{2,5})\b')

# Common false positives — words that look like tickers but aren't
_TICKER_FALSE_POSITIVES = {
    "CEO", "CFO", "CTO", "COO", "IPO", "SEC", "FDA", "FTC", "DOJ",
    "GDP", "CPI", "PPI", "PMI", "ETF", "NYSE", "FOMC", "OPEC",
    "FBI", "CIA", "NATO", "IMF", "WHO", "CDC", "EPA", "FCC", "IRS",
    "AI", "EV", "US", "UK", "EU", "IT", "HR", "PR", "TV", "AM", "PM",
    "OTC", "PE", "VC", "ESG", "DEI", "ROI", "EPS", "ATH", "OI", "IV",
    "DD", "WSB", "YTD", "QOQ", "MOM", "RSI", "HQ", "DC", "LA", "NY",
    "AND", "THE", "FOR", "NEW", "ALL", "HAS", "ARE", "ITS", "NOT",
    "TOP", "HOW", "WHY", "CAN", "MAY", "GET", "SET", "SAY", "SEE",
    "BUT", "HIS", "HER", "WHO", "OUT", "OLD", "BIG", "CEO", "LLC",
    "INC", "LTD", "PLC", "ETF", "USD", "EUR", "GBP", "JPY", "BPS",
    "GDP", "CPI", "PMI", "ISM", "PCE", "NFP", "API", "CEO", "CFO",
    "DOE", "DOD", "FAQ", "FED", "FYI", "ICE", "IMO", "IPO", "IRA",
    "LED", "MBA", "MBS", "NFT", "OEM", "PSI", "RFP", "ROE", "SOP",
}


def extract_symbols_from_headline(
    headline: str,
    known_symbols: set[str] | None = None,
) -> list[str]:
    """Extract stock ticker symbols from a news headline.

    Recognizes:
    1. $SYMBOL format (high confidence)
    2. ALLCAPS words that match known symbol databases
    3. Company name → symbol reverse lookup from SYMBOL_COMPANY_MAP

    Args:
        headline: News headline text.
        known_symbols: Optional set of valid symbols to filter against.
                       If None, uses SYMBOL_COMPANY_MAP keys.

    Returns:
        List of extracted symbols, deduplicated.
    """
    if not headline:
        return []

    if known_symbols is None:
        known_symbols = set(SYMBOL_COMPANY_MAP.keys())

    found = set()

    # 1. $TICKER pattern (high confidence)
    for match in _TICKER_RE.finditer(headline):
        ticker = match.group(1)
        if ticker not in _TICKER_FALSE_POSITIVES:
            found.add(ticker)

    # 2. ALLCAPS words that match known symbols
    for match in _ALLCAPS_RE.finditer(headline):
        word = match.group(1)
        if word in known_symbols and word not in _TICKER_FALSE_POSITIVES:
            found.add(word)

    # 3. Company name reverse lookup
    headline_lower = headline.lower()
    for symbol, aliases in SYMBOL_COMPANY_MAP.items():
        for alias in aliases:
            if alias in headline_lower:
                found.add(symbol)
                break

    return sorted(found)
