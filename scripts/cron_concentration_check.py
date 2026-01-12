#!/usr/bin/env python3
"""Concentration Check Cron Job.

Checks portfolio concentration limits and generates alerts.

Cron setup (run every 15 minutes during market hours):
    */15 9-16 * * 1-5 cd /home/nock/projects/quant_suite && PYTHONPATH=. python3 scripts/cron_concentration_check.py >> /home/nock/quant_results/logs/concentration_check.log 2>&1

Usage:
    PYTHONPATH=. python scripts/cron_concentration_check.py
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from src.core.paths import paths
from src.alerts.alert_manager import AlertManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def check_concentration():
    """Run concentration check."""
    logger.info("=" * 60)
    logger.info(f"Concentration Check - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    logger.info("=" * 60)

    # Initialize alert manager
    output_dir = paths.base / "alerts"
    output_dir.mkdir(exist_ok=True)

    manager = AlertManager(output_dir=output_dir)

    # Run concentration check
    alerts = await manager.check_concentration()

    # Log results
    result = {
        "timestamp": datetime.now().isoformat(),
        "alerts_triggered": len(alerts),
        "alerts": [a.to_dict() for a in alerts],
    }

    if alerts:
        logger.warning(f"CONCENTRATION ALERTS: {len(alerts)}")
        for alert in alerts:
            logger.warning(f"  {alert.format_console()}")
    else:
        logger.info("All concentration limits within bounds")

    # Save results
    log_dir = paths.base / "logs"
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / "concentration_check_history.json"
    history = []
    if log_file.exists():
        try:
            with open(log_file) as f:
                history = json.load(f)
        except Exception:
            history = []

    history.append(result)
    # Keep last 500 checks (about 2 weeks at 15-min intervals during market hours)
    history = history[-500:]

    with open(log_file, "w") as f:
        json.dump(history, f, indent=2)

    return result


def main():
    result = asyncio.run(check_concentration())
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
