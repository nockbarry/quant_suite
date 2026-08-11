#!/usr/bin/env python3
"""Run conviction velocity and crisis alpha signal engines."""
import sys, json, logging
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.signals.conviction_velocity import ConvictionVelocityEngine
from src.signals.crisis_alpha import CrisisAlphaEngine
from src.core.paths import paths

logging.basicConfig(level=logging.INFO, format="%(asctime)s [signal-engines] %(message)s")
logger = logging.getLogger(__name__)

def main():
    results = {"timestamp": datetime.now().isoformat(), "conviction_velocity": [], "crisis_alpha": []}

    # Conviction velocity
    try:
        cv_engine = ConvictionVelocityEngine()
        cv_signals = cv_engine.scan_all_theses()
        logger.info(f"Conviction velocity: {len(cv_signals)} signals")
        for s in cv_signals:
            logger.info(f"  {s.thesis_name}: {s.signal_direction} (v={s.velocity_3d:+.1f}pp/d)")
            results["conviction_velocity"].append({
                "thesis": s.thesis_name, "direction": s.signal_direction,
                "velocity_3d": s.velocity_3d, "velocity_7d": s.velocity_7d,
                "conviction": s.current_conviction, "symbols": s.symbols,
            })
    except Exception as e:
        logger.error(f"Conviction velocity error: {e}")

    # Crisis alpha
    try:
        ca_engine = CrisisAlphaEngine()
        ca_signals = ca_engine.generate_signals()
        logger.info(f"Crisis alpha: {len(ca_signals)} signals")
        for s in ca_signals:
            logger.info(f"  {s.symbol}: RSI={s.rsi:.0f}, VIX={s.vix_level:.1f}")
            results["crisis_alpha"].append({
                "symbol": s.symbol, "vix": s.vix_level, "rsi": s.rsi,
                "hit_rate": s.historical_hit_rate, "entry": s.entry_price,
            })
    except Exception as e:
        logger.error(f"Crisis alpha error: {e}")

    # Save results
    output = paths.live / "signal_engines.json"
    with open(output, 'w') as f:
        json.dump(results, f, indent=2)
    logger.info(f"Saved to {output}")

if __name__ == "__main__":
    main()
