"""
Universal Data Sources - Free API Hub and Commodity Scrapers

Provides access to:
- FRED (Federal Reserve Economic Data) - macro indicators
- Commodity ETF proxies (GLD, SLV, USO, etc.)
- Industry data scrapers (DRAM prices, semi equipment)
- Blog/article scrapers for alpha research

All with proper rate limiting, caching, and point-in-time safety.
"""

from .free_api_hub import FreeAPIHub, FREDClient
from .commodity_scraper import CommoditySource
from .blog_scraper import BlogScraper, BlogSourceConfig, ScrapedArticle

__all__ = [
    "FreeAPIHub",
    "FREDClient",
    "CommoditySource",
    "BlogScraper",
    "BlogSourceConfig",
    "ScrapedArticle",
]
