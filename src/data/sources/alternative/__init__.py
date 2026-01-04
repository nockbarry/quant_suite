"""Alternative data sources for trading strategies."""

from .etf_flows import (
    ETF_UNIVERSE,
    ETFCategory,
    ETFFlowData,
    ETFFlowEstimator,
    ETFFlowSource,
    ETFInfo,
    RiskAppetiteIndicator,
    RotationSignal,
    SectorFlowSummary,
    detect_sector_rotation,
    fetch_sector_flows,
)
from .insider import (
    Form4Monitor,
    InsiderDataSource,
    InsiderRole,
    InsiderSummary,
    InsiderTransaction,
    TransactionType,
    fetch_insider_summary,
    find_cluster_buying,
)
from .news import (
    NewsArticle,
    NewsDataSource,
    NewsSourceConfig,
    RSSNewsSource,
    extract_symbols_from_text,
)
from .options_flow import (
    OptionContract,
    OptionsFlowAnalyzer,
    OptionsFlowSource,
    OptionsFlowSummary,
    OptionType,
    PutCallRatioSource,
    UnusualActivity,
    UnusualActivityType,
    fetch_options_flow,
    fetch_unusual_options,
)
from .reddit import (
    BEARISH_WORDS,
    BULLISH_WORDS,
    COMPANY_TO_TICKER,
    TICKER_BLACKLIST,
    RedditComment,
    RedditDataSource,
    RedditPost,
    SymbolExtractor,
    SymbolMention,
    TradestieAPI,
    fetch_reddit_sentiment,
    fetch_wsb_trending,
)
from .weather import (
    AGRICULTURAL_REGIONS,
    MAJOR_LOCATIONS,
    LocationConfig,
    WeatherData,
    WeatherDataSource,
    WeatherFeatureEngine,
    get_sector_locations,
)

# Google Trends - optional import
try:
    from .google_trends import (
        GoogleTrendsFeatures,
        GoogleTrendsSource,
        RetailAttentionSignal,
        TrendsResult,
        create_google_trends_source,
    )
    GOOGLE_TRENDS_AVAILABLE = True
except ImportError:
    GOOGLE_TRENDS_AVAILABLE = False

# Short Interest - optional import
try:
    from .short_interest import (
        ShortInterestData,
        ShortInterestFeatures,
        ShortInterestSource,
        ShortSqueezeSignal,
        create_short_interest_source,
    )
    SHORT_INTEREST_AVAILABLE = True
except ImportError:
    SHORT_INTEREST_AVAILABLE = False

__all__ = [
    # News
    "NewsArticle",
    "NewsSourceConfig",
    "NewsDataSource",
    "RSSNewsSource",
    "extract_symbols_from_text",
    # Reddit
    "RedditPost",
    "RedditComment",
    "SymbolMention",
    "SymbolExtractor",
    "RedditDataSource",
    "TradestieAPI",
    "fetch_reddit_sentiment",
    "fetch_wsb_trending",
    "TICKER_BLACKLIST",
    "COMPANY_TO_TICKER",
    "BULLISH_WORDS",
    "BEARISH_WORDS",
    # Weather
    "WeatherData",
    "LocationConfig",
    "WeatherDataSource",
    "WeatherFeatureEngine",
    "MAJOR_LOCATIONS",
    "AGRICULTURAL_REGIONS",
    "get_sector_locations",
    # Options Flow
    "OptionType",
    "UnusualActivityType",
    "OptionContract",
    "UnusualActivity",
    "OptionsFlowSummary",
    "OptionsFlowAnalyzer",
    "OptionsFlowSource",
    "PutCallRatioSource",
    "fetch_options_flow",
    "fetch_unusual_options",
    # Insider Trading
    "TransactionType",
    "InsiderRole",
    "InsiderTransaction",
    "InsiderSummary",
    "InsiderDataSource",
    "Form4Monitor",
    "fetch_insider_summary",
    "find_cluster_buying",
    # ETF Flows
    "ETFCategory",
    "ETF_UNIVERSE",
    "ETFInfo",
    "ETFFlowData",
    "SectorFlowSummary",
    "RotationSignal",
    "ETFFlowEstimator",
    "ETFFlowSource",
    "RiskAppetiteIndicator",
    "fetch_sector_flows",
    "detect_sector_rotation",
    # Google Trends (if available)
    "GoogleTrendsSource",
    "GoogleTrendsFeatures",
    "TrendsResult",
    "RetailAttentionSignal",
    "create_google_trends_source",
    "GOOGLE_TRENDS_AVAILABLE",
    # Short Interest (if available)
    "ShortInterestSource",
    "ShortInterestFeatures",
    "ShortInterestData",
    "ShortSqueezeSignal",
    "create_short_interest_source",
    "SHORT_INTEREST_AVAILABLE",
]
