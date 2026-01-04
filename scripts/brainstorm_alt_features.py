#!/usr/bin/env python3
"""
Brainstorm Agent: Generate new ALTERNATIVE data feature ideas.

This script generates 3 new feature ideas for the ALTERNATIVE domain
and logs them to the session tracker.
"""

import sys
sys.path.insert(0, '/home/nock/projects/quant_suite')

from workflows.research.session_tracker import get_tracker

# Initialize the session tracker
tracker = get_tracker()

# =============================================================================
# NEW ALTERNATIVE DATA FEATURE IDEAS
# =============================================================================

# These features fill gaps in the current ALTERNATIVE domain coverage:
# - Existing: google_trends, short_interest, insider_transactions, finbert,
#             earnings_calls, patents, job_postings
# - Missing: web traffic, dark pool activity, options unusual activity,
#            supply chain data, ESG events, congressional trading

NEW_ALTERNATIVE_FEATURES = [
    {
        "title": "Congressional Trading Signal",
        "description": """
Feature: congress_trade_momentum
Domain: ALTERNATIVE

Description: Tracks buy/sell activity from members of Congress using mandatory
disclosure filings (STOCK Act data). Measures the aggregate direction and
magnitude of insider congressional trading in a specific stock over the past
30 days.

Formula: sum(buy_value - sell_value) / sum(buy_value + sell_value)
Range: -1.0 (net selling) to +1.0 (net buying)

Rationale: Congressional members often have advance knowledge of legislation,
contracts, and regulatory decisions that impact specific companies. Academic
studies have shown that congressional portfolios outperform the market by
5-6% annually. This feature captures potential information asymmetry from
legally disclosed congressional trading activity.

Data Requirements:
- STOCK Act disclosure data (free from House/Senate websites)
- Daily aggregation of buys/sells by stock
- 30-day rolling window calculation

Priority: HIGH - Free data, strong theoretical backing, low correlation with
existing alternative features.

Implementation Notes:
- Data available from housestockwatcher.com or senatestockwatcher.com APIs
- Focus on trades >$15K (more likely to be intentional)
- Consider party affiliation for sector-specific signal strength
""",
        "category": "feature",
        "evidence": {
            "rationale": "Congressional trading outperforms market by 5-6% annually per academic studies",
            "data_source": "STOCK Act mandatory disclosures (free)",
            "theoretical_basis": "Information asymmetry from legislative knowledge",
            "correlation_with_existing": "Low - no existing congressional/political features"
        },
        "tags": ["brainstorm", "alternative", "feature", "congressional", "political"]
    },
    {
        "title": "Dark Pool Activity Ratio",
        "description": """
Feature: dark_pool_activity_zscore
Domain: ALTERNATIVE

Description: Measures unusual dark pool trading volume relative to lit exchange
volume. High dark pool activity often indicates institutional accumulation or
distribution before major price moves.

Formula: (dark_pool_volume / total_volume) - rolling_mean(ratio, 20) / rolling_std(ratio, 20)
Range: Z-score (typically -3 to +3)

Rationale: Dark pools allow institutions to execute large orders without
revealing their intentions. Unusual spikes in dark pool ratio often precede
significant moves:
- High dark pool buying = accumulation before breakout
- High dark pool selling = distribution before breakdown

Data Requirements:
- FINRA ADF/TRF data (short sale volume as proxy, free)
- Or paid APIs: IEX Cloud, Quandl, Bloomberg

Priority: HIGH - Captures institutional activity invisible in regular volume.
Strong signal for large-cap stocks with active institutional ownership.

Implementation Notes:
- Use FINRA short volume as proxy (free, released daily)
- Calculate ratio: short_exempt_volume / total_volume
- High ratio + price increase = potential short squeeze setup
- Focus on stocks with >50% institutional ownership
""",
        "category": "feature",
        "evidence": {
            "rationale": "Dark pool activity reveals institutional intentions before public moves",
            "data_source": "FINRA ADF data (free) or IEX Cloud API (paid)",
            "theoretical_basis": "Information asymmetry from institutional order flow",
            "correlation_with_existing": "Low - complements short_interest with flow data"
        },
        "tags": ["brainstorm", "alternative", "feature", "dark_pool", "institutional"]
    },
    {
        "title": "Supply Chain Disruption Score",
        "description": """
Feature: supply_chain_stress_index
Domain: ALTERNATIVE

Description: Composite score measuring supply chain health for a company based
on supplier/customer financial stress, shipping delays, and input cost changes.
Early warning system for earnings surprises.

Formula: weighted_average(
    supplier_stress_score * 0.4,
    shipping_delay_index * 0.3,
    input_cost_change * 0.3
)
Range: 0 (healthy) to 100 (severe stress)

Rationale: Supply chain issues typically impact companies 1-2 quarters before
appearing in earnings. This feature captures:
- Credit default swap spreads of major suppliers (financial stress)
- Baltic Dry Index / container shipping rates (logistics)
- Commodity input costs (raw material inflation)

Data Requirements:
- Company supplier lists (10-K filings, FactSet relationships)
- Baltic Dry Index (free from investing.com)
- CDS spreads for major suppliers (Bloomberg, ICE)
- Commodity futures for key inputs (free from Yahoo Finance)

Priority: MEDIUM-HIGH - Requires company-specific customization but provides
unique forward-looking signal not captured by any existing feature.

Implementation Notes:
- Start with sector ETFs (XLK, XLE, XLI) as proxies
- Use Markit iTraxx for sector credit stress
- Baltic Dry Index for shipping-sensitive companies
- Focus on manufacturing, retail, and consumer discretionary
""",
        "category": "feature",
        "evidence": {
            "rationale": "Supply chain issues precede earnings surprises by 1-2 quarters",
            "data_source": "Baltic Dry Index (free), CDS spreads (paid), commodity futures (free)",
            "theoretical_basis": "Operational risk propagation through supply networks",
            "correlation_with_existing": "Low - no existing supply chain or credit features"
        },
        "tags": ["brainstorm", "alternative", "feature", "supply_chain", "macro"]
    }
]


