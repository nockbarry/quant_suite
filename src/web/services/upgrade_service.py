"""Upgrade history service."""
import json
from src.core.paths import paths


def get_upgrade_dashboard_data() -> dict:
    """Load upgrade history and proposals for the dashboard."""
    log_file = paths.base / "logs" / "upgrade_log.jsonl"
    upgrades = []
    if log_file.exists():
        with open(log_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    upgrades.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue

    proposals_dir = paths.base / "upgrades"
    proposals = []
    if proposals_dir.exists():
        for f in sorted(proposals_dir.glob("*.json"), reverse=True)[:20]:
            try:
                with open(f) as fh:
                    proposals.append(json.load(fh))
            except (json.JSONDecodeError, OSError):
                continue

    # Separate pending (Tier 3 or unapproved) from completed
    pending_proposals = [
        p for p in proposals
        if p.get('tier') == 3 or (not p.get('applied') and not p.get('approved'))
    ]

    return {
        "upgrades": list(reversed(upgrades[-20:])),  # Most recent first
        "proposals": pending_proposals,
        "total_applied": len([u for u in upgrades if u.get("merged")]),
        "total_rolled_back": len([u for u in upgrades if u.get("rollback")]),
        "total_proposed": len(proposals),
    }
