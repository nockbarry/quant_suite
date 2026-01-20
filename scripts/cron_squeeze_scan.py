#!/usr/bin/env python3
"""Cron job for scanning squeeze candidates.

Runs daily to identify stocks with squeeze potential:
- High short interest (>15% of float)
- High days to cover (>3)
- Increasing social mentions

Saves results to ~/quant_results/live/squeeze_candidates.json

Usage:
    # Direct run
    python scripts/cron_squeeze_scan.py

    # Via cron (add to setup_cron.sh)
    30 6 * * 1-5 /path/to/cron_squeeze_scan.py

Created: 2026-01-20
"""

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.paths import paths
from src.synthesis.alternative_signals import SqueezeScanner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def run_squeeze_scan():
    """Run squeeze candidate scan."""
    logger.info("Starting squeeze candidate scan...")

    scanner = SqueezeScanner(
        min_short_pct=0.15,
        min_days_to_cover=3.0,
        max_market_cap_b=10.0,
    )

    # Extended universe to scan
    extended_universe = [
        # Original list
        "GME", "AMC", "BBBY", "KOSS", "EXPR",
        "SPCE", "NKLA", "RIDE", "WKHS", "GOEV",
        "CLOV", "WISH", "SOFI", "PLTR",
        "CVNA", "UPST", "AFRM", "HOOD",
        # Additional high short interest names
        "BYND", "FUBO", "TLRY", "SNDL", "ACB",
        "LCID", "RIVN", "FSR", "FFIE",
        "MARA", "RIOT", "HUT", "BITF",
        "BBIG", "MULN", "HYMC", "REV",
        "ATER", "GEVO", "BLNK", "CHPT",
        # Biotech squeeze candidates
        "SRNE", "VXRT", "OCGN", "INO", "NVAX",
    ]

    candidates = await scanner.scan(extended_universe)

    logger.info(f"Found {len(candidates)} squeeze candidates")

    # Prepare output
    output = {
        "timestamp": datetime.now().isoformat(),
        "scan_universe_size": len(extended_universe),
        "candidates_found": len(candidates),
        "candidates": [c.to_dict() for c in candidates[:20]],  # Top 20
    }

    # Save to file
    output_path = paths.live / "squeeze_candidates.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    logger.info(f"Saved results to {output_path}")

    # Print summary
    if candidates:
        print("\n=== Top Squeeze Candidates ===")
        for c in candidates[:5]:
            print(f"  {c.symbol}: Score {c.squeeze_score:.2f} | "
                  f"Short {c.short_percent_of_float:.1%} | "
                  f"DTC {c.days_to_cover:.1f}")
    else:
        print("No squeeze candidates found meeting criteria")

    return candidates


def main():
    """Main entry point."""
    try:
        asyncio.run(run_squeeze_scan())
    except KeyboardInterrupt:
        logger.info("Scan interrupted")
    except Exception as e:
        logger.error(f"Scan failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
