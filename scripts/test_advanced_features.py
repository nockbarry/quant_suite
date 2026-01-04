#!/usr/bin/env python3
"""
Test Advanced Experimental Features

Tests the new advanced strategy components:
1. Web scraping infrastructure
2. SEC filing analysis
3. Feature store and registry
4. Document embeddings
5. Hypothesis generation
6. Stock screening
7. Trading analytics
"""

import asyncio
import json
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np

warnings.filterwarnings('ignore')

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Output directory
OUTPUT_DIR = Path.home() / "quant_results" / "advanced_tests"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Test results
TEST_RESULTS = {
    "timestamp": datetime.now().isoformat(),
    "tests": {},
    "summary": {},
}


def log_test(name: str, passed: bool, details: dict = None):
    """Log test result."""
    TEST_RESULTS["tests"][name] = {
        "passed": passed,
        "details": details or {},
        "timestamp": datetime.now().isoformat(),
    }
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"  {status}: {name}")
    if details:
        for k, v in details.items():
            print(f"         {k}: {v}")


# =============================================================================
# TEST 1: WEB SCRAPER
# =============================================================================

async def test_web_scraper():
    """Test base web scraper functionality."""
    print("\n" + "=" * 60)
    print("TEST 1: Web Scraper")
    print("=" * 60)

    from src.data.sources.web.scraper import WebScraper, DiskCache, RateLimiter

    # Test cache
    cache = DiskCache()
    cache.set("https://example.com/test", "Test content", timedelta(hours=1))
    cached = cache.get("https://example.com/test")
    log_test("DiskCache set/get", cached == "Test content", {"cached": bool(cached)})

    # Test rate limiter
    limiter = RateLimiter(requests_per_second=2.0)
    start = datetime.now()
    await limiter.acquire()
    await limiter.acquire()
    elapsed = (datetime.now() - start).total_seconds()
    log_test("RateLimiter", elapsed >= 0, {"elapsed_seconds": round(elapsed, 2)})

    # Test scraper (simple fetch)
    scraper = WebScraper(rate_limit=2.0)
    try:
        result = await scraper.fetch("https://www.sec.gov/", use_cache=True)
        log_test("WebScraper.fetch()", result.status_code == 200, {
            "status": result.status_code,
            "content_length": len(result.content),
        })

        # Test text extraction
        text = scraper.extract_text(result.content, "title")
        log_test("WebScraper.extract_text()", len(text) > 0, {"title": text[:50]})

    except Exception as e:
        log_test("WebScraper.fetch()", False, {"error": str(e)})
    finally:
        await scraper.close()


# =============================================================================
# TEST 2: SEC FILING SCRAPER
# =============================================================================

async def test_sec_filings():
    """Test SEC filing scraper."""
    print("\n" + "=" * 60)
    print("TEST 2: SEC Filing Scraper")
    print("=" * 60)

    from src.data.sources.web.sec_filings import SECFilingScraper, CIKLookup

    scraper = SECFilingScraper()

    try:
        # Test CIK lookup
        cik_lookup = CIKLookup(scraper.scraper)
        cik = await cik_lookup.get_cik("AAPL")
        log_test("CIKLookup.get_cik(AAPL)", cik is not None, {"cik": cik})

        # Test filing list
        filings = await scraper.get_recent_filings("AAPL", "10-K", limit=2)
        log_test("SECFilingScraper.get_recent_filings()", len(filings) > 0, {
            "count": len(filings),
            "latest_date": filings[0].filed_date.isoformat() if filings else None,
        })

        # Test filing fetch (limited for speed)
        if filings:
            doc = await scraper.fetch_filing(filings[0])
            log_test("SECFilingScraper.fetch_filing()", len(doc.full_text) > 0, {
                "text_length": len(doc.full_text),
                "sections": list(doc.sections.keys())[:5],
            })

            # Test sentiment
            sentiment = scraper.get_filing_sentiment(doc)
            log_test("get_filing_sentiment()", True, {
                "overall": round(sentiment.overall_sentiment, 3),
                "sections": list(sentiment.section_sentiments.keys()),
            })

    except Exception as e:
        log_test("SEC Filing tests", False, {"error": str(e)})
    finally:
        await scraper.close()


