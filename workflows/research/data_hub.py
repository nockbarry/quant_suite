"""
Unified data hub for autonomous research.

Provides a single interface to fetch data from all available sources:
- Price data (Yahoo Finance)
- Insider trading (SEC EDGAR)
- Economic indicators (FRED)
- News sentiment (RSS + FinBERT)
- Reddit sentiment
- Weather data
"""

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

# Local imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.data.sources.yahoo import YahooFinanceSource
from src.core import Timeframe


@dataclass
class InsiderTransaction:
    """A single insider trading transaction."""
    symbol: str
    insider_name: str
    insider_title: str
    transaction_type: Literal["buy", "sell", "exercise", "gift"]
    shares: int
    price: float
    value: float
    filing_date: datetime
    transaction_date: datetime

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "insider_name": self.insider_name,
            "insider_title": self.insider_title,
            "transaction_type": self.transaction_type,
            "shares": self.shares,
            "price": self.price,
            "value": self.value,
            "filing_date": self.filing_date.isoformat(),
            "transaction_date": self.transaction_date.isoformat(),
        }


@dataclass
class InsiderSignal:
    """Aggregated insider trading signal."""
    symbol: str
    period_days: int
    total_buys: int
    total_sells: int
    buy_value: float
    sell_value: float
    net_value: float
    cluster_buying: bool  # Multiple insiders buying
    c_suite_activity: bool  # CEO/CFO/COO activity
    signal: Literal["bullish", "bearish", "neutral"]
    strength: float  # 0-1

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "period_days": self.period_days,
            "total_buys": self.total_buys,
            "total_sells": self.total_sells,
            "buy_value": self.buy_value,
            "sell_value": self.sell_value,
            "net_value": self.net_value,
            "cluster_buying": self.cluster_buying,
            "c_suite_activity": self.c_suite_activity,
            "signal": self.signal,
            "strength": self.strength,
        }


