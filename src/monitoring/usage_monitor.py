"""Claude Code Max Plan Usage Monitor.

Parses Claude Code session transcripts (.jsonl) to compute exact token usage,
equivalent API costs, and projected monthly capacity against the Max plan budget.

Data sources:
- ~/.claude/projects/-home-nock-projects-quant-suite/*.jsonl — per-message token usage
- ~/.claude/stats-cache.json — pre-aggregated daily activity stats
- ~/quant_results/scheduler/completions/ — session type/duration metadata
"""

import json
import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from src.core.paths import paths

logger = logging.getLogger(__name__)

# Claude API pricing (per million tokens) — used to compute equivalent cost
# These are the standard API rates; Max plan is flat-rate but we use these
# to estimate what % of the plan budget we're consuming.
PRICING = {
    "opus": {
        "input": 15.0,
        "output": 75.0,
        "cache_write": 18.75,
        "cache_read": 1.875,
    },
    "sonnet": {
        "input": 3.0,
        "output": 15.0,
        "cache_write": 3.75,
        "cache_read": 0.375,
    },
    "haiku": {
        "input": 0.80,
        "output": 4.0,
        "cache_write": 1.0,
        "cache_read": 0.08,
    },
}

# Max 5x plan: Anthropic doesn't publish exact token limits.
# We track equivalent API cost as a usage proxy.
# Output tokens at Opus rates ($75/MTok) are the primary capacity driver.
# Cache reads are ~90% discounted so they barely count toward limits.
# This budget is a rough estimate — calibrate based on actual throttling.
MAX_5X_BUDGET_USD = 1200.0  # Estimated monthly API-equivalent capacity


def _model_tier(model_id: str) -> str:
    """Map model ID to pricing tier."""
    if not model_id:
        return "opus"
    m = model_id.lower()
    if "haiku" in m:
        return "haiku"
    if "sonnet" in m:
        return "sonnet"
    return "opus"


@dataclass
class DailyUsage:
    date: str
    sessions: int = 0
    messages: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    by_model: dict = field(default_factory=lambda: defaultdict(lambda: {
        "input": 0, "output": 0, "cache_write": 0, "cache_read": 0, "messages": 0,
    }))

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_write_tokens + self.cache_read_tokens

    @property
    def equivalent_cost_usd(self) -> float:
        """What this usage would cost at API prices."""
        cost = 0.0
        for model_id, usage in self.by_model.items():
            tier = _model_tier(model_id)
            rates = PRICING[tier]
            cost += usage["input"] / 1_000_000 * rates["input"]
            cost += usage["output"] / 1_000_000 * rates["output"]
            cost += usage["cache_write"] / 1_000_000 * rates["cache_write"]
            cost += usage["cache_read"] / 1_000_000 * rates["cache_read"]
        return cost

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "sessions": self.sessions,
            "messages": self.messages,
            "tool_calls": self.tool_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "total_tokens": self.total_tokens,
            "equivalent_cost_usd": round(self.equivalent_cost_usd, 4),
            "by_model": {k: dict(v) for k, v in self.by_model.items()},
        }


@dataclass
class UsageSummary:
    current_month: str
    days: list[DailyUsage]
    total_cost: float = 0.0
    daily_avg_cost: float = 0.0
    projected_monthly_cost: float = 0.0
    capacity_pct: float = 0.0
    sessions_today: int = 0
    sessions_month: int = 0
    messages_month: int = 0
    output_tokens_month: int = 0
    budget: float = MAX_5X_BUDGET_USD

    def to_dict(self) -> dict:
        return {
            "current_month": self.current_month,
            "total_cost": round(self.total_cost, 2),
            "daily_avg_cost": round(self.daily_avg_cost, 2),
            "projected_monthly_cost": round(self.projected_monthly_cost, 2),
            "capacity_pct": round(self.capacity_pct, 1),
            "sessions_today": self.sessions_today,
            "sessions_month": self.sessions_month,
            "messages_month": self.messages_month,
            "output_tokens_month": self.output_tokens_month,
            "budget": self.budget,
            "days": [d.to_dict() for d in self.days],
        }


def _get_project_dir() -> Path:
    """Get the Claude Code project directory for this project."""
    return Path.home() / ".claude" / "projects" / "-home-nock-projects-quant-suite"


