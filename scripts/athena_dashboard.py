#!/usr/bin/env python3
"""
Project Athena - Operations Console

Real-time view of the autonomous trading system in action.
Watch agents work, signals emerge, and decisions flow.

Run: streamlit run scripts/athena_dashboard.py
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd

# =============================================================================
# CONFIG - Minimal, terminal-like
# =============================================================================

st.set_page_config(
    page_title="Athena Ops",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&display=swap');

    .stApp {
        background: #0a0a0a;
        font-family: 'JetBrains Mono', 'Courier New', monospace;
    }

    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding: 0.5rem; max-width: 100%; }

    /* Terminal text */
    .terminal {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.8rem;
        line-height: 1.4;
        color: #c9d1d9;
    }

    .terminal-header {
        color: #58a6ff;
        border-bottom: 1px solid #30363d;
        padding-bottom: 0.25rem;
        margin-bottom: 0.5rem;
        font-weight: 600;
    }

    .terminal-dim { color: #484f58; }
    .terminal-green { color: #3fb950; }
    .terminal-red { color: #f85149; }
    .terminal-yellow { color: #d29922; }
    .terminal-blue { color: #58a6ff; }
    .terminal-purple { color: #a371f7; }
    .terminal-orange { color: #f0883e; }

    /* Panel styling */
    .panel {
        background: #0d1117;
        border: 1px solid #30363d;
        border-radius: 4px;
        padding: 0.75rem;
        margin-bottom: 0.5rem;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.8rem;
    }

    .panel-title {
        color: #8b949e;
        font-size: 0.65rem;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 0.5rem;
        border-bottom: 1px solid #21262d;
        padding-bottom: 0.25rem;
    }

    /* Activity feed */
    .feed-item {
        padding: 0.3rem 0;
        border-bottom: 1px solid #161b22;
        display: flex;
        gap: 0.75rem;
    }
    .feed-time { color: #484f58; width: 50px; }
    .feed-type { width: 100px; }
    .feed-content { color: #8b949e; flex: 1; }

    /* Agent status */
    .agent-row {
        display: flex;
        justify-content: space-between;
        padding: 0.25rem 0;
        border-bottom: 1px solid #161b22;
    }
    .agent-active { color: #3fb950; }
    .agent-idle { color: #484f58; }

    /* Signal rows */
    .signal-bull { color: #3fb950; }
    .signal-bear { color: #f85149; }
    .signal-neutral { color: #8b949e; }

    /* Convergence highlight */
    .convergence {
        background: #1c1c0a;
        border-left: 2px solid #f0883e;
        padding: 0.4rem 0.6rem;
        margin: 0.25rem 0;
    }

    /* Status bar */
    .status-bar {
        background: #161b22;
        border: 1px solid #30363d;
        padding: 0.5rem 1rem;
        display: flex;
        justify-content: space-between;
        font-size: 0.75rem;
        margin-bottom: 0.5rem;
        border-radius: 4px;
    }
    .status-item { display: flex; gap: 0.5rem; }
    .status-label { color: #8b949e; }
    .status-value { color: #c9d1d9; }

    /* ASCII box drawing */
    .ascii-box {
        border: 1px solid #30363d;
        background: #0d1117;
        padding: 0.5rem;
        white-space: pre;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.75rem;
        overflow-x: auto;
    }

    /* Hide streamlit defaults */
    .stDataFrame { font-size: 0.75rem !important; }
    div[data-testid="stVerticalBlock"] > div { gap: 0.25rem; }
</style>
""", unsafe_allow_html=True)

# =============================================================================
# DATA
# =============================================================================

RESULTS_DIR = Path.home() / "quant_results"

def load_state():
    f = RESULTS_DIR / "live" / "state.json"
    return json.load(open(f)) if f.exists() else {}