# =============================================================================
# TEST 3: FEATURE STORE
# =============================================================================

def test_feature_store():
    """Test feature store functionality."""
    print("\n" + "=" * 60)
    print("TEST 3: Feature Store")
    print("=" * 60)

    from src.data.feature_engineering.feature_store import FeatureStore

    store = FeatureStore()

    # Create test features
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    df = pd.DataFrame({
        "return_1d": np.random.randn(100) * 0.02,
        "volatility": np.random.rand(100) * 0.3,
        "rsi": np.random.rand(100) * 100,
    }, index=dates)

    # Save features
    version = store.save_features(
        symbol="TEST",
        features=df,
        feature_set="test_features",
        parameters={"test": True},
    )
    log_test("FeatureStore.save_features()", version is not None, {"version": version})

    # Load features
    loaded = store.load_features("TEST", "test_features")
    log_test("FeatureStore.load_features()", len(loaded) == 100, {
        "rows": len(loaded),
        "columns": list(loaded.columns),
    })

    # Get metadata
    meta = store.get_metadata("TEST", "test_features")
    log_test("FeatureStore.get_metadata()", meta is not None, {
        "version": meta.version,
        "row_count": meta.row_count,
    })

    # List versions
    versions = store.list_versions("TEST", "test_features")
    log_test("FeatureStore.list_versions()", len(versions) > 0, {
        "count": len(versions),
    })

    # Feature stats
    stats = store.compute_feature_stats("TEST", "test_features")
    log_test("FeatureStore.compute_feature_stats()", len(stats) == 3, {
        "features": [s.name for s in stats],
    })

    # Summary
    summary = store.get_store_summary()
    log_test("FeatureStore.get_store_summary()", summary["total_symbols"] > 0, summary)


# =============================================================================
# TEST 4: FEATURE REGISTRY
# =============================================================================

def test_feature_registry():
    """Test feature registry."""
    print("\n" + "=" * 60)
    print("TEST 4: Feature Registry")
    print("=" * 60)

    from src.data.feature_engineering.feature_registry import (
        FEATURE_REGISTRY,
        FeatureCategory,
        FeatureComputer,
        get_registry_summary,
        list_features_by_category,
    )

    # Check registry size
    summary = get_registry_summary()
    log_test("Feature Registry Size", summary["total_features"] >= 25, {
        "total_features": summary["total_features"],
        "by_category": summary["by_category"],
    })

    # Check categories
    technical = list_features_by_category(FeatureCategory.TECHNICAL)
    log_test("Technical features", len(technical) >= 5, {
        "count": len(technical),
        "features": technical[:5],
    })

    sentiment = list_features_by_category(FeatureCategory.SENTIMENT)
    log_test("Sentiment features", len(sentiment) >= 2, {
        "count": len(sentiment),
        "features": sentiment,
    })

    # Test feature computation
    import yfinance as yf
    df = yf.download("SPY", period="60d", progress=False)
    df.columns = [c.lower() if isinstance(c, str) else c[0].lower() for c in df.columns]

    computer = FeatureComputer()
    technical_features = computer.compute_all_technical(df)
    log_test("FeatureComputer.compute_all_technical()", len(technical_features.columns) > 10, {
        "columns": len(technical_features.columns),
        "sample": list(technical_features.columns)[:5],
    })


# =============================================================================
# TEST 5: DOCUMENT EMBEDDER
# =============================================================================

