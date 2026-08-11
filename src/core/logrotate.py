"""Size-based log rotation for append-only jsonl/log files.

The system's two busiest append points (process_events.jsonl, operator_log
.jsonl) grew to 298MB/146MB with no rotation, which also made the bug
monitor's log scans useless. Callers invoke rotate_if_large() before
appending; rotation is a cheap rename chain (file.1, file.2, ...) with the
oldest dropped. A stat per call is negligible at this write volume, and
rotation only ever renames — nothing is deleted until the keep-chain rolls
off (weekly cron_log_cleanup.sh prunes archives beyond 60 days).
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_MAX_MB = 64
DEFAULT_KEEP = 3


def rotate_if_large(path: Path, max_mb: int = DEFAULT_MAX_MB, keep: int = DEFAULT_KEEP) -> bool:
    """Rotate `path` to `path.1` (shifting older rotations up) if it exceeds max_mb.

    Returns True if a rotation happened. Never raises — a rotation failure
    must not break the write it precedes.
    """
    try:
        if not path.exists() or path.stat().st_size < max_mb * 1024 * 1024:
            return False
        # Shift path.(keep-1) -> path.keep, ..., path.1 -> path.2; drop the oldest.
        oldest = path.with_name(f"{path.name}.{keep}")
        oldest.unlink(missing_ok=True)
        for i in range(keep - 1, 0, -1):
            src = path.with_name(f"{path.name}.{i}")
            if src.exists():
                src.rename(path.with_name(f"{path.name}.{i + 1}"))
        path.rename(path.with_name(f"{path.name}.1"))
        logger.info(f"Rotated {path.name} ({max_mb}MB threshold)")
        return True
    except Exception as e:
        logger.warning(f"Log rotation failed for {path}: {e}")
        return False
