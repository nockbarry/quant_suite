"""Forced thesis ranking (Fix #6, 2026-06-09 eval).

Conviction clusters at 74-80% across all theses, so the ladder produces
closet equal-weight. The weekly /thesis review now FORCE-RANKS active theses
(strict ordinal, no ties) into <results>/theses/ranking.json; the builder
applies a budget tilt 1.2x (rank 1) -> 0.8x (rank N) so the ranking actually
differentiates sizing.

Stale guard: a ranking older than MAX_AGE_DAYS is ignored (theses change).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MAX_AGE_DAYS = 14


def _path() -> Path:
    base = Path(os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results")))
    return base / "theses" / "ranking.json"


def save_ranking(thesis_ids: list[str], note: str = "") -> None:
    """Persist a strict ordinal ranking (best first)."""
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "updated": date.today().isoformat(),
        "ranking": list(thesis_ids),
        "note": note or "Strict ordinal ranking from weekly /thesis review. Best first.",
    }, indent=2))
    logger.info(f"Saved thesis ranking ({len(thesis_ids)} theses)")


def load_ranking() -> Optional[list[str]]:
    """Load the ranking if present and fresh; None otherwise."""
    p = _path()
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text())
        updated = datetime.fromisoformat(d["updated"]).date()
        if (date.today() - updated).days > MAX_AGE_DAYS:
            logger.info(f"Thesis ranking stale ({updated}); ignoring")
            return None
        ranking = d.get("ranking") or None
        return list(ranking) if ranking else None
    except Exception as e:
        logger.warning(f"ranking.json unreadable ({e}); no rank tilt")
        return None
