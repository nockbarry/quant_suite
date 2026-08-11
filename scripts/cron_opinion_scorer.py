#!/usr/bin/env python3
"""Cron job: Score market opinions at 5d/10d/30d horizons.

Schedule: 5:20 PM ET Mon-Fri (after prediction scorer, before belief updater).

Independent reliability fix C: this previously scored only the default
~/quant_results instance, leaving Beta (2055 opinions) and Gamma (815)
unscored — DecisionQualityTracker couldn't see their signal health.

Now discovers ALL instance result dirs (~/quant_results, ~/quant_results_*)
and spawns a subprocess for each with QUANT_RESULTS_DIR set so paths and
DB connections rebind to the per-instance state. Single cron entry, all
instances covered.
"""

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("opinion-scorer")


def _score_current_instance() -> int:
    """Score the instance pointed to by QUANT_RESULTS_DIR (default if unset).

    This is the actual scoring work — runs in-process. Used both by the
    direct invocation path and by per-instance subprocesses.
    """
    from src.db.database import init_db
    from src.opinions.scorer import OpinionScorer

    init_db()
    scorer = OpinionScorer()
    summary = scorer.score_due_opinions()
    instance_label = os.environ.get("QUANT_RESULTS_DIR", "default")
    logger.info(
        f"[{instance_label}] scored: "
        f"5d={summary['scored_5d']}, 10d={summary['scored_10d']}, "
        f"30d={summary['scored_30d']}, errors={summary['errors']}"
    )
    return 0 if summary["errors"] == 0 else 1


def _discover_instance_dirs() -> list[Path]:
    """Find all instance result dirs.

    Returns ~/quant_results plus any ~/quant_results_<name> with state.json.
    """
    home = Path.home()
    dirs: list[Path] = []
    default = home / "quant_results"
    if default.exists():
        dirs.append(default)
    for p in sorted(home.glob("quant_results_*")):
        if p.is_dir() and (p / "live" / "state.json").exists():
            dirs.append(p)
    return dirs


def _score_instance_subprocess(instance_dir: Path) -> int:
    """Spawn a subprocess scoring just this instance.

    Subprocess gets QUANT_RESULTS_DIR set so all path resolution and DB
    connections rebind. Re-invokes this script with --self.
    """
    env = os.environ.copy()
    env["QUANT_RESULTS_DIR"] = str(instance_dir)
    cmd = [sys.executable, str(Path(__file__).resolve()), "--self"]
    project_root = Path(__file__).resolve().parents[1]
    env.setdefault("PYTHONPATH", str(project_root))
    logger.info(f"scoring instance dir: {instance_dir}")
    proc = subprocess.run(cmd, env=env, cwd=str(project_root))
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Opinion scoring cron entry")
    parser.add_argument(
        "--self",
        dest="self_mode",
        action="store_true",
        help="Score only the instance at QUANT_RESULTS_DIR (used by subprocesses)",
    )
    args = parser.parse_args()

    if args.self_mode:
        return _score_current_instance()

    # Multi-instance fan-out
    dirs = _discover_instance_dirs()
    if not dirs:
        logger.warning("no instance result dirs discovered; running on current env only")
        return _score_current_instance()

    logger.info(f"discovered {len(dirs)} instance(s): {[d.name for d in dirs]}")
    failures = 0
    for d in dirs:
        rc = _score_instance_subprocess(d)
        if rc != 0:
            logger.warning(f"instance {d.name} returned non-zero ({rc})")
            failures += 1

    if failures > 0:
        logger.error(f"{failures}/{len(dirs)} instances failed scoring")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
