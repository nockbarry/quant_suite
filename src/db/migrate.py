"""Migrate existing YAML/JSON files into SQLite.

Reads from ~/quant_results/ file-based storage and populates all DB tables.
Safe to re-run (upsert logic via merge).

Usage:
    PYTHONPATH=. python -m src.db.migrate
    PYTHONPATH=. python -m src.db.migrate --dry-run
"""

import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import yaml
from sqlalchemy.orm import Session

from src.db.database import get_db, init_db, get_sync_engine
from src.db.models import (
    Base,
    Company,
    Sector,
    ThesisRecord,
    SignpostRecord,
    LearningRecord,
    DecisionRecord,
    SignalProvenanceRecord,
    AgentRun,
    ProcessEvent,
    Document,
    Insight,
    Experiment,
)

logger = logging.getLogger(__name__)


def _results_dir() -> Path:
    return Path(os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results")))


def _parse_datetime(val) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val)
        except (ValueError, TypeError):
            return None
    return None


def migrate_companies(session: Session) -> int:
    """Migrate company YAML files."""
    companies_dir = _results_dir() / "knowledge" / "companies"
    if not companies_dir.exists():
        return 0

    count = 0
    for yaml_file in companies_dir.glob("*.yaml"):
        try:
            data = yaml.safe_load(yaml_file.read_text())
            if not data or not data.get("symbol"):
                continue

            company = Company(
                symbol=data["symbol"],
                name=data.get("name", ""),
                updated=_parse_datetime(data.get("updated")) or datetime.utcnow(),
                business_model=data.get("business_model", ""),
                moat=data.get("moat", ""),
                earnings_quality=data.get("earnings_quality", ""),
                management_view=data.get("management_view", ""),
                sector=data.get("sector", ""),
                market_cap_tier=data.get("market_cap_tier", ""),
                key_risks=json.dumps(data.get("key_risks", [])),
                key_catalysts=json.dumps(data.get("key_catalysts", [])),
                sector_position=data.get("sector_position", ""),
                typical_volatility=data.get("typical_volatility", ""),
                earnings_behavior=data.get("earnings_behavior", ""),
                correlation_notes=data.get("correlation_notes", ""),
                best_setups=data.get("best_setups", ""),
                avoid_when=data.get("avoid_when", ""),
                valuation_notes=data.get("valuation_notes", ""),
                historical_range=data.get("historical_range", ""),
            )
            session.merge(company)
            count += 1
        except Exception as e:
            print(f"  WARN: Failed to migrate {yaml_file.name}: {e}")

    return count


def migrate_sectors(session: Session) -> int:
    """Migrate sector YAML files."""
    sectors_dir = _results_dir() / "knowledge" / "sectors"
    if not sectors_dir.exists():
        return 0

    count = 0
    for yaml_file in sectors_dir.glob("*.yaml"):
        try:
            data = yaml.safe_load(yaml_file.read_text())
            if not data or not data.get("sector"):
                continue

            sector = Sector(
                sector=data["sector"],
                updated=_parse_datetime(data.get("updated")) or datetime.utcnow(),
                current_cycle_position=data.get("current_cycle_position", ""),
                cycle_sensitivity=data.get("cycle_sensitivity", ""),
                key_drivers=json.dumps(data.get("key_drivers", [])),
                leading_indicators=json.dumps(data.get("leading_indicators", [])),
                correlations=json.dumps(data.get("correlations", {})),
                rotation_patterns=data.get("rotation_patterns", ""),
                current_assessment=data.get("current_assessment", ""),
                relative_strength=data.get("relative_strength", ""),
                leaders=json.dumps(data.get("leaders", [])),
                laggards=json.dumps(data.get("laggards", [])),
                what_works_here=data.get("what_works_here", ""),
                what_to_avoid=data.get("what_to_avoid", ""),
            )
            session.merge(sector)
            count += 1
        except Exception as e:
            print(f"  WARN: Failed to migrate {yaml_file.name}: {e}")

    return count


