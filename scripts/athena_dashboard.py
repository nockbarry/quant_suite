#!/usr/bin/env python3
"""
Project Athena - Command Center

Dense, information-rich trading dashboard.
Run: streamlit run scripts/athena_dashboard.py
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import time

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# =============================================================================
# CONFIG
# =============================================================================

st.set_page_config(
    page_title="Athena",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Compact dark theme
st.markdown("""
<style>
    .stApp { background: #0d1117; }
    #MainMenu, footer, header { visibility: hidden; }

    /* Tighter spacing */
    .block-container { padding: 1rem 1rem 0 1rem; max-width: 100%; }
    div[data-testid="stVerticalBlock"] > div { gap: 0.25rem; }

    /* Compact metrics */
    [data-testid="stMetricValue"] { font-size: 1.1rem !important; }
    [data-testid="stMetricLabel"] { font-size: 0.7rem !important; }
    [data-testid="stMetricDelta"] { font-size: 0.7rem !important; }

    /* Dense tables */
    .dataframe { font-size: 0.75rem !important; }
    .dataframe td, .dataframe th { padding: 0.2rem 0.4rem !important; }

    /* Compact tabs */
    .stTabs [data-baseweb="tab-list"] { gap: 0; background: #161b22; }
    .stTabs [data-baseweb="tab"] { padding: 0.4rem 1rem; font-size: 0.8rem; }

    /* Info boxes */
    .info-box {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 4px;
        padding: 0.5rem;
        margin: 0.25rem 0;
        font-size: 0.8rem;
    }
    .info-box-header {
        color: #8b949e;
        font-size: 0.65rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 0.25rem;
    }

    /* Signals */
    .signal-row {
        display: flex;
        justify-content: space-between;
        padding: 0.3rem 0;
        border-bottom: 1px solid #21262d;
        font-size: 0.8rem;
    }
    .signal-bull { color: #3fb950; }
    .signal-bear { color: #f85149; }
    .signal-neutral { color: #8b949e; }

    /* Header bar */
    .header-bar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        background: #161b22;
        padding: 0.5rem 1rem;
        border-radius: 4px;
        margin-bottom: 0.5rem;
        border: 1px solid #30363d;
    }
    .header-title {
        font-size: 1.1rem;
        font-weight: 600;
        color: #58a6ff;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    .header-metrics {
        display: flex;
        gap: 2rem;
        font-size: 0.85rem;
    }
    .header-metric {
        text-align: right;
    }
    .header-metric-label { color: #8b949e; font-size: 0.65rem; }
    .header-metric-value { font-weight: 600; }
    .positive { color: #3fb950; }
    .negative { color: #f85149; }

    /* Section headers */
    .section-header {
        font-size: 0.7rem;
        color: #8b949e;
        text-transform: uppercase;
        letter-spacing: 1px;
        padding: 0.5rem 0 0.25rem 0;
        border-bottom: 1px solid #21262d;
        margin-bottom: 0.25rem;
    }

    /* Convergence highlight */
    .convergence-item {
        background: #1c2128;
        border-left: 3px solid #f0883e;
        padding: 0.4rem 0.6rem;
        margin: 0.25rem 0;
        font-size: 0.8rem;
    }

    /* Status indicators */
    .status-ok { color: #3fb950; }
    .status-warn { color: #d29922; }
    .status-error { color: #f85149; }

    /* Scrollable containers */
    .scroll-container {
        max-height: 300px;
        overflow-y: auto;
    }
</style>
""", unsafe_allow_html=True)

# =============================================================================
# DATA LOADING
# =============================================================================

RESULTS_DIR = Path.home() / "quant_results"


def load_state():
    """Load unified state."""
    f = RESULTS_DIR / "live" / "state.json"
    if f.exists():
        with open(f) as file:
            return json.load(file)
    return {}


def load_theses():
    """Load active theses."""
    import yaml
    theses = []
    d = RESULTS_DIR / "theses"
    if d.exists():
        for f in d.glob("*.yaml"):
            try:
                with open(f) as file:
                    t = yaml.safe_load(file)
                    if t and t.get("status") == "active":
                        theses.append(t)
            except:
                pass
    return theses


def load_convergences():
    """Load signal convergences."""
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


def load_social():
    """Load social signals."""
    f = RESULTS_DIR / "social" / "wsb_signals.json"
    if f.exists():
        with open(f) as file:
            return json.load(file)
    return {"signals": []}


def load_suggestions():
    """Load thesis suggestions."""
    f = RESULTS_DIR / "suggestions" / "thesis_suggestions.json"
    if f.exists():
        with open(f) as file:
            data = json.load(file)
            return [s for s in data.get("suggestions", []) if s.get("status") == "pending"]
    return []


def load_provenance():
    """Load signal provenance."""
    signals = []
    d = RESULTS_DIR / "signal_provenance"
    if d.exists():
        for f in d.glob("*.json"):
            try:
                with open(f) as file:
                    signals.extend(json.load(file).get("signals", []))
            except:
                pass
    return signals


def load_activity():
    """Load recent activity."""
    f = RESULTS_DIR / "logs" / "operator_log.jsonl"
    entries = []
    if f.exists():
        with open(f) as file:
            for line in file:
                try:
                    entries.append(json.loads(line.strip()))
                except:
                    pass
    return entries[-50:]


def load_alerts():
    """Load today's alerts."""
    today = datetime.now().strftime("%Y%m%d")
    f = RESULTS_DIR / "alerts" / f"alerts_{today}.json"
    if f.exists():
        with open(f) as file:
            return json.load(file)
    return []


# =============================================================================
# MAIN
# =============================================================================

def main():
    # Load all data
    state = load_state()
    theses = load_theses()
    convergences = load_convergences()
    social = load_social()
    suggestions = load_suggestions()
    provenance = load_provenance()
    activity = load_activity()
    alerts = load_alerts()

    portfolio = state.get("portfolio", {})
    positions = state.get("positions", [])
    market = state.get("market", {})
    signals = state.get("signals", {})

    # Calculate key metrics
    equity = portfolio.get("equity", 0)
    day_pnl = portfolio.get("day_pnl", 0)
    day_pnl_pct = portfolio.get("day_pnl_pct", 0)
    cash = portfolio.get("cash", 0)

    total_value = sum(p.get("market_value", 0) for p in positions) if positions else 0
    max_conc = max(p.get("market_value", 0) / total_value for p in positions) if positions and total_value > 0 else 0

    early_signals = len([s for s in social.get("signals", []) if s.get("signal_vintage", 99) <= 7])

    # Header bar
    pnl_class = "positive" if day_pnl >= 0 else "negative"
    regime = market.get("regime", "unknown").upper()

    st.markdown(f"""
    <div class="header-bar">
        <div class="header-title">🏛️ ATHENA COMMAND CENTER</div>
        <div class="header-metrics">
            <div class="header-metric">
                <div class="header-metric-label">EQUITY</div>
                <div class="header-metric-value">${equity:,.0f}</div>
            </div>
            <div class="header-metric">
                <div class="header-metric-label">DAY P&L</div>
                <div class="header-metric-value {pnl_class}">${day_pnl:+,.0f} ({day_pnl_pct:+.2f}%)</div>
            </div>
            <div class="header-metric">
                <div class="header-metric-label">REGIME</div>
                <div class="header-metric-value">{regime}</div>
            </div>
            <div class="header-metric">
                <div class="header-metric-label">POSITIONS</div>
                <div class="header-metric-value">{len(positions)}</div>
            </div>
            <div class="header-metric">
                <div class="header-metric-label">CONVERGENCES</div>
                <div class="header-metric-value" style="color: #f0883e;">{len(convergences)}</div>
            </div>
            <div class="header-metric">
                <div class="header-metric-label">EARLY SIGNALS</div>
                <div class="header-metric-value" style="color: #58a6ff;">{early_signals}</div>
            </div>
            <div class="header-metric">
                <div class="header-metric-label">UPDATED</div>
                <div class="header-metric-value">{datetime.now().strftime("%H:%M:%S")}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Main layout - 4 columns
    col1, col2, col3, col4 = st.columns([1.5, 1.5, 1, 1])

    # Column 1: Positions
    with col1:
        st.markdown('<div class="section-header">POSITIONS</div>', unsafe_allow_html=True)

        if positions:
            df = pd.DataFrame(positions)
            if "market_value" in df.columns:
                df = df.sort_values("market_value", ascending=False)
                df["pnl"] = df.get("unrealized_pnl", 0)
                df["pnl_pct"] = df.get("unrealized_pnl_pct", 0)
                df["wgt"] = df["market_value"] / total_value * 100 if total_value > 0 else 0

                # Format for display
                display_df = df[["symbol", "quantity", "market_value", "pnl", "pnl_pct", "wgt"]].copy()
                display_df.columns = ["SYM", "QTY", "VALUE", "P&L", "P&L%", "WT%"]
                display_df["VALUE"] = display_df["VALUE"].apply(lambda x: f"${x:,.0f}")
                display_df["P&L"] = display_df["P&L"].apply(lambda x: f"${x:+,.0f}")
                display_df["P&L%"] = display_df["P&L%"].apply(lambda x: f"{x:+.1f}%")
                display_df["WT%"] = display_df["WT%"].apply(lambda x: f"{x:.1f}%")

                st.dataframe(display_df, use_container_width=True, hide_index=True, height=400)
        else:
            st.info("No positions")

    # Column 2: Theses & Exposure
    with col2:
        st.markdown('<div class="section-header">THESIS EXPOSURE</div>', unsafe_allow_html=True)

        if theses and positions:
            # Build exposure table
            symbol_thesis = {}
            for t in theses:
                for sym in t.get("positions", []):
                    symbol_thesis[sym] = t.get("name", "Unknown")

            thesis_exposure = {}
            thesis_pnl = {}
            for p in positions:
                sym = p.get("symbol", "")
                tname = symbol_thesis.get(sym, "Unassigned")
                thesis_exposure[tname] = thesis_exposure.get(tname, 0) + p.get("market_value", 0)
                thesis_pnl[tname] = thesis_pnl.get(tname, 0) + p.get("unrealized_pnl", 0)

            rows = []
            for tname, exp in sorted(thesis_exposure.items(), key=lambda x: -x[1]):
                pnl = thesis_pnl.get(tname, 0)
                pct = exp / total_value * 100 if total_value > 0 else 0
                # Find conviction
                conv = next((t.get("conviction", 0) for t in theses if t.get("name") == tname), 0)
                rows.append({
                    "THESIS": tname[:25],
                    "EXPOSURE": f"${exp:,.0f}",
                    "WT%": f"{pct:.1f}%",
                    "P&L": f"${pnl:+,.0f}",
                    "CONV": f"{conv}%",
                })

            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=200)

        st.markdown('<div class="section-header">SIGNPOSTS</div>', unsafe_allow_html=True)

        # Show signposts from theses
        signposts_shown = 0
        for t in theses[:5]:
            for sp in t.get("signposts", [])[:2]:
                status = sp.get("status", "pending")
                icon = "✓" if status == "triggered" else "○"
                st.markdown(f"""
                <div class="info-box">
                    <span style="color: {'#3fb950' if status == 'triggered' else '#8b949e'};">{icon}</span>
                    <strong>{t.get('name', '?')[:15]}</strong>: {sp.get('description', '')[:40]}
                </div>
                """, unsafe_allow_html=True)
                signposts_shown += 1
                if signposts_shown >= 6:
                    break
            if signposts_shown >= 6:
                break

    # Column 3: Convergences & Signals
    with col3:
        st.markdown('<div class="section-header">CONVERGENCES</div>', unsafe_allow_html=True)

        if convergences:
            for c in convergences[:6]:
                dir_class = "signal-bull" if c["direction"] == "bullish" else "signal-bear" if c["direction"] == "bearish" else "signal-neutral"
                dir_icon = "▲" if c["direction"] == "bullish" else "▼" if c["direction"] == "bearish" else "●"
                agents_str = ", ".join(c["names"][:3])

                st.markdown(f"""
                <div class="convergence-item">
                    <div style="display: flex; justify-content: space-between;">
                        <span class="{dir_class}"><strong>{dir_icon} {c['symbol']}</strong></span>
                        <span style="color: #f0883e;">{c['agents']} agents</span>
                    </div>
                    <div style="color: #8b949e; font-size: 0.7rem;">{agents_str}</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown('<div class="info-box">No convergences detected</div>', unsafe_allow_html=True)

        st.markdown('<div class="section-header">EARLY SIGNALS (SOCIAL)</div>', unsafe_allow_html=True)

        early = [s for s in social.get("signals", []) if s.get("signal_vintage", 99) <= 7][:5]
        if early:
            for s in early:
                phase = s.get("current_phase", "?")
                phase_color = "#3fb950" if phase == "early" else "#d29922" if phase == "growing" else "#8b949e"
                st.markdown(f"""
                <div class="signal-row">
                    <span><strong>{s.get('symbol', '?')}</strong></span>
                    <span style="color: {phase_color};">{phase} ({s.get('signal_vintage', 0)}d)</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown('<div class="info-box">No early signals</div>', unsafe_allow_html=True)

        st.markdown('<div class="section-header">SUGGESTIONS</div>', unsafe_allow_html=True)

        if suggestions:
            for s in suggestions[:4]:
                sources = list(set(s.get("signal_sources", [])))[:2]
                sources_str = ", ".join(sources) if sources else "?"
                conf = s.get("confidence_score", 0)
                st.markdown(f"""
                <div class="info-box">
                    <strong>{s.get('symbol', '?')}</strong> — {s.get('suggested_name', '?')[:20]}
                    <div style="color: #8b949e; font-size: 0.7rem;">{s.get('signal_count', 0)} signals ({sources_str}) • {conf:.0%}</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown('<div class="info-box">No pending suggestions</div>', unsafe_allow_html=True)

    # Column 4: Activity & Status
    with col4:
        st.markdown('<div class="section-header">ACTIVITY</div>', unsafe_allow_html=True)

        today = datetime.now().strftime("%Y-%m-%d")
        recent = [a for a in activity if a.get("timestamp", "").startswith(today)][-10:]

        if recent:
            for a in reversed(recent):
                ts = a.get("timestamp", "")[-8:-3] if a.get("timestamp") else "?"  # HH:MM
                etype = a.get("type", a.get("event", "?"))[:15]
                details = str(a.get("details", a.get("message", "")))[:30]

                if "alert" in etype.lower():
                    color = "#d29922"
                elif "signal" in etype.lower():
                    color = "#58a6ff"
                elif "agent" in etype.lower():
                    color = "#a371f7"
                else:
                    color = "#8b949e"

                st.markdown(f"""
                <div class="signal-row">
                    <span style="color: {color};">{etype}</span>
                    <span style="color: #484f58;">{ts}</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown('<div class="info-box">No activity today</div>', unsafe_allow_html=True)

        st.markdown('<div class="section-header">STATUS</div>', unsafe_allow_html=True)

        # System status checks
        state_file = RESULTS_DIR / "live" / "state.json"
        state_age = (datetime.now() - datetime.fromtimestamp(state_file.stat().st_mtime)).seconds // 60 if state_file.exists() else 999

        active_prov = len([p for p in provenance if p.get("outcome") == "pending"])
        hit_prov = len([p for p in provenance if p.get("outcome") == "hit"])
        closed_prov = len([p for p in provenance if p.get("outcome") in ["hit", "miss"]])
        hit_rate = hit_prov / closed_prov if closed_prov > 0 else 0

        status_items = [
            ("State", f"{state_age}m ago", "status-ok" if state_age < 10 else "status-warn" if state_age < 30 else "status-error"),
            ("Theses", f"{len(theses)} active", "status-ok" if theses else "status-warn"),
            ("Signals", f"{active_prov} tracking", "status-ok"),
            ("Hit Rate", f"{hit_rate:.0%}", "status-ok" if hit_rate > 0.5 else "status-warn"),
            ("Cash", f"${cash:,.0f}", "status-ok" if cash > 5000 else "status-warn"),
            ("Max Pos", f"{max_conc:.1%}", "status-ok" if max_conc < 0.15 else "status-warn" if max_conc < 0.20 else "status-error"),
        ]

        for label, value, status_class in status_items:
            st.markdown(f"""
            <div class="signal-row">
                <span>{label}</span>
                <span class="{status_class}">{value}</span>
            </div>
            """, unsafe_allow_html=True)

        st.markdown('<div class="section-header">ALERTS</div>', unsafe_allow_html=True)

        if alerts:
            for a in alerts[:5]:
                priority = a.get("priority", "medium")
                p_color = "#f85149" if priority == "critical" else "#d29922" if priority == "high" else "#8b949e"
                st.markdown(f"""
                <div class="info-box" style="border-left: 2px solid {p_color};">
                    <strong>{a.get('symbol', '?')}</strong>: {a.get('description', '')[:35]}
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown('<div class="info-box" style="color: #3fb950;">No alerts today</div>', unsafe_allow_html=True)

    # Bottom section - Top Signals & Charts
    st.markdown("<br>", unsafe_allow_html=True)

    bcol1, bcol2 = st.columns([1, 1])

    with bcol1:
        st.markdown('<div class="section-header">TOP SIGNALS</div>', unsafe_allow_html=True)

        top_signals = signals.get("watchlist", [])[:10] if signals else []
        if top_signals:
            rows = []
            for sig in top_signals:
                direction = sig.get("direction", "neutral")
                d_icon = "▲" if direction == "bullish" else "▼" if direction == "bearish" else "●"
                rows.append({
                    "": d_icon,
                    "SYM": sig.get("symbol", "?"),
                    "TYPE": sig.get("type", "?")[:10],
                    "STRENGTH": f"{sig.get('strength', 0):.2f}",
                    "DESCRIPTION": sig.get("description", "")[:40],
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("No active signals in watchlist")

    with bcol2:
        st.markdown('<div class="section-header">POSITION CHART</div>', unsafe_allow_html=True)

        if positions:
            df = pd.DataFrame(positions).nlargest(15, "market_value")

            pnl_values = df.get("unrealized_pnl", pd.Series([0] * len(df)))
            colors = ["#3fb950" if p >= 0 else "#f85149" for p in pnl_values]

            fig = go.Figure(data=[
                go.Bar(
                    x=df["symbol"],
                    y=df["market_value"],
                    marker_color=colors,
                    text=df["market_value"].apply(lambda x: f"${x/1000:.1f}k"),
                    textposition="outside",
                    textfont=dict(size=9),
                )
            ])

            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=10, r=10, t=10, b=30),
                height=180,
                xaxis=dict(showgrid=False, tickfont=dict(size=9)),
                yaxis=dict(showgrid=True, gridcolor="#21262d", tickfont=dict(size=9)),
                bargap=0.3,
            )

            st.plotly_chart(fig, use_container_width=True)

    # Auto-refresh in sidebar
    with st.sidebar:
        st.markdown("### Controls")
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()

        auto = st.checkbox("Auto-refresh (30s)")
        if auto:
            time.sleep(30)
            st.rerun()

        st.markdown("---")
        st.markdown("### Quick Commands")
        st.code("streamlit run scripts/athena_dashboard.py", language="bash")
        st.markdown("**Update state:**")
        st.code("./scripts/mission_control.sh --quick", language="bash")


if __name__ == "__main__":
    main()