def load_operator_log():
    f = RESULTS_DIR / "logs" / "operator_log.jsonl"
    if not f.exists():
        return []
    entries = []
    for line in open(f):
        try:
            entries.append(json.loads(line.strip()))
        except:
            pass
    return entries[-100:]

def load_agent_activity():
    f = RESULTS_DIR / "logs" / "agent_activity.jsonl"
    if not f.exists():
        return []
    entries = []
    for line in open(f):
        try:
            entries.append(json.loads(line.strip()))
        except:
            pass
    return entries[-100:]

def load_convergences():
    try:
        from src.monitoring.swarm_monitor import get_swarm_monitor
        monitor = get_swarm_monitor()
        return [
            {
                "symbol": c.symbol or "MARKET",
                "direction": c.direction,
                "agents": c.agent_count,
                "score": c.convergence_score,
                "names": list(set(s.agent_name.replace("-agent", "") for s in c.signals)),
            }
            for c in monitor.find_convergences(min_agents=2)[:10]
        ]
    except:
        return []

def load_swarm_signals():
    try:
        from src.monitoring.swarm_monitor import get_swarm_monitor
        monitor = get_swarm_monitor()
        return monitor.get_recent_signals(max_age_hours=24)
    except:
        return []

def load_social():
    f = RESULTS_DIR / "social" / "wsb_signals.json"
    return json.load(open(f)) if f.exists() else {"signals": []}

def load_suggestions():
    f = RESULTS_DIR / "suggestions" / "thesis_suggestions.json"
    if f.exists():
        data = json.load(open(f))
        return [s for s in data.get("suggestions", []) if s.get("status") == "pending"]
    return []

def load_provenance():
    signals = []
    d = RESULTS_DIR / "signal_provenance"
    if d.exists():
        for f in d.glob("*.json"):
            try:
                signals.extend(json.load(open(f)).get("signals", []))
            except:
                pass
    return signals

def load_theses():
    import yaml
    theses = []
    d = RESULTS_DIR / "theses"
    if d.exists():
        for f in d.glob("*.yaml"):
            try:
                t = yaml.safe_load(open(f))
                if t and t.get("status") == "active":
                    theses.append(t)
            except:
                pass
    return theses

# =============================================================================
# RENDER FUNCTIONS
# =============================================================================