def migrate_theses(session: Session) -> int:
    """Migrate thesis YAML files."""
    theses_dir = _results_dir() / "theses"
    if not theses_dir.exists():
        return 0

    count = 0
    for yaml_file in theses_dir.glob("*.yaml"):
        try:
            data = yaml.safe_load(yaml_file.read_text())
            if not data or not data.get("id"):
                continue

            signpost_data = data.pop("signposts", []) or []

            thesis = ThesisRecord(
                id=data["id"],
                name=data.get("name", ""),
                created=_parse_datetime(data.get("created")) or datetime.utcnow(),
                status=data.get("status", "active"),
                summary=data.get("summary", ""),
                bull_case=data.get("bull_case", ""),
                bear_case=data.get("bear_case", ""),
                conviction=data.get("conviction", 50.0),
                positions=json.dumps(data.get("positions", [])),
                invalidation_triggers=json.dumps(data.get("invalidation_triggers", [])),
                last_review=_parse_datetime(data.get("last_review")),
                next_review=_parse_datetime(data.get("next_review")),
                review_interval_days=data.get("review_interval_days", 7),
                conviction_history=json.dumps(data.get("conviction_history", [])),
                notes=json.dumps(data.get("notes", [])),
            )
            session.merge(thesis)

            # Delete existing signposts for this thesis, re-create
            session.query(SignpostRecord).filter_by(thesis_id=data["id"]).delete()
            for sp_data in signpost_data:
                if isinstance(sp_data, dict):
                    sp = SignpostRecord(
                        thesis_id=data["id"],
                        description=sp_data.get("description", ""),
                        status=sp_data.get("status", "pending"),
                        bullish_if=sp_data.get("bullish_if", ""),
                        bearish_if=sp_data.get("bearish_if", ""),
                        target_date=sp_data.get("target_date"),
                        triggered_at=_parse_datetime(sp_data.get("triggered_at")),
                        outcome=sp_data.get("outcome"),
                    )
                    session.add(sp)

            count += 1
        except Exception as e:
            print(f"  WARN: Failed to migrate {yaml_file.name}: {e}")

    return count


def migrate_learnings(session: Session) -> int:
    """Migrate learning JSON files (monthly)."""
    learnings_dir = _results_dir() / "learnings"
    if not learnings_dir.exists():
        return 0

    count = 0
    for json_file in learnings_dir.glob("*.json"):
        try:
            data = json.loads(json_file.read_text())
            items = data if isinstance(data, list) else data.get("learnings", [])

            for item in items:
                if not item.get("id"):
                    continue
                learning = LearningRecord(
                    id=item["id"],
                    created=_parse_datetime(item.get("created")) or datetime.utcnow(),
                    decision_id=item.get("decision_id"),
                    symbol=item.get("symbol", ""),
                    action=item.get("action", ""),
                    outcome=item.get("outcome", ""),
                    pnl_pct=item.get("pnl_pct", 0.0),
                    hold_days=item.get("hold_days", 0),
                    what_happened=item.get("what_happened", ""),
                    what_i_learned=item.get("what_i_learned", ""),
                    how_this_changes_approach=item.get("how_this_changes_approach", ""),
                    pattern_name=item.get("pattern_name"),
                    pattern_description=item.get("pattern_description"),
                    pattern_setup=item.get("pattern_setup"),
                    pattern_typical_outcome=item.get("pattern_typical_outcome"),
                    pattern_action=item.get("pattern_action"),
                    tags=json.dumps(item.get("tags", [])),
                    thesis_id=item.get("thesis_id"),
                    confidence_at_entry=item.get("confidence_at_entry"),
                )
                session.merge(learning)
                count += 1
        except Exception as e:
            print(f"  WARN: Failed to migrate {json_file.name}: {e}")

    return count


