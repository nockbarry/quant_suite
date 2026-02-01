#!/usr/bin/env python3
"""Swarm Visualizer - Timeline and heatmap displays for swarm intelligence.

Provides visual displays for:
- Agent activity timeline (ASCII art)
- Signal convergence heatmap by symbol
- Real-time watch mode

Usage:
    python -m src.monitoring.swarm_visualizer
    python -m src.monitoring.swarm_visualizer --watch
    python -m src.monitoring.swarm_visualizer --heatmap
"""

import argparse
import time
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional

from .swarm_monitor import (
    SwarmMonitor,
    get_swarm_monitor,
    AgentRun,
    SwarmSignal,
    SignalConvergence,
    AgentStatus,
)


class SwarmVisualizer:
    """Visualize swarm activity with ASCII displays."""

    # Short names for agents
    AGENT_SHORT_NAMES = {
        "critic-agent": "critic",
        "monitor-agent": "monitor",
        "news-analyst-agent": "news",
        "research-agent": "research",
        "alpha-discovery-agent": "alpha",
        "brainstorm-agent": "brainstorm",
        "regime-detector-agent": "regime",
        "hypothesis-generator-agent": "hypothesis",
        "text-research-agent": "text",
        "macro-research-agent": "macro",
        "data-acquisition-agent": "data",
        "orchestrator-agent": "orchestrator",
    }

    def __init__(self, monitor: Optional[SwarmMonitor] = None):
        self.monitor = monitor or get_swarm_monitor()

    def render_timeline(
        self,
        hours: int = 4,
        width: int = 60
    ) -> str:
        """Render an ASCII timeline of agent activity.

        Shows agent runs and convergences over time.
        """
        now = datetime.now()
        start_time = now - timedelta(hours=hours)

        # Get data
        signals = self.monitor.get_recent_signals(max_age_hours=hours)
        convergences = self.monitor.find_convergences(max_age_hours=hours)

        # Group signals by time slot (15-min intervals)
        slot_minutes = 15
        slots_per_hour = 60 // slot_minutes
        total_slots = hours * slots_per_hour

        # Create time slots
        time_slots = []
        for i in range(total_slots):
            slot_start = start_time + timedelta(minutes=i * slot_minutes)
            slot_end = slot_start + timedelta(minutes=slot_minutes)
            time_slots.append({
                "start": slot_start,
                "end": slot_end,
                "signals": [],
                "agents": set(),
            })

        # Assign signals to slots
        for signal in signals:
            for slot in time_slots:
                if slot["start"] <= signal.timestamp < slot["end"]:
                    slot["signals"].append(signal)
                    slot["agents"].add(signal.agent_name)
                    break

        # Build output
        lines = [
            "SWARM ACTIVITY TIMELINE",
            f"═{'═' * (width - 2)}═",
            f"Period: {start_time.strftime('%H:%M')} - {now.strftime('%H:%M')} ({hours}h)",
            "",
        ]

        # Group slots by hour for cleaner display
        for hour_idx in range(hours):
            hour_start = start_time + timedelta(hours=hour_idx)
            hour_label = hour_start.strftime("%H:%M")

            hour_slots = time_slots[hour_idx * slots_per_hour:(hour_idx + 1) * slots_per_hour]

            # Check if any activity in this hour
            hour_signals = []
            hour_agents = set()
            for slot in hour_slots:
                hour_signals.extend(slot["signals"])
                hour_agents.update(slot["agents"])

            if hour_signals:
                lines.append(f"{hour_label} ┃")

                # Show agents that ran
                for agent in sorted(hour_agents):
                    short_name = self.AGENT_SHORT_NAMES.get(agent, agent[:10])
                    agent_signals = [s for s in hour_signals if s.agent_name == agent]

                    # Create activity bar
                    bar_width = min(len(agent_signals) * 3, 30)
                    bar = "━" * bar_width

                    # Direction indicator
                    directions = [s.direction for s in agent_signals]
                    if all(d == "bullish" for d in directions):
                        end_marker = "▲"
                    elif all(d == "bearish" for d in directions):
                        end_marker = "▼"
                    else:
                        end_marker = "◆"

                    # Symbols mentioned
                    symbols = set(s.symbol for s in agent_signals if s.symbol)
                    symbol_str = ", ".join(sorted(symbols)[:3]) if symbols else "market"

                    lines.append(
                        f"      ┃ [{short_name:10}]{bar}{end_marker} {len(agent_signals)} sig: {symbol_str}"
                    )

                # Check for convergences in this hour
                hour_convergences = [
                    c for c in convergences
                    if hour_start <= c.first_signal < hour_start + timedelta(hours=1)
                ]
                for conv in hour_convergences:
                    symbol = conv.symbol or "MARKET"
                    direction = "↑" if conv.direction == "bullish" else "↓"
                    lines.append(
                        f"      ┃ ════> CONVERGENCE: {symbol} {direction} "
                        f"({conv.agent_count} agents, {conv.convergence_score:.0%})"
                    )

                lines.append("      ┃")
            else:
                lines.append(f"{hour_label} ┃ (no activity)")

        lines.append(f"═{'═' * (width - 2)}═")
        return "\n".join(lines)

    def render_heatmap(
        self,
        hours: int = 24,
        top_n: int = 10
    ) -> str:
        """Render a signal heatmap showing agent agreement by symbol.

        Shows how many agents have signals on each symbol and their direction.
        """
        signals = self.monitor.get_recent_signals(max_age_hours=hours)

        # Group by symbol and agent
        symbol_agent_signals = defaultdict(lambda: defaultdict(list))
        for signal in signals:
            symbol = signal.symbol or "MARKET"
            symbol_agent_signals[symbol][signal.agent_name].append(signal)

        # Calculate stats per symbol
        symbol_stats = []
        for symbol, agents in symbol_agent_signals.items():
            # Aggregate direction
            all_signals = []
            for agent_signals in agents.values():
                all_signals.extend(agent_signals)

            bullish = sum(1 for s in all_signals if s.direction == "bullish")
            bearish = sum(1 for s in all_signals if s.direction == "bearish")
            neutral = sum(1 for s in all_signals if s.direction == "neutral")

            # Net direction
            if bullish > bearish + neutral:
                net_direction = "bullish"
            elif bearish > bullish + neutral:
                net_direction = "bearish"
            else:
                net_direction = "neutral"

            avg_confidence = sum(s.confidence for s in all_signals) / len(all_signals)

            symbol_stats.append({
                "symbol": symbol,
                "agent_count": len(agents),
                "signal_count": len(all_signals),
                "bullish": bullish,
                "bearish": bearish,
                "neutral": neutral,
                "net_direction": net_direction,
                "avg_confidence": avg_confidence,
                "agents": list(agents.keys()),
            })

        # Sort by agent count (convergence indicator)
        symbol_stats.sort(key=lambda x: (x["agent_count"], x["signal_count"]), reverse=True)
        symbol_stats = symbol_stats[:top_n]

        # Get unique agents for header
        all_agents = set()
        for stat in symbol_stats:
            all_agents.update(stat["agents"])
        agents_ordered = sorted(all_agents)
        agent_short = [self.AGENT_SHORT_NAMES.get(a, a[:6])[:6] for a in agents_ordered]

        # Build output
        lines = [
            f"SIGNAL HEATMAP ({hours}h)",
            "═" * 70,
            "",
        ]

        # Header row with agent names
        header = f"{'SYMBOL':<10}"
        for short in agent_short:
            header += f"{short:^7}"
        header += f"{'CONV':^6}{'DIR':^8}"
        lines.append(header)
        lines.append("─" * len(header))

        # Data rows
        for stat in symbol_stats:
            row = f"{stat['symbol']:<10}"

            for agent in agents_ordered:
                if agent in stat["agents"]:
                    # Get direction for this agent
                    agent_signals = symbol_agent_signals[stat["symbol"]][agent]
                    bullish = sum(1 for s in agent_signals if s.direction == "bullish")
                    bearish = sum(1 for s in agent_signals if s.direction == "bearish")

                    if bullish > bearish:
                        cell = "[+++]" if bullish > 1 else "[ + ]"
                    elif bearish > bullish:
                        cell = "[---]" if bearish > 1 else "[ - ]"
                    else:
                        cell = "[ ~ ]"
                    row += f"{cell:^7}"
                else:
                    row += f"{'':^7}"

            # Convergence bar
            conv_bar = "█" * min(stat["agent_count"], 5)
            row += f"{conv_bar:<6}"

            # Direction indicator
            dir_str = {
                "bullish": "↑ BULL",
                "bearish": "↓ BEAR",
                "neutral": "~ NEUT"
            }.get(stat["net_direction"], "")
            row += f"{dir_str:^8}"

            lines.append(row)

        lines.append("")
        lines.append("Legend: +++ strong bullish, --- strong bearish, ~ neutral")
        lines.append("        CONV = number of agents with signals")
        lines.append("═" * 70)

        return "\n".join(lines)

    def render_active_agents(self) -> str:
        """Render current active agent status."""
        status = self.monitor.get_swarm_status()
        active = status["active_runs"]

        lines = [
            "ACTIVE AGENTS",
            "═" * 50,
        ]

        if not active:
            lines.append("No agents currently running")
        else:
            for name, run in active.items():
                short_name = self.AGENT_SHORT_NAMES.get(name, name)
                duration = run.get("duration_seconds", 0)
                task = run.get("task_description", "")[:40]
                lines.append(f"  ⚡ {short_name:15} {duration:5.0f}s | {task}")

        lines.append("═" * 50)
        return "\n".join(lines)

    def render_convergence_summary(self) -> str:
        """Render summary of current convergences."""
        convergences = self.monitor.find_convergences(min_agents=2)

        lines = [
            "SIGNAL CONVERGENCES",
            "═" * 60,
        ]

        if not convergences:
            lines.append("No convergences detected (need 2+ agents agreeing)")
        else:
            for conv in convergences[:10]:
                symbol = conv.symbol or "MARKET"
                direction = "📈" if conv.direction == "bullish" else "📉" if conv.direction == "bearish" else "➖"
                agents = [self.AGENT_SHORT_NAMES.get(s.agent_name, s.agent_name[:8]) for s in conv.signals]
                agent_str = ", ".join(sorted(set(agents)))

                lines.append(
                    f"  {direction} {symbol:8} | {conv.agent_count} agents | "
                    f"{conv.convergence_score:.0%} conf | {agent_str}"
                )

        lines.append("═" * 60)
        return "\n".join(lines)

    def render_full_dashboard(self, hours: int = 4) -> str:
        """Render full swarm dashboard with all components."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        sections = [
            f"╔{'═' * 68}╗",
            f"║{'SWARM INTELLIGENCE DASHBOARD':^68}║",
            f"║{now:^68}║",
            f"╚{'═' * 68}╝",
            "",
            self.render_active_agents(),
            "",
            self.render_convergence_summary(),
            "",
            self.render_heatmap(hours=hours, top_n=8),
            "",
            self.render_timeline(hours=min(hours, 6)),
        ]

        return "\n".join(sections)


def watch_mode(visualizer: SwarmVisualizer, interval: int = 30, hours: int = 4):
    """Run in watch mode with periodic refresh."""
    print("\033[2J\033[H")  # Clear screen
    print("Swarm Visualizer - Watch Mode (Ctrl+C to exit)")
    print(f"Refreshing every {interval} seconds...\n")

    try:
        while True:
            print("\033[H")  # Move cursor to top
            print(visualizer.render_full_dashboard(hours=hours))
            print(f"\n[Last refresh: {datetime.now().strftime('%H:%M:%S')}]")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nExiting watch mode.")


def main():
    parser = argparse.ArgumentParser(description="Swarm Intelligence Visualizer")
    parser.add_argument("--watch", action="store_true", help="Watch mode with auto-refresh")
    parser.add_argument("--interval", type=int, default=30, help="Refresh interval in seconds")
    parser.add_argument("--hours", type=int, default=4, help="Hours of history to show")
    parser.add_argument("--heatmap", action="store_true", help="Show only heatmap")
    parser.add_argument("--timeline", action="store_true", help="Show only timeline")
    parser.add_argument("--convergences", action="store_true", help="Show only convergences")

    args = parser.parse_args()

    visualizer = SwarmVisualizer()

    if args.watch:
        watch_mode(visualizer, interval=args.interval, hours=args.hours)
    elif args.heatmap:
        print(visualizer.render_heatmap(hours=args.hours))
    elif args.timeline:
        print(visualizer.render_timeline(hours=args.hours))
    elif args.convergences:
        print(visualizer.render_convergence_summary())
    else:
        print(visualizer.render_full_dashboard(hours=args.hours))


if __name__ == "__main__":
    main()
