#!/usr/bin/env python3
"""Calendar CLI - Manage market calendar, predictions, and learnings.

Usage:
    # Initialize calendar with 2026 data
    python scripts/calendar_cli.py init

    # View upcoming events
    python scripts/calendar_cli.py events --days 7
    python scripts/calendar_cli.py events --week
    python scripts/calendar_cli.py events --month 2026-03
    python scripts/calendar_cli.py events --category fed

    # View predictions
    python scripts/calendar_cli.py predictions
    python scripts/calendar_cli.py predictions --source claude
    python scripts/calendar_cli.py predictions --due

    # Resolve a prediction
    python scripts/calendar_cli.py resolve <prediction_id> --status correct --notes "Played out as expected"

    # Add a learning
    python scripts/calendar_cli.py learn "Fed more hawkish than expected" --event fomc_2026_01 --tags fed,policy
    python scripts/calendar_cli.py learn "Earnings beat but stock sold off" --symbol NVDA

    # Add custom event
    python scripts/calendar_cli.py add-event "Custom Event" 2026-03-15 --category custom --impact medium

    # Add prediction
    python scripts/calendar_cli.py add-prediction "My prediction" --source manual --target-date 2026-06-30

    # Statistics
    python scripts/calendar_cli.py stats

    # Export
    python scripts/calendar_cli.py export --output calendar_backup.json

Created: 2026-01-20
"""

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.knowledge.market_calendar import (
    MarketCalendar,
    CalendarEvent,
    Prediction,
    CalendarLearning,
    EventCategory,
    EventImpact,
    PredictionStatus,
    initialize_2026_calendar,
)


def cmd_init(args):
    """Initialize calendar with 2026 data."""
    print("Initializing 2026 market calendar...")
    calendar = initialize_2026_calendar()
    stats = calendar.get_statistics()
    print(f"\nCalendar initialized:")
    print(f"  Events: {stats['total_events']}")
    print(f"  Predictions: {stats['total_predictions']}")
    print(f"  Learnings: {stats['total_learnings']}")


def cmd_events(args):
    """View calendar events."""
    calendar = MarketCalendar()

    if args.week:
        print(calendar.get_week_summary())
        return

    if args.month:
        year, month = map(int, args.month.split("-"))
        print(calendar.get_month_summary(year, month))
        return

    # Get events in range
    start = date.today()
    end = start + timedelta(days=args.days)

    category = EventCategory(args.category) if args.category else None
    min_impact = EventImpact(args.min_impact) if args.min_impact else None

    events = calendar.get_events_in_range(start, end, category=category, min_impact=min_impact)

    if not events:
        print(f"No events in the next {args.days} days")
        return

    print(f"\n{'='*60}")
    print(f"UPCOMING EVENTS ({len(events)} events, next {args.days} days)")
    print(f"{'='*60}\n")

    # Group by date
    current_date = None
    for e in events:
        if e.date != current_date:
            current_date = e.date
            print(f"\n{e.date.strftime('%A, %B %d, %Y')}")
            print("-" * 40)

        impact_emoji = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
            "unknown": "⚪"
        }.get(e.impact.value, "⚪")

        time_str = f" ({e.time})" if e.time else ""
        print(f"  {impact_emoji} [{e.category.value.upper()}] {e.title}{time_str}")
        print(f"     {e.description[:80]}...")
        if e.symbols_affected:
            print(f"     Symbols: {', '.join(e.symbols_affected[:5])}")


def cmd_predictions(args):
    """View predictions."""
    calendar = MarketCalendar()

    if args.due:
        predictions = calendar.get_predictions_due_for_review()
        print(f"\n{'='*60}")
        print(f"PREDICTIONS DUE FOR REVIEW ({len(predictions)})")
        print(f"{'='*60}\n")
    elif args.source:
        predictions = calendar.get_predictions_by_source(args.source)
        print(f"\n{'='*60}")
        print(f"PREDICTIONS FROM {args.source.upper()} ({len(predictions)})")
        print(f"{'='*60}\n")
    else:
        predictions = calendar.get_pending_predictions()
        print(f"\n{'='*60}")
        print(f"PENDING PREDICTIONS ({len(predictions)})")
        print(f"{'='*60}\n")

    for p in predictions[:args.limit]:
        status_emoji = {
            "pending": "⏳",
            "correct": "✅",
            "incorrect": "❌",
            "partial": "🟡",
            "expired": "⚪"
        }.get(p.status.value, "❓")

        direction_emoji = {
            "bullish": "📈",
            "bearish": "📉",
            "neutral": "➡️"
        }.get(p.direction or "", "")

        print(f"{status_emoji} {p.title}")
        print(f"   Source: {p.source}" + (f" ({p.source_detail})" if p.source_detail else ""))
        print(f"   {direction_emoji} {p.prediction[:100]}...")
        if p.target_date:
            days_until = (p.target_date - date.today()).days
            print(f"   Target: {p.target_date} ({days_until} days)")
        if p.confidence:
            print(f"   Confidence: {p.confidence:.0%}")
        if p.symbols:
            print(f"   Symbols: {', '.join(p.symbols)}")
        print(f"   ID: {p.id}")
        print()