def migrate_decisions(session: Session) -> int:
    """Migrate decision JSON files (daily)."""
    decisions_dir = _results_dir() / "decisions"
    if not decisions_dir.exists():
        return 0

    count = 0
    for json_file in decisions_dir.glob("decisions_*.json"):
        try:
            data = json.loads(json_file.read_text())
            items = data if isinstance(data, list) else data.get("decisions", [])

            for item in items:
                if not item.get("id"):
                    continue
                decision = DecisionRecord(
                    id=item["id"],
                    timestamp=_parse_datetime(item.get("timestamp")) or datetime.utcnow(),
                    symbol=item.get("symbol", ""),
                    action=item.get("action", ""),
                    confidence=item.get("confidence", 0.0),
                    size_pct=item.get("size_pct", 0.0),
                    limit_price=item.get("limit_price"),
                    stop_loss_pct=item.get("stop_loss_pct", 15.0),
                    take_profit_pct=item.get("take_profit_pct", 0.0),
                    expected_hold_days=item.get("expected_hold_days", 5),
                    reasoning=item.get("reasoning", ""),
                    key_factors=json.dumps(item.get("key_factors", [])),
                    risks=json.dumps(item.get("risks", [])),
                    context=json.dumps(item.get("context", {})),
                    status=item.get("status", "pending"),
                    execution_price=item.get("execution_price"),
                    execution_time=_parse_datetime(item.get("execution_time")),
                    exit_price=item.get("exit_price"),
                    exit_time=_parse_datetime(item.get("exit_time")),
                    actual_hold_days=item.get("actual_hold_days"),
                    realized_pnl=item.get("realized_pnl"),
                    realized_pnl_pct=item.get("realized_pnl_pct"),
                    outcome_notes=item.get("outcome_notes"),
                    thesis_id=item.get("thesis_id"),
                    pre_mortem=item.get("pre_mortem"),
                    adversarial_notes=item.get("adversarial_notes"),
                    learning_extracted=item.get("learning_extracted", False),
                    setup_type=item.get("setup_type", "thesis_driven"),
                    signal_ids=json.dumps(item.get("signal_ids", [])),
                    convergence_id=item.get("convergence_id"),
                    llm_interaction_id=item.get("llm_interaction_id"),
                    briefing_id=item.get("briefing_id"),
                )
                session.merge(decision)
                count += 1
        except Exception as e:
            print(f"  WARN: Failed to migrate {json_file.name}: {e}")

    return count


def migrate_signal_provenance(session: Session) -> int:
    """Migrate signal provenance JSON files."""
    prov_dir = _results_dir() / "signal_provenance"
    if not prov_dir.exists():
        return 0

    count = 0
    for json_file in prov_dir.glob("*.json"):
        try:
            data = json.loads(json_file.read_text())
            if not data.get("signal_id"):
                continue

            record = SignalProvenanceRecord(
                signal_id=data["signal_id"],
                source=data.get("source", ""),
                symbol=data.get("symbol", ""),
                first_detected=_parse_datetime(data.get("first_detected")) or datetime.utcnow(),
                detection_method=data.get("detection_method", ""),
                initial_confidence=data.get("initial_confidence", 0.5),
                initial_direction=data.get("initial_direction", "neutral"),
                initial_description=data.get("initial_description", ""),
                confidence_history=json.dumps(data.get("confidence_history", [])),
                corroborating_signals=json.dumps(data.get("corroborating_signals", [])),
                linked_thesis_id=data.get("linked_thesis_id"),
                linked_thesis_name=data.get("linked_thesis_name"),
                thesis_created_from_signal=data.get("thesis_created_from_signal", False),
                days_to_thesis=data.get("days_to_thesis"),
                thesis_linked_at=_parse_datetime(data.get("thesis_linked_at")),
                outcome=data.get("outcome", "pending"),
                outcome_date=_parse_datetime(data.get("outcome_date")),
                pnl_contribution=data.get("pnl_contribution"),
                outcome_notes=data.get("outcome_notes", ""),
                metadata_json=json.dumps(data.get("metadata", {})),
                created_at=_parse_datetime(data.get("created_at")) or datetime.utcnow(),
                updated_at=_parse_datetime(data.get("updated_at")) or datetime.utcnow(),
                decision_ids=json.dumps(data.get("decision_ids", [])),
            )
            session.merge(record)
            count += 1
        except Exception as e:
            print(f"  WARN: Failed to migrate {json_file.name}: {e}")

    return count


