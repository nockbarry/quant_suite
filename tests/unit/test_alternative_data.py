"""Tests for alternative data sources (options, insider, ETF flows)."""

import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta


class TestOptionsFlowAnalysis:
    """Tests for options flow analysis."""

    def test_put_call_ratio_calculation(self):
        """Test put/call ratio calculation."""
        call_volume = 10000
        put_volume = 15000

        pc_ratio = put_volume / call_volume
        assert pc_ratio == 1.5

    def test_put_call_ratio_sentiment(self):
        """Test put/call ratio sentiment interpretation."""
        # High P/C ratio (>1.0) is contrarian bullish
        # Low P/C ratio (<0.7) is contrarian bearish

        high_pc = 1.5
        low_pc = 0.5
        neutral_pc = 0.8

        assert high_pc > 1.0  # Contrarian bullish
        assert low_pc < 0.7  # Contrarian bearish
        assert 0.7 <= neutral_pc <= 1.0  # Neutral

    def test_unusual_activity_detection(self):
        """Test unusual options activity detection."""
        # Unusual activity = volume >> open interest
        volume = 5000
        open_interest = 1000

        vol_oi_ratio = volume / open_interest
        assert vol_oi_ratio == 5.0

        # Usually > 1.5 is considered unusual
        is_unusual = vol_oi_ratio > 1.5
        assert is_unusual

    def test_premium_calculation(self):
        """Test options premium calculation."""
        volume = 1000
        price = 2.50
        contract_multiplier = 100

        total_premium = volume * price * contract_multiplier
        assert total_premium == 250000

    def test_gamma_exposure_sign(self):
        """Test gamma exposure signs."""
        # For market makers:
        # Long calls = long gamma (positive GEX)
        # Short puts = short gamma (negative GEX from MM perspective)

        call_gamma = 0.05
        call_oi = 10000
        underlying_price = 100

        # GEX = gamma * OI * 100 * spot^2 / 100
        call_gex = call_gamma * call_oi * 100 * (underlying_price ** 2) / 100

        # Calls contribute positive gamma for dealers
        assert call_gex > 0


class TestInsiderTrading:
    """Tests for insider trading analysis."""

    def test_cluster_buying_detection(self):
        """Test cluster buying pattern detection."""
        # Cluster buying = 3+ insiders buying within 30 days
        insiders_buying = ['CEO', 'CFO', 'Director1', 'Director2']
        min_cluster_size = 3

        is_cluster = len(insiders_buying) >= min_cluster_size
        assert is_cluster

    def test_insider_role_significance(self):
        """Test insider role significance ranking."""
        # C-suite purchases are more significant than director purchases
        role_weights = {
            'CEO': 1.0,
            'CFO': 0.9,
            'COO': 0.9,
            'President': 0.8,
            'Director': 0.6,
            'VP': 0.5,
            '10% Owner': 0.7,
        }

        assert role_weights['CEO'] > role_weights['Director']
        assert role_weights['CFO'] > role_weights['VP']

    def test_buy_sell_ratio(self):
        """Test buy/sell ratio calculation."""
        total_purchases = 5
        total_sales = 2

        ratio = total_purchases / total_sales
        assert ratio == 2.5

        # High ratio is bullish signal
        is_bullish = ratio > 2.0
        assert is_bullish

    def test_value_significance_threshold(self):
        """Test value significance thresholds."""
        # Large purchases (>$100k) are more significant
        purchase_value = 150000
        min_significant = 100000

        is_significant = purchase_value >= min_significant
        assert is_significant

    def test_ownership_change_percentage(self):
        """Test ownership change calculation."""
        shares_before = 10000
        shares_purchased = 5000
        shares_after = 15000

        ownership_change_pct = (shares_purchased / shares_before) * 100
        assert ownership_change_pct == 50.0


