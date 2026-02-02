#!/usr/bin/env python3
"""
Project Athena - Command Center Dashboard

A professional-grade trading intelligence dashboard combining:
- Real-time portfolio monitoring
- Swarm intelligence visualization
- Signal convergence detection
- Thesis tracking and performance
- Social signal early detection
- Risk management

Run: streamlit run scripts/athena_dashboard.py
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import time

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

# =============================================================================
# PAGE CONFIG & STYLING
# =============================================================================

st.set_page_config(
    page_title="Athena Command Center",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Professional dark theme CSS
st.markdown("""
<style>
    /* Dark theme base */
    .stApp {
        background: linear-gradient(180deg, #0a0a0f 0%, #121218 100%);
    }

    /* Hide default streamlit elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* Custom header */
    .main-header {
        background: linear-gradient(90deg, #1a1a2e 0%, #16213e 50%, #1a1a2e 100%);
        padding: 1rem 2rem;
        border-radius: 10px;
        margin-bottom: 1rem;
        border: 1px solid #2d2d44;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    }

    .main-title {
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(90deg, #00d4ff, #7b2cbf);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0;
        letter-spacing: 2px;
    }

    .sub-title {
        color: #888;
        font-size: 0.9rem;
        margin-top: 0.25rem;
    }

    /* Metric cards */
    .metric-card {
        background: linear-gradient(145deg, #1e1e2f 0%, #252538 100%);
        border: 1px solid #3d3d5c;
        border-radius: 12px;
        padding: 1.25rem;
        text-align: center;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
    }

    .metric-card:hover {
        border-color: #00d4ff;
        box-shadow: 0 4px 25px rgba(0,212,255,0.15);
    }

    .metric-value {
        font-size: 2rem;
        font-weight: 700;
        color: #fff;
        margin: 0.5rem 0;
    }

    .metric-value.positive { color: #00ff88; }
    .metric-value.negative { color: #ff4757; }
    .metric-value.warning { color: #ffa502; }
    .metric-value.info { color: #00d4ff; }

    .metric-label {
        font-size: 0.75rem;
        color: #888;
        text-transform: uppercase;
        letter-spacing: 1px;
    }

    .metric-delta {
        font-size: 0.9rem;
        margin-top: 0.25rem;
    }

    /* Section headers */
    .section-header {
        font-size: 1.1rem;
        font-weight: 600;
        color: #00d4ff;
        text-transform: uppercase;
        letter-spacing: 2px;
        margin: 1.5rem 0 1rem 0;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid #2d2d44;
    }

    /* Signal cards */
    .signal-card {
        background: #1a1a2e;
        border-left: 3px solid #00d4ff;
        padding: 0.75rem 1rem;
        margin: 0.5rem 0;
        border-radius: 0 8px 8px 0;
    }

    .signal-card.bullish { border-left-color: #00ff88; }
    .signal-card.bearish { border-left-color: #ff4757; }
    .signal-card.convergence { border-left-color: #ffa502; background: #2a2a1e; }

    /* Activity feed */
    .activity-item {
        background: #16161e;
        border-radius: 8px;
        padding: 0.75rem;
        margin: 0.5rem 0;
        border: 1px solid #2d2d44;
        font-size: 0.85rem;
    }

    .activity-time {
        color: #666;
        font-size: 0.75rem;
    }

    /* Thesis cards */
    .thesis-card {
        background: linear-gradient(145deg, #1a1a2e 0%, #1e2235 100%);
        border: 1px solid #3d3d5c;
        border-radius: 12px;
        padding: 1rem;
        margin: 0.5rem 0;
    }

    .thesis-name {
        font-size: 1rem;
        font-weight: 600;
        color: #fff;
    }

    .conviction-bar {
        height: 6px;
        background: #2d2d44;
        border-radius: 3px;
        margin-top: 0.5rem;
        overflow: hidden;
    }

    .conviction-fill {
        height: 100%;
        border-radius: 3px;
        transition: width 0.5s ease;
    }

    /* Status indicators */
    .status-dot {
        display: inline-block;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        margin-right: 6px;
    }

    .status-dot.active { background: #00ff88; box-shadow: 0 0 8px #00ff88; }
    .status-dot.warning { background: #ffa502; box-shadow: 0 0 8px #ffa502; }
    .status-dot.error { background: #ff4757; box-shadow: 0 0 8px #ff4757; }
    .status-dot.inactive { background: #444; }

    /* Swarm visualization */
    .agent-chip {
        display: inline-block;
        background: #2d2d44;
        color: #00d4ff;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.75rem;
        margin: 0.25rem;
        border: 1px solid #3d3d5c;
    }

    .agent-chip.active {
        background: #1a3a1a;
        color: #00ff88;
        border-color: #00ff88;
    }

    /* Tables */
    .dataframe {
        font-size: 0.85rem !important;
    }

    /* Streamlit overrides */
    .stMetric {
        background: transparent !important;
    }

    [data-testid="stMetricValue"] {
        font-size: 1.75rem !important;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: #16161e;
        padding: 0.5rem;
        border-radius: 10px;
    }

    .stTabs [data-baseweb="tab"] {
        background: transparent;
        border-radius: 8px;
        color: #888;
        padding: 0.5rem 1rem;
    }

    .stTabs [aria-selected="true"] {
        background: linear-gradient(90deg, #1a3a5c, #2a4a6c) !important;
        color: #00d4ff !important;
    }

    /* Expander styling */
    .streamlit-expanderHeader {
        background: #1a1a2e !important;
        border-radius: 8px !important;
    }

    /* Progress bars */
    .stProgress > div > div {
        background: linear-gradient(90deg, #00d4ff, #7b2cbf) !important;
    }
</style>
""", unsafe_allow_html=True)


# =============================================================================
# DATA LOADING
# =============================================================================

RESULTS_DIR = Path.home() / "quant_results"


@st.cache_data(ttl=30)
def load_unified_state():
    """Load the unified state file."""
    state_file = RESULTS_DIR / "live" / "state.json"
    if state_file.exists():
        with open(state_file) as f:
            return json.load(f)
    return {}


@st.cache_data(ttl=30)
def load_swarm_signals():
    """Load swarm signal data."""
    signals_dir = RESULTS_DIR / "live" / "signals"
    signals = []

    if signals_dir.exists():
        for f in signals_dir.glob("*.json"):
            try:
                with open(f) as file:
                    data = json.load(file)
                    if isinstance(data, list):
                        signals.extend(data)
                    else:
                        signals.append(data)
            except:
                pass

    return signals


@st.cache_data(ttl=30)
def load_social_signals():
    """Load WSB and social signals."""
    wsb_file = RESULTS_DIR / "social" / "wsb_signals.json"
    if wsb_file.exists():
        with open(wsb_file) as f:
            return json.load(f)
    return {"signals": [], "total_symbols": 0}


@st.cache_data(ttl=30)
def load_thesis_suggestions():
    """Load auto-generated thesis suggestions."""
    suggestions_file = RESULTS_DIR / "suggestions" / "thesis_suggestions.json"
    if suggestions_file.exists():
        with open(suggestions_file) as f:
            data = json.load(f)
            return [s for s in data.get("suggestions", []) if s.get("status") == "pending"]
    return []


@st.cache_data(ttl=30)
def load_signal_provenance():
    """Load signal provenance data."""
    prov_dir = RESULTS_DIR / "signal_provenance"
    signals = []

    if prov_dir.exists():
        for f in prov_dir.glob("*.json"):
            try:
                with open(f) as file:
                    data = json.load(file)
                    signals.extend(data.get("signals", []))
            except:
                pass

    return signals


@st.cache_data(ttl=30)
def load_agent_activity():
    """Load agent activity log."""
    log_file = RESULTS_DIR / "logs" / "agent_activity.jsonl"
    activities = []

    if log_file.exists():
        with open(log_file) as f:
            for line in f:
                try:
                    activities.append(json.loads(line.strip()))
                except:
                    pass

    # Return last 50 activities
    return activities[-50:]


@st.cache_data(ttl=60)
def load_theses():
    """Load all active theses."""
    theses_dir = RESULTS_DIR / "theses"
    theses = []

    if theses_dir.exists():
        import yaml
        for f in theses_dir.glob("*.yaml"):
            try:
                with open(f) as file:
                    thesis = yaml.safe_load(file)
                    if thesis and thesis.get("status") == "active":
                        theses.append(thesis)
            except:
                pass

    return theses


@st.cache_data(ttl=30)
def load_convergences():
    """Load signal convergences from swarm monitor."""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from src.monitoring.swarm_monitor import get_swarm_monitor

        monitor = get_swarm_monitor()
        convergences = monitor.find_convergences(min_agents=2)

        return [
            {
                "symbol": c.symbol or "MARKET",
                "direction": c.direction,
                "agent_count": c.agent_count,
                "score": c.convergence_score,
                "agents": [s.agent_name for s in c.signals],
            }
            for c in convergences[:10]
        ]
    except Exception as e:
        return []


def load_operator_log():
    """Load operator log entries."""
    log_file = RESULTS_DIR / "logs" / "operator_log.jsonl"
    entries = []

    if log_file.exists():
        with open(log_file) as f:
            for line in f:
                try:
                    entries.append(json.loads(line.strip()))
                except:
                    pass

    return entries[-30:]


# =============================================================================
# VISUALIZATION HELPERS
# =============================================================================

def create_portfolio_chart(positions: list) -> go.Figure:
    """Create portfolio allocation chart."""
    if not positions:
        return None

    # Group by thesis or sector
    df = pd.DataFrame(positions)

    if df.empty or "market_value" not in df.columns:
        return None

    df = df.nlargest(15, "market_value")

    fig = go.Figure(data=[
        go.Bar(
            x=df["symbol"],
            y=df["market_value"],
            marker=dict(
                color=df.get("unrealized_pnl", [0] * len(df)),
                colorscale=[[0, "#ff4757"], [0.5, "#2d2d44"], [1, "#00ff88"]],
                cmid=0,
            ),
            text=df["market_value"].apply(lambda x: f"${x:,.0f}"),
            textposition="auto",
        )
    ])

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=30, b=20),
        height=250,
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="#2d2d44"),
    )

    return fig


def create_pnl_gauge(pnl_pct: float) -> go.Figure:
    """Create P&L gauge chart."""
    color = "#00ff88" if pnl_pct >= 0 else "#ff4757"

    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=pnl_pct,
        number={"suffix": "%", "font": {"size": 40, "color": color}},
        gauge={
            "axis": {"range": [-5, 5], "tickcolor": "#444"},
            "bar": {"color": color},
            "bgcolor": "#1a1a2e",
            "borderwidth": 0,
            "steps": [
                {"range": [-5, -2], "color": "#3d1a1a"},
                {"range": [-2, 0], "color": "#2d2d1a"},
                {"range": [0, 2], "color": "#1a2d1a"},
                {"range": [2, 5], "color": "#1a3d1a"},
            ],
        },
    ))

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        height=200,
        margin=dict(l=20, r=20, t=30, b=20),
    )

    return fig


def create_convergence_chart(convergences: list) -> go.Figure:
    """Create convergence visualization."""
    if not convergences:
        return None

    df = pd.DataFrame(convergences)

    colors = ["#00ff88" if d == "bullish" else "#ff4757" if d == "bearish" else "#ffa502"
              for d in df["direction"]]

    fig = go.Figure(data=[
        go.Bar(
            x=df["symbol"],
            y=df["agent_count"],
            marker=dict(color=colors),
            text=df["agent_count"].apply(lambda x: f"{x} agents"),
            textposition="auto",
        )
    ])

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=10, b=20),
        height=200,
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="#2d2d44", title="Agents Agreeing"),
    )

    return fig


def create_thesis_exposure_chart(theses: list, positions: list) -> go.Figure:
    """Create thesis exposure sunburst."""
    if not theses or not positions:
        return None

    # Build symbol -> thesis mapping
    symbol_thesis = {}
    for thesis in theses:
        for symbol in thesis.get("positions", []):
            symbol_thesis[symbol] = thesis.get("name", "Unknown")

    # Calculate exposure
    exposure = {}
    for pos in positions:
        symbol = pos.get("symbol", "")
        thesis_name = symbol_thesis.get(symbol, "Unassigned")
        if thesis_name not in exposure:
            exposure[thesis_name] = 0
        exposure[thesis_name] += pos.get("market_value", 0)

    if not exposure:
        return None

    labels = list(exposure.keys())
    values = list(exposure.values())

    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.5,
        textinfo="label+percent",
        textposition="outside",
        marker=dict(
            colors=px.colors.qualitative.Set2[:len(labels)],
            line=dict(color="#1a1a2e", width=2),
        ),
    )])

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=20, b=20),
        height=300,
        showlegend=False,
    )

    return fig


# =============================================================================
# MAIN DASHBOARD
# =============================================================================

def main():
    # Header
    st.markdown("""
    <div class="main-header">
        <h1 class="main-title">🏛️ ATHENA COMMAND CENTER</h1>
        <p class="sub-title">Hybrid Intelligence Trading System • Real-time Monitoring</p>
    </div>
    """, unsafe_allow_html=True)

    # Load all data
    state = load_unified_state()
    theses = load_theses()
    convergences = load_convergences()
    social = load_social_signals()
    suggestions = load_thesis_suggestions()
    provenance = load_signal_provenance()
    activities = load_agent_activity()

    portfolio = state.get("portfolio", {})
    positions = state.get("positions", [])
    market = state.get("market", {})

    # Top metrics row
    col1, col2, col3, col4, col5, col6 = st.columns(6)

    with col1:
        value = portfolio.get("equity", 0)
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Portfolio Value</div>
            <div class="metric-value">${value:,.0f}</div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        pnl = portfolio.get("day_pnl", 0)
        pnl_pct = portfolio.get("day_pnl_pct", 0)
        pnl_class = "positive" if pnl >= 0 else "negative"
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Day P&L</div>
            <div class="metric-value {pnl_class}">${pnl:+,.0f}</div>
            <div class="metric-delta" style="color: {'#00ff88' if pnl >= 0 else '#ff4757'}">{pnl_pct:+.2f}%</div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        regime = market.get("regime", "unknown").upper()
        regime_color = "info" if regime in ["RISK_ON", "BULLISH"] else "warning" if regime == "NEUTRAL" else "negative"
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Market Regime</div>
            <div class="metric-value {regime_color}">{regime}</div>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        conv_count = len(convergences)
        conv_class = "warning" if conv_count > 0 else ""
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Convergences</div>
            <div class="metric-value {conv_class}">{conv_count}</div>
            <div class="metric-delta" style="color: #888">Swarm Agreement</div>
        </div>
        """, unsafe_allow_html=True)

    with col5:
        early_signals = len([s for s in social.get("signals", [])
                            if s.get("signal_vintage", 99) <= 7])
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Early Signals</div>
            <div class="metric-value info">{early_signals}</div>
            <div class="metric-delta" style="color: #888">Social Alpha</div>
        </div>
        """, unsafe_allow_html=True)

    with col6:
        pending_suggestions = len(suggestions)
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Thesis Ideas</div>
            <div class="metric-value">{pending_suggestions}</div>
            <div class="metric-delta" style="color: #888">Auto-Generated</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Main content tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 OVERVIEW",
        "🧠 SWARM INTELLIGENCE",
        "📈 PORTFOLIO",
        "📋 THESES",
        "⚡ ACTIVITY"
    ])

    # ==========================================================================
    # TAB 1: OVERVIEW
    # ==========================================================================
    with tab1:
        col_left, col_right = st.columns([2, 1])

        with col_left:
            st.markdown('<div class="section-header">Signal Convergences</div>', unsafe_allow_html=True)

            if convergences:
                for conv in convergences[:5]:
                    direction = conv["direction"]
                    dir_class = "bullish" if direction == "bullish" else "bearish" if direction == "bearish" else ""
                    dir_icon = "📈" if direction == "bullish" else "📉" if direction == "bearish" else "➖"

                    agents_short = [a.replace("-agent", "") for a in conv["agents"][:4]]

                    st.markdown(f"""
                    <div class="signal-card convergence">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <span style="font-size: 1.25rem; font-weight: 600;">{dir_icon} {conv['symbol']}</span>
                                <span style="color: #888; margin-left: 1rem;">{conv['agent_count']} agents agree • {conv['score']:.0%} confidence</span>
                            </div>
                            <div>
                                {''.join([f'<span class="agent-chip">{a}</span>' for a in agents_short])}
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                chart = create_convergence_chart(convergences)
                if chart:
                    st.plotly_chart(chart, use_container_width=True)
            else:
                st.info("No signal convergences detected. Agents are analyzing independently.")

            st.markdown('<div class="section-header">Top Positions</div>', unsafe_allow_html=True)

            if positions:
                df = pd.DataFrame(positions).head(10)
                if "market_value" in df.columns:
                    df = df.sort_values("market_value", ascending=False)
                    df["P&L"] = df.get("unrealized_pnl", 0).apply(lambda x: f"${x:+,.0f}")
                    df["P&L %"] = df.get("unrealized_pnl_pct", 0).apply(lambda x: f"{x:+.1f}%")
                    df["Value"] = df["market_value"].apply(lambda x: f"${x:,.0f}")

                    st.dataframe(
                        df[["symbol", "quantity", "Value", "P&L", "P&L %"]].head(10),
                        use_container_width=True,
                        hide_index=True,
                    )

        with col_right:
            st.markdown('<div class="section-header">Thesis Suggestions</div>', unsafe_allow_html=True)

            if suggestions:
                for s in suggestions[:3]:
                    conf = s.get("confidence_score", 0)
                    conf_color = "#00ff88" if conf > 0.7 else "#ffa502" if conf > 0.5 else "#888"

                    st.markdown(f"""
                    <div class="thesis-card">
                        <div class="thesis-name">{s.get('symbol', '?')} — {s.get('suggested_name', 'Unknown')}</div>
                        <div style="color: #888; font-size: 0.85rem; margin: 0.5rem 0;">
                            {s.get('signal_count', 0)} signals • {', '.join(set(s.get('signal_sources', []))[:3])}
                        </div>
                        <div class="conviction-bar">
                            <div class="conviction-fill" style="width: {conf*100}%; background: {conf_color};"></div>
                        </div>
                        <div style="text-align: right; color: {conf_color}; margin-top: 0.25rem;">{conf:.0%} confidence</div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("No pending thesis suggestions")

            st.markdown('<div class="section-header">Early Signals (Social)</div>', unsafe_allow_html=True)

            early = [s for s in social.get("signals", []) if s.get("signal_vintage", 99) <= 7][:5]
            if early:
                for sig in early:
                    phase = sig.get("current_phase", "unknown")
                    phase_color = "#00ff88" if phase == "early" else "#ffa502" if phase == "growing" else "#888"

                    st.markdown(f"""
                    <div class="signal-card">
                        <div style="display: flex; justify-content: space-between;">
                            <span style="font-weight: 600;">{sig.get('symbol', '?')}</span>
                            <span style="color: {phase_color};">{phase.upper()}</span>
                        </div>
                        <div style="color: #888; font-size: 0.8rem;">
                            {sig.get('signal_vintage', 0)}d old • {sig.get('total_mentions', 0)} mentions
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("No early social signals detected")

    # ==========================================================================
    # TAB 2: SWARM INTELLIGENCE
    # ==========================================================================
    with tab2:
        col_left, col_right = st.columns([2, 1])

        with col_left:
            st.markdown('<div class="section-header">Agent Activity</div>', unsafe_allow_html=True)

            # Show recent agent activities
            today = datetime.now().strftime("%Y-%m-%d")
            today_activities = [a for a in activities if a.get("timestamp", "").startswith(today)]

            if today_activities:
                agent_counts = {}
                for a in today_activities:
                    agent = a.get("agent_name", a.get("type", "unknown"))
                    agent_counts[agent] = agent_counts.get(agent, 0) + 1

                cols = st.columns(min(len(agent_counts), 6))
                for i, (agent, count) in enumerate(sorted(agent_counts.items(), key=lambda x: -x[1])[:6]):
                    with cols[i]:
                        short_name = agent.replace("-agent", "").replace("_", " ").title()
                        st.markdown(f"""
                        <div class="metric-card" style="padding: 0.75rem;">
                            <div class="metric-label">{short_name}</div>
                            <div class="metric-value info" style="font-size: 1.5rem;">{count}</div>
                        </div>
                        """, unsafe_allow_html=True)
            else:
                st.info("No agent activity recorded today")

            st.markdown('<div class="section-header">Signal Heatmap</div>', unsafe_allow_html=True)

            # Create a heatmap of signals by agent and symbol
            if provenance:
                # Group by symbol and source
                heatmap_data = {}
                for sig in provenance[-100:]:  # Last 100 signals
                    symbol = sig.get("symbol", "MARKET")
                    source = sig.get("source", "unknown")
                    key = (symbol, source)
                    heatmap_data[key] = heatmap_data.get(key, 0) + 1

                if heatmap_data:
                    symbols = list(set(k[0] for k in heatmap_data.keys()))[:10]
                    sources = list(set(k[1] for k in heatmap_data.keys()))

                    z_data = [[heatmap_data.get((s, src), 0) for src in sources] for s in symbols]

                    fig = go.Figure(data=go.Heatmap(
                        z=z_data,
                        x=sources,
                        y=symbols,
                        colorscale=[[0, "#1a1a2e"], [0.5, "#00d4ff"], [1, "#00ff88"]],
                        showscale=False,
                    ))

                    fig.update_layout(
                        template="plotly_dark",
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        margin=dict(l=60, r=20, t=20, b=40),
                        height=300,
                    )

                    st.plotly_chart(fig, use_container_width=True)

        with col_right:
            st.markdown('<div class="section-header">Convergence Details</div>', unsafe_allow_html=True)

            if convergences:
                for conv in convergences:
                    with st.expander(f"{conv['symbol']} — {conv['direction'].upper()}", expanded=False):
                        st.write(f"**Agents:** {len(conv['agents'])}")
                        st.write(f"**Confidence:** {conv['score']:.0%}")
                        st.write("**Contributing Agents:**")
                        for agent in conv['agents']:
                            st.markdown(f"• {agent.replace('-agent', '')}")
            else:
                st.info("No active convergences")

            st.markdown('<div class="section-header">Signal Provenance</div>', unsafe_allow_html=True)

            active_prov = [p for p in provenance if p.get("outcome") == "pending"]
            hit_prov = [p for p in provenance if p.get("outcome") == "hit"]

            total = len(provenance)
            active = len(active_prov)
            hit_rate = len(hit_prov) / max(total - active, 1) if total > active else 0

            col_a, col_b = st.columns(2)
            with col_a:
                st.metric("Active Signals", active)
            with col_b:
                st.metric("Historical Hit Rate", f"{hit_rate:.0%}")

    # ==========================================================================
    # TAB 3: PORTFOLIO
    # ==========================================================================
    with tab3:
        col_left, col_right = st.columns([2, 1])

        with col_left:
            st.markdown('<div class="section-header">Position Breakdown</div>', unsafe_allow_html=True)

            chart = create_portfolio_chart(positions)
            if chart:
                st.plotly_chart(chart, use_container_width=True)

            st.markdown('<div class="section-header">All Positions</div>', unsafe_allow_html=True)

            if positions:
                df = pd.DataFrame(positions)
                if "market_value" in df.columns:
                    df = df.sort_values("market_value", ascending=False)

                    # Calculate concentration
                    total_value = df["market_value"].sum()
                    df["Weight"] = (df["market_value"] / total_value * 100).round(1).astype(str) + "%"

                    display_cols = ["symbol", "quantity", "market_value", "Weight"]
                    if "unrealized_pnl" in df.columns:
                        df["P&L"] = df["unrealized_pnl"].apply(lambda x: f"${x:+,.0f}")
                        display_cols.append("P&L")
                    if "unrealized_pnl_pct" in df.columns:
                        df["P&L %"] = df["unrealized_pnl_pct"].apply(lambda x: f"{x:+.1f}%")
                        display_cols.append("P&L %")

                    df["market_value"] = df["market_value"].apply(lambda x: f"${x:,.0f}")
                    df = df.rename(columns={"market_value": "Value"})
                    display_cols = [c if c != "market_value" else "Value" for c in display_cols]

                    st.dataframe(df[display_cols], use_container_width=True, hide_index=True, height=400)

        with col_right:
            st.markdown('<div class="section-header">Thesis Exposure</div>', unsafe_allow_html=True)

            chart = create_thesis_exposure_chart(theses, positions)
            if chart:
                st.plotly_chart(chart, use_container_width=True)
            else:
                st.info("No thesis data available")

            st.markdown('<div class="section-header">Risk Metrics</div>', unsafe_allow_html=True)

            # Calculate risk metrics
            if positions:
                total_value = sum(p.get("market_value", 0) for p in positions)
                max_position = max(p.get("market_value", 0) for p in positions) if positions else 0
                max_concentration = max_position / total_value if total_value > 0 else 0

                st.metric("Max Concentration", f"{max_concentration:.1%}")
                st.metric("Position Count", len(positions))

                # Sector concentration (simplified)
                st.metric("Cash Available", f"${portfolio.get('cash', 0):,.0f}")

    # ==========================================================================
    # TAB 4: THESES
    # ==========================================================================
    with tab4:
        if theses:
            for thesis in sorted(theses, key=lambda t: -t.get("conviction", 0)):
                conviction = thesis.get("conviction", 0)
                conv_color = "#00ff88" if conviction > 70 else "#ffa502" if conviction > 40 else "#ff4757"

                with st.expander(f"📋 {thesis.get('name', 'Unknown')} — {conviction}% conviction", expanded=False):
                    col1, col2 = st.columns([2, 1])

                    with col1:
                        st.write(f"**Summary:** {thesis.get('summary', 'No summary')}")
                        st.write(f"**Positions:** {', '.join(thesis.get('positions', []))}")

                        # Calculate exposure
                        thesis_value = sum(
                            p.get("market_value", 0) for p in positions
                            if p.get("symbol") in thesis.get("positions", [])
                        )
                        st.write(f"**Exposure:** ${thesis_value:,.0f}")

                        # Signposts
                        signposts = thesis.get("signposts", [])
                        if signposts:
                            st.write("**Signposts:**")
                            for sp in signposts:
                                status = sp.get("status", "pending")
                                icon = "✅" if status == "triggered" else "⏳"
                                st.write(f"  {icon} {sp.get('description', 'No description')}")

                    with col2:
                        # Conviction gauge
                        st.markdown(f"""
                        <div style="text-align: center; padding: 1rem;">
                            <div style="font-size: 3rem; color: {conv_color};">{conviction}%</div>
                            <div style="color: #888;">Conviction</div>
                        </div>
                        """, unsafe_allow_html=True)

                        invalidation = thesis.get("invalidation_triggers", [])
                        if invalidation:
                            st.write("**Invalidation:**")
                            for trigger in invalidation[:2]:
                                st.write(f"  ⚠️ {trigger}")
        else:
            st.info("No active theses. Create one with `/thesis` command.")

    # ==========================================================================
    # TAB 5: ACTIVITY
    # ==========================================================================
    with tab5:
        col_left, col_right = st.columns([2, 1])

        with col_left:
            st.markdown('<div class="section-header">Live Activity Feed</div>', unsafe_allow_html=True)

            operator_log = load_operator_log()

            if operator_log:
                for entry in reversed(operator_log[-15:]):
                    timestamp = entry.get("timestamp", "")[:19]
                    event_type = entry.get("type", entry.get("event", "unknown"))

                    # Color code by type
                    if "alert" in event_type.lower():
                        icon = "🔔"
                        border_color = "#ffa502"
                    elif "signal" in event_type.lower():
                        icon = "📊"
                        border_color = "#00d4ff"
                    elif "agent" in event_type.lower():
                        icon = "🤖"
                        border_color = "#7b2cbf"
                    elif "decision" in event_type.lower():
                        icon = "✅"
                        border_color = "#00ff88"
                    else:
                        icon = "📝"
                        border_color = "#3d3d5c"

                    details = entry.get("details", entry.get("message", str(entry)[:100]))
                    if isinstance(details, dict):
                        details = json.dumps(details)[:100]

                    st.markdown(f"""
                    <div class="activity-item" style="border-left: 3px solid {border_color};">
                        <div style="display: flex; justify-content: space-between;">
                            <span>{icon} <strong>{event_type}</strong></span>
                            <span class="activity-time">{timestamp}</span>
                        </div>
                        <div style="color: #888; margin-top: 0.25rem; font-size: 0.8rem;">
                            {details[:100]}...
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("No activity logged yet")

        with col_right:
            st.markdown('<div class="section-header">System Status</div>', unsafe_allow_html=True)

            # Check various system components
            state_file = RESULTS_DIR / "live" / "state.json"
            state_age = (datetime.now() - datetime.fromtimestamp(state_file.stat().st_mtime)).seconds if state_file.exists() else 9999

            components = [
                ("Unified State", state_age < 600, f"Updated {state_age//60}m ago"),
                ("Swarm Monitor", len(convergences) >= 0, f"{len(convergences)} convergences"),
                ("Social Tracker", social.get("total_symbols", 0) >= 0, f"{social.get('total_symbols', 0)} symbols"),
                ("Theses", len(theses) > 0, f"{len(theses)} active"),
            ]

            for name, healthy, detail in components:
                status_class = "active" if healthy else "warning"
                st.markdown(f"""
                <div class="activity-item">
                    <span class="status-dot {status_class}"></span>
                    <strong>{name}</strong>
                    <span style="color: #888; float: right;">{detail}</span>
                </div>
                """, unsafe_allow_html=True)

            st.markdown('<div class="section-header">Quick Actions</div>', unsafe_allow_html=True)

            if st.button("🔄 Refresh Data", use_container_width=True):
                st.cache_data.clear()
                st.rerun()

            if st.button("📊 Update State", use_container_width=True):
                st.code("PYTHONPATH=. python3 -c 'from src.synthesis.daemon import LiveDaemon; import asyncio; asyncio.run(LiveDaemon().update_now())'")

    # Footer
    st.markdown("""
    <div style="text-align: center; color: #444; margin-top: 2rem; padding: 1rem; border-top: 1px solid #2d2d44;">
        Project Athena • Hybrid Intelligence Trading System •
        Last refresh: """ + datetime.now().strftime("%H:%M:%S") + """
    </div>
    """, unsafe_allow_html=True)

    # Auto-refresh
    if st.sidebar.checkbox("Auto-refresh (30s)", value=False):
        time.sleep(30)
        st.rerun()


if __name__ == "__main__":
    main()