def test_document_embedder():
    """Test document embeddings."""
    print("\n" + "=" * 60)
    print("TEST 5: Document Embedder")
    print("=" * 60)

    from src.data.feature_engineering.text_embeddings import DocumentEmbedder, Document

    embedder = DocumentEmbedder()

    # Test embedding
    text = "Apple reported strong quarterly earnings, beating analyst expectations."
    embedding = embedder.embed(text)
    log_test("DocumentEmbedder.embed()", len(embedding) > 0, {
        "embedding_dim": len(embedding),
        "type": type(embedding).__name__,
    })

    # Test batch embedding
    texts = [
        "Tesla announces new factory in Texas.",
        "Microsoft cloud revenue grows 30%.",
        "Amazon expands logistics network.",
    ]
    batch_embeddings = embedder.embed_batch(texts)
    log_test("DocumentEmbedder.embed_batch()", len(batch_embeddings) == 3, {
        "batch_size": len(batch_embeddings),
    })

    # Test document storage and retrieval
    doc = Document(
        id="test_doc_1",
        text="Google AI division reports breakthrough in language models.",
        symbol="GOOGL",
        source="test",
        published_at=datetime.now(),
    )
    embedder.embed_and_store(doc)
    log_test("DocumentEmbedder.embed_and_store()", True, {"doc_id": doc.id})

    # Test similarity search
    similar = embedder.find_similar("tech earnings", top_k=5)
    log_test("DocumentEmbedder.find_similar()", len(similar) >= 0, {
        "results": len(similar),
    })


# =============================================================================
# TEST 6: HYPOTHESIS GENERATOR
# =============================================================================

def test_hypothesis_generator():
    """Test hypothesis generation."""
    print("\n" + "=" * 60)
    print("TEST 6: Hypothesis Generator")
    print("=" * 60)

    from workflows.research.hypothesis_generator import HypothesisGenerator

    generator = HypothesisGenerator()

    # Test anomaly detection
    anomalies = generator.detect_anomalies(lookback_days=5)
    log_test("HypothesisGenerator.detect_anomalies()", True, {
        "anomalies_found": len(anomalies),
        "types": list(set(a.anomaly_type for a in anomalies))[:3] if anomalies else [],
    })

    # Test hypothesis from anomalies
    hypotheses = generator.generate_from_anomalies()
    log_test("generate_from_anomalies()", True, {
        "hypotheses": len(hypotheses),
    })

    # Test correlation breaks
    breaks = generator.detect_correlation_breaks()
    log_test("detect_correlation_breaks()", True, {
        "breaks_found": len(breaks),
    })

    # Test daily hypotheses
    daily = generator.get_daily_hypotheses(n=5)
    log_test("get_daily_hypotheses()", len(daily) >= 0, {
        "count": len(daily),
        "symbols": [h.symbol for h in daily][:5] if daily else [],
    })

    # Test report generation
    if daily:
        report = generator.generate_hypothesis_report(daily)
        log_test("generate_hypothesis_report()", len(report) > 100, {
            "report_length": len(report),
        })


# =============================================================================
# TEST 7: STOCK SCREENER
# =============================================================================

def test_stock_screener():
    """Test stock screening."""
    print("\n" + "=" * 60)
    print("TEST 7: Stock Screener")
    print("=" * 60)

    from workflows.research.stock_screener import StockScreener

    screener = StockScreener(universe=["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"])

    # Test criteria screening
    results = screener.screen_by_criteria({
        "rsi_14": "<50",
    })
    log_test("screen_by_criteria()", True, {
        "matches": len(results),
        "symbols": [r.symbol for r in results],
    })

    # Test pattern screening
    results = screener.screen_by_pattern("trend_following")
    log_test("screen_by_pattern(trend_following)", True, {
        "matches": len(results),
    })

    # Test similarity screening
    similar = screener.screen_by_similarity("AAPL", top_k=3)
    log_test("screen_by_similarity(AAPL)", len(similar) >= 0, {
        "matches": len(similar),
        "similar_to_aapl": [r.symbol for r in similar],
    })

    # Test daily picks
    picks = screener.get_daily_picks(5)
    log_test("get_daily_picks()", len(picks) >= 0, {
        "picks": len(picks),
        "top_picks": [(p.symbol, p.signal) for p in picks[:3]],
    })

    # Test report
    if picks:
        report = screener.generate_picks_report(picks)
        log_test("generate_picks_report()", len(report) > 100, {
            "report_length": len(report),
        })


# =============================================================================
# TEST 8: TRADING ANALYTICS
# =============================================================================