def migrate_agent_activity(session: Session) -> int:
    """Migrate agent_activity.jsonl into agent_runs table."""
    log_file = _results_dir() / "logs" / "agent_activity.jsonl"
    if not log_file.exists():
        return 0

    count = 0
    for line in log_file.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            agent_id = data.get("agent_id", "")
            if not agent_id:
                continue

            run = AgentRun(
                id=agent_id,
                agent_type=data.get("agent_type", data.get("type", "unknown")),
                task=data.get("task", data.get("description", "")),
                trigger_reason=data.get("trigger_reason", ""),
                parent_run_id=data.get("parent_agent_id"),
                started_at=_parse_datetime(data.get("started_at", data.get("timestamp"))),
                completed_at=_parse_datetime(data.get("completed_at")),
                status=data.get("status", "completed"),
                tokens_used=data.get("tokens_used", 0),
                cost_usd=data.get("cost_usd", 0.0),
                signals_generated=json.dumps(data.get("signals_generated", [])),
                decisions_influenced=json.dumps(data.get("decisions_influenced", [])),
                findings_summary=data.get("result_summary", data.get("summary", "")),
                raw_output=data.get("raw_output", "")[:10000],
            )
            session.merge(run)
            count += 1
        except Exception as e:
            print(f"  WARN: Failed to parse agent activity line: {e}")

    return count


def migrate_operator_log(session: Session) -> int:
    """Migrate operator_log.jsonl into process_events table."""
    log_file = _results_dir() / "logs" / "operator_log.jsonl"
    if not log_file.exists():
        return 0

    count = 0
    for line in log_file.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            event_id = data.get("id", f"op_{count}_{data.get('timestamp', '')}")

            event = ProcessEvent(
                id=event_id,
                timestamp=_parse_datetime(data.get("timestamp")) or datetime.utcnow(),
                event_type=data.get("event_type", data.get("type", "operator_check")),
                source="operator_loop",
                symbol=data.get("symbol"),
                severity=data.get("severity", "info"),
                title=data.get("title", data.get("summary", "")),
                detail=json.dumps(data) if isinstance(data, dict) else str(data),
            )
            session.merge(event)
            count += 1
        except Exception as e:
            print(f"  WARN: Failed to parse operator log line: {e}")

    return count


# ---------------------------------------------------------------------------
# Document index backfill
# ---------------------------------------------------------------------------

_EXCLUDES = {
    "JSON", "YAML", "HTML", "HTTP", "HTTPS", "NULL", "TRUE", "FALSE",
    "READ", "WRITE", "EXEC", "NOTE", "FILE", "PATH", "TEXT", "DATA",
    "FULL", "QUICK", "START", "HERE", "INDEX", "PLAN", "SCAN",
    "REPORT", "SUMMARY", "ANALYSIS", "MORNING", "BRIEFING", "REVIEW",
    "TRADE", "CARD", "ACTION", "COMPLETE", "VERDICT", "SCORE",
    "MACRO", "REGIME", "ALPHA", "MONDAY", "WEEKLY", "SCORECARD",
}

DIRECTORY_MAP = {
    "briefings": ("briefing", "skill:morning-briefing", {".md", ".json"}),
    "eod_reviews": ("eod_review", "skill:eod-review", {".md", ".json"}),
    "critic_reports": ("critic_report", "agent:critic", {".md", ".json", ".txt"}),
    "validation_reports": ("validation_report", "agent:research", {".md", ".json"}),
    "research_results": ("research_result", "agent:research", {".md", ".json"}),
    "macro_research": ("macro_research", "agent:macro-research", {".md", ".json", ".txt"}),
    "regime_reports": ("regime_report", "agent:regime-detector", {".md", ".json", ".txt"}),
    "alpha_discovery": ("alpha_discovery", "agent:alpha-discovery", {".md", ".json", ".txt"}),
    "research_reports": ("research_report", "agent:research", {".md", ".json"}),
    "strategy_reports": ("strategy_report", "agent:research", {".md", ".json"}),
    "reports": ("report", "system", {".md", ".json"}),
    "performance_reports": ("performance_report", "system", {".md", ".json"}),
    "news_analysis": ("news_analysis", "agent:news-analyst", {".md", ".json"}),
    "swarm_history": ("swarm_report", "skill:swarm-operator", {".json"}),
}


