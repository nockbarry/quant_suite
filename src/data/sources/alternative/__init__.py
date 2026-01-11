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

# Congressional Trades
from .congressional_trades import (
    Chamber,
    TradeType,
    AssetType as CongressAssetType,
    CongressionalTrade,
    CongressionalCluster,
    CongressionalTradesSource,
    NOTABLE_TRADERS,
    fetch_congressional_trades,
    find_congressional_clusters,
)

# Prediction Markets
from .prediction_markets import (
    MarketCategory,
    MarketSource,
    PredictionMarket,
    MacroSignal,
    PredictionMarketsSource,
    fetch_prediction_markets,
    get_macro_signals,
)

# Expert Sentiment (Inverse Cramer, etc.)
from .expert_sentiment import (
    SentimentType,
    ExpertType,
    SignalAction,
    ExpertCall,
    ExpertConsensus,
    ExpertSentimentSource,
    EXPERT_PROFILES,
    fetch_expert_calls,
    get_inverse_cramer,
    get_expert_consensus,
)

# VIX Term Structure
from .vix_structure import (
    VIXTermStructure,
    VIXStructureSource,
    get_vix_structure,
    get_vix_signal,
)

# Put/Call Ratio
from .put_call import (
    PutCallData,
    PutCallSource,
    get_put_call_data,
    get_put_call_signal,
)

# AAII Sentiment
from .aaii_sentiment import (
    AAIISentiment,
    AAIISentimentSource,
    get_aaii_sentiment,
    get_aaii_signal,
)

# Finviz Screener
from .finviz_screens import (
    ScreenResult,
    FinvizScreens,
    FinvizScreener,
    SCREEN_DEFINITIONS,
    get_finviz_screens,
    get_screen_candidates,
)

# Newsletter Sentiment (Investors Intelligence)
from .newsletter_sentiment import (
    NewsletterSentiment,
    NewsletterSentimentSource,
    get_newsletter_sentiment,
    get_newsletter_signal,
)

# Commitment of Traders (COT)
from .cot_report import (
    COTPosition,
    COTReport,
    COTSource,
    CONTRACT_MAP as COT_CONTRACT_MAP,
    get_cot_report,
    get_cot_signal,
    get_equity_cot_signal,
)

# Earnings Calendar
from .earnings_calendar import (
    EarningsEvent,
    EarningsCalendar,
    EarningsCalendarSource,
    get_earnings_calendar,
    get_earnings_today,
    check_earnings_soon,
)

# Economic Calendar
from .economic_calendar import (
    ReleaseCategory,
    ReleaseImportance,
    EconomicRelease,
    EconomicCalendar,
    EconomicCalendarSource,
    RELEASE_DEFINITIONS,
    get_economic_calendar,
    get_high_impact_releases,
    has_fomc_this_week,
)

# Fed Futures
from .fed_futures import (
    FOMCMeeting,
    FedExpectations,
    FedFuturesSource,
    FOMC_DATES_2026,
    get_fed_expectations,
    get_next_fomc_date,
    get_rate_path_signal,
)

# Treasury Calendar
from .treasury_calendar import (
    SecurityType,
    TreasuryAuction,
    TreasuryCalendar,
    TreasuryCalendarSource,
    SECURITY_IMPACT,
    get_treasury_calendar,
    get_high_impact_auctions,
    get_weekly_issuance,
)

# IPO Calendar
from .ipo_calendar import (
    IPOEvent,
    IPOCalendar,
    IPOCalendarSource,
    get_ipo_calendar,
    get_upcoming_ipos,
    get_large_ipos,
)

# FDA Calendar
from .fda_calendar import (
    EventType as FDAEventType,
    FDAEvent,
    FDACalendar,
    FDACalendarSource,
    APPROVAL_RATES,
    get_fda_calendar,
    get_upcoming_pdufa,
    get_binary_events,
    check_fda_catalyst,
)

# Patent Filings
from .patent_filings import (
    Patent,
    PatentActivity,
    PatentDatabase,
    USPTOSource,
    COMPANY_ASSIGNEES,
    get_patent_activity,
    get_top_innovators,
    get_accelerating_innovation,
)

# Job Postings
from .job_postings import (
    JobPostings,
    JobDatabase,
    JobPostingSource,
    CAREER_PAGES,
    get_job_postings,
    get_expanding_companies,
    get_contracting_companies,
)

# App Rankings
from .app_rankings import (
    AppStore,
    AppCategory,
    AppRanking,
    CompanyAppSummary,
    AppRankingDatabase,
    AppRankingSource,
    APP_COMPANY_MAP,
    get_app_rankings,
    get_top_apps,
    get_rising_apps,
)