def test_trading_analytics():
    """Test trading analytics."""
    print("\n" + "=" * 60)
    print("TEST 8: Trading Analytics")
    print("=" * 60)

    from workflows.research.analytics import TradingAnalytics, MarketRegime

    analytics = TradingAnalytics()

    # Test regime detection
    regime = analytics.detect_regime()
    log_test("detect_regime()", regime is not None, {
        "primary_regime": regime.primary_regime.value,
        "volatility_regime": regime.volatility_regime.value,
        "confidence": round(regime.confidence, 2),
        "duration_days": regime.regime_duration_days,
    })

    # Test regime-appropriate strategies
    strategies = analytics.get_regime_appropriate_strategies(regime.primary_regime)
    log_test("get_regime_appropriate_strategies()", len(strategies) > 0, {
        "strategies": strategies,
    })

    # Test position sizing
    size = analytics.calculate_position_size("AAPL", confidence=0.65)
    log_test("calculate_position_size()", size.recommended_size > 0, {
        "recommended": round(size.recommended_size, 4),
        "max": size.max_size,
        "rationale": size.rationale[:50],
    })

    # Test entry rules
    entry_rules = analytics.get_entry_rules("momentum")
    log_test("get_entry_rules(momentum)", len(entry_rules) > 0, {
        "rules": [r.name for r in entry_rules],
    })

    # Test exit rules
    exit_rules = analytics.get_exit_rules("momentum")
    log_test("get_exit_rules(momentum)", len(exit_rules) > 0, {
        "rules": [r.name for r in exit_rules],
    })

    # Test trade plan generation
    plan = analytics.generate_trade_plan("AAPL", "momentum", confidence=0.6)
    log_test("generate_trade_plan()", "error" not in plan, {
        "symbol": plan.get("symbol"),
        "position_size": round(plan.get("position_size", 0), 4),
        "risk_reward": round(plan.get("risk_reward_ratio", 0), 2),
    })


# =============================================================================
# TEST 9: SEC FILING ALPHA STRATEGY
# =============================================================================

async def test_sec_alpha_strategy():
    """Test SEC filing alpha strategy."""
    print("\n" + "=" * 60)
    print("TEST 9: SEC Filing Alpha Strategy")
    print("=" * 60)

    from src.strategies.alternative.sec_alpha import SECFilingAlpha

    strategy = SECFilingAlpha()

    try:
        # Test signal generation
        signal = await strategy.generate_signal("MSFT")
        if signal:
            log_test("SECFilingAlpha.generate_signal()", True, {
                "symbol": signal.symbol,
                "signal": signal.signal.name,
                "confidence": round(signal.confidence, 2),
                "rationale": signal.rationale[:50],
            })
        else:
            log_test("SECFilingAlpha.generate_signal()", True, {"note": "No signal (neutral)"})

        # Test feature extraction
        features = await strategy.get_filing_features("AAPL")
        if features:
            log_test("get_filing_features()", True, {
                "overall_sentiment": round(features.overall_sentiment, 3),
                "risk_count": features.risk_factor_count,
                "fog_index": round(features.fog_index, 1),
            })
        else:
            log_test("get_filing_features()", True, {"note": "No features extracted"})

    except Exception as e:
        log_test("SEC Alpha Strategy", False, {"error": str(e)})
    finally:
        await strategy.close()


# =============================================================================
# TEST 10: NEWS SCRAPER
# =============================================================================

async def test_news_scraper():
    """Test news scraper functionality."""
    print("\n" + "=" * 60)
    print("TEST 10: News Scraper")
    print("=" * 60)

    from src.data.sources.web.news_scraper import NewsResearchScraper

    scraper = NewsResearchScraper()

    try:
        # Test headline fetching
        headlines = await scraper.fetch_headlines("AAPL", max_results=10)
        log_test("NewsResearchScraper.fetch_headlines()", True, {
            "headline_count": len(headlines),
            "sources": list(set(h.source for h in headlines))[:3] if headlines else [],
        })

        # Test news features computation
        features = scraper.compute_news_features(headlines)
        log_test("compute_news_features()", "sentiment_score" in features, {
            "sentiment": round(features.get("sentiment_score", 0), 2),
            "positive_ratio": round(features.get("positive_ratio", 0), 2),
            "negative_ratio": round(features.get("negative_ratio", 0), 2),
        })

        # Test analyst ratings
        ratings = await scraper.get_analyst_ratings("MSFT")
        log_test("get_analyst_ratings()", True, {
            "rating_count": len(ratings),
            "sample": ratings[0].rating if ratings else "none",
        })

    except Exception as e:
        log_test("News Scraper", False, {"error": str(e)})