def _get_cache_path() -> Path:
    """Cache path for parsed usage data."""
    cache_dir = paths.base / "logs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "usage_cache.json"


def _parse_session_file(filepath: Path) -> dict:
    """Parse a single .jsonl session file for usage data.

    Returns dict keyed by date string with token breakdowns.
    """
    daily: dict[str, dict] = {}
    session_ids = set()
    tool_call_count = 0

    try:
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                entry_type = entry.get("type")
                timestamp = entry.get("timestamp", "")

                if entry_type == "assistant":
                    msg = entry.get("message", {})
                    usage = msg.get("usage", {})
                    model = msg.get("model", "")
                    sid = entry.get("sessionId", "")

                    if not usage:
                        continue

                    # Parse date from timestamp
                    if timestamp:
                        try:
                            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                            date_str = dt.strftime("%Y-%m-%d")
                        except (ValueError, TypeError):
                            continue
                    else:
                        continue

                    if sid:
                        session_ids.add(sid)

                    inp = usage.get("input_tokens", 0)
                    out = usage.get("output_tokens", 0)
                    cw = usage.get("cache_creation_input_tokens", 0)
                    cr = usage.get("cache_read_input_tokens", 0)

                    # Count tool calls from content blocks
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        tool_call_count += sum(
                            1 for c in content
                            if isinstance(c, dict) and c.get("type") == "tool_use"
                        )

                    if date_str not in daily:
                        daily[date_str] = {
                            "messages": 0,
                            "tool_calls": 0,
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "cache_write_tokens": 0,
                            "cache_read_tokens": 0,
                            "session_ids": set(),
                            "by_model": defaultdict(lambda: {
                                "input": 0, "output": 0, "cache_write": 0, "cache_read": 0, "messages": 0,
                            }),
                        }

                    d = daily[date_str]
                    d["messages"] += 1
                    d["input_tokens"] += inp
                    d["output_tokens"] += out
                    d["cache_write_tokens"] += cw
                    d["cache_read_tokens"] += cr
                    d["session_ids"].add(sid)

                    bm = d["by_model"][model]
                    bm["input"] += inp
                    bm["output"] += out
                    bm["cache_write"] += cw
                    bm["cache_read"] += cr
                    bm["messages"] += 1

    except Exception as e:
        logger.warning(f"Error parsing {filepath.name}: {e}")

    # Add tool calls to the last date
    for date_str in daily:
        daily[date_str]["tool_calls"] = tool_call_count

    # Convert sets to counts for serialization
    for date_str in daily:
        daily[date_str]["sessions"] = len(daily[date_str].pop("session_ids"))
        daily[date_str]["by_model"] = {k: dict(v) for k, v in daily[date_str]["by_model"].items()}

    return daily


def _load_cached_usage() -> dict:
    """Load cached usage data if fresh enough."""
    cache_path = _get_cache_path()
    if not cache_path.exists():
        return {}

    try:
        with open(cache_path) as f:
            data = json.load(f)

        # Cache valid for 5 minutes
        cached_at = data.get("cached_at", "")
        if cached_at:
            cached_time = datetime.fromisoformat(cached_at)
            if (datetime.now() - cached_time).total_seconds() < 300:
                return data
    except Exception:
        pass

    return {}