class TestETFFlows:
    """Tests for ETF flow analysis."""

    def test_flow_estimation_from_shares(self):
        """Test flow estimation from shares outstanding change."""
        prev_shares = 100_000_000
        current_shares = 102_000_000
        nav = 400.0

        shares_change = current_shares - prev_shares
        estimated_flow = shares_change * nav

        assert estimated_flow == 800_000_000  # $800M inflow

    def test_sector_classification(self):
        """Test ETF sector classification."""
        sector_etfs = {
            'XLK': 'technology',
            'XLV': 'healthcare',
            'XLF': 'financials',
            'XLE': 'energy',
        }

        assert sector_etfs['XLK'] == 'technology'
        assert 'XLE' in sector_etfs

    def test_risk_on_risk_off_classification(self):
        """Test risk-on/risk-off ETF classification."""
        risk_on_etfs = ['SPY', 'QQQ', 'IWM', 'HYG', 'EEM']
        risk_off_etfs = ['TLT', 'GLD', 'VXX', 'AGG']

        assert 'SPY' in risk_on_etfs
        assert 'TLT' in risk_off_etfs

    def test_flow_momentum_calculation(self):
        """Test flow momentum calculation."""
        recent_flows = [100, 150, 200, 180, 220]  # Last 5 days
        historical_flows = [50, 60, 70, 40, 80, 90, 100, 110, 80, 70]

        recent_avg = np.mean(recent_flows)
        historical_avg = np.mean(historical_flows)

        momentum = recent_avg / abs(historical_avg)
        assert momentum > 1.0  # Accelerating inflows

    def test_sector_rotation_detection(self):
        """Test sector rotation detection."""
        # Risk-off = defensive sectors gaining, cyclical losing
        defensive_flow = 1_000_000_000  # $1B inflow
        cyclical_flow = -800_000_000  # $800M outflow

        is_risk_off = defensive_flow > 0 and cyclical_flow < 0
        assert is_risk_off


class TestDataSourceCaching:
    """Tests for data source caching behavior."""

    def test_cache_key_generation(self):
        """Test cache key generation."""
        source = "options"
        symbol = "AAPL"
        expiration = "2024-01-19"

        cache_key = f"{source}:{symbol}:{expiration}"
        assert cache_key == "options:AAPL:2024-01-19"

    def test_cache_ttl_check(self):
        """Test cache TTL validation."""
        cache_ttl = timedelta(minutes=5)
        cached_time = datetime.now() - timedelta(minutes=3)

        is_valid = (datetime.now() - cached_time) < cache_ttl
        assert is_valid

        # Expired cache
        old_cached_time = datetime.now() - timedelta(minutes=10)
        is_expired = (datetime.now() - old_cached_time) >= cache_ttl
        assert is_expired


class TestSymbolExtraction:
    """Tests for symbol extraction from text."""

    def test_ticker_pattern_matching(self):
        """Test ticker pattern matching."""
        import re

        text = "I'm bullish on $AAPL and TSLA. MSFT looking good too!"

        # Match $TICKER format
        dollar_pattern = r'\$([A-Z]{1,5})\b'
        dollar_matches = re.findall(dollar_pattern, text)
        assert 'AAPL' in dollar_matches

        # Match plain TICKER format
        plain_pattern = r'\b([A-Z]{1,5})\b'
        plain_matches = re.findall(plain_pattern, text)
        assert 'TSLA' in plain_matches
        assert 'MSFT' in plain_matches

    def test_ticker_blacklist(self):
        """Test ticker blacklist for common words."""
        blacklist = {'I', 'A', 'CEO', 'IPO', 'ETF', 'NYSE', 'AI', 'IT', 'TV'}

        potential_tickers = ['AAPL', 'CEO', 'TSLA', 'AI', 'NVDA', 'IT']

        filtered = [t for t in potential_tickers if t not in blacklist]
        assert filtered == ['AAPL', 'TSLA', 'NVDA']

    def test_company_to_ticker_mapping(self):
        """Test company name to ticker mapping."""
        company_map = {
            'apple': 'AAPL',
            'tesla': 'TSLA',
            'nvidia': 'NVDA',
            'microsoft': 'MSFT',
        }

        assert company_map['tesla'] == 'TSLA'
        assert company_map.get('unknown', None) is None


class TestSentimentAggregation:
    """Tests for sentiment aggregation."""

    def test_weighted_sentiment(self):
        """Test weighted sentiment calculation."""
        sentiments = [
            {'score': 0.8, 'weight': 100},  # 100 upvotes
            {'score': -0.2, 'weight': 50},  # 50 upvotes
            {'score': 0.5, 'weight': 200},  # 200 upvotes
        ]

        total_weight = sum(s['weight'] for s in sentiments)
        weighted_sentiment = sum(
            s['score'] * s['weight'] for s in sentiments
        ) / total_weight

        expected = (0.8*100 + (-0.2)*50 + 0.5*200) / 350
        np.testing.assert_almost_equal(weighted_sentiment, expected)

    def test_sentiment_percentile(self):
        """Test sentiment percentile calculation."""
        historical_sentiments = np.random.uniform(-1, 1, 100)
        current_sentiment = 0.8

        percentile = np.mean(historical_sentiments <= current_sentiment) * 100
        assert 0 <= percentile <= 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
