#!/usr/bin/env python3
"""Run prediction market signal pipeline.

Fetches thesis-relevant markets from Polymarket and Manifold,
detects probability shifts, flags thesis-market divergences,
and writes signals to ~/quant_results/live/prediction_market_signals.json.

Usage:
    PYTHONPATH=. python3 scripts/run_prediction_markets.py

Cron (every 2 hours, Mon-Fri):
    0 6,8,10,12,14,16 * * 1-5 cd /home/nock/projects/quant_suite && \
        PYTHONPATH=. python3 scripts/run_prediction_markets.py \
        >> ~/quant_results/logs/prediction_markets.log 2>&1
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [pred-markets] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("=" * 60)
    logger.info(f"Prediction Market Signal Pipeline — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    from src.data.sources.alternative.prediction_market_signals import (
        PredictionMarketCollector,
    )

    collector = PredictionMarketCollector()
    signals = await collector.collect()

    # Print summary
    if signals:
        logger.info(f"Generated {len(signals)} signals:")
        for sig in signals[:10]:
            change_str = f"{sig.probability_change_24h:+.1%}" if sig.signal_type == "probability_shift" else "divergence"
            logger.info(
                f"  [{sig.signal_type}] {sig.matched_thesis}: "
                f"{sig.question[:60]} — {sig.current_probability:.0%} ({change_str}) "
                f"→ {sig.signal_direction} (strength={sig.signal_strength:.2f})"
            )
    else:
        logger.info("No actionable signals detected (no probability shifts > 5% or thesis divergences > 30%)")

    # Log to ProcessEvent
    try:
        from src.autonomy.provenance import log_event

        signal_summary = ", ".join(
            f"{s.matched_thesis[:20]}={s.signal_direction}" for s in signals[:5]
        ) if signals else "none"

        log_event(
            "prediction_market_scan",
            source="cron:prediction_markets",
            title=f"Prediction markets: {len(signals)} signals ({signal_summary})",
            severity="info",
        )
    except Exception:
        pass

    logger.info("Pipeline complete")
    return signals


if __name__ == "__main__":
    asyncio.run(main())
