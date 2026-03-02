"""Canonical setup type and reasoning category taxonomies.

Formalizes the existing setup_type string field on DecisionRecord
so we can aggregate performance consistently.
"""

SETUP_TYPES: dict[str, str] = {
    "thesis_driven": "Position based on an investment thesis with signposts",
    "signal_convergence": "3+ independent signals aligned on same direction",
    "technical_breakout": "Price breaking key technical level (resistance, channel)",
    "mean_reversion": "Fading extreme move expecting return to mean",
    "momentum": "Following established trend with confirmation",
    "event_driven": "Positioned ahead of known catalyst (earnings, FDA, policy)",
    "insider_following": "Following insider buying/selling patterns",
    "congressional": "Following congressional trading disclosures",
    "squeeze": "High short interest + rising volume/price squeeze setup",
    "sector_rotation": "Rotating into strengthening sector, out of weakening",
    "rebalance": "Portfolio rebalancing for risk/concentration management",
}

REASONING_CATEGORIES: dict[str, str] = {
    "thesis_driven": "Decision follows an active investment thesis",
    "technical": "Based on technical analysis signals",
    "geopolitical": "Driven by geopolitical events or analysis",
    "earnings": "Positioned around earnings announcement",
    "momentum": "Following price/volume momentum",
    "mean_reversion": "Expecting reversion from extreme levels",
    "event_driven": "Catalyzed by specific upcoming event",
    "sentiment": "Based on sentiment analysis (social, survey, expert)",
    "insider_following": "Following insider buying/selling activity",
    "congressional": "Following congressional trading patterns",
}

# Mapping from informal/messy setup_type strings to canonical values
SETUP_TYPE_ALIASES: dict[str, str] = {
    "thesis": "thesis_driven",
    "thesis-driven": "thesis_driven",
    "convergence": "signal_convergence",
    "breakout": "technical_breakout",
    "technical": "technical_breakout",
    "reversion": "mean_reversion",
    "mean-reversion": "mean_reversion",
    "event": "event_driven",
    "earnings": "event_driven",
    "insider": "insider_following",
    "congress": "congressional",
    "rotation": "sector_rotation",
    "balance": "rebalance",
    "rebal": "rebalance",
}


def normalize_setup_type(raw: str) -> str:
    """Normalize a setup_type string to canonical form."""
    if not raw:
        return "thesis_driven"
    raw_lower = raw.lower().strip()
    if raw_lower in SETUP_TYPES:
        return raw_lower
    return SETUP_TYPE_ALIASES.get(raw_lower, raw_lower)


def get_setup_description(setup_type: str) -> str:
    """Return human-readable description for a setup type."""
    return SETUP_TYPES.get(setup_type, f"Custom setup: {setup_type}")
