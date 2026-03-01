"""Agents panel — shows running/recent agents from AgentRun table."""

from datetime import datetime

from textual.widgets import Static


class AgentsPanel(Static):
    """Running and recent agents with heartbeat age and status."""

    def refresh_data(self) -> None:
        lines = ["[b]AGENTS[/b]", ""]
        try:
            from src.db.database import get_db
            from src.db.models import AgentRun

            with get_db() as session:
                runs = (
                    session.query(AgentRun)
                    .order_by(AgentRun.started_at.desc())
                    .limit(15)
                    .all()
                )

                running = [r for r in runs if r.status == "running"]
                done = [r for r in runs if r.status != "running"]

                if running:
                    for r in running:
                        age = _age_str(r.started_at)
                        hb = _hb_str(r.heartbeat_at) if r.heartbeat_at else "no hb"
                        lines.append(
                            f"  [green]●[/green] {r.agent_type[:18]:<18} {age:>6}  {hb}"
                        )
                else:
                    lines.append("  [dim]No running agents[/dim]")

                lines.append("")
                for r in done[:8]:
                    icon = "[green]✓[/green]" if r.status == "completed" else "[red]✗[/red]"
                    dur = r.to_dict().get("duration_display", "?")
                    lines.append(
                        f"  {icon} {r.agent_type[:18]:<18} {r.status:<9} {dur or ''}"
                    )
        except Exception as e:
            lines.append(f"  [red]Error: {e}[/red]")

        self.update("\n".join(lines))


def _age_str(dt: datetime | None) -> str:
    if not dt:
        return "?"
    delta = (datetime.utcnow() - dt).total_seconds()
    if delta < 60:
        return f"{int(delta)}s"
    if delta < 3600:
        return f"{int(delta // 60)}m"
    return f"{int(delta // 3600)}h"


def _hb_str(dt: datetime | None) -> str:
    if not dt:
        return ""
    delta = (datetime.utcnow() - dt).total_seconds()
    if delta < 60:
        return f"hb:{int(delta)}s"
    return f"[yellow]hb:{int(delta // 60)}m[/yellow]"