def cmd_resolve(args):
    """Resolve a prediction."""
    calendar = MarketCalendar()

    status = PredictionStatus(args.status)
    pred = calendar.resolve_prediction(
        args.prediction_id,
        status=status,
        actual_outcome=args.outcome or "",
        accuracy_score=args.accuracy,
        notes=args.notes or ""
    )

    if pred:
        print(f"✅ Resolved prediction: {pred.title}")
        print(f"   Status: {status.value}")
        if args.outcome:
            print(f"   Outcome: {args.outcome}")
    else:
        print(f"❌ Prediction not found: {args.prediction_id}")


def cmd_learn(args):
    """Add a learning."""
    calendar = MarketCalendar()

    tags = args.tags.split(",") if args.tags else []

    learning = calendar.add_learning(
        content=args.content,
        source=args.source,
        event_id=args.event,
        prediction_id=args.prediction,
        symbol=args.symbol,
        tags=tags,
        confidence=args.confidence,
    )

    print(f"✅ Added learning: {learning.id}")
    print(f"   Content: {learning.content[:80]}...")
    if learning.event_ids:
        print(f"   Linked to events: {', '.join(learning.event_ids)}")
    if learning.prediction_ids:
        print(f"   Linked to predictions: {', '.join(learning.prediction_ids)}")


def cmd_add_event(args):
    """Add a custom event."""
    calendar = MarketCalendar()

    event_date = date.fromisoformat(args.date)
    category = EventCategory(args.category)
    impact = EventImpact(args.impact)

    symbols = args.symbols.split(",") if args.symbols else []
    sectors = args.sectors.split(",") if args.sectors else []

    event = calendar.add_event(
        title=args.title,
        event_date=event_date,
        category=category,
        impact=impact,
        description=args.description or args.title,
        symbols_affected=symbols,
        sectors_affected=sectors,
        time=args.time,
        source=args.source,
    )

    print(f"✅ Added event: {event.id}")
    print(f"   Title: {event.title}")
    print(f"   Date: {event.date}")


def cmd_add_prediction(args):
    """Add a prediction."""
    calendar = MarketCalendar()

    target_date = date.fromisoformat(args.target_date) if args.target_date else None
    symbols = args.symbols.split(",") if args.symbols else []
    assumptions = args.assumptions.split("|") if args.assumptions else []
    triggers = args.triggers.split("|") if args.triggers else []

    pred = calendar.add_prediction(
        title=args.title,
        prediction=args.prediction,
        source=args.source,
        target_date=target_date,
        category=EventCategory(args.category) if args.category else EventCategory.CUSTOM,
        confidence=args.confidence,
        symbols=symbols,
        direction=args.direction,
        reasoning=args.reasoning or "",
        key_assumptions=assumptions,
        invalidation_triggers=triggers,
    )

    print(f"✅ Added prediction: {pred.id}")
    print(f"   Title: {pred.title}")
    print(f"   Source: {pred.source}")


def cmd_stats(args):
    """Show calendar statistics."""
    calendar = MarketCalendar()
    stats = calendar.get_statistics()

    print(f"\n{'='*60}")
    print("CALENDAR STATISTICS")
    print(f"{'='*60}\n")

    print(f"Total Events: {stats['total_events']}")
    print(f"Total Predictions: {stats['total_predictions']}")
    print(f"Total Learnings: {stats['total_learnings']}")
    print()
    print(f"Upcoming Events (7 days): {stats['upcoming_events_7d']}")
    print(f"Upcoming Events (30 days): {stats['upcoming_events_30d']}")
    print()
    print(f"Predictions Pending: {stats['predictions_pending']}")
    print(f"Predictions Due for Review: {stats['predictions_due_review']}")

    if stats['overall_prediction_accuracy'] is not None:
        print(f"\nOverall Prediction Accuracy: {stats['overall_prediction_accuracy']:.1%}")

    if stats['claude_prediction_accuracy'] is not None:
        print(f"Claude Prediction Accuracy: {stats['claude_prediction_accuracy']:.1%}")

    # Show accuracy by source
    print("\nPrediction Accuracy by Source:")
    for source in ["claude", "goldman_sachs", "jpmorgan", "morgan_stanley"]:
        source_stats = calendar.get_prediction_accuracy(source=source)
        if source_stats['total'] > 0:
            acc = source_stats['accuracy']
            acc_str = f"{acc:.1%}" if acc is not None else "N/A"
            print(f"  {source}: {source_stats['resolved']}/{source_stats['total']} resolved, {acc_str} accuracy")


