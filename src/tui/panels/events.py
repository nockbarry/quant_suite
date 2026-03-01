"""Events panel — live event feed from ProcessEvent table."""

import json
from datetime import datetime

from textual.widgets import Static


class EventsPanel(Static):
    """Scrolling event log: recent ProcessEvent rows."""

    def refresh_data(self) -> None:
        lines = ["[b]EVENT LOG[/b]  ", ""]
        try:
            from src.db.database import get_db
            from src.db.models import ProcessEvent

            with get_db() as session:
                events = (
                    session.query(ProcessEvent)
                    .order_by(ProcessEvent.timestamp.desc())
                    .limit(30)
                    .all()
                )

                if not events:
                    lines.append("  [dim]No events yet[/dim]")
                    self.update("\n".join(lines))
                    return

                for e in events:
                    ts = e.timestamp.strftime("%H:%M:%S") if e.timestamp else "??:??:??"
                    sev_color = {"info": "dim", "warning": "yellow", "critical": "red"}.get(
                        e.severity, "dim"
                    )
                    etype = e.event_type[:20]
                    sym = e.symbol or ""
                    title_short = (e.title or "")[:45]
                    lines.append(
                        f"  [{sev_color}]{ts}[/{sev_color}] "
                        f"{etype:<20} {sym:<6} {title_short}"
                    )

        except Exception as e:
            lines.append(f"  [red]Error: {e}[/red]")

        self.update("\n".join(lines))