def render_status_bar(state, convergences, suggestions):
    portfolio = state.get("portfolio", {})
    equity = portfolio.get("equity", 0)
    pnl = portfolio.get("day_pnl", 0)
    pnl_pct = portfolio.get("day_pnl_pct", 0)
    pnl_class = "terminal-green" if pnl >= 0 else "terminal-red"

    regime = state.get("market", {}).get("regime", "?").upper()
    positions = len(state.get("positions", []))

    st.markdown(f"""
    <div class="status-bar">
        <div class="status-item">
            <span class="status-label">EQUITY</span>
            <span class="status-value">${equity:,.0f}</span>
        </div>
        <div class="status-item">
            <span class="status-label">DAY</span>
            <span class="{pnl_class}">${pnl:+,.0f} ({pnl_pct:+.2f}%)</span>
        </div>
        <div class="status-item">
            <span class="status-label">REGIME</span>
            <span class="terminal-blue">{regime}</span>
        </div>
        <div class="status-item">
            <span class="status-label">POS</span>
            <span class="status-value">{positions}</span>
        </div>
        <div class="status-item">
            <span class="status-label">CONV</span>
            <span class="terminal-orange">{len(convergences)}</span>
        </div>
        <div class="status-item">
            <span class="status-label">SUGG</span>
            <span class="terminal-purple">{len(suggestions)}</span>
        </div>
        <div class="status-item">
            <span class="status-label">TIME</span>
            <span class="terminal-dim">{datetime.now().strftime("%H:%M:%S")}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_agent_activity(activity):
    """Render agent activity panel."""
    today = datetime.now().strftime("%Y-%m-%d")
    today_activity = [a for a in activity if a.get("timestamp", "").startswith(today)]

    # Count by type
    running = []
    completed = []
    for a in today_activity:
        if a.get("type") == "agent_start":
            running.append(a)
        elif a.get("type") == "agent_complete":
            completed.append(a)

    # Get currently running (started but not completed)
    completed_ids = {a.get("agent_id") for a in completed}
    active = [a for a in running if a.get("agent_id") not in completed_ids]

    html = '<div class="panel"><div class="panel-title">🤖 AGENT ACTIVITY</div>'

    if active:
        html += '<div style="margin-bottom: 0.5rem;">'
        for a in active[-5:]:
            name = a.get("agent_name", "?").replace("-agent", "")
            task = a.get("task", "")[:30]
            html += f'<div class="agent-row"><span class="agent-active">● {name}</span><span class="terminal-dim">{task}</span></div>'
        html += '</div>'
    else:
        html += '<div class="terminal-dim" style="margin-bottom: 0.5rem;">No agents running</div>'

    # Recent completions
    html += '<div class="terminal-dim" style="font-size: 0.7rem; margin-top: 0.5rem;">RECENT:</div>'
    for a in list(reversed(completed))[-5:]:
        name = a.get("agent_name", "?").replace("-agent", "")
        ts = a.get("timestamp", "")[-8:-3] if a.get("timestamp") else ""
        html += f'<div class="feed-item"><span class="feed-time">{ts}</span><span class="terminal-green">✓ {name}</span></div>'

    if not completed:
        html += '<div class="terminal-dim">No completions today</div>'

    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


def render_convergences(convergences):
    """Render signal convergences."""
    html = '<div class="panel"><div class="panel-title">⚡ CONVERGENCES</div>'

    if convergences:
        for c in convergences[:6]:
            dir_class = "signal-bull" if c["direction"] == "bullish" else "signal-bear" if c["direction"] == "bearish" else "signal-neutral"
            dir_icon = "▲" if c["direction"] == "bullish" else "▼" if c["direction"] == "bearish" else "●"
            agents = ", ".join(c["names"][:4])

            html += f'''
            <div class="convergence">
                <div style="display: flex; justify-content: space-between;">
                    <span class="{dir_class}">{dir_icon} <strong>{c["symbol"]}</strong></span>
                    <span class="terminal-orange">{c["agents"]} agents | {c["score"]:.0%}</span>
                </div>
                <div class="terminal-dim" style="font-size: 0.7rem;">{agents}</div>
            </div>
            '''
    else:
        html += '<div class="terminal-dim">No convergences detected</div>'

    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


def render_swarm_signals(signals):
    """Render recent swarm signals."""
    html = '<div class="panel"><div class="panel-title">📡 SIGNAL FEED</div>'

    if signals:
        for s in list(reversed(signals))[:12]:
            ts = s.timestamp.strftime("%H:%M") if hasattr(s, 'timestamp') else "?"
            agent = s.agent_name.replace("-agent", "") if hasattr(s, 'agent_name') else "?"
            symbol = s.symbol or "MARKET" if hasattr(s, 'symbol') else "?"
            direction = s.direction if hasattr(s, 'direction') else "?"
            conf = s.confidence if hasattr(s, 'confidence') else 0

            dir_class = "signal-bull" if direction == "bullish" else "signal-bear" if direction == "bearish" else "signal-neutral"
            dir_icon = "▲" if direction == "bullish" else "▼" if direction == "bearish" else "●"

            html += f'''
            <div class="feed-item">
                <span class="feed-time">{ts}</span>
                <span class="terminal-purple">{agent[:8]}</span>
                <span class="{dir_class}">{dir_icon} {symbol}</span>
                <span class="terminal-dim">{conf:.0%}</span>
            </div>
            '''
    else:
        html += '<div class="terminal-dim">No signals in last 24h</div>'

    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


def render_operator_feed(log):
    """Render operator activity feed."""
    html = '<div class="panel"><div class="panel-title">📋 OPERATOR LOG</div>'

    today = datetime.now().strftime("%Y-%m-%d")
    today_log = [e for e in log if e.get("timestamp", "").startswith(today)]

    if today_log:
        for entry in list(reversed(today_log))[-15:]:
            ts = entry.get("timestamp", "")[-8:-3] if entry.get("timestamp") else "?"
            etype = entry.get("type", entry.get("event", "?"))[:12]

            # Color by type
            if "alert" in etype.lower():
                color = "terminal-yellow"
            elif "signal" in etype.lower():
                color = "terminal-blue"
            elif "agent" in etype.lower():
                color = "terminal-purple"
            elif "decision" in etype.lower() or "trade" in etype.lower():
                color = "terminal-green"
            elif "error" in etype.lower():
                color = "terminal-red"
            else:
                color = "terminal-dim"

            details = str(entry.get("details", entry.get("message", "")))[:40]

            html += f'''
            <div class="feed-item">
                <span class="feed-time">{ts}</span>
                <span class="{color}">{etype}</span>
                <span class="feed-content">{details}</span>
            </div>
            '''
    else:
        html += '<div class="terminal-dim">No activity today</div>'

    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


def render_suggestions(suggestions, social):
    """Render thesis suggestions and social signals."""
    html = '<div class="panel"><div class="panel-title">💡 THESIS SUGGESTIONS</div>'

    if suggestions:
        for s in suggestions[:4]:
            symbol = s.get("symbol", "?")
            name = s.get("suggested_name", "")[:25]
            sources = list(set(s.get("signal_sources", [])))[:2]
            conf = s.get("confidence_score", 0)

            html += f'''
            <div style="padding: 0.3rem 0; border-bottom: 1px solid #161b22;">
                <div><span class="terminal-blue">{symbol}</span> — {name}</div>
                <div class="terminal-dim" style="font-size: 0.7rem;">{s.get("signal_count", 0)} signals • {", ".join(sources)} • {conf:.0%}</div>
            </div>
            '''
    else:
        html += '<div class="terminal-dim">No pending suggestions</div>'

    # Early social signals
    html += '<div class="panel-title" style="margin-top: 0.75rem;">📱 EARLY SIGNALS</div>'
    early = [s for s in social.get("signals", []) if s.get("signal_vintage", 99) <= 7][:5]

    if early:
        for s in early:
            phase = s.get("current_phase", "?")
            phase_color = "terminal-green" if phase == "early" else "terminal-yellow" if phase == "growing" else "terminal-dim"

            html += f'''
            <div class="feed-item">
                <span class="terminal-blue">{s.get("symbol", "?")}</span>
                <span class="{phase_color}">{phase}</span>
                <span class="terminal-dim">{s.get("signal_vintage", 0)}d old</span>
            </div>
            '''
    else:
        html += '<div class="terminal-dim">No early signals</div>'

    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


def render_swarm_timeline(signals):
    """Render ASCII swarm timeline."""
    now = datetime.now()
    hours = 4

    # Group signals by hour
    hourly = {}
    for s in signals:
        if hasattr(s, 'timestamp'):
            hour = s.timestamp.strftime("%H:00")
            if hour not in hourly:
                hourly[hour] = []
            hourly[hour].append(s)

    lines = ["SWARM ACTIVITY TIMELINE", "═" * 60]

    for i in range(hours):
        hour_start = now - timedelta(hours=hours-i-1)
        hour_label = hour_start.strftime("%H:00")

        if hour_label in hourly:
            sigs = hourly[hour_label]
            agents = set(s.agent_name.replace("-agent", "")[:6] for s in sigs if hasattr(s, 'agent_name'))
            agent_str = " ".join(f"[{a}]" for a in list(agents)[:4])
            lines.append(f"{hour_label} ┃ {agent_str} → {len(sigs)} signals")
        else:
            lines.append(f"{hour_label} ┃ (no activity)")

    lines.append("═" * 60)

    st.markdown(f'<div class="ascii-box">{chr(10).join(lines)}</div>', unsafe_allow_html=True)


def render_provenance_stats(provenance):
    """Render signal provenance statistics."""
    active = len([p for p in provenance if p.get("outcome") == "pending"])
    hits = len([p for p in provenance if p.get("outcome") == "hit"])
    misses = len([p for p in provenance if p.get("outcome") == "miss"])
    total_closed = hits + misses
    hit_rate = hits / total_closed if total_closed > 0 else 0

    html = f'''
    <div class="panel">
        <div class="panel-title">📊 SIGNAL PROVENANCE</div>
        <div class="agent-row"><span>Tracking</span><span class="terminal-blue">{active}</span></div>
        <div class="agent-row"><span>Closed</span><span>{total_closed}</span></div>
        <div class="agent-row"><span>Hit Rate</span><span class="{'terminal-green' if hit_rate > 0.5 else 'terminal-yellow'}">{hit_rate:.0%}</span></div>
        <div class="agent-row"><span>Total</span><span class="terminal-dim">{len(provenance)}</span></div>
    </div>
    '''
    st.markdown(html, unsafe_allow_html=True)


def render_system_status(state, theses):
    """Render system status panel."""
    state_file = RESULTS_DIR / "live" / "state.json"
    state_age = (datetime.now() - datetime.fromtimestamp(state_file.stat().st_mtime)).seconds // 60 if state_file.exists() else 999

    portfolio = state.get("portfolio", {})
    cash = portfolio.get("cash", 0)

    positions = state.get("positions", [])
    total_value = sum(p.get("market_value", 0) for p in positions) if positions else 1
    max_conc = max(p.get("market_value", 0) / total_value for p in positions) if positions else 0

    html = f'''
    <div class="panel">
        <div class="panel-title">⚙️ SYSTEM STATUS</div>
        <div class="agent-row"><span>State</span><span class="{'terminal-green' if state_age < 10 else 'terminal-yellow'}">{state_age}m ago</span></div>
        <div class="agent-row"><span>Theses</span><span>{len(theses)} active</span></div>
        <div class="agent-row"><span>Cash</span><span class="{'terminal-green' if cash > 5000 else 'terminal-yellow'}">${cash:,.0f}</span></div>
        <div class="agent-row"><span>Max Pos</span><span class="{'terminal-green' if max_conc < 0.15 else 'terminal-yellow'}">{max_conc:.1%}</span></div>
    </div>
    '''
    st.markdown(html, unsafe_allow_html=True)


# =============================================================================
# MAIN
# =============================================================================

def main():
    # Load data
    state = load_state()
    operator_log = load_operator_log()
    agent_activity = load_agent_activity()
    convergences = load_convergences()
    swarm_signals = load_swarm_signals()
    social = load_social()
    suggestions = load_suggestions()
    provenance = load_provenance()
    theses = load_theses()

    # Status bar
    render_status_bar(state, convergences, suggestions)

    # Main layout - 3 columns
    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        render_agent_activity(agent_activity)
        render_convergences(convergences)

    with col2:
        render_swarm_signals(swarm_signals)
        render_swarm_timeline(swarm_signals)

    with col3:
        render_operator_feed(operator_log)
        render_suggestions(suggestions, social)

    # Bottom row
    bcol1, bcol2, bcol3 = st.columns([1, 1, 1])

    with bcol1:
        render_provenance_stats(provenance)

    with bcol2:
        render_system_status(state, theses)

    with bcol3:
        # Refresh controls
        st.markdown("""
        <div class="panel">
            <div class="panel-title">🔄 CONTROLS</div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("Refresh", use_container_width=True):
            st.rerun()

        auto = st.checkbox("Auto (10s)")
        if auto:
            time.sleep(10)
            st.rerun()


if __name__ == "__main__":
    main()