def cmd_export(args):
    """Export calendar to JSON."""
    calendar = MarketCalendar()
    data = calendar.export_to_json()

    output_path = Path(args.output)
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"✅ Exported calendar to {output_path}")
    print(f"   Events: {len(data['events'])}")
    print(f"   Predictions: {len(data['predictions'])}")
    print(f"   Learnings: {len(data['learnings'])}")


def main():
    parser = argparse.ArgumentParser(description="Market Calendar CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init
    init_parser = subparsers.add_parser("init", help="Initialize calendar with 2026 data")

    # events
    events_parser = subparsers.add_parser("events", help="View calendar events")
    events_parser.add_argument("--days", type=int, default=7, help="Number of days to look ahead")
    events_parser.add_argument("--week", action="store_true", help="Show week summary")
    events_parser.add_argument("--month", help="Show month summary (YYYY-MM)")
    events_parser.add_argument("--category", help="Filter by category")
    events_parser.add_argument("--min-impact", help="Minimum impact level")

    # predictions
    pred_parser = subparsers.add_parser("predictions", help="View predictions")
    pred_parser.add_argument("--source", help="Filter by source")
    pred_parser.add_argument("--due", action="store_true", help="Show only due for review")
    pred_parser.add_argument("--limit", type=int, default=20, help="Max predictions to show")

    # resolve
    resolve_parser = subparsers.add_parser("resolve", help="Resolve a prediction")
    resolve_parser.add_argument("prediction_id", help="Prediction ID")
    resolve_parser.add_argument("--status", required=True,
                                choices=["correct", "incorrect", "partial", "expired"],
                                help="Resolution status")
    resolve_parser.add_argument("--outcome", help="What actually happened")
    resolve_parser.add_argument("--accuracy", type=float, help="Accuracy score 0-1")
    resolve_parser.add_argument("--notes", help="Additional notes")

    # learn
    learn_parser = subparsers.add_parser("learn", help="Add a learning")
    learn_parser.add_argument("content", help="Learning content")
    learn_parser.add_argument("--source", default="manual", help="Source (briefing, research, manual)")
    learn_parser.add_argument("--event", help="Link to event ID")
    learn_parser.add_argument("--prediction", help="Link to prediction ID")
    learn_parser.add_argument("--symbol", help="Related symbol")
    learn_parser.add_argument("--tags", help="Comma-separated tags")
    learn_parser.add_argument("--confidence", type=float, default=0.5, help="Confidence 0-1")

    # add-event
    add_event_parser = subparsers.add_parser("add-event", help="Add a custom event")
    add_event_parser.add_argument("title", help="Event title")
    add_event_parser.add_argument("date", help="Event date (YYYY-MM-DD)")
    add_event_parser.add_argument("--category", default="custom", help="Event category")
    add_event_parser.add_argument("--impact", default="medium", help="Impact level")
    add_event_parser.add_argument("--description", help="Event description")
    add_event_parser.add_argument("--symbols", help="Comma-separated affected symbols")
    add_event_parser.add_argument("--sectors", help="Comma-separated affected sectors")
    add_event_parser.add_argument("--time", help="Event time (e.g., '14:00 ET')")
    add_event_parser.add_argument("--source", help="Event source")

    # add-prediction
    add_pred_parser = subparsers.add_parser("add-prediction", help="Add a prediction")
    add_pred_parser.add_argument("title", help="Prediction title")
    add_pred_parser.add_argument("prediction", help="Prediction text")
    add_pred_parser.add_argument("--source", default="manual", help="Prediction source")
    add_pred_parser.add_argument("--target-date", help="Target date (YYYY-MM-DD)")
    add_pred_parser.add_argument("--category", help="Category")
    add_pred_parser.add_argument("--confidence", type=float, help="Confidence 0-1")
    add_pred_parser.add_argument("--symbols", help="Comma-separated symbols")
    add_pred_parser.add_argument("--direction", choices=["bullish", "bearish", "neutral"])
    add_pred_parser.add_argument("--reasoning", help="Reasoning")
    add_pred_parser.add_argument("--assumptions", help="Pipe-separated assumptions")
    add_pred_parser.add_argument("--triggers", help="Pipe-separated invalidation triggers")

    # stats
    stats_parser = subparsers.add_parser("stats", help="Show calendar statistics")

    # export
    export_parser = subparsers.add_parser("export", help="Export calendar to JSON")
    export_parser.add_argument("--output", default="calendar_export.json", help="Output file path")

    args = parser.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "events":
        cmd_events(args)
    elif args.command == "predictions":
        cmd_predictions(args)
    elif args.command == "resolve":
        cmd_resolve(args)
    elif args.command == "learn":
        cmd_learn(args)
    elif args.command == "add-event":
        cmd_add_event(args)
    elif args.command == "add-prediction":
        cmd_add_prediction(args)
    elif args.command == "stats":
        cmd_stats(args)
    elif args.command == "export":
        cmd_export(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
