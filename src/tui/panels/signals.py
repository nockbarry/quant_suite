"""Signals panel — recent signal events from ProcessEvent table."""

import json
from datetime import datetime, timedelta

from textual.widgets import Static


class SignalsPanel(Static):
    """Recent signal events and convergences."""

    def refresh_data(self) -> None:
        lines = ["[b]SIGNALS (24h)[/b]", ""]
        try:
            from src.db.database import get_db
            from src.db.models import ProcessEvent

            cutoff = datetime.utcnow() - timedelta(hours=24)

            with get_db() as session:
                events = (
                    session.query(ProcessEvent)
                    .filter(
                        ProcessEvent.event_type.like("signal_%"),
                        ProcessEvent.timestamp > cutoff,
                    )
                    .order_by(ProcessEvent.timestamp.desc())
                    .limit(20)
                    .all()
                )

                # Separate convergences from individual signals
                convergences = [e for e in events if "convergence" in e.event_type]
                signals = [e for e in events if "convergence" not in e.event_type]

                if convergences:
                    for e in convergences[:3]:
                        detail = _parse_detail(e.detail)
                        count = detail.get("signal_count", "?")
                        direction = detail.get("direction", "?")
                        icon = "[green]^[/green]" if direction == "bullish" else "[red]v[/red]"
                        lines.append(
                            f"  {icon} [bold]{e.symbol or '?'}[/bold] "
                            f"({count} signals, {direction})"
                        )
                    lines.append("")

                if signals:
                    for e in signals[:10]:
                        detail = _parse_detail(e.detail)
                        direction = detail.get("direction", "")
                        source = e.source[:10] if e.source else "?"
                        icon = "[green]^[/green]" if direction == "bullish" else "[red]v[/red]" if direction == "bearish" else "[dim]-[/dim]"
                        age = _age_str(e.timestamp)
                        lines.append(
                            f"  {icon} {e.symbol or '?':<6} {source:<10} {age:>5}"
                        )
                else:
                    lines.append("  [dim]No recent signals[/dim]")

        except Exception as e:
            lines.append(f"  [red]Error: {e}[/red]")

        self.update("\n".join(lines))


def _parse_detail(detail_str: str) -> dict:
    try:
        if detail_str:
            return json.loads(detail_str)
    except (json.JSONDecodeError, TypeError):
        pass
    return {}


def _age_str(dt: datetime | None) -> str:
    if not dt:
        return "?"
    delta = (datetime.utcnow() - dt).total_seconds()
    if delta < 60:
        return f"{int(delta)}s"
    if delta < 3600:
        return f"{int(delta // 60)}m"
    return f"{int(delta // 3600)}h"
