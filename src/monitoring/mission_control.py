#!/usr/bin/env python3
"""Mission Control - Unified view of the entire trading system.

Combines:
- Unified Dashboard (portfolio, risk, signals)
- Swarm Visualizer (agent activity, convergences)
- Data freshness (data sources status)
- Social signals (WSB, Stocktwits)

Single-terminal view of all system activity with auto-refresh.

Usage:
    python -m src.monitoring.mission_control
    python -m src.monitoring.mission_control --watch
    python -m src.monitoring.mission_control --compact
"""

import argparse
import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.core.paths import paths
from .unified_dashboard import UnifiedDashboard, UnifiedSystemStatus
from .swarm_visualizer import SwarmVisualizer
from .swarm_monitor import get_swarm_monitor

logger = logging.getLogger(__name__)


class MissionControl:
    """Combined mission control dashboard."""

    def __init__(self, results_dir: Path = None):
        self.results_dir = results_dir or paths.base
        self.unified = UnifiedDashboard(self.results_dir)
        self.swarm_viz = SwarmVisualizer()
        self._social_tracker = None

    def _get_social_signals(self) -> dict:
        """Get social signal summary."""
        try:
            # Check for WSB signals
            wsb_signals_file = self.results_dir / "social" / "wsb_signals.json"
            wsb_data = {}
            if wsb_signals_file.exists():
                with open(wsb_signals_file) as f:
                    wsb_data = json.load(f)

            # Get early signals (< 7 days old)
            early_signals = []
            all_signals = wsb_data.get("signals", [])
            for signal in all_signals[:10]:
                vintage = signal.get("signal_vintage", 0)
                phase = signal.get("current_phase", "unknown")
                if vintage <= 7 and phase in ["early", "growing"]:
                    early_signals.append(signal)

            return {
                "total_symbols": wsb_data.get("total_symbols", 0),
                "early_signals": len(early_signals),
                "top_symbols": [s.get("symbol") for s in all_signals[:5]],
                "early": early_signals[:3],
                "last_update": wsb_data.get("updated_at", "never"),
            }
        except Exception as e:
            logger.debug(f"Error getting social signals: {e}")
            return {"total_symbols": 0, "early_signals": 0, "top_symbols": [], "early": []}

    def _get_thesis_suggestions(self) -> list[dict]:
        """Get pending thesis suggestions."""
        try:
            suggestions_file = self.results_dir / "suggestions" / "thesis_suggestions.json"
            if not suggestions_file.exists():
                return []

            with open(suggestions_file) as f:
                data = json.load(f)

            pending = [
                s for s in data.get("suggestions", [])
                if s.get("status") == "pending"
            ]
            return pending[:3]
        except Exception:
            return []

    def _get_signal_provenance_summary(self) -> dict:
        """Get signal provenance summary."""
        try:
            provenance_dir = self.results_dir / "signal_provenance"
            if not provenance_dir.exists():
                return {"total": 0, "active": 0, "hit_rate": 0}

            total = 0
            active = 0
            hits = 0
            closed = 0

            for f in provenance_dir.glob("*.json"):
                with open(f) as file:
                    data = json.load(file)
                    signals = data.get("signals", [])
                    total += len(signals)
                    for s in signals:
                        outcome = s.get("outcome", "pending")
                        if outcome == "pending":
                            active += 1
                        elif outcome == "hit":
                            hits += 1
                            closed += 1
                        elif outcome == "miss":
                            closed += 1

            hit_rate = hits / closed if closed > 0 else 0

            return {
                "total": total,
                "active": active,
                "hit_rate": hit_rate,
                "closed": closed,
            }
        except Exception:
            return {"total": 0, "active": 0, "hit_rate": 0}

    async def get_full_status(self) -> dict:
        """Get complete system status."""
        # Get unified status
        unified_status = await self.unified.get_unified_status()

        # Get swarm status
        swarm_monitor = get_swarm_monitor()
        swarm_status = swarm_monitor.get_swarm_status()
        convergences = swarm_monitor.find_convergences(min_agents=2)

        # Get social signals
        social = self._get_social_signals()

        # Get thesis suggestions
        suggestions = self._get_thesis_suggestions()

        # Get provenance summary
        provenance = self._get_signal_provenance_summary()

        return {
            "unified": unified_status,
            "swarm": {
                "active_runs": len(swarm_status.get("active_runs", {})),
                "total_signals": swarm_status.get("total_signals", 0),
                "convergences": [
                    {
                        "symbol": c.symbol or "MARKET",
                        "direction": c.direction,
                        "agent_count": c.agent_count,
                        "score": c.convergence_score,
                    }
                    for c in convergences[:5]
                ],
            },
            "social": social,
            "suggestions": suggestions,
            "provenance": provenance,
        }

    def render_compact(self, status: dict) -> str:
        """Render compact single-screen view."""
        unified: UnifiedSystemStatus = status["unified"]
        swarm = status["swarm"]
        social = status["social"]
        suggestions = status["suggestions"]
        provenance = status["provenance"]

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        mode = unified.mode.value.upper()

        lines = []

        # Header
        lines.append("╔" + "═" * 78 + "╗")
        lines.append(f"║{'PROJECT ATHENA - MISSION CONTROL':^78}║")
        lines.append(f"║{now:^78}║")
        lines.append("╚" + "═" * 78 + "╝")
        lines.append("")

        # Row 1: Portfolio & Risk | Swarm Activity
        pnl_sign = "+" if unified.daily_pnl >= 0 else ""
        pnl_color = "32" if unified.daily_pnl >= 0 else "31"  # green or red

        lines.append(f"┌{'─' * 38}┬{'─' * 38}┐")
        lines.append(f"│ {'PORTFOLIO':<36} │ {'SWARM INTELLIGENCE':<36} │")
        lines.append(f"├{'─' * 38}┼{'─' * 38}┤")
        lines.append(f"│ Value:    ${unified.portfolio_value:>14,.2f}       │ Active Agents:  {swarm['active_runs']:<20} │")
        lines.append(f"│ Day P&L: \033[{pnl_color}m${pnl_sign}{unified.daily_pnl:>14,.2f}\033[0m       │ Total Signals:  {swarm['total_signals']:<20} │")
        lines.append(f"│ Positions: {unified.positions_count:>14}       │ Convergences:   {len(swarm['convergences']):<20} │")
        lines.append(f"│ Max Conc:  {unified.max_concentration:>13.1%}       │ {'':36} │")
        lines.append(f"└{'─' * 38}┴{'─' * 38}┘")
        lines.append("")

        # Row 2: Convergences (if any)
        if swarm['convergences']:
            lines.append("┌" + "─" * 78 + "┐")
            lines.append(f"│ {'SIGNAL CONVERGENCES (2+ agents agree)':<76} │")
            lines.append("├" + "─" * 78 + "┤")
            for conv in swarm['convergences'][:3]:
                symbol = conv['symbol']
                direction = "↑ BULL" if conv['direction'] == "bullish" else "↓ BEAR" if conv['direction'] == "bearish" else "~ NEUT"
                lines.append(f"│   {symbol:<10} {direction:<10} {conv['agent_count']} agents, {conv['score']:.0%} confidence{' ' * 29} │")
            lines.append("└" + "─" * 78 + "┘")
            lines.append("")

        # Row 3: Social Signals & Thesis Suggestions
        lines.append(f"┌{'─' * 38}┬{'─' * 38}┐")
        lines.append(f"│ {'SOCIAL SIGNALS':<36} │ {'THESIS SUGGESTIONS':<36} │")
        lines.append(f"├{'─' * 38}┼{'─' * 38}┤")

        # Build row content
        if social['early_signals'] > 0:
            left_header = f"│ Early Signals: {social['early_signals']:<21} │"
        else:
            left_header = f"│ Symbols Tracked: {social['total_symbols']:<19} │"

        if suggestions:
            right_header = f" Pending: {len(suggestions):<27} │"
        else:
            right_header = f" No pending suggestions{' ' * 14} │"

        lines.append(left_header + right_header)

        # Early signals
        for i in range(2):
            early_list = social.get('early', [])
            if i < len(early_list):
                sig = early_list[i]
                symbol = sig.get('symbol', 'UNK')[:6]
                phase = sig.get('current_phase', 'unk')[:8]
                vintage = sig.get('signal_vintage', 0)
                left = f"│   {symbol}: {phase} ({vintage}d){' ' * (23 - len(symbol) - len(phase))} │"
            else:
                left = f"│   {'-':<35} │"

            if i < len(suggestions):
                s = suggestions[i]
                sym = s.get('symbol', 'UNK')[:6]
                conf = s.get('confidence_score', 0)
                right = f" {sym}: {conf:.0%} confidence{' ' * 18} │"
            else:
                right = f" {'-':<36} │"

            lines.append(left + right)

        lines.append(f"└{'─' * 38}┴{'─' * 38}┘")
        lines.append("")

        # Row 4: Signal Provenance & Top Signals
        lines.append(f"┌{'─' * 38}┬{'─' * 38}┐")
        lines.append(f"│ {'SIGNAL PROVENANCE':<36} │ {'TOP SIGNALS':<36} │")
        lines.append(f"├{'─' * 38}┼{'─' * 38}┤")
        # Build provenance and signals rows
        hit_rate_str = f"{provenance['hit_rate']:.0%}"
        prov_lines = [
            f"│ Total Tracked:  {provenance['total']:<20} │",
            f"│ Active:         {provenance['active']:<20} │",
            f"│ Hit Rate:       {hit_rate_str:<20} │",
        ]

        signal_lines = []
        for i in range(3):
            if i < len(unified.top_signals):
                sig = unified.top_signals[i]
                sym = sig.get('symbol', 'MKT')[:6]
                desc = sig.get('description', '')[:26]
                signal_lines.append(f" {sym}: {desc:<30} │")
            else:
                if i == 0:
                    signal_lines.append(f" No active signals{' ' * 19} │")
                else:
                    signal_lines.append(f" {'-':<36} │")

        for i in range(3):
            lines.append(prov_lines[i] + signal_lines[i])

        lines.append(f"└{'─' * 38}┴{'─' * 38}┘")
        lines.append("")

        # Row 5: System Status
        risk_status = unified.risk_status.upper()
        risk_color = "32" if risk_status == "OK" else "33" if risk_status == "WARNING" else "31"

        lines.append(f"┌{'─' * 78}┐")
        lines.append(f"│ {'SYSTEM STATUS':<76} │")
        lines.append(f"├{'─' * 78}┤")
        lines.append(f"│ Mode: {mode:<8}  Regime: {unified.market_regime.upper():<12}  Risk: \033[{risk_color}m{risk_status:<8}\033[0m  Data Quality: {unified.data_quality_score:.0f}%{' ' * 8} │")
        lines.append(f"│ PDT Trades: {unified.pdt_trades_used}/3   Cron: {unified.cron_jobs_ok} ok, {unified.cron_jobs_failed} failed   Disk: {unified.disk_space_pct:.0f}% free   Alerts: {len(unified.active_alerts)}{' ' * 12} │")
        lines.append(f"└{'─' * 78}┘")

        return "\n".join(lines)

    def render_full(self, status: dict, hours: int = 4) -> str:
        """Render full dashboard with swarm activity."""
        unified: UnifiedSystemStatus = status["unified"]

        # Build full output - start with compact view
        lines = [self.render_compact(status)]
        lines.append("")

        # Swarm Timeline
        lines.append(self.swarm_viz.render_timeline(hours=min(hours, 4), width=78))
        lines.append("")

        # Thesis Exposure (if any)
        if unified.thesis_exposure:
            lines.append("┌" + "─" * 78 + "┐")
            lines.append(f"│ {'THESIS EXPOSURE':<76} │")
            lines.append("├" + "─" * 78 + "┤")
            for name, exp in sorted(unified.thesis_exposure.items(), key=lambda x: -x[1].get("value", 0))[:5]:
                pnl = exp.get("day_pnl", 0)
                pnl_sign = "+" if pnl >= 0 else ""
                pnl_color = "32" if pnl >= 0 else "31"
                value_pct = exp.get("pct", 0)
                line = f"│   {name[:25]:<25}  ${exp.get('value', 0):>10,.0f} ({value_pct:>5.1f}%)  \033[{pnl_color}mP&L: ${pnl_sign}{pnl:>8,.0f}\033[0m{' ' * 10} │"
                lines.append(line)
            lines.append("└" + "─" * 78 + "┘")

        return "\n".join(lines)

    async def watch(self, interval: int = 30, compact: bool = False, hours: int = 4):
        """Watch mode with periodic refresh."""
        print("\033[2J\033[H")  # Clear screen
        print("Mission Control - Watch Mode (Ctrl+C to exit)")
        print(f"Refreshing every {interval} seconds...\n")

        try:
            while True:
                print("\033[H")  # Move cursor to top
                status = await self.get_full_status()

                if compact:
                    output = self.render_compact(status)
                else:
                    output = self.render_full(status, hours=hours)

                print(output)
                print(f"\n[Last refresh: {datetime.now().strftime('%H:%M:%S')}]")
                await asyncio.sleep(interval)
        except KeyboardInterrupt:
            print("\nExiting watch mode.")


async def main():
    parser = argparse.ArgumentParser(description="Mission Control - Unified System View")
    parser.add_argument("--watch", action="store_true", help="Watch mode with auto-refresh")
    parser.add_argument("--interval", type=int, default=30, help="Refresh interval in seconds")
    parser.add_argument("--compact", action="store_true", help="Compact single-screen view")
    parser.add_argument("--hours", type=int, default=4, help="Hours of history for swarm timeline")
    parser.add_argument("--json", action="store_true", help="Output JSON")

    args = parser.parse_args()

    control = MissionControl()

    if args.watch:
        await control.watch(interval=args.interval, compact=args.compact, hours=args.hours)
    else:
        status = await control.get_full_status()

        if args.json:
            # Convert to JSON-serializable format
            output = {
                "timestamp": datetime.now().isoformat(),
                "unified": status["unified"].to_dict(),
                "swarm": status["swarm"],
                "social": status["social"],
                "suggestions": status["suggestions"],
                "provenance": status["provenance"],
            }
            print(json.dumps(output, indent=2))
        elif args.compact:
            print(control.render_compact(status))
        else:
            print(control.render_full(status, hours=args.hours))


if __name__ == "__main__":
    asyncio.run(main())
