"""
Agent Wrapper with Automatic Monitoring Integration.

Wraps agent spawning to automatically track activity in the monitoring dashboard,
regardless of whether the agent itself can write to the logs.
"""

import asyncio
import json
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .agent_monitor import (
    AgentActivityMonitor,
    AgentType,
    AgentStatus,
    get_agent_monitor,
)


@dataclass
class AgentResult:
    """Result from an agent execution."""
    agent_id: str
    success: bool
    output: str
    duration_seconds: float
    error: str | None = None


class MonitoredAgentRunner:
    """
    Runs agents with automatic monitoring integration.

    This wrapper:
    1. Logs agent start to the activity monitor
    2. Tracks execution time
    3. Logs completion/failure
    4. Updates the unified dashboard
    """

    def __init__(self):
        self.monitor = get_agent_monitor()
        self.results_dir = Path.home() / "quant_results"
        self.logs_dir = self.results_dir / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def run_python_agent(
        self,
        name: str,
        agent_type: AgentType,
        script: str,
        timeout: int = 300,
        background: bool = False,
    ) -> AgentResult | str:
        """
        Run a Python script as a monitored agent.

        Args:
            name: Human-readable agent name/task
            agent_type: Type of agent
            script: Python script content to execute
            timeout: Timeout in seconds
            background: If True, run in background and return agent_id

        Returns:
            AgentResult if foreground, agent_id if background
        """
        # Start monitoring
        agent_id = self.monitor.start_agent(agent_type, name)

        # Write script to temp file
        script_path = self.logs_dir / f"agent_{agent_id}.py"
        script_path.write_text(script)

        if background:
            # Run in background with output capture
            output_path = self.logs_dir / f"agent_{agent_id}.output"
            self._run_background(script_path, output_path, timeout, agent_id)
            return agent_id
        else:
            # Run synchronously
            return self._run_sync(script_path, timeout, agent_id)

    def _run_sync(self, script_path: Path, timeout: int, agent_id: str) -> AgentResult:
        """Run agent synchronously."""
        start_time = time.time()

        try:
            result = subprocess.run(
                ["python3", str(script_path)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(Path.home() / "projects" / "quant_suite"),
                env={"PYTHONPATH": str(Path.home() / "projects" / "quant_suite")},
            )

            duration = time.time() - start_time
            success = result.returncode == 0
            output = result.stdout + result.stderr
            error = result.stderr if not success else None

            # Log completion
            self.monitor.complete_agent(
                agent_id,
                result_summary=output[:500] if success else f"Error: {error[:200]}",
                success=success,
                error_message=error,
            )

            return AgentResult(
                agent_id=agent_id,
                success=success,
                output=output,
                duration_seconds=duration,
                error=error,
            )

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            self.monitor.complete_agent(
                agent_id,
                result_summary="Timeout",
                success=False,
                error_message=f"Agent timed out after {timeout}s",
            )
            return AgentResult(
                agent_id=agent_id,
                success=False,
                output="",
                duration_seconds=duration,
                error=f"Timeout after {timeout}s",
            )
        except Exception as e:
            duration = time.time() - start_time
            self.monitor.complete_agent(
                agent_id,
                result_summary="Exception",
                success=False,
                error_message=str(e),
            )
            return AgentResult(
                agent_id=agent_id,
                success=False,
                output="",
                duration_seconds=duration,
                error=str(e),
            )

    def _run_background(
        self,
        script_path: Path,
        output_path: Path,
        timeout: int,
        agent_id: str,
    ) -> None:
        """Start agent in background."""
        # Create wrapper script that logs completion
        wrapper_script = f'''
import subprocess
import json
from datetime import datetime
from pathlib import Path

# Run the actual agent
result = subprocess.run(
    ["python3", "{script_path}"],
    capture_output=True,
    text=True,
    timeout={timeout},
    cwd=str(Path.home() / "projects" / "quant_suite"),
)

# Write output
output_path = Path("{output_path}")
output_path.write_text(result.stdout + result.stderr)

# Log completion to activity log
log_path = Path.home() / "quant_results" / "logs" / "agent_activity.jsonl"
record = {{
    "timestamp": datetime.now().isoformat(),
    "type": "agent_complete",
    "agent_id": "{agent_id}",
    "status": "completed" if result.returncode == 0 else "failed",
    "result_summary": (result.stdout[:500] if result.returncode == 0 else result.stderr[:200]),
}}
with open(log_path, "a") as f:
    f.write(json.dumps(record) + "\\n")
'''

        wrapper_path = self.logs_dir / f"wrapper_{agent_id}.py"
        wrapper_path.write_text(wrapper_script)

        # Start background process
        subprocess.Popen(
            ["python3", str(wrapper_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(Path.home() / "projects" / "quant_suite"),
        )

    def check_agent_status(self, agent_id: str) -> dict:
        """Check status of a background agent."""
        output_path = self.logs_dir / f"agent_{agent_id}.output"

        if output_path.exists():
            return {
                "status": "completed",
                "output": output_path.read_text()[:2000],
            }
        else:
            return {
                "status": "running",
                "output": None,
            }


# Market watcher that runs as a daemon
MARKET_WATCHER_SCRIPT = '''
"""Market watcher daemon - runs independently of Claude Code."""
import json
import time
from datetime import datetime
from pathlib import Path

def market_check():
    """Perform a single market check."""
    state_file = Path.home() / "quant_results" / "live" / "state.json"
    log_file = Path.home() / "quant_results" / "logs" / "market_watch.log"

    log_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(state_file) as f:
            state = json.load(f)

        market = state.get("market", {})
        portfolio = state.get("portfolio", {})
        positions = state.get("positions", [])

        # Extract metrics
        spy_price = market.get("spy_price", 0)
        spy_change = market.get("spy_change_pct", 0)
        vix = market.get("vix", 0)
        equity = portfolio.get("equity", 0)
        day_pnl_pct = portfolio.get("day_pnl_pct", 0)

        # Check alerts
        alerts = []
        if vix > 25:
            alerts.append(f"VIX HIGH: {vix:.2f}")
        if day_pnl_pct < -3:
            alerts.append(f"DRAWDOWN: {day_pnl_pct:.2f}%")

        for pos in positions:
            try:
                pnl = float(pos.get("unrealized_pnl_pct", 0))
                if pnl < -5:
                    alerts.append(f"{pos.get('symbol', 'UNK')} DOWN {pnl:.1f}%")
            except:
                continue

        # Format check
        timestamp = datetime.now().strftime("%H:%M:%S")
        check = f"""
=== MARKET CHECK [{timestamp}] ===
SPY: ${spy_price:.2f} ({spy_change:+.2f}%)
VIX: {vix:.2f}
Portfolio: ${equity:,.2f} ({day_pnl_pct:+.2f}%)
Alerts: {"; ".join(alerts) if alerts else "None"}
"""

        # Write to log
        with open(log_file, "a") as f:
            f.write(check)

        # Update agent activity log
        activity_log = Path.home() / "quant_results" / "logs" / "agent_activity.jsonl"
        record = {
            "timestamp": datetime.now().isoformat(),
            "type": "market_check",
            "spy": spy_price,
            "spy_change": spy_change,
            "vix": vix,
            "equity": equity,
            "day_pnl_pct": day_pnl_pct,
            "alerts": alerts,
        }
        with open(activity_log, "a") as f:
            f.write(json.dumps(record) + "\\n")

        return check, alerts

    except Exception as e:
        return f"Error: {e}", []


def run_watcher(interval_seconds: int = 300, duration_minutes: int = 60):
    """Run market watcher for specified duration."""
    checks = int(duration_minutes * 60 / interval_seconds)

    print(f"Starting market watcher: {checks} checks, {interval_seconds}s interval")

    for i in range(checks):
        check, alerts = market_check()
        print(check)

        if alerts:
            print("!!! ALERTS TRIGGERED !!!")
            for alert in alerts:
                print(f"  - {alert}")

        if i < checks - 1:
            time.sleep(interval_seconds)

    print("Market watcher complete")


if __name__ == "__main__":
    import sys
    interval = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    run_watcher(interval, duration)
'''


def create_market_watcher_daemon():
    """Create the market watcher script for daemon execution."""
    scripts_dir = Path.home() / "projects" / "quant_suite" / "scripts" / "daemons"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    script_path = scripts_dir / "market_watcher.py"
    script_path.write_text(MARKET_WATCHER_SCRIPT)
    script_path.chmod(0o755)

    return script_path


# Research agent that logs its own activity
RESEARCH_AGENT_SCRIPT = '''
"""Research agent that logs its own activity."""
import json
from datetime import datetime
from pathlib import Path

def log_activity(event_type: str, data: dict):
    """Log activity to the central log."""
    log_path = Path.home() / "quant_results" / "logs" / "agent_activity.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "timestamp": datetime.now().isoformat(),
        "type": event_type,
        **data,
    }

    with open(log_path, "a") as f:
        f.write(json.dumps(record) + "\\n")


def run_research(task: str):
    """Run a research task with activity logging."""
    agent_id = f"research_{datetime.now().strftime('%H%M%S')}"

    # Log start
    log_activity("agent_start", {
        "agent_id": agent_id,
        "agent_type": "research",
        "task": task,
        "started_at": datetime.now().isoformat(),
    })

    try:
        # Load context
        state_file = Path.home() / "quant_results" / "live" / "state.json"
        with open(state_file) as f:
            state = json.load(f)

        # Perform research (simplified for daemon)
        portfolio = state.get("portfolio", {})
        positions = state.get("positions", [])

        # Calculate metrics
        total = portfolio.get("equity", 0)
        winners = [p for p in positions if float(p.get("unrealized_pnl_pct", 0)) > 5]
        losers = [p for p in positions if float(p.get("unrealized_pnl_pct", 0)) < -5]

        result = {
            "total_equity": total,
            "positions": len(positions),
            "winners_5pct": len(winners),
            "losers_5pct": len(losers),
            "top_winner": max(positions, key=lambda p: float(p.get("unrealized_pnl_pct", 0)))["symbol"] if positions else None,
        }

        # Log completion
        log_activity("agent_complete", {
            "agent_id": agent_id,
            "status": "completed",
            "result_summary": json.dumps(result),
            "completed_at": datetime.now().isoformat(),
        })

        return result

    except Exception as e:
        log_activity("agent_complete", {
            "agent_id": agent_id,
            "status": "failed",
            "error_message": str(e),
            "completed_at": datetime.now().isoformat(),
        })
        raise


if __name__ == "__main__":
    import sys
    task = sys.argv[1] if len(sys.argv) > 1 else "general research"
    result = run_research(task)
    print(json.dumps(result, indent=2))
'''


def create_research_daemon():
    """Create the research agent script for daemon execution."""
    scripts_dir = Path.home() / "projects" / "quant_suite" / "scripts" / "daemons"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    script_path = scripts_dir / "research_agent.py"
    script_path.write_text(RESEARCH_AGENT_SCRIPT)
    script_path.chmod(0o755)

    return script_path
