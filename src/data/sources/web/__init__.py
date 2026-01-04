"""Web scraping sources for alternative data."""

from .scraper import (
    WebScraper,
    RateLimiter,
    DiskCache,
    RobotsChecker,
    ScrapingConfig,
    ScrapedContent,
    WebScrapingPipeline,
    scrape_financial_page,
)
from .sec_filings import SECFilingScraper, Filing, FilingDocument
from .news_scraper import NewsResearchScraper, Headline, Article, AnalystRating

__all__ = [
    # Base scraping
    "WebScraper",
    "RateLimiter",
    "DiskCache",
    # Robots.txt compliance
    "RobotsChecker",
    "ScrapingConfig",
    "ScrapedContent",
    "WebScrapingPipeline",
    "scrape_financial_page",
    # SEC
    "SECFilingScraper",
    "Filing",
    "FilingDocument",
    # News
    "NewsResearchScraper",
    "Headline",
    "Article",
    "AnalystRating",
]