def _extract_file_date(filename: str) -> datetime | None:
    """Try to extract a date from a filename."""
    for pat, fmt in [
        (r"(\d{4}-\d{2}-\d{2})", "%Y-%m-%d"),
        (r"(\d{8}_\d{6})", "%Y%m%d_%H%M%S"),
        (r"(\d{8})", "%Y%m%d"),
    ]:
        m = re.search(pat, filename)
        if m:
            try:
                return datetime.strptime(m.group(1), fmt)
            except ValueError:
                continue
    return None


def _title_from_filename(filepath: Path) -> str:
    """Generate a readable title from a filename."""
    name = filepath.stem
    name = re.sub(r"_?\d{8}(_\d{6})?", "", name)
    name = re.sub(r"_?\d{4}-\d{2}-\d{2}", "", name)
    name = name.strip("_").replace("_", " ").strip()
    return name.title() if name else filepath.name


def _extract_symbols(text: str) -> list[str]:
    """Extract stock symbols from text content."""
    symbols = set()
    for m in re.finditer(r'\$([A-Z]{1,5})\b', text[:5000]):
        symbols.add(m.group(1))
    for m in re.finditer(r'\b([A-Z]{2,5})(?:_|\b)', text[:500]):
        if m.group(1) not in _EXCLUDES:
            symbols.add(m.group(1))
    return sorted(symbols)[:10]


def migrate_documents(session: Session) -> int:
    """Scan mapped directories and index files as documents."""
    results_dir = _results_dir()
    count = 0

    for dirname, (doc_type, source, extensions) in DIRECTORY_MAP.items():
        dir_path = results_dir / dirname
        if not dir_path.is_dir():
            continue

        for filepath in sorted(dir_path.iterdir()):
            if filepath.is_dir() or filepath.suffix not in extensions:
                continue

            doc_id = f"doc_{dirname}_{filepath.stem}"
            title = _title_from_filename(filepath)
            created = _extract_file_date(filepath.name)

            content_inline = None
            symbols = []
            try:
                content = filepath.read_text(errors="replace")
                if filepath.stat().st_size <= 10240:
                    content_inline = content
                symbols = _extract_symbols(content[:5000])
                if not created:
                    created = datetime.fromtimestamp(filepath.stat().st_mtime)
            except Exception:
                if not created:
                    try:
                        created = datetime.fromtimestamp(filepath.stat().st_mtime)
                    except Exception:
                        created = datetime.utcnow()

            # Auto-generate summary
            summary = title
            if content_inline:
                text = content_inline
                if text.startswith("---"):
                    lines = text.split("\n")
                    end = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == "---"), 0)
                    summary = "\n".join(lines[end + 1:])[:500].strip() or title
                elif not text.startswith("{"):
                    summary = text[:500].strip()

            doc = Document(
                id=doc_id,
                doc_type=doc_type,
                title=title,
                summary=summary,
                file_path=str(filepath),
                content_inline=content_inline,
                created=created,
                symbols=json.dumps(symbols),
                tags=json.dumps([]),
                source=source,
            )
            session.merge(doc)
            count += 1

    return count


def migrate_insights(session: Session) -> int:
    """Import insights from session tracker JSON."""
    insights_path = _results_dir() / "research_tracker" / "insights.json"
    if not insights_path.exists():
        return 0

    try:
        data = json.loads(insights_path.read_text())
    except Exception as e:
        print(f"  WARN: Could not read insights.json: {e}")
        return 0

    count = 0
    for key, ins in data.items():
        insight_id = ins.get("id", key)
        record = Insight(
            id=insight_id,
            title=ins.get("title", ""),
            description=ins.get("description", ""),
            category=ins.get("category", ""),
            tags=json.dumps(ins.get("tags", [])),
            evidence=json.dumps(ins.get("evidence", {})),
            confidence=ins.get("confidence", 0.5),
            validated=ins.get("validated", False),
            actionable=ins.get("actionable", True),
            implemented=ins.get("implemented", False),
            source_session=ins.get("source_session", ""),
            related_insights=json.dumps(ins.get("related_insights", [])),
            created_at=_parse_datetime(ins.get("created_at")) or datetime.utcnow(),
            updated_at=_parse_datetime(ins.get("updated_at")) or datetime.utcnow(),
        )
        session.merge(record)
        count += 1

    return count