def main():
    """Log the 3 new alternative data feature ideas to the session tracker."""
    print("=" * 60)
    print("BRAINSTORM SESSION: ALTERNATIVE DATA FEATURES")
    print("=" * 60)
    print()

    logged_insights = []

    for i, feature in enumerate(NEW_ALTERNATIVE_FEATURES, 1):
        print(f"{i}. {feature['title']}")
        print("-" * 40)

        # Log to session tracker
        insight = tracker.log_insight(
            title=feature['title'],
            description=feature['description'],
            category=feature['category'],
            evidence=feature['evidence'],
            session_id="brainstorm_alt_features_2026_01_03",
            tags=feature['tags'],
            confidence=0.7,  # Medium-high confidence, needs validation
        )

        logged_insights.append(insight)
        print(f"   Logged as: {insight.id}")
        print(f"   Category: {insight.category}")
        print(f"   Confidence: {insight.confidence}")
        print(f"   Tags: {', '.join(insight.tags)}")
        print()

    print("=" * 60)
    print("BRAINSTORM SESSION SUMMARY")
    print("=" * 60)
    print(f"Focus: ALTERNATIVE data domain")
    print(f"New Feature Ideas Generated: {len(logged_insights)}")
    print()
    print("NEW FEATURE IDEAS:")
    print("1. Congressional Trading Signal (congress_trade_momentum)")
    print("   - Priority: HIGH")
    print("   - Data: Free STOCK Act disclosures")
    print()
    print("2. Dark Pool Activity Ratio (dark_pool_activity_zscore)")
    print("   - Priority: HIGH")
    print("   - Data: Free FINRA ADF data")
    print()
    print("3. Supply Chain Disruption Score (supply_chain_stress_index)")
    print("   - Priority: MEDIUM-HIGH")
    print("   - Data: Mix of free/paid sources")
    print()
    print("NEXT STEPS:")
    print("1. Test congress_trade_momentum with research-agent")
    print("2. Implement dark_pool_activity_zscore using FINRA data")
    print("3. Build supply_chain_stress_index prototype for tech sector")
    print("4. Validate with critic-agent before production")
    print()
    print(f"All {len(logged_insights)} insights logged to session tracker.")
    print(f"Storage: /home/nock/quant_results/research_tracker/insights.json")

    # Show summary from tracker
    report = tracker.generate_summary_report()
    print()
    print("=" * 60)
    print("SESSION TRACKER STATUS")
    print("=" * 60)
    print(f"Total Insights: {report['totals']['insights']}")
    print(f"Total Experiments: {report['totals']['experiments']}")
    print(f"Actionable Insights: {report['actionable_insights']}")


if __name__ == "__main__":
    main()
