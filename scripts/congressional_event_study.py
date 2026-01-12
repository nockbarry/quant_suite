#!/usr/bin/env python3
"""Congressional Trading Event Study - Comprehensive Historical Analysis.

Analyzes whether congressional trades predict future market movements using
pre-computed event study data from GitHub (adrianmross/congress_trades_dashboard).

Key Questions:
1. Do politicians trade BEFORE positive/negative news? (pre-disclosure drift)
2. Does the move continue AFTER disclosure? (post-disclosure drift)
3. Is there exploitable alpha following congressional trades?
4. Which sectors show the strongest predictive signal?

Data Sources:
- GitHub: adrianmross/congress_trades_dashboard (2020-2023 data)
- GitHub: noodleslove/House-of-Representative-Analysis-I (2020-2022 data)

Usage:
    PYTHONPATH=. python scripts/congressional_event_study.py
    PYTHONPATH=. python scripts/congressional_event_study.py --report
"""

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.core.paths import paths

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def load_event_study_data(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load purchase and sell impact data."""

    purchase_path = data_dir / "purchase_impact.csv"
    sell_path = data_dir / "sell_impact.csv"

    if not purchase_path.exists() or not sell_path.exists():
        raise FileNotFoundError(f"Data files not found in {data_dir}. Run download first.")

    logger.info(f"Loading data from {data_dir}")

    purchases = pd.read_csv(purchase_path)
    sells = pd.read_csv(sell_path)

    # Parse dates
    purchases['disclosure_date'] = pd.to_datetime(purchases['disclosure_date'])
    purchases['date'] = pd.to_datetime(purchases['date'])
    sells['disclosure_date'] = pd.to_datetime(sells['disclosure_date'])
    sells['date'] = pd.to_datetime(sells['date'])

    logger.info(f"Loaded {len(purchases)} purchase events, {len(sells)} sell events")

    return purchases, sells


def analyze_event_window(df: pd.DataFrame, trade_type: str) -> dict[str, Any]:
    """Analyze returns around disclosure events.

    trading_days_before_after:
    - Negative = days BEFORE disclosure (stock moved before public knew)
    - Zero = disclosure day
    - Positive = days AFTER disclosure
    """

    results = {
        "trade_type": trade_type,
        "total_events": df['disclosure_date'].nunique(),
        "total_observations": len(df),
    }

    # Group by event window
    window_returns = df.groupby('trading_days_before_after')['daily_return'].agg(['mean', 'std', 'count'])
    window_returns.columns = ['mean_return', 'std_return', 'count']

    # Pre-disclosure drift (days -7 to -1)
    pre_disclosure = df[df['trading_days_before_after'].between(-7, -1)]
    if len(pre_disclosure) > 0:
        pre_cum_return = pre_disclosure.groupby('disclosure_date')['daily_return'].sum().mean()
        results['pre_disclosure_drift_7d'] = pre_cum_return * 100  # Convert to percentage
    else:
        results['pre_disclosure_drift_7d'] = 0

    # Disclosure day (day 0)
    disclosure_day = df[df['trading_days_before_after'] == 0]
    if len(disclosure_day) > 0:
        results['disclosure_day_return'] = disclosure_day['daily_return'].mean() * 100
    else:
        results['disclosure_day_return'] = 0

    # Post-disclosure drift - various windows
    for window in [5, 10, 20, 30]:
        post = df[df['trading_days_before_after'].between(1, window)]
        if len(post) > 0:
            post_cum = post.groupby('disclosure_date')['daily_return'].sum().mean()
            results[f'post_disclosure_drift_{window}d'] = post_cum * 100
        else:
            results[f'post_disclosure_drift_{window}d'] = 0

    # Total event return (day -7 to day +30)
    total = df[df['trading_days_before_after'].between(-7, 30)]
    if len(total) > 0:
        total_cum = total.groupby('disclosure_date')['daily_return'].sum().mean()
        results['total_event_return'] = total_cum * 100
    else:
        results['total_event_return'] = 0

    # Statistical significance
    # Test if pre-disclosure returns are significantly different from zero
    pre_returns = pre_disclosure.groupby('disclosure_date')['daily_return'].sum()
    if len(pre_returns) > 30:  # Need enough samples
        from scipy import stats
        t_stat, p_value = stats.ttest_1samp(pre_returns, 0)
        results['pre_disclosure_t_stat'] = t_stat
        results['pre_disclosure_p_value'] = p_value
        results['pre_disclosure_significant'] = p_value < 0.05

    return results


def analyze_by_sector(df: pd.DataFrame, trade_type: str) -> pd.DataFrame:
    """Analyze returns by sector."""

    sector_results = []

    for sector in df['sector'].dropna().unique():
        sector_df = df[df['sector'] == sector]

        # Pre-disclosure drift
        pre = sector_df[sector_df['trading_days_before_after'].between(-7, -1)]
        if len(pre) > 100:  # Minimum sample size
            pre_drift = pre.groupby('disclosure_date')['daily_return'].sum().mean() * 100

            # Post-disclosure drift
            post = sector_df[sector_df['trading_days_before_after'].between(1, 20)]
            post_drift = post.groupby('disclosure_date')['daily_return'].sum().mean() * 100 if len(post) > 0 else 0

            n_events = sector_df['disclosure_date'].nunique()

            sector_results.append({
                'sector': sector,
                'trade_type': trade_type,
                'n_events': n_events,
                'pre_disclosure_drift': pre_drift,
                'post_disclosure_drift_20d': post_drift,
                'total_drift': pre_drift + post_drift,
            })

    return pd.DataFrame(sector_results)


def analyze_information_advantage(purchases: pd.DataFrame, sells: pd.DataFrame) -> dict[str, Any]:
    """
    Test for information advantage:
    - If politicians have insider knowledge, we expect:
      - Buys: positive pre-disclosure drift (stock rises before disclosure)
      - Sells: negative pre-disclosure drift (stock falls before disclosure)
    """

    results = {}

    # For purchases: do stocks go UP before disclosure?
    purchase_pre = purchases[purchases['trading_days_before_after'].between(-7, -1)]
    purchase_pre_returns = purchase_pre.groupby('disclosure_date')['daily_return'].sum()

    results['purchase_pre_drift_mean'] = purchase_pre_returns.mean() * 100
    results['purchase_pre_drift_positive_pct'] = (purchase_pre_returns > 0).mean() * 100

    # For sells: do stocks go DOWN before disclosure?
    sell_pre = sells[sells['trading_days_before_after'].between(-7, -1)]
    sell_pre_returns = sell_pre.groupby('disclosure_date')['daily_return'].sum()

    results['sell_pre_drift_mean'] = sell_pre_returns.mean() * 100
    results['sell_pre_drift_negative_pct'] = (sell_pre_returns < 0).mean() * 100

    # Combined signal: buy pre-drift minus sell pre-drift
    # If positive, they're timing the market correctly
    results['timing_advantage'] = results['purchase_pre_drift_mean'] - results['sell_pre_drift_mean']

    # Post-disclosure following signal
    purchase_post = purchases[purchases['trading_days_before_after'].between(1, 20)]
    purchase_post_returns = purchase_post.groupby('disclosure_date')['daily_return'].sum()

    sell_post = sells[sells['trading_days_before_after'].between(1, 20)]
    sell_post_returns = sell_post.groupby('disclosure_date')['daily_return'].sum()

    results['purchase_post_drift_mean'] = purchase_post_returns.mean() * 100
    results['sell_post_drift_mean'] = sell_post_returns.mean() * 100

    # Exploitable alpha: if you follow congressional trades on disclosure
    # Buy what they bought, short what they sold
    # Expected return = buy_post_return - sell_post_return
    results['following_strategy_return'] = results['purchase_post_drift_mean'] - results['sell_post_drift_mean']

    return results


def generate_report(
    purchase_analysis: dict,
    sell_analysis: dict,
    info_advantage: dict,
    purchase_by_sector: pd.DataFrame,
    sell_by_sector: pd.DataFrame,
    output_dir: Path,
) -> str:
    """Generate comprehensive event study report."""

    report = f"""
# Congressional Trading Event Study

**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Data Source:** adrianmross/congress_trades_dashboard (GitHub)

---

## Executive Summary

This study analyzes {purchase_analysis['total_events']:,} purchase events and {sell_analysis['total_events']:,} sell events
to determine if congressional trades contain predictive information.

### Key Findings

| Metric | Purchases | Sales |
|--------|-----------|-------|
| Pre-disclosure drift (7d) | {purchase_analysis['pre_disclosure_drift_7d']:+.3f}% | {sell_analysis['pre_disclosure_drift_7d']:+.3f}% |
| Disclosure day return | {purchase_analysis['disclosure_day_return']:+.3f}% | {sell_analysis['disclosure_day_return']:+.3f}% |
| Post-disclosure drift (5d) | {purchase_analysis['post_disclosure_drift_5d']:+.3f}% | {sell_analysis['post_disclosure_drift_5d']:+.3f}% |
| Post-disclosure drift (20d) | {purchase_analysis['post_disclosure_drift_20d']:+.3f}% | {sell_analysis['post_disclosure_drift_20d']:+.3f}% |
| Total event return (-7 to +30d) | {purchase_analysis['total_event_return']:+.3f}% | {sell_analysis['total_event_return']:+.3f}% |

---

## 1. Information Advantage Analysis

**Key Question:** Do politicians trade BEFORE stocks move in their favor?

| Metric | Value | Interpretation |
|--------|-------|----------------|
| Purchase pre-drift (7d before) | {info_advantage['purchase_pre_drift_mean']:+.3f}% | {"Positive = Bought before rise" if info_advantage['purchase_pre_drift_mean'] > 0 else "Negative = Bought before fall"} |
| Purchase pre-drift positive % | {info_advantage['purchase_pre_drift_positive_pct']:.1f}% | {"Above 50% = Good timing" if info_advantage['purchase_pre_drift_positive_pct'] > 50 else "Below 50% = Poor timing"} |
| Sell pre-drift (7d before) | {info_advantage['sell_pre_drift_mean']:+.3f}% | {"Negative = Sold before fall" if info_advantage['sell_pre_drift_mean'] < 0 else "Positive = Sold before rise"} |
| Sell pre-drift negative % | {info_advantage['sell_pre_drift_negative_pct']:.1f}% | {"Above 50% = Good timing" if info_advantage['sell_pre_drift_negative_pct'] > 50 else "Below 50% = Poor timing"} |
| **Combined Timing Advantage** | {info_advantage['timing_advantage']:+.3f}% | {"Positive = Info advantage exists" if info_advantage['timing_advantage'] > 0 else "No clear advantage"} |

### Interpretation

"""

    if info_advantage['timing_advantage'] > 0.5:
        report += """
**EVIDENCE OF INFORMATION ADVANTAGE DETECTED**

Politicians appear to be trading with material non-public information:
- Purchases precede stock rises
- Sales precede stock falls
- This creates a combined timing advantage of {:.2f}% over 7 trading days

This suggests congressional trades may be predictive of future price movements.
""".format(info_advantage['timing_advantage'])
    elif info_advantage['timing_advantage'] > 0:
        report += """
**MARGINAL INFORMATION ADVANTAGE**

There is weak evidence of informed trading:
- Small positive timing advantage: {:.3f}%
- May not be statistically significant
- Could be explained by sector selection or market timing
""".format(info_advantage['timing_advantage'])
    else:
        report += """
**NO CLEAR INFORMATION ADVANTAGE**

Politicians do not appear to have significant timing advantage:
- Combined timing advantage is negative or near zero
- Congressional trades may not be predictive
"""

    report += f"""
---

## 2. Post-Disclosure Exploitability

**Key Question:** Can we profit by following congressional trades AFTER they're disclosed?

| Strategy | 20-day Return | Interpretation |
|----------|---------------|----------------|
| Buy after purchase disclosure | {info_advantage['purchase_post_drift_mean']:+.3f}% | {"Profitable" if info_advantage['purchase_post_drift_mean'] > 0 else "Not profitable"} |
| Sell after sale disclosure | {info_advantage['sell_post_drift_mean']:+.3f}% | {"Profitable" if info_advantage['sell_post_drift_mean'] < 0 else "Not profitable"} |
| **Long/Short Strategy** | {info_advantage['following_strategy_return']:+.3f}% | {"Alpha exists" if info_advantage['following_strategy_return'] > 0 else "No alpha"} |

### Trading Implications

"""

    if info_advantage['following_strategy_return'] > 0.5:
        report += f"""
**EXPLOITABLE ALPHA EXISTS**

A strategy that:
1. Buys stocks that congress purchased (on disclosure)
2. Shorts stocks that congress sold (on disclosure)

Would generate approximately **{info_advantage['following_strategy_return']:.2f}% return per event over 20 days**.

Annualized (assuming 12 events/year): **{info_advantage['following_strategy_return'] * 12:.1f}% annual alpha**
"""
    else:
        report += """
**LIMITED EXPLOITABILITY**

Post-disclosure returns do not offer clear alpha:
- Market may already be pricing in the information
- Transaction costs would likely eliminate any edge
"""

    report += """
---

## 3. Sector Analysis

### Purchases by Sector (Ranked by Total Drift)

| Sector | Events | Pre-Drift | Post-Drift (20d) | Total |
|--------|--------|-----------|------------------|-------|
"""

    purchase_sectors = purchase_by_sector.sort_values('total_drift', ascending=False)
    for _, row in purchase_sectors.head(10).iterrows():
        report += f"| {row['sector']} | {row['n_events']} | {row['pre_disclosure_drift']:+.2f}% | {row['post_disclosure_drift_20d']:+.2f}% | {row['total_drift']:+.2f}% |\n"

    report += """
### Sales by Sector (Ranked by Total Drift - most negative first)

| Sector | Events | Pre-Drift | Post-Drift (20d) | Total |
|--------|--------|-----------|------------------|-------|
"""

    sell_sectors = sell_by_sector.sort_values('total_drift', ascending=True)
    for _, row in sell_sectors.head(10).iterrows():
        report += f"| {row['sector']} | {row['n_events']} | {row['pre_disclosure_drift']:+.2f}% | {row['post_disclosure_drift_20d']:+.2f}% | {row['total_drift']:+.2f}% |\n"

    report += """
---

## 4. Recommendations for Trading System

### Immediate Actions

1. **Archive Daily Congressional Trades**
   - Set up daily collection from House/Senate Stock Watcher RSS
   - Store with transaction_date and disclosure_date
   - This builds our proprietary historical dataset

2. **Build Disclosure Alert System**
   - Alert on new disclosures for active positions
   - Alert on cluster buying (3+ politicians same stock)
   - Alert on notable trader activity (Pelosi, Tuberville, etc.)

3. **Integrate into Signal Aggregator**
   - Add congressional signal to unified state
   - Weight based on: cluster size, notable traders, sector relevance

### Research Extensions

1. **Committee-Stock Correlation**
   - Do Armed Services members outperform in defense stocks?
   - Do Finance Committee members outperform in banking?

2. **Filing Delay Analysis**
   - Do longer delays (15-45 days) correlate with larger pre-disclosure moves?
   - This would indicate intentional delay to exploit information

3. **Cross-Reference with News**
   - Match congressional trades to subsequent news events
   - Identify what type of information they're trading on

---

## Technical Notes

- Pre-disclosure period: 7 trading days before disclosure
- Post-disclosure periods: 5, 10, 20, 30 trading days after
- Returns are daily log returns
- Cumulative returns calculated per disclosure event then averaged

"""

    return report


def run_event_study(data_dir: Path | None = None, output_dir: Path | None = None) -> dict[str, Any]:
    """Run comprehensive event study analysis."""

    data_dir = data_dir or paths.base / "congressional_study" / "raw_data"
    output_dir = output_dir or paths.base / "congressional_study"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    purchases, sells = load_event_study_data(data_dir)

    logger.info("Analyzing purchase events...")
    purchase_analysis = analyze_event_window(purchases, "purchase")

    logger.info("Analyzing sell events...")
    sell_analysis = analyze_event_window(sells, "sell")

    logger.info("Analyzing information advantage...")
    info_advantage = analyze_information_advantage(purchases, sells)

    logger.info("Analyzing by sector...")
    purchase_by_sector = analyze_by_sector(purchases, "purchase")
    sell_by_sector = analyze_by_sector(sells, "sell")

    # Generate report
    report = generate_report(
        purchase_analysis,
        sell_analysis,
        info_advantage,
        purchase_by_sector,
        sell_by_sector,
        output_dir,
    )

    # Save report
    report_path = output_dir / "event_study_report.md"
    with open(report_path, 'w') as f:
        f.write(report)
    logger.info(f"Report saved to {report_path}")

    # Save results as JSON
    results = {
        "generated": datetime.now().isoformat(),
        "purchase_analysis": purchase_analysis,
        "sell_analysis": sell_analysis,
        "information_advantage": info_advantage,
        "purchase_by_sector": purchase_by_sector.to_dict('records'),
        "sell_by_sector": sell_by_sector.to_dict('records'),
    }

    results_path = output_dir / "event_study_results.json"
    with open(results_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    logger.info(f"Results saved to {results_path}")

    # Print summary
    print("\n" + "=" * 70)
    print("CONGRESSIONAL TRADING EVENT STUDY - SUMMARY")
    print("=" * 70)
    print(f"\nPurchase events analyzed: {purchase_analysis['total_events']:,}")
    print(f"Sell events analyzed: {sell_analysis['total_events']:,}")

    print("\n📊 KEY FINDINGS:")
    print(f"  Pre-disclosure timing advantage: {info_advantage['timing_advantage']:+.3f}%")
    print(f"  Post-disclosure following alpha: {info_advantage['following_strategy_return']:+.3f}%")

    if info_advantage['timing_advantage'] > 0.5:
        print("\n  ⚠️  EVIDENCE OF INFORMATION ADVANTAGE DETECTED")

    if info_advantage['following_strategy_return'] > 0.5:
        print("  ✅ EXPLOITABLE ALPHA EXISTS (post-disclosure following)")

    print(f"\n📁 Full report: {report_path}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Congressional Trading Event Study")
    parser.add_argument("--data-dir", type=str, help="Directory with event study data")
    parser.add_argument("--output", type=str, help="Output directory")
    parser.add_argument("--report", action="store_true", help="Generate full report")

    args = parser.parse_args()

    data_dir = Path(args.data_dir) if args.data_dir else None
    output_dir = Path(args.output) if args.output else None

    run_event_study(data_dir=data_dir, output_dir=output_dir)


if __name__ == "__main__":
    main()
