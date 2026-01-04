"""
Symbol Universe with Sector Categorization

Provides comprehensive symbol metadata for sector-aware research:
- Sector/Industry classification
- Market cap groupings
- Beta categories (high/low volatility)
- Correlation clusters
- ETF sector proxies

Enables:
- Sector-specific strategy testing
- Cross-sector pattern validation
- Universe screening for experiments
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Sector(Enum):
    """Standard GICS sectors."""
    TECHNOLOGY = "technology"
    HEALTHCARE = "healthcare"
    FINANCIALS = "financials"
    CONSUMER_DISCRETIONARY = "consumer_discretionary"
    CONSUMER_STAPLES = "consumer_staples"
    INDUSTRIALS = "industrials"
    ENERGY = "energy"
    MATERIALS = "materials"
    UTILITIES = "utilities"
    REAL_ESTATE = "real_estate"
    COMMUNICATION = "communication"
    ETF = "etf"
    CRYPTO = "crypto"


class Industry(Enum):
    """Industry sub-classifications."""
    # Technology
    SEMICONDUCTORS = "semiconductors"
    SOFTWARE = "software"
    CLOUD = "cloud"
    HARDWARE = "hardware"
    CYBERSECURITY = "cybersecurity"

    # Healthcare
    BIOTECH = "biotech"
    PHARMA = "pharma"
    MEDICAL_DEVICES = "medical_devices"

    # Financials
    BANKS = "banks"
    INVESTMENT_BANKS = "investment_banks"
    INSURANCE = "insurance"
    PAYMENTS = "payments"

    # Consumer
    E_COMMERCE = "e_commerce"
    RETAIL = "retail"
    AUTOMOTIVE = "automotive"
    ENTERTAINMENT = "entertainment"
    RESTAURANTS = "restaurants"

    # ETF Types
    BROAD_MARKET = "broad_market"
    SECTOR_ETF = "sector_etf"
    VOLATILITY = "volatility"
    BOND = "bond"
    COMMODITY = "commodity"

    # Other
    DIVERSIFIED = "diversified"
    UNKNOWN = "unknown"


class MarketCap(Enum):
    """Market cap categories."""
    MEGA = "mega"        # > $200B
    LARGE = "large"      # $10B - $200B
    MID = "mid"          # $2B - $10B
    SMALL = "small"      # $300M - $2B
    MICRO = "micro"      # < $300M


class VolatilityProfile(Enum):
    """Volatility categories."""
    HIGH = "high"        # Beta > 1.3
    MEDIUM = "medium"    # Beta 0.8 - 1.3
    LOW = "low"          # Beta < 0.8
    INVERSE = "inverse"  # Negative beta (hedges)


@dataclass
class SymbolMetadata:
    """Comprehensive symbol metadata."""
    symbol: str
    name: str
    sector: Sector
    industry: Industry
    market_cap: MarketCap
    volatility: VolatilityProfile
    beta: float = 1.0
    avg_volume: int = 0
    is_etf: bool = False
    correlation_cluster: str = ""
    tags: list[str] = field(default_factory=list)


# =============================================================================
# SYMBOL DATABASE
# =============================================================================

SYMBOL_DATABASE: dict[str, SymbolMetadata] = {
    # -----------------------------------------------------
    # TECHNOLOGY - Mega Cap
    # -----------------------------------------------------
    "AAPL": SymbolMetadata(
        symbol="AAPL", name="Apple Inc.",
        sector=Sector.TECHNOLOGY, industry=Industry.HARDWARE,
        market_cap=MarketCap.MEGA, volatility=VolatilityProfile.MEDIUM,
        beta=1.2, correlation_cluster="tech_mega",
        tags=["faang", "dividend", "buyback"],
    ),
    "MSFT": SymbolMetadata(
        symbol="MSFT", name="Microsoft Corp.",
        sector=Sector.TECHNOLOGY, industry=Industry.SOFTWARE,
        market_cap=MarketCap.MEGA, volatility=VolatilityProfile.MEDIUM,
        beta=1.1, correlation_cluster="tech_mega",
        tags=["faang", "cloud", "dividend"],
    ),
    "GOOGL": SymbolMetadata(
        symbol="GOOGL", name="Alphabet Inc.",
        sector=Sector.COMMUNICATION, industry=Industry.SOFTWARE,
        market_cap=MarketCap.MEGA, volatility=VolatilityProfile.MEDIUM,
        beta=1.15, correlation_cluster="tech_mega",
        tags=["faang", "ai", "advertising"],
    ),
    "AMZN": SymbolMetadata(
        symbol="AMZN", name="Amazon.com Inc.",
        sector=Sector.CONSUMER_DISCRETIONARY, industry=Industry.E_COMMERCE,
        market_cap=MarketCap.MEGA, volatility=VolatilityProfile.HIGH,
        beta=1.3, correlation_cluster="tech_mega",
        tags=["faang", "cloud", "retail"],
    ),
    "META": SymbolMetadata(
        symbol="META", name="Meta Platforms Inc.",
        sector=Sector.COMMUNICATION, industry=Industry.SOFTWARE,
        market_cap=MarketCap.MEGA, volatility=VolatilityProfile.HIGH,
        beta=1.4, correlation_cluster="tech_mega",
        tags=["faang", "ai", "metaverse"],
    ),
    "NVDA": SymbolMetadata(
        symbol="NVDA", name="NVIDIA Corp.",
        sector=Sector.TECHNOLOGY, industry=Industry.SEMICONDUCTORS,
        market_cap=MarketCap.MEGA, volatility=VolatilityProfile.HIGH,
        beta=1.8, correlation_cluster="semiconductors",
        tags=["ai", "datacenter", "gaming"],
    ),
    "TSLA": SymbolMetadata(
        symbol="TSLA", name="Tesla Inc.",
        sector=Sector.CONSUMER_DISCRETIONARY, industry=Industry.AUTOMOTIVE,
        market_cap=MarketCap.MEGA, volatility=VolatilityProfile.HIGH,
        beta=2.0, correlation_cluster="ev",
        tags=["ev", "energy", "high_vol"],
    ),

    # -----------------------------------------------------
    # TECHNOLOGY - Semiconductors
    # -----------------------------------------------------
    "AMD": SymbolMetadata(
        symbol="AMD", name="Advanced Micro Devices",
        sector=Sector.TECHNOLOGY, industry=Industry.SEMICONDUCTORS,
        market_cap=MarketCap.LARGE, volatility=VolatilityProfile.HIGH,
        beta=1.7, correlation_cluster="semiconductors",
        tags=["ai", "datacenter", "gaming"],
    ),
    "AVGO": SymbolMetadata(
        symbol="AVGO", name="Broadcom Inc.",
        sector=Sector.TECHNOLOGY, industry=Industry.SEMICONDUCTORS,
        market_cap=MarketCap.MEGA, volatility=VolatilityProfile.MEDIUM,
        beta=1.2, correlation_cluster="semiconductors",
        tags=["infrastructure", "dividend"],
    ),
    "QCOM": SymbolMetadata(
        symbol="QCOM", name="Qualcomm Inc.",
        sector=Sector.TECHNOLOGY, industry=Industry.SEMICONDUCTORS,
        market_cap=MarketCap.LARGE, volatility=VolatilityProfile.MEDIUM,
        beta=1.3, correlation_cluster="semiconductors",
        tags=["mobile", "5g", "dividend"],
    ),
    "MU": SymbolMetadata(
        symbol="MU", name="Micron Technology",
        sector=Sector.TECHNOLOGY, industry=Industry.SEMICONDUCTORS,
        market_cap=MarketCap.LARGE, volatility=VolatilityProfile.HIGH,
        beta=1.5, correlation_cluster="semiconductors",
        tags=["memory", "cyclical"],
    ),
    "MRVL": SymbolMetadata(
        symbol="MRVL", name="Marvell Technology",
        sector=Sector.TECHNOLOGY, industry=Industry.SEMICONDUCTORS,
        market_cap=MarketCap.LARGE, volatility=VolatilityProfile.HIGH,
        beta=1.6, correlation_cluster="semiconductors",
        tags=["infrastructure", "datacenter"],
    ),
    "INTC": SymbolMetadata(
        symbol="INTC", name="Intel Corp.",
        sector=Sector.TECHNOLOGY, industry=Industry.SEMICONDUCTORS,
        market_cap=MarketCap.LARGE, volatility=VolatilityProfile.MEDIUM,
        beta=1.0, correlation_cluster="semiconductors",
        tags=["legacy", "dividend", "turnaround"],
    ),

    # -----------------------------------------------------
    # TECHNOLOGY - Software & Cloud
    # -----------------------------------------------------
    "CRM": SymbolMetadata(
        symbol="CRM", name="Salesforce Inc.",
        sector=Sector.TECHNOLOGY, industry=Industry.CLOUD,
        market_cap=MarketCap.LARGE, volatility=VolatilityProfile.MEDIUM,
        beta=1.2, correlation_cluster="saas",
        tags=["saas", "ai"],
    ),
    "ADBE": SymbolMetadata(
        symbol="ADBE", name="Adobe Inc.",
        sector=Sector.TECHNOLOGY, industry=Industry.SOFTWARE,
        market_cap=MarketCap.LARGE, volatility=VolatilityProfile.MEDIUM,
        beta=1.2, correlation_cluster="saas",
        tags=["saas", "creative", "ai"],
    ),
    "NOW": SymbolMetadata(
        symbol="NOW", name="ServiceNow Inc.",
        sector=Sector.TECHNOLOGY, industry=Industry.CLOUD,
        market_cap=MarketCap.LARGE, volatility=VolatilityProfile.MEDIUM,
        beta=1.3, correlation_cluster="saas",
        tags=["saas", "enterprise"],
    ),
    "CRWD": SymbolMetadata(
        symbol="CRWD", name="CrowdStrike Holdings",
        sector=Sector.TECHNOLOGY, industry=Industry.CYBERSECURITY,
        market_cap=MarketCap.LARGE, volatility=VolatilityProfile.HIGH,
        beta=1.5, correlation_cluster="cybersecurity",
        tags=["cybersecurity", "saas", "growth"],
    ),
    "NET": SymbolMetadata(
        symbol="NET", name="Cloudflare Inc.",
        sector=Sector.TECHNOLOGY, industry=Industry.CLOUD,
        market_cap=MarketCap.MID, volatility=VolatilityProfile.HIGH,
        beta=1.7, correlation_cluster="cloud_growth",
        tags=["cloud", "security", "growth"],
    ),
    "PLTR": SymbolMetadata(
        symbol="PLTR", name="Palantir Technologies",
        sector=Sector.TECHNOLOGY, industry=Industry.SOFTWARE,
        market_cap=MarketCap.MID, volatility=VolatilityProfile.HIGH,
        beta=1.8, correlation_cluster="ai",
        tags=["ai", "government", "data"],
    ),

    # -----------------------------------------------------
    # FINANCIALS
    # -----------------------------------------------------
    "JPM": SymbolMetadata(
        symbol="JPM", name="JPMorgan Chase",
        sector=Sector.FINANCIALS, industry=Industry.BANKS,
        market_cap=MarketCap.MEGA, volatility=VolatilityProfile.MEDIUM,
        beta=1.1, correlation_cluster="banks",
        tags=["dividend", "quality"],
    ),
    "GS": SymbolMetadata(
        symbol="GS", name="Goldman Sachs",
        sector=Sector.FINANCIALS, industry=Industry.INVESTMENT_BANKS,
        market_cap=MarketCap.LARGE, volatility=VolatilityProfile.HIGH,
        beta=1.3, correlation_cluster="investment_banks",
        tags=["trading", "dividend"],
    ),
    "V": SymbolMetadata(
        symbol="V", name="Visa Inc.",
        sector=Sector.FINANCIALS, industry=Industry.PAYMENTS,
        market_cap=MarketCap.MEGA, volatility=VolatilityProfile.LOW,
        beta=0.9, correlation_cluster="payments",
        tags=["quality", "growth", "dividend"],
    ),
    "MA": SymbolMetadata(
        symbol="MA", name="Mastercard Inc.",
        sector=Sector.FINANCIALS, industry=Industry.PAYMENTS,
        market_cap=MarketCap.MEGA, volatility=VolatilityProfile.LOW,
        beta=0.95, correlation_cluster="payments",
        tags=["quality", "growth", "dividend"],
    ),

    # -----------------------------------------------------
    # HEALTHCARE
    # -----------------------------------------------------
    "UNH": SymbolMetadata(
        symbol="UNH", name="UnitedHealth Group",
        sector=Sector.HEALTHCARE, industry=Industry.DIVERSIFIED,
        market_cap=MarketCap.MEGA, volatility=VolatilityProfile.LOW,
        beta=0.7, correlation_cluster="healthcare_mega",
        tags=["defensive", "dividend"],
    ),
    "JNJ": SymbolMetadata(
        symbol="JNJ", name="Johnson & Johnson",
        sector=Sector.HEALTHCARE, industry=Industry.DIVERSIFIED,
        market_cap=MarketCap.MEGA, volatility=VolatilityProfile.LOW,
        beta=0.6, correlation_cluster="healthcare_mega",
        tags=["defensive", "dividend", "pharma"],
    ),
    "LLY": SymbolMetadata(
        symbol="LLY", name="Eli Lilly",
        sector=Sector.HEALTHCARE, industry=Industry.PHARMA,
        market_cap=MarketCap.MEGA, volatility=VolatilityProfile.MEDIUM,
        beta=0.8, correlation_cluster="pharma",
        tags=["glp1", "weight_loss", "growth"],
    ),
    "MRNA": SymbolMetadata(
        symbol="MRNA", name="Moderna Inc.",
        sector=Sector.HEALTHCARE, industry=Industry.BIOTECH,
        market_cap=MarketCap.LARGE, volatility=VolatilityProfile.HIGH,
        beta=1.6, correlation_cluster="biotech",
        tags=["mrna", "vaccines", "high_vol"],
    ),

    # -----------------------------------------------------
    # CONSUMER
    # -----------------------------------------------------
    "WMT": SymbolMetadata(
        symbol="WMT", name="Walmart Inc.",
        sector=Sector.CONSUMER_STAPLES, industry=Industry.RETAIL,
        market_cap=MarketCap.MEGA, volatility=VolatilityProfile.LOW,
        beta=0.5, correlation_cluster="retail",
        tags=["defensive", "dividend"],
    ),
    "COST": SymbolMetadata(
        symbol="COST", name="Costco Wholesale",
        sector=Sector.CONSUMER_STAPLES, industry=Industry.RETAIL,
        market_cap=MarketCap.MEGA, volatility=VolatilityProfile.LOW,
        beta=0.7, correlation_cluster="retail",
        tags=["quality", "membership"],
    ),
    "HD": SymbolMetadata(
        symbol="HD", name="Home Depot",
        sector=Sector.CONSUMER_DISCRETIONARY, industry=Industry.RETAIL,
        market_cap=MarketCap.MEGA, volatility=VolatilityProfile.MEDIUM,
        beta=1.0, correlation_cluster="home_improvement",
        tags=["housing", "dividend"],
    ),
    "NFLX": SymbolMetadata(
        symbol="NFLX", name="Netflix Inc.",
        sector=Sector.COMMUNICATION, industry=Industry.ENTERTAINMENT,
        market_cap=MarketCap.LARGE, volatility=VolatilityProfile.HIGH,
        beta=1.4, correlation_cluster="streaming",
        tags=["streaming", "faang"],
    ),
    "DIS": SymbolMetadata(
        symbol="DIS", name="Walt Disney",
        sector=Sector.COMMUNICATION, industry=Industry.ENTERTAINMENT,
        market_cap=MarketCap.LARGE, volatility=VolatilityProfile.MEDIUM,
        beta=1.1, correlation_cluster="entertainment",
        tags=["streaming", "parks", "content"],
    ),

    # -----------------------------------------------------
    # ENERGY
    # -----------------------------------------------------
    "XOM": SymbolMetadata(
        symbol="XOM", name="Exxon Mobil",
        sector=Sector.ENERGY, industry=Industry.DIVERSIFIED,
        market_cap=MarketCap.MEGA, volatility=VolatilityProfile.HIGH,
        beta=1.4, correlation_cluster="oil_majors",
        tags=["oil", "dividend", "value"],
    ),
    "CVX": SymbolMetadata(
        symbol="CVX", name="Chevron Corp.",
        sector=Sector.ENERGY, industry=Industry.DIVERSIFIED,
        market_cap=MarketCap.MEGA, volatility=VolatilityProfile.HIGH,
        beta=1.3, correlation_cluster="oil_majors",
        tags=["oil", "dividend", "value"],
    ),

    # -----------------------------------------------------
    # ETFs - Broad Market
    # -----------------------------------------------------
    "SPY": SymbolMetadata(
        symbol="SPY", name="S&P 500 ETF",
        sector=Sector.ETF, industry=Industry.BROAD_MARKET,
        market_cap=MarketCap.MEGA, volatility=VolatilityProfile.MEDIUM,
        beta=1.0, is_etf=True, correlation_cluster="market",
        tags=["benchmark", "sp500", "large_cap"],
    ),
    "QQQ": SymbolMetadata(
        symbol="QQQ", name="Nasdaq-100 ETF",
        sector=Sector.ETF, industry=Industry.BROAD_MARKET,
        market_cap=MarketCap.MEGA, volatility=VolatilityProfile.HIGH,
        beta=1.1, is_etf=True, correlation_cluster="tech_market",
        tags=["benchmark", "nasdaq", "tech"],
    ),
    "IWM": SymbolMetadata(
        symbol="IWM", name="Russell 2000 ETF",
        sector=Sector.ETF, industry=Industry.BROAD_MARKET,
        market_cap=MarketCap.LARGE, volatility=VolatilityProfile.HIGH,
        beta=1.2, is_etf=True, correlation_cluster="small_cap",
        tags=["benchmark", "small_cap"],
    ),
    "DIA": SymbolMetadata(
        symbol="DIA", name="Dow Jones ETF",
        sector=Sector.ETF, industry=Industry.BROAD_MARKET,
        market_cap=MarketCap.LARGE, volatility=VolatilityProfile.LOW,
        beta=0.9, is_etf=True, correlation_cluster="market",
        tags=["benchmark", "dow", "value"],
    ),

    # -----------------------------------------------------
    # ETFs - Sector
    # -----------------------------------------------------
    "XLK": SymbolMetadata(
        symbol="XLK", name="Technology Sector ETF",
        sector=Sector.ETF, industry=Industry.SECTOR_ETF,
        market_cap=MarketCap.LARGE, volatility=VolatilityProfile.MEDIUM,
        beta=1.1, is_etf=True, correlation_cluster="tech_market",
        tags=["sector", "technology"],
    ),
    "XLF": SymbolMetadata(
        symbol="XLF", name="Financials Sector ETF",
        sector=Sector.ETF, industry=Industry.SECTOR_ETF,
        market_cap=MarketCap.LARGE, volatility=VolatilityProfile.MEDIUM,
        beta=1.1, is_etf=True, correlation_cluster="financials",
        tags=["sector", "financials"],
    ),
    "XLE": SymbolMetadata(
        symbol="XLE", name="Energy Sector ETF",
        sector=Sector.ETF, industry=Industry.SECTOR_ETF,
        market_cap=MarketCap.LARGE, volatility=VolatilityProfile.HIGH,
        beta=1.4, is_etf=True, correlation_cluster="energy",
        tags=["sector", "energy", "oil"],
    ),
    "XLV": SymbolMetadata(
        symbol="XLV", name="Healthcare Sector ETF",
        sector=Sector.ETF, industry=Industry.SECTOR_ETF,
        market_cap=MarketCap.LARGE, volatility=VolatilityProfile.LOW,
        beta=0.7, is_etf=True, correlation_cluster="healthcare",
        tags=["sector", "healthcare", "defensive"],
    ),

    # -----------------------------------------------------
    # ETFs - Other
    # -----------------------------------------------------
    "TLT": SymbolMetadata(
        symbol="TLT", name="20+ Year Treasury ETF",
        sector=Sector.ETF, industry=Industry.BOND,
        market_cap=MarketCap.LARGE, volatility=VolatilityProfile.MEDIUM,
        beta=-0.3, is_etf=True, correlation_cluster="bonds",
        tags=["bonds", "rates", "hedge"],
    ),
    "GLD": SymbolMetadata(
        symbol="GLD", name="Gold ETF",
        sector=Sector.ETF, industry=Industry.COMMODITY,
        market_cap=MarketCap.LARGE, volatility=VolatilityProfile.MEDIUM,
        beta=0.0, is_etf=True, correlation_cluster="commodities",
        tags=["gold", "safe_haven", "hedge"],
    ),
    "VIX": SymbolMetadata(
        symbol="^VIX", name="VIX Volatility Index",
        sector=Sector.ETF, industry=Industry.VOLATILITY,
        market_cap=MarketCap.LARGE, volatility=VolatilityProfile.HIGH,
        beta=-3.0, is_etf=True, correlation_cluster="volatility",
        tags=["volatility", "fear", "hedge"],
    ),
}


# =============================================================================
# UNIVERSE MANAGEMENT
# =============================================================================

class SymbolUniverse:
    """
    Manages symbol universe with sector-aware filtering.

    Usage:
        universe = SymbolUniverse()

        # Get all tech symbols
        tech = universe.get_by_sector(Sector.TECHNOLOGY)

        # Get high volatility semiconductors
        high_vol_semis = universe.get_by_filters(
            sector=Sector.TECHNOLOGY,
            industry=Industry.SEMICONDUCTORS,
            volatility=VolatilityProfile.HIGH
        )

        # Get correlation clusters
        clusters = universe.get_correlation_clusters()
    """

    def __init__(self, symbols: dict[str, SymbolMetadata] | None = None):
        self.symbols = symbols or SYMBOL_DATABASE

    def get_all(self) -> list[str]:
        """Get all symbols."""
        return list(self.symbols.keys())

    def get_metadata(self, symbol: str) -> SymbolMetadata | None:
        """Get metadata for a symbol."""
        return self.symbols.get(symbol)

    def get_by_sector(self, sector: Sector) -> list[str]:
        """Get symbols in a sector."""
        return [s for s, m in self.symbols.items() if m.sector == sector]

    def get_by_industry(self, industry: Industry) -> list[str]:
        """Get symbols in an industry."""
        return [s for s, m in self.symbols.items() if m.industry == industry]

    def get_by_volatility(self, volatility: VolatilityProfile) -> list[str]:
        """Get symbols by volatility profile."""
        return [s for s, m in self.symbols.items() if m.volatility == volatility]

    def get_by_market_cap(self, cap: MarketCap) -> list[str]:
        """Get symbols by market cap."""
        return [s for s, m in self.symbols.items() if m.market_cap == cap]

    def get_by_tag(self, tag: str) -> list[str]:
        """Get symbols with a specific tag."""
        return [s for s, m in self.symbols.items() if tag in m.tags]

    def get_etfs(self) -> list[str]:
        """Get all ETF symbols."""
        return [s for s, m in self.symbols.items() if m.is_etf]

    def get_stocks(self) -> list[str]:
        """Get all stock symbols (non-ETF)."""
        return [s for s, m in self.symbols.items() if not m.is_etf]

    def get_by_filters(
        self,
        sector: Sector | None = None,
        industry: Industry | None = None,
        volatility: VolatilityProfile | None = None,
        market_cap: MarketCap | None = None,
        is_etf: bool | None = None,
        tags: list[str] | None = None,
    ) -> list[str]:
        """Get symbols matching multiple filters."""
        result = []
        for symbol, meta in self.symbols.items():
            if sector and meta.sector != sector:
                continue
            if industry and meta.industry != industry:
                continue
            if volatility and meta.volatility != volatility:
                continue
            if market_cap and meta.market_cap != market_cap:
                continue
            if is_etf is not None and meta.is_etf != is_etf:
                continue
            if tags and not all(t in meta.tags for t in tags):
                continue
            result.append(symbol)
        return result

    def get_correlation_clusters(self) -> dict[str, list[str]]:
        """Get symbols grouped by correlation cluster."""
        clusters: dict[str, list[str]] = {}
        for symbol, meta in self.symbols.items():
            cluster = meta.correlation_cluster
            if cluster:
                if cluster not in clusters:
                    clusters[cluster] = []
                clusters[cluster].append(symbol)
        return clusters

    def get_sector_summary(self) -> dict[str, int]:
        """Get count of symbols by sector."""
        summary: dict[str, int] = {}
        for meta in self.symbols.values():
            sector = meta.sector.value
            summary[sector] = summary.get(sector, 0) + 1
        return summary

    def get_research_universes(self) -> dict[str, list[str]]:
        """
        Get predefined universes for research.

        Returns different universes for specific research goals.
        """
        return {
            # Broad market testing
            "market_etfs": ["SPY", "QQQ", "IWM", "DIA"],

            # Sector ETFs for cross-sector analysis
            "sector_etfs": ["XLK", "XLF", "XLE", "XLV"],

            # High volatility for mean reversion/breakout
            "high_volatility": self.get_by_volatility(VolatilityProfile.HIGH)[:10],

            # Low volatility for trend following
            "low_volatility": self.get_by_volatility(VolatilityProfile.LOW),

            # Tech mega caps
            "tech_mega": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA"],

            # Semiconductors
            "semiconductors": self.get_by_industry(Industry.SEMICONDUCTORS),

            # AI plays
            "ai_focused": self.get_by_tag("ai"),

            # Defensive
            "defensive": self.get_by_tag("defensive"),

            # High growth
            "growth": self.get_by_tag("growth"),

            # FAANG+
            "faang_plus": self.get_by_tag("faang") + ["NVDA", "TSLA"],

            # Value plays
            "value": self.get_by_tag("value"),

            # Dividend payers
            "dividend": self.get_by_tag("dividend"),

            # Full stock universe
            "all_stocks": self.get_stocks(),

            # Full universe
            "all": self.get_all(),
        }


# =============================================================================
# SECTOR-BASED HYPOTHESIS TEMPLATES
# =============================================================================

# Map sectors to strategies that historically work well.
SECTOR_STRATEGY_AFFINITY = {
    Sector.TECHNOLOGY: [
        "momentum",          # Tech tends to trend
        "breakout",          # News-driven breakouts
        "insider_momentum",  # Insider buying signals
    ],
    Sector.FINANCIALS: [
        "mean_reversion",    # Rate-sensitive reversals
        "rsi_reversal",      # Oversold bounces
        "correlation",       # Interbank correlation
    ],
    Sector.HEALTHCARE: [
        "volatility_breakout",  # Biotech events
        "bollinger_reversal",   # Mean reversion
    ],
    Sector.ENERGY: [
        "momentum",          # Commodity-driven trends
        "breakout",          # Oil price breakouts
        "correlation",       # Cross-commodity
    ],
    Sector.CONSUMER_DISCRETIONARY: [
        "momentum",          # Consumer trends
        "sentiment_momentum",  # Consumer sentiment
    ],
    Sector.CONSUMER_STAPLES: [
        "mean_reversion",    # Low vol, mean revert
        "dividend",          # Income strategies
    ],
    Sector.ETF: [
        "momentum",          # Trend following
        "mean_reversion",    # Sector rotation
        "correlation",       # Cross-ETF
        "breakout",          # Range breakouts
    ],
}


def get_strategy_suggestions_for_symbol(symbol: str) -> list[str]:
    """Get suggested strategies for a symbol based on its sector."""
    universe = SymbolUniverse()
    meta = universe.get_metadata(symbol)
    if not meta:
        return ["momentum", "rsi_reversal", "breakout"]

    sector_strategies = SECTOR_STRATEGY_AFFINITY.get(meta.sector, [])

    # Add volatility-specific strategies
    if meta.volatility == VolatilityProfile.HIGH:
        sector_strategies.extend(["volatility_breakout", "bollinger_reversal"])
    elif meta.volatility == VolatilityProfile.LOW:
        sector_strategies.extend(["mean_reversion", "sma_crossover"])

    return list(set(sector_strategies))


def get_cross_sector_pairs() -> list[tuple[str, str]]:
    """Get interesting cross-sector pairs for correlation analysis."""
    return [
        ("SPY", "TLT"),   # Stocks vs Bonds
        ("SPY", "GLD"),   # Stocks vs Gold
        ("QQQ", "IWM"),   # Growth vs Value/Small
        ("XLK", "XLF"),   # Tech vs Financials
        ("XLE", "XLK"),   # Energy vs Tech
        ("SPY", "^VIX"),  # Market vs Fear
        ("NVDA", "AMD"),  # GPU competition
        ("V", "MA"),      # Payment duopoly
        ("AAPL", "MSFT"), # Tech mega rivalry
    ]