def migrate_experiments(session: Session) -> int:
    """Import experiments from session tracker JSON."""
    experiments_path = _results_dir() / "research_tracker" / "experiments.json"
    if not experiments_path.exists():
        return 0

    try:
        data = json.loads(experiments_path.read_text())
    except Exception as e:
        print(f"  WARN: Could not read experiments.json: {e}")
        return 0

    count = 0
    for key, exp in data.items():
        exp_id = exp.get("id", key)
        record = Experiment(
            id=exp_id,
            strategy=exp.get("strategy", ""),
            symbol=exp.get("symbol", ""),
            params=json.dumps(exp.get("params", {})),
            result=exp.get("result", ""),
            sharpe=exp.get("sharpe"),
            p_value=exp.get("p_value"),
            notes=exp.get("notes", ""),
            session_id=exp.get("session_id", ""),
            run_at=_parse_datetime(exp.get("run_at")) or datetime.utcnow(),
        )
        session.merge(record)
        count += 1

    return count


def run_migration(dry_run: bool = False):
    """Run full migration from files to SQLite."""
    print("=" * 60)
    print("Athena Database Migration")
    print(f"  Source: {_results_dir()}")
    print(f"  Target: {_results_dir() / 'athena.db'}")
    print(f"  Dry run: {dry_run}")
    print("=" * 60)

    # Create tables
    init_db()
    print("Tables created/verified.")

    if dry_run:
        print("\nDRY RUN — scanning files only:")
        rd = _results_dir()
        for label, path, pattern in [
            ("Companies", rd / "knowledge" / "companies", "*.yaml"),
            ("Sectors", rd / "knowledge" / "sectors", "*.yaml"),
            ("Theses", rd / "theses", "*.yaml"),
            ("Learnings", rd / "learnings", "*.json"),
            ("Decisions", rd / "decisions", "decisions_*.json"),
            ("Signal Provenance", rd / "signal_provenance", "*.json"),
        ]:
            if path.exists():
                files = list(path.glob(pattern))
                print(f"  {label}: {len(files)} files")
            else:
                print(f"  {label}: directory not found")

        for label, path in [
            ("Agent Activity", rd / "logs" / "agent_activity.jsonl"),
            ("Operator Log", rd / "logs" / "operator_log.jsonl"),
        ]:
            if path.exists():
                lines = len([l for l in path.read_text().strip().split("\n") if l.strip()])
                print(f"  {label}: {lines} records")
            else:
                print(f"  {label}: file not found")

        # Document backfill preview
        print("\n  --- Document Index ---")
        doc_count = 0
        for dirname, (doc_type, source, extensions) in DIRECTORY_MAP.items():
            dir_path = rd / dirname
            if dir_path.is_dir():
                files = [f for f in dir_path.iterdir() if f.suffix in extensions and f.is_file()]
                print(f"  {dirname}: {len(files)} files -> {doc_type}")
                doc_count += len(files)
        print(f"  Total documents to index: {doc_count}")

        # Session tracker preview
        insights_path = rd / "research_tracker" / "insights.json"
        experiments_path = rd / "research_tracker" / "experiments.json"
        if insights_path.exists():
            data = json.loads(insights_path.read_text())
            print(f"  Insights: {len(data)} records")
        if experiments_path.exists():
            data = json.loads(experiments_path.read_text())
            print(f"  Experiments: {len(data)} records")
        return

    with get_db() as session:
        migrators = [
            ("Companies", migrate_companies),
            ("Sectors", migrate_sectors),
            ("Theses", migrate_theses),
            ("Decisions", migrate_decisions),
            ("Learnings", migrate_learnings),
            ("Signal Provenance", migrate_signal_provenance),
            ("Agent Activity", migrate_agent_activity),
            ("Operator Log", migrate_operator_log),
            ("Documents", migrate_documents),
            ("Insights", migrate_insights),
            ("Experiments", migrate_experiments),
        ]

        total = 0
        for label, func in migrators:
            count = func(session)
            print(f"  {label}: {count} records migrated")
            total += count

        session.commit()
        print(f"\nTotal: {total} records migrated successfully.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    run_migration(dry_run=dry_run)