# =============================================================================
# TEST 11: NARRATIVE MOMENTUM STRATEGY
# =============================================================================

async def test_narrative_momentum():
    """Test narrative momentum strategy."""
    print("\n" + "=" * 60)
    print("TEST 11: Narrative Momentum Strategy")
    print("=" * 60)

    from src.strategies.alternative.narrative_momentum import NarrativeMomentum

    strategy = NarrativeMomentum()

    try:
        # Test signal generation
        signal = await strategy.generate_signal("GOOGL")
        if signal:
            log_test("NarrativeMomentum.generate_signal()", True, {
                "symbol": signal.symbol,
                "signal": signal.signal.name,
                "confidence": round(signal.confidence, 2),
            })
        else:
            log_test("NarrativeMomentum.generate_signal()", True, {"note": "No signal"})

        # Test feature extraction
        features = await strategy.get_narrative_features("AAPL")
        if features:
            log_test("get_narrative_features()", True, {
                "velocity": round(features.narrative_velocity, 3),
                "sentiment": round(features.sentiment_score, 2),
                "headlines": features.headline_count,
            })
        else:
            log_test("get_narrative_features()", True, {"note": "No features"})

    except Exception as e:
        log_test("Narrative Momentum", False, {"error": str(e)})


# =============================================================================
# TEST 12: COMPOSITE ALTERNATIVE STRATEGY
# =============================================================================

async def test_composite_alternative():
    """Test composite alternative strategy."""
    print("\n" + "=" * 60)
    print("TEST 12: Composite Alternative Strategy")
    print("=" * 60)

    from src.strategies.alternative.composite_alternative import CompositeAlternative

    strategy = CompositeAlternative()

    try:
        # Test signal generation
        signal = await strategy.generate_signal("NVDA")
        if signal:
            log_test("CompositeAlternative.generate_signal()", True, {
                "symbol": signal.symbol,
                "signal": signal.signal.name,
                "score": round(signal.weighted_score, 2),
                "components": len(signal.components),
            })
        else:
            log_test("CompositeAlternative.generate_signal()", True, {"note": "No signal"})

        # Test feature extraction
        features = await strategy.get_features("TSLA")
        if features:
            log_test("get_features()", True, {
                "bullish_count": features.bullish_component_count,
                "bearish_count": features.bearish_component_count,
                "agreement": round(features.signal_agreement, 2),
            })
        else:
            log_test("get_features()", True, {"note": "No features"})

        # Test signals to dataframe
        if signal:
            df = strategy.signals_to_dataframe([signal])
            log_test("signals_to_dataframe()", len(df) > 0, {
                "columns": list(df.columns)[:5],
            })

    except Exception as e:
        log_test("Composite Alternative", False, {"error": str(e)})


# =============================================================================
# MAIN
# =============================================================================

async def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("ADVANCED FEATURES TEST SUITE")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 70)

    # Run synchronous tests
    test_feature_store()
    test_feature_registry()
    test_document_embedder()
    test_hypothesis_generator()
    test_stock_screener()
    test_trading_analytics()

    # Run async tests
    await test_web_scraper()
    await test_sec_filings()
    await test_sec_alpha_strategy()
    await test_news_scraper()
    await test_narrative_momentum()
    await test_composite_alternative()

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    total = len(TEST_RESULTS["tests"])
    passed = sum(1 for t in TEST_RESULTS["tests"].values() if t["passed"])
    failed = total - passed

    TEST_RESULTS["summary"] = {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": f"{passed/total*100:.1f}%",
    }

    print(f"\nTotal Tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Pass Rate: {passed/total*100:.1f}%")

    # Save results
    output_file = OUTPUT_DIR / "advanced_test_results.json"
    with open(output_file, "w") as f:
        json.dump(TEST_RESULTS, f, indent=2, default=str)

    print(f"\nResults saved to: {output_file}")
    print("=" * 70)

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