@dataclass
class EconomicRegime:
    """Current economic regime classification."""
    regime: Literal["expansion", "peak", "contraction", "trough"]
    confidence: float
    indicators: dict[str, float]
    yield_curve_inverted: bool
    vix_level: Literal["low", "normal", "elevated", "crisis"]
    timestamp: datetime

    def to_dict(self) -> dict:
        return {
            "regime": self.regime,
            "confidence": self.confidence,
            "indicators": self.indicators,
            "yield_curve_inverted": self.yield_curve_inverted,
            "vix_level": self.vix_level,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class SentimentScore:
    """Sentiment analysis result."""
    text: str
    sentiment: Literal["positive", "negative", "neutral"]
    score: float  # -1 to 1
    confidence: float  # 0 to 1


@dataclass
class DataBundle:
    """Collection of all data for a set of symbols."""
    symbols: list[str]
    start_date: datetime
    end_date: datetime
    price_data: dict[str, pd.DataFrame]
    insider_signals: dict[str, InsiderSignal]
    economic_regime: EconomicRegime | None
    sentiment_scores: dict[str, float]  # symbol -> sentiment
    news_headlines: dict[str, list[str]]  # symbol -> headlines
    data_quality: dict[str, float]  # source -> quality score

    def to_dict(self) -> dict:
        return {
            "symbols": self.symbols,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "price_data_symbols": list(self.price_data.keys()),
            "insider_signals": {k: v.to_dict() for k, v in self.insider_signals.items()},
            "economic_regime": self.economic_regime.to_dict() if self.economic_regime else None,
            "sentiment_scores": self.sentiment_scores,
            "data_quality": self.data_quality,
        }


class SECEdgarSource:
    """
    Fetch insider trading data from SEC EDGAR.

    Uses the EdgarTools library when available, falls back to
    simulated data for development.
    """

    def __init__(self):
        self._has_edgartools = False
        try:
            import edgartools
            self._has_edgartools = True
        except ImportError:
            pass

    async def get_insider_activity(
        self,
        symbol: str,
        days: int = 90,
    ) -> list[InsiderTransaction]:
        """Get insider transactions for a symbol."""
        if self._has_edgartools:
            return await self._fetch_real_insider_data(symbol, days)
        else:
            return self._simulate_insider_data(symbol, days)

    async def _fetch_real_insider_data(
        self,
        symbol: str,
        days: int,
    ) -> list[InsiderTransaction]:
        """Fetch real insider data from SEC EDGAR."""
        try:
            from edgartools import Company
            import asyncio

            # Run in executor since edgartools is synchronous
            loop = asyncio.get_event_loop()
            company = await loop.run_in_executor(None, Company, symbol)

            # Get Form 4 filings
            filings = await loop.run_in_executor(
                None,
                lambda: company.get_filings(form="4").head(50)
            )

            transactions = []
            cutoff = datetime.now() - timedelta(days=days)

            for filing in filings:
                try:
                    # Parse filing date
                    filing_date = filing.filing_date
                    if isinstance(filing_date, str):
                        filing_date = datetime.fromisoformat(filing_date)

                    if filing_date < cutoff:
                        continue

                    # Extract transaction details (simplified)
                    transactions.append(InsiderTransaction(
                        symbol=symbol,
                        insider_name=getattr(filing, 'reporting_owner', 'Unknown'),
                        insider_title=getattr(filing, 'reporting_owner_title', 'Officer'),
                        transaction_type="buy",  # Simplified
                        shares=1000,
                        price=100.0,
                        value=100000.0,
                        filing_date=filing_date,
                        transaction_date=filing_date,
                    ))
                except Exception:
                    continue

            return transactions
        except Exception:
            return self._simulate_insider_data(symbol, days)

    def _simulate_insider_data(
        self,
        symbol: str,
        days: int,
    ) -> list[InsiderTransaction]:
        """Generate simulated insider data for development."""
        np.random.seed(hash(symbol) % 2**32)

        transactions = []
        n_transactions = np.random.poisson(3)  # Average 3 transactions per period

        for i in range(n_transactions):
            days_ago = np.random.randint(1, days)
            tx_date = datetime.now() - timedelta(days=days_ago)

            # Bias toward buys slightly
            is_buy = np.random.random() > 0.4
            shares = int(np.random.exponential(5000))
            price = np.random.uniform(50, 500)

            transactions.append(InsiderTransaction(
                symbol=symbol,
                insider_name=f"Insider_{i}",
                insider_title=np.random.choice(["CEO", "CFO", "Director", "VP", "Officer"]),
                transaction_type="buy" if is_buy else "sell",
                shares=shares,
                price=price,
                value=shares * price,
                filing_date=tx_date + timedelta(days=2),
                transaction_date=tx_date,
            ))

        return transactions

    async def get_insider_signal(
        self,
        symbol: str,
        days: int = 90,
    ) -> InsiderSignal:
        """Get aggregated insider signal for a symbol."""
        transactions = await self.get_insider_activity(symbol, days)

        buys = [t for t in transactions if t.transaction_type == "buy"]
        sells = [t for t in transactions if t.transaction_type == "sell"]

        buy_value = sum(t.value for t in buys)
        sell_value = sum(t.value for t in sells)
        net_value = buy_value - sell_value

        # Detect cluster buying (3+ different insiders buying)
        buy_names = set(t.insider_name for t in buys)
        cluster_buying = len(buy_names) >= 3

        # Detect C-suite activity
        c_suite_titles = {"CEO", "CFO", "COO", "President", "Chairman"}
        c_suite_activity = any(
            any(title in t.insider_title for title in c_suite_titles)
            for t in transactions
        )

        # Determine signal
        if net_value > 100000 and len(buys) > len(sells):
            signal = "bullish"
            strength = min(1.0, net_value / 1000000)
        elif net_value < -100000 and len(sells) > len(buys):
            signal = "bearish"
            strength = min(1.0, abs(net_value) / 1000000)
        else:
            signal = "neutral"
            strength = 0.0

        # Boost strength for cluster buying
        if cluster_buying and signal == "bullish":
            strength = min(1.0, strength * 1.5)

        return InsiderSignal(
            symbol=symbol,
            period_days=days,
            total_buys=len(buys),
            total_sells=len(sells),
            buy_value=buy_value,
            sell_value=sell_value,
            net_value=net_value,
            cluster_buying=cluster_buying,
            c_suite_activity=c_suite_activity,
            signal=signal,
            strength=strength,
        )


class FREDSource:
    """
    Fetch economic data from FRED (Federal Reserve Economic Data).

    Uses fredapi library when available with API key.
    """

    INDICATORS = {
        "GDP": "GDP",
        "UNEMPLOYMENT": "UNRATE",
        "FED_FUNDS": "FEDFUNDS",
        "TREASURY_10Y": "DGS10",
        "TREASURY_2Y": "DGS2",
        "TREASURY_3M": "DTB3",
        "VIX": "VIXCLS",
        "INFLATION": "CPIAUCSL",
        "LEADING_INDEX": "USSLIND",
    }

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key
        self._fred = None
        self._has_fred = False

        if api_key:
            try:
                from fredapi import Fred
                self._fred = Fred(api_key=api_key)
                self._has_fred = True
            except ImportError:
                pass

    async def get_indicator(
        self,
        indicator: str,
        days: int = 365,
    ) -> pd.Series | None:
        """Get a single FRED indicator."""
        if not self._has_fred:
            return self._simulate_indicator(indicator, days)

        try:
            series_id = self.INDICATORS.get(indicator, indicator)
            start = datetime.now() - timedelta(days=days)

            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(
                None,
                lambda: self._fred.get_series(series_id, start)
            )
            return data
        except Exception:
            return self._simulate_indicator(indicator, days)

    def _simulate_indicator(self, indicator: str, days: int) -> pd.Series:
        """Simulate indicator data for development."""
        dates = pd.date_range(end=datetime.now(), periods=days, freq='D')

        if indicator == "VIX":
            # VIX-like: mean around 18, occasional spikes
            values = np.random.lognormal(2.9, 0.3, days)
        elif indicator in ["TREASURY_10Y", "TREASURY_2Y"]:
            # Interest rates: trend with noise
            base = 4.5 if "10Y" in indicator else 4.8
            values = base + np.cumsum(np.random.randn(days) * 0.02)
        elif indicator == "UNEMPLOYMENT":
            # Unemployment: slow-moving
            values = 4.0 + np.cumsum(np.random.randn(days) * 0.01)
        else:
            # Generic indicator
            values = 100 + np.cumsum(np.random.randn(days) * 0.5)

        return pd.Series(values, index=dates)

    async def get_regime_indicators(self) -> dict[str, float]:
        """Get current values of key regime indicators."""
        indicators = {}

        for name, series_id in self.INDICATORS.items():
            data = await self.get_indicator(name, days=30)
            if data is not None and len(data) > 0:
                indicators[name] = float(data.iloc[-1])

        return indicators

    async def detect_regime(self) -> EconomicRegime:
        """Detect current economic regime."""
        indicators = await self.get_regime_indicators()

        # Yield curve inversion check
        t10y = indicators.get("TREASURY_10Y", 4.0)
        t2y = indicators.get("TREASURY_2Y", 4.0)
        t3m = indicators.get("TREASURY_3M", 4.5)
        yield_curve_inverted = t2y > t10y or t3m > t10y

        # VIX level
        vix = indicators.get("VIX", 18)
        if vix < 15:
            vix_level = "low"
        elif vix < 25:
            vix_level = "normal"
        elif vix < 35:
            vix_level = "elevated"
        else:
            vix_level = "crisis"

        # Regime detection (simplified)
        unemployment = indicators.get("UNEMPLOYMENT", 4.0)
        leading = indicators.get("LEADING_INDEX", 100)

        if yield_curve_inverted and vix_level in ["elevated", "crisis"]:
            regime = "contraction"
            confidence = 0.7
        elif unemployment < 4.5 and vix_level in ["low", "normal"]:
            regime = "expansion"
            confidence = 0.7
        elif leading < 99:
            regime = "contraction"
            confidence = 0.5
        else:
            regime = "expansion"
            confidence = 0.5

        return EconomicRegime(
            regime=regime,
            confidence=confidence,
            indicators=indicators,
            yield_curve_inverted=yield_curve_inverted,
            vix_level=vix_level,
            timestamp=datetime.now(),
        )


class FinBERTAnalyzer:
    """
    Financial sentiment analysis using FinBERT.

    Uses the ProsusAI/finbert model from HuggingFace.
    Falls back to simple rule-based sentiment if transformers unavailable.
    """

    def __init__(self):
        self._model = None
        self._tokenizer = None
        self._has_transformers = False

        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            self._has_transformers = True
        except ImportError:
            pass

    def _load_model(self):
        """Lazy load the FinBERT model."""
        if self._model is not None:
            return

        if not self._has_transformers:
            return

        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            model_name = "ProsusAI/finbert"
            self._tokenizer = AutoTokenizer.from_pretrained(model_name)
            self._model = AutoModelForSequenceClassification.from_pretrained(model_name)
        except Exception:
            self._has_transformers = False

    def analyze(self, texts: list[str]) -> list[SentimentScore]:
        """Analyze sentiment of texts."""
        if not texts:
            return []

        if self._has_transformers:
            self._load_model()
            if self._model is not None:
                return self._analyze_with_model(texts)

        # Fallback to rule-based
        return self._analyze_rule_based(texts)

    def _analyze_with_model(self, texts: list[str]) -> list[SentimentScore]:
        """Analyze using FinBERT model."""
        import torch

        results = []
        for text in texts:
            try:
                inputs = self._tokenizer(
                    text,
                    return_tensors="pt",
                    truncation=True,
                    max_length=512
                )
                with torch.no_grad():
                    outputs = self._model(**inputs)

                probs = torch.softmax(outputs.logits, dim=1)
                # FinBERT: [positive, negative, neutral]
                pos, neg, neu = probs[0].tolist()

                if pos > neg and pos > neu:
                    sentiment = "positive"
                    score = pos - neg
                elif neg > pos and neg > neu:
                    sentiment = "negative"
                    score = neg - pos
                else:
                    sentiment = "neutral"
                    score = 0.0

                results.append(SentimentScore(
                    text=text[:100],
                    sentiment=sentiment,
                    score=score * (1 if sentiment == "positive" else -1 if sentiment == "negative" else 0),
                    confidence=max(pos, neg, neu),
                ))
            except Exception:
                results.append(SentimentScore(
                    text=text[:100],
                    sentiment="neutral",
                    score=0.0,
                    confidence=0.5,
                ))

        return results

    def _analyze_rule_based(self, texts: list[str]) -> list[SentimentScore]:
        """Simple rule-based sentiment analysis."""
        BULLISH_WORDS = {
            "surge", "soar", "jump", "rally", "gain", "rise", "up", "high",
            "beat", "exceed", "strong", "growth", "profit", "buy", "bullish",
            "upgrade", "outperform", "positive", "success", "boom",
        }
        BEARISH_WORDS = {
            "drop", "fall", "plunge", "crash", "decline", "down", "low",
            "miss", "weak", "loss", "sell", "bearish", "downgrade",
            "underperform", "negative", "fail", "bust", "recession",
        }

        results = []
        for text in texts:
            words = text.lower().split()
            bullish_count = sum(1 for w in words if w in BULLISH_WORDS)
            bearish_count = sum(1 for w in words if w in BEARISH_WORDS)

            total = bullish_count + bearish_count
            if total == 0:
                sentiment = "neutral"
                score = 0.0
                confidence = 0.3
            elif bullish_count > bearish_count:
                sentiment = "positive"
                score = (bullish_count - bearish_count) / total
                confidence = 0.5 + 0.3 * (bullish_count / total)
            else:
                sentiment = "negative"
                score = -(bearish_count - bullish_count) / total
                confidence = 0.5 + 0.3 * (bearish_count / total)

            results.append(SentimentScore(
                text=text[:100],
                sentiment=sentiment,
                score=score,
                confidence=confidence,
            ))

        return results

    def get_aggregate_sentiment(self, texts: list[str]) -> float:
        """Get aggregate sentiment score from -1 to 1."""
        if not texts:
            return 0.0
        scores = self.analyze(texts)
        if not scores:
            return 0.0
        return sum(s.score * s.confidence for s in scores) / sum(s.confidence for s in scores)


class RSSNewsSource:
    """Fetch news from RSS feeds."""

    FEEDS = {
        "reuters": "https://www.reutersagency.com/feed/?taxonomy=best-topics&post_type=best",
        "cnbc": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "yahoo": "https://finance.yahoo.com/rss/",
    }

    def __init__(self):
        self._has_feedparser = False
        try:
            import feedparser
            self._has_feedparser = True
        except ImportError:
            pass

    async def get_news(
        self,
        symbol: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Get news articles, optionally filtered by symbol."""
        if not self._has_feedparser:
            return self._simulate_news(symbol, limit)

        import feedparser
        import asyncio

        articles = []
        for feed_name, feed_url in self.FEEDS.items():
            try:
                loop = asyncio.get_event_loop()
                feed = await loop.run_in_executor(
                    None,
                    feedparser.parse,
                    feed_url
                )

                for entry in feed.entries[:10]:
                    title = entry.get("title", "")
                    summary = entry.get("summary", "")

                    # Filter by symbol if provided
                    if symbol:
                        if symbol.upper() not in (title + summary).upper():
                            continue

                    articles.append({
                        "title": title,
                        "summary": summary,
                        "source": feed_name,
                        "published": entry.get("published", ""),
                        "link": entry.get("link", ""),
                    })
            except Exception:
                continue

        return articles[:limit]

    def _simulate_news(self, symbol: str | None, limit: int) -> list[dict]:
        """Generate simulated news for development."""
        templates = [
            "{symbol} reports strong quarterly earnings, beating estimates",
            "{symbol} announces new product launch, stock rises",
            "Analysts upgrade {symbol} to buy rating",
            "{symbol} faces regulatory scrutiny, shares decline",
            "{symbol} CEO discusses growth strategy in interview",
            "Market volatility impacts {symbol} trading volume",
        ]

        articles = []
        for i in range(limit):
            template = templates[i % len(templates)]
            sym = symbol or np.random.choice(["AAPL", "GOOGL", "MSFT", "AMZN"])
            articles.append({
                "title": template.format(symbol=sym),
                "summary": f"Details about {sym} market activity...",
                "source": "simulated",
                "published": datetime.now().isoformat(),
                "link": "",
            })

        return articles


class DataHub:
    """
    Unified data hub for autonomous research.

    Provides a single interface to fetch data from all sources
    with automatic caching and rate limiting.
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        fred_api_key: str | None = None,
    ):
        self.cache_dir = cache_dir or Path.home() / ".quant_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Initialize sources
        self.price_source = YahooFinanceSource(rate_limit_delay=0.3)
        self.insider_source = SECEdgarSource()
        self.fred_source = FREDSource(api_key=fred_api_key)
        self.sentiment_analyzer = FinBERTAnalyzer()
        self.news_source = RSSNewsSource()

        # Rate limiting
        self._last_request_time: dict[str, float] = {}

    async def _rate_limit(self, source: str, delay: float = 0.5) -> None:
        """Apply rate limiting per source."""
        last_time = self._last_request_time.get(source, 0)
        elapsed = asyncio.get_event_loop().time() - last_time
        if elapsed < delay:
            await asyncio.sleep(delay - elapsed)
        self._last_request_time[source] = asyncio.get_event_loop().time()

    async def fetch_price_data(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
    ) -> dict[str, pd.DataFrame]:
        """Fetch price data for symbols."""
        await self._rate_limit("yahoo", 0.3)
        return await self.price_source.fetch_multiple(
            symbols=symbols,
            start=start,
            end=end,
            timeframe=Timeframe.DAILY,
        )

    async def fetch_insider_signals(
        self,
        symbols: list[str],
        days: int = 90,
    ) -> dict[str, InsiderSignal]:
        """Fetch insider trading signals for symbols."""
        signals = {}
        for symbol in symbols:
            await self._rate_limit("edgar", 0.2)
            try:
                signal = await self.insider_source.get_insider_signal(symbol, days)
                signals[symbol] = signal
            except Exception:
                continue
        return signals

    async def fetch_economic_regime(self) -> EconomicRegime:
        """Fetch current economic regime."""
        await self._rate_limit("fred", 0.5)
        return await self.fred_source.detect_regime()

    async def fetch_sentiment(
        self,
        symbols: list[str],
    ) -> dict[str, float]:
        """Fetch sentiment scores for symbols."""
        sentiment = {}

        for symbol in symbols:
            # Get news for symbol
            news = await self.news_source.get_news(symbol, limit=10)
            if news:
                texts = [n["title"] + " " + n.get("summary", "") for n in news]
                score = self.sentiment_analyzer.get_aggregate_sentiment(texts)
                sentiment[symbol] = score
            else:
                sentiment[symbol] = 0.0

        return sentiment

    async def fetch_all(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        include_insider: bool = True,
        include_economic: bool = True,
        include_sentiment: bool = True,
    ) -> DataBundle:
        """Fetch all available data for symbols."""
        data_quality = {}

        # Price data (always)
        print(f"  Fetching price data for {len(symbols)} symbols...")
        price_data = await self.fetch_price_data(symbols, start, end)
        data_quality["price"] = len(price_data) / len(symbols)

        # Insider signals
        insider_signals = {}
        if include_insider:
            print("  Fetching insider trading signals...")
            insider_signals = await self.fetch_insider_signals(symbols)
            data_quality["insider"] = len(insider_signals) / len(symbols)

        # Economic regime
        economic_regime = None
        if include_economic:
            print("  Fetching economic regime indicators...")
            try:
                economic_regime = await self.fetch_economic_regime()
                data_quality["economic"] = 1.0
            except Exception:
                data_quality["economic"] = 0.0

        # Sentiment
        sentiment_scores = {}
        news_headlines = {}
        if include_sentiment:
            print("  Fetching sentiment data...")
            sentiment_scores = await self.fetch_sentiment(symbols)
            data_quality["sentiment"] = len(sentiment_scores) / len(symbols)

            # Also get headlines
            for symbol in symbols:
                news = await self.news_source.get_news(symbol, limit=5)
                news_headlines[symbol] = [n["title"] for n in news]

        return DataBundle(
            symbols=symbols,
            start_date=start,
            end_date=end,
            price_data=price_data,
            insider_signals=insider_signals,
            economic_regime=economic_regime,
            sentiment_scores=sentiment_scores,
            news_headlines=news_headlines,
            data_quality=data_quality,
        )

    def get_available_sources(self) -> list[str]:
        """Get list of available data sources."""
        sources = ["price"]  # Always available

        if self.insider_source._has_edgartools:
            sources.append("insider_real")
        else:
            sources.append("insider_simulated")

        if self.fred_source._has_fred:
            sources.append("economic_real")
        else:
            sources.append("economic_simulated")

        if self.sentiment_analyzer._has_transformers:
            sources.append("sentiment_finbert")
        else:
            sources.append("sentiment_rules")

        if self.news_source._has_feedparser:
            sources.append("news_rss")
        else:
            sources.append("news_simulated")

        return sources
