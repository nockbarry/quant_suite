"""System panel — state.json freshness, DB health, daemon status."""

import os
import time
from datetime import datetime
from pathlib import Path

from textual.widgets import Static


def _state_path() -> Path:
    results = os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results"))
    return Path(results) / "live" / "state.json"


def _db_path() -> Path:
    results = os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results"))
    return Path(results) / "athena.db"


class SystemPanel(Static):
    """System health: state freshness, DB, event counts, agents."""

    def refresh_data(self) -> None:
        lines = ["[b]SYSTEM HEALTH[/b]", ""]

        # State.json freshness
        try:
            sp = _state_path()
            if sp.exists():
                age_s = time.time() - sp.stat().st_mtime
                if age_s < 600:
                    lines.append(f"  State: [green]{int(age_s)}s ago ✓[/green]")
                elif age_s < 3600:
                    lines.append(f"  State: [yellow]{int(age_s // 60)}m ago[/yellow]")
                else:
                    lines.append(f"  State: [red]{int(age_s // 3600)}h ago ✗[/red]")
            else:
                lines.append("  State: [red]NOT FOUND[/red]")
        except Exception:
            lines.append("  State: [red]ERROR[/red]")

        # DB health + event count
        try:
            from src.db.database import get_db
            from src.db.models import ProcessEvent, AgentRun

            with get_db() as session:
                event_count = session.query(ProcessEvent).count()
                running_count = session.query(AgentRun).filter(
                    AgentRun.status == "running"
                ).count()
                stale_count = 0
                # Check for stale agents (heartbeat > 10 min)
                from datetime import timedelta
                hb_cutoff = datetime.utcnow() - timedelta(minutes=10)
                stale = session.query(AgentRun).filter(
                    AgentRun.status == "running",
                    AgentRun.heartbeat_at != None,
                    AgentRun.heartbeat_at < hb_cutoff,
                ).count()
                stale_count = stale

            lines.append(f"  DB: [green]OK[/green] ({event_count:,} events)")
            if stale_count > 0:
                lines.append(f"  Agents: {running_count} running, [red]{stale_count} stale[/red]")
            else:
                lines.append(f"  Agents: {running_count} running, 0 stale")
        except Exception as e:
            lines.append(f"  DB: [red]ERROR ({e})[/red]")

        # Broker status (quick check)
        try:
            import yaml
            creds_path = Path.home() / "projects/quant_suite/config/credentials.yaml"
            if creds_path.exists():
                with open(creds_path) as f:
                    creds = yaml.safe_load(f)
                has_key = bool(creds.get("alpaca", {}).get("api_key"))
                lines.append(f"  Broker: {'[green]Configured[/green]' if has_key else '[red]No key[/red]'}")
            else:
                lines.append("  Broker: [dim]No config[/dim]")
        except Exception:
            lines.append("  Broker: [dim]Unknown[/dim]")

        # Current time
        lines.append(f"  Time: {datetime.now().strftime('%H:%M:%S ET')}")

        self.update("\n".join(lines))