# GitHub Activity
from .github_activity import (
    GitHubRepo,
    GitHubActivity,
    GitHubDatabase,
    GitHubSource,
    COMPANY_ORGS,
    get_github_activity,
    get_top_github_companies,
    get_growing_github_presence,
)

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
    # Congressional Trades
    "Chamber",
    "TradeType",
    "CongressAssetType",
    "CongressionalTrade",
    "CongressionalCluster",
    "CongressionalTradesSource",
    "NOTABLE_TRADERS",
    "fetch_congressional_trades",
    "find_congressional_clusters",
    # Prediction Markets
    "MarketCategory",
    "MarketSource",
    "PredictionMarket",
    "MacroSignal",
    "PredictionMarketsSource",
    "fetch_prediction_markets",
    "get_macro_signals",
    # Expert Sentiment
    "SentimentType",
    "ExpertType",
    "SignalAction",
    "ExpertCall",
    "ExpertConsensus",
    "ExpertSentimentSource",
    "EXPERT_PROFILES",
    "fetch_expert_calls",
    "get_inverse_cramer",
    "get_expert_consensus",
    # VIX Term Structure
    "VIXTermStructure",
    "VIXStructureSource",
    "get_vix_structure",
    "get_vix_signal",
    # Put/Call Ratio
    "PutCallData",
    "PutCallSource",
    "get_put_call_data",
    "get_put_call_signal",
    # AAII Sentiment
    "AAIISentiment",
    "AAIISentimentSource",
    "get_aaii_sentiment",
    "get_aaii_signal",
    # Finviz Screener
    "ScreenResult",
    "FinvizScreens",
    "FinvizScreener",
    "SCREEN_DEFINITIONS",
    "get_finviz_screens",
    "get_screen_candidates",
    # Newsletter Sentiment
    "NewsletterSentiment",
    "NewsletterSentimentSource",
    "get_newsletter_sentiment",
    "get_newsletter_signal",
    # COT Report
    "COTPosition",
    "COTReport",
    "COTSource",
    "COT_CONTRACT_MAP",
    "get_cot_report",
    "get_cot_signal",
    "get_equity_cot_signal",
    # Earnings Calendar
    "EarningsEvent",
    "EarningsCalendar",
    "EarningsCalendarSource",
    "get_earnings_calendar",
    "get_earnings_today",
    "check_earnings_soon",
    # Economic Calendar
    "ReleaseCategory",
    "ReleaseImportance",
    "EconomicRelease",
    "EconomicCalendar",
    "EconomicCalendarSource",
    "RELEASE_DEFINITIONS",
    "get_economic_calendar",
    "get_high_impact_releases",
    "has_fomc_this_week",
    # Fed Futures
    "FOMCMeeting",
    "FedExpectations",
    "FedFuturesSource",
    "FOMC_DATES_2026",
    "get_fed_expectations",
    "get_next_fomc_date",
    "get_rate_path_signal",
    # Treasury Calendar
    "SecurityType",
    "TreasuryAuction",
    "TreasuryCalendar",
    "TreasuryCalendarSource",
    "SECURITY_IMPACT",
    "get_treasury_calendar",
    "get_high_impact_auctions",
    "get_weekly_issuance",
    # IPO Calendar
    "IPOEvent",
    "IPOCalendar",
    "IPOCalendarSource",
    "get_ipo_calendar",
    "get_upcoming_ipos",
    "get_large_ipos",
    # FDA Calendar
    "FDAEventType",
    "FDAEvent",
    "FDACalendar",
    "FDACalendarSource",
    "APPROVAL_RATES",
    "get_fda_calendar",
    "get_upcoming_pdufa",
    "get_binary_events",
    "check_fda_catalyst",
    # Patent Filings
    "Patent",
    "PatentActivity",
    "PatentDatabase",
    "USPTOSource",
    "COMPANY_ASSIGNEES",
    "get_patent_activity",
    "get_top_innovators",
    "get_accelerating_innovation",
    # Job Postings
    "JobPostings",
    "JobDatabase",
    "JobPostingSource",
    "CAREER_PAGES",
    "get_job_postings",
    "get_expanding_companies",
    "get_contracting_companies",
    # App Rankings
    "AppStore",
    "AppCategory",
    "AppRanking",
    "CompanyAppSummary",
    "AppRankingDatabase",
    "AppRankingSource",
    "APP_COMPANY_MAP",
    "get_app_rankings",
    "get_top_apps",
    "get_rising_apps",
    # GitHub Activity
    "GitHubRepo",
    "GitHubActivity",
    "GitHubDatabase",
    "GitHubSource",
    "COMPANY_ORGS",
    "get_github_activity",
    "get_top_github_companies",
    "get_growing_github_presence",
]