def _save_cached_usage(data: dict) -> None:
    """Save usage data to cache."""
    cache_path = _get_cache_path()
    try:
        with open(cache_path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save usage cache: {e}")


def _scan_all_sessions(days: int = 60) -> dict[str, DailyUsage]:
    """Scan all session .jsonl files and aggregate by day.

    Uses a file-level cache to avoid re-parsing unchanged files.
    """
    # Try cache first
    cached = _load_cached_usage()
    if cached.get("daily"):
        result = {}
        for date_str, d in cached["daily"].items():
            du = DailyUsage(
                date=date_str,
                sessions=d.get("sessions", 0),
                messages=d.get("messages", 0),
                tool_calls=d.get("tool_calls", 0),
                input_tokens=d.get("input_tokens", 0),
                output_tokens=d.get("output_tokens", 0),
                cache_write_tokens=d.get("cache_write_tokens", 0),
                cache_read_tokens=d.get("cache_read_tokens", 0),
            )
            # Rebuild by_model
            for model, usage in d.get("by_model", {}).items():
                du.by_model[model] = usage
            result[date_str] = du
        return result

    proj_dir = _get_project_dir()
    if not proj_dir.exists():
        return {}

    cutoff = (datetime.now() - timedelta(days=days)).timestamp()
    daily_agg: dict[str, DailyUsage] = {}

    # Parse each .jsonl file
    for fp in proj_dir.glob("*.jsonl"):
        if fp.stat().st_mtime < cutoff:
            continue

        file_daily = _parse_session_file(fp)

        for date_str, data in file_daily.items():
            if date_str not in daily_agg:
                daily_agg[date_str] = DailyUsage(date=date_str)

            du = daily_agg[date_str]
            du.sessions += data.get("sessions", 0)
            du.messages += data.get("messages", 0)
            du.tool_calls += data.get("tool_calls", 0)
            du.input_tokens += data.get("input_tokens", 0)
            du.output_tokens += data.get("output_tokens", 0)
            du.cache_write_tokens += data.get("cache_write_tokens", 0)
            du.cache_read_tokens += data.get("cache_read_tokens", 0)

            for model, usage in data.get("by_model", {}).items():
                bm = du.by_model[model]
                for k in ("input", "output", "cache_write", "cache_read", "messages"):
                    bm[k] = bm.get(k, 0) + usage.get(k, 0)

    # Also pull session counts from stats-cache.json (more accurate)
    stats_cache = Path.home() / ".claude" / "stats-cache.json"
    if stats_cache.exists():
        try:
            with open(stats_cache) as f:
                stats = json.load(f)
            for entry in stats.get("dailyActivity", []):
                date_str = entry.get("date", "")
                if date_str in daily_agg:
                    # Stats-cache has more accurate session/tool counts
                    daily_agg[date_str].sessions = max(
                        daily_agg[date_str].sessions,
                        entry.get("sessionCount", 0),
                    )
                    daily_agg[date_str].tool_calls = max(
                        daily_agg[date_str].tool_calls,
                        entry.get("toolCallCount", 0),
                    )
        except Exception:
            pass

    # Save to cache
    cache_data = {
        "cached_at": datetime.now().isoformat(),
        "daily": {k: v.to_dict() for k, v in daily_agg.items()},
    }
    _save_cached_usage(cache_data)

    return daily_agg


def get_usage_summary(days: int = 30) -> UsageSummary:
    """Get usage summary for the current month with daily breakdown."""
    daily = _scan_all_sessions(days=max(days, 60))

    now = datetime.now()
    current_month = now.strftime("%Y-%m")
    today_str = now.strftime("%Y-%m-%d")

    # Filter to current month
    month_days = sorted(
        [d for d in daily.values() if d.date.startswith(current_month)],
        key=lambda d: d.date,
    )

    # Also include recent days outside current month for the chart
    cutoff = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    all_days = sorted(
        [d for d in daily.values() if d.date >= cutoff],
        key=lambda d: d.date,
    )

    total_cost = sum(d.equivalent_cost_usd for d in month_days)
    days_with_usage = len([d for d in month_days if d.messages > 0])

    daily_avg = total_cost / days_with_usage if days_with_usage > 0 else 0

    # Project to end of month
    day_of_month = now.day
    import calendar
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    remaining_weekdays = sum(
        1 for d in range(day_of_month + 1, days_in_month + 1)
        if datetime(now.year, now.month, d).weekday() < 5
    )
    # Project based on weekday average (trading system runs Mon-Fri)
    weekday_days = len([d for d in month_days if d.messages > 0 and
                        datetime.strptime(d.date, "%Y-%m-%d").weekday() < 5])
    weekday_avg = total_cost / weekday_days if weekday_days > 0 else daily_avg
    projected = total_cost + (remaining_weekdays * weekday_avg)

    capacity_pct = (projected / MAX_5X_BUDGET_USD * 100) if MAX_5X_BUDGET_USD > 0 else 0

    today_usage = daily.get(today_str)
    sessions_today = today_usage.sessions if today_usage else 0

    return UsageSummary(
        current_month=current_month,
        days=all_days,
        total_cost=total_cost,
        daily_avg_cost=daily_avg,
        projected_monthly_cost=projected,
        capacity_pct=capacity_pct,
        sessions_today=sessions_today,
        sessions_month=sum(d.sessions for d in month_days),
        messages_month=sum(d.messages for d in month_days),
        output_tokens_month=sum(d.output_tokens for d in month_days),
        budget=MAX_5X_BUDGET_USD,
    )


# Session type → model mapping (mirrors session_wrapper.sh get_model)
SESSION_MODEL_MAP = {
    "morning-briefing": "opus",
    "trade-decision": "opus",
    "eod-review": "opus",
    "operator": "opus",
    "brainstorm": "opus",
    "theorist": "opus",
    "evening-research": "opus",
    "hypothesis-gen": "opus",
    "research": "sonnet",
    "thesis": "sonnet",
    "signal-scan": "sonnet",
    "research-theory": "sonnet",
    "internal-review": "sonnet",
    "analyst": "sonnet",
    "research-queue": "sonnet",
}

# Session type → timeout in minutes (mirrors session_wrapper.sh get_timeout)
SESSION_TIMEOUT_MAP = {
    "morning-briefing": 15,
    "trade-decision": 10,
    "eod-review": 15,
    "research": 20,
    "thesis": 10,
    "brainstorm": 15,
    "signal-scan": 15,
    "research-theory": 15,
    "internal-review": 10,
    "analyst": 5,
    "theorist": 15,
    "evening-research": 15,
    "hypothesis-gen": 15,
    "research-queue": 30,
    "operator": 480,
}

# Estimated output tokens per minute by model tier (from empirical observation)
# These approximate how many output tokens Claude generates per minute of session
_EST_OUTPUT_TOKENS_PER_MIN = {
    "opus": 800,
    "sonnet": 1200,
    "haiku": 2000,
}


def get_session_breakdown(days: int = 30) -> list[dict]:
    """Get session type breakdown from scheduler completions with cost estimates.

    Cross-references completion records with model assignments and durations
    to estimate per-session-type API-equivalent cost.
    """
    completions_dir = paths.base / "scheduler" / "completions"

    if not completions_dir.exists():
        return []

    cutoff = (datetime.now() - timedelta(days=days)).timestamp()
    type_stats: dict[str, dict] = {}

    for fp in sorted(completions_dir.glob("*.json")):
        if fp.stat().st_mtime < cutoff:
            continue
        try:
            with open(fp) as f:
                data = json.load(f)
            stype = data.get("session_type", "unknown")
            duration = data.get("duration_seconds", 0)
            success = data.get("success", False)

            if stype not in type_stats:
                type_stats[stype] = {
                    "session_type": stype,
                    "model": SESSION_MODEL_MAP.get(stype, "sonnet"),
                    "timeout_min": SESSION_TIMEOUT_MAP.get(stype, 15),
                    "count": 0,
                    "successes": 0,
                    "total_duration_s": 0,
                    "est_total_cost_usd": 0.0,
                }
            type_stats[stype]["count"] += 1
            if success:
                type_stats[stype]["successes"] += 1
            type_stats[stype]["total_duration_s"] += duration
        except Exception:
            continue

    result = list(type_stats.values())
    for r in result:
        r["avg_duration_s"] = r["total_duration_s"] / r["count"] if r["count"] > 0 else 0
        r["success_rate"] = r["successes"] / r["count"] * 100 if r["count"] > 0 else 0

        # Estimate cost per session based on model and typical duration
        model_tier = r["model"]
        timeout_min = r["timeout_min"]
        rates = PRICING.get(model_tier, PRICING["sonnet"])
        est_tokens_per_min = _EST_OUTPUT_TOKENS_PER_MIN.get(model_tier, 1000)

        # Use actual avg duration if available, otherwise timeout * 0.7
        avg_min = r["avg_duration_s"] / 60 if r["avg_duration_s"] > 0 else timeout_min * 0.7
        est_output_tokens = avg_min * est_tokens_per_min
        # Assume 3:1 input:output ratio (typical for Claude with tool use)
        est_input_tokens = est_output_tokens * 3

        est_cost_per_session = (
            est_output_tokens / 1_000_000 * rates["output"]
            + est_input_tokens / 1_000_000 * rates["input"]
        )
        r["est_cost_per_session"] = round(est_cost_per_session, 2)
        r["est_total_cost_usd"] = round(est_cost_per_session * r["count"], 2)

    return sorted(result, key=lambda x: x["est_total_cost_usd"], reverse=True)


def format_tokens(n: int) -> str:
    """Human-readable token count."""
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)
