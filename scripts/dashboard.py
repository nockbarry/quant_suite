#!/usr/bin/env python3
"""Streamlit Dashboard - Real-time portfolio and market monitoring.

Run with: streamlit run scripts/dashboard.py
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.paths import paths

import streamlit as st
import pandas as pd

# Page config
st.set_page_config(
    page_title="Project Athena Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


def load_state():
    """Load unified state."""
    state_file = paths.live_state
    if state_file.exists():
        with open(state_file) as f:
            return json.load(f)
    return None


def load_alerts():
    """Load today's alerts."""
    today = datetime.now().strftime("%Y%m%d")
    alerts_file = paths.base / "alerts" / f"alerts_{today}.json"
    if alerts_file.exists():
        with open(alerts_file) as f:
            return json.load(f)
    return []


def load_signposts():
    """Load signposts configuration."""
    signposts_file = paths.base / "config" / "signposts.json"
    if signposts_file.exists():
        with open(signposts_file) as f:
            return json.load(f)
    return []


def load_pending_trades():
    """Load pending trades from rules engine."""
    queue_file = paths.base / "rules" / "trade_queue.json"
    if queue_file.exists():
        with open(queue_file) as f:
            trades = json.load(f)
        return [t for t in trades if t.get("status") == "pending"]
    return []


def load_sector_data():
    """Load sector rotation data."""
    sector_file = paths.live / "sectors" / "rotation_state.json"
    if sector_file.exists():
        with open(sector_file) as f:
            return json.load(f)
    return None


def load_drawdown_state():
    """Load drawdown protection state."""
    dd_file = paths.base / "risk" / "drawdown_state.json"
    if dd_file.exists():
        with open(dd_file) as f:
            return json.load(f)
    return None


# Main dashboard
def main():
    st.title("📈 Project Athena Dashboard")

    # Sidebar
    st.sidebar.header("Navigation")
    page = st.sidebar.radio("Select Page", [
        "Portfolio Overview",
        "Signposts & Alerts",
        "Sector Rotation",
        "Risk Management",
        "Pending Actions",
    ])

    # Load data
    state = load_state()
    alerts = load_alerts()

    if page == "Portfolio Overview":
        render_portfolio_overview(state)
    elif page == "Signposts & Alerts":
        render_signposts_alerts(alerts)
    elif page == "Sector Rotation":
        render_sector_rotation()
    elif page == "Risk Management":
        render_risk_management()
    elif page == "Pending Actions":
        render_pending_actions()


def render_portfolio_overview(state):
    """Render portfolio overview page."""
    st.header("Portfolio Overview")

    if not state:
        st.warning("No state data available. Run the daemon to update.")
        return

    # Top metrics
    col1, col2, col3, col4 = st.columns(4)

    portfolio = state.get("portfolio", {})
    with col1:
        st.metric(
            "Portfolio Value",
            f"${portfolio.get('total_equity', 0):,.0f}",
            f"{portfolio.get('day_pnl_pct', 0):+.2f}%"
        )

    with col2:
        st.metric(
            "Cash",
            f"${portfolio.get('cash', 0):,.0f}",
            f"{portfolio.get('cash', 0) / max(portfolio.get('total_equity', 1), 1) * 100:.1f}%"
        )

    market = state.get("market", {})
    with col3:
        st.metric("VIX", f"{market.get('vix', 0):.1f}")

    with col4:
        regime = market.get("regime", "unknown")
        st.metric("Regime", regime.upper())

    st.divider()

    # Positions table
    st.subheader("Positions")
    positions = state.get("positions", [])

    if positions:
        df = pd.DataFrame(positions)
        if "unrealized_pnl_pct" in df.columns:
            df["P&L"] = df["unrealized_pnl_pct"].apply(lambda x: f"{x:+.1f}%")

        # Color code P&L
        st.dataframe(
            df[["symbol", "quantity", "market_value", "P&L"]].head(20) if "P&L" in df.columns else df.head(20),
            use_container_width=True,
        )
    else:
        st.info("No positions loaded")

    # Theses summary
    st.subheader("Active Theses")
    theses = state.get("theses", [])

    if theses:
        for thesis in theses:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"**{thesis.get('name', 'Unknown')}**")
                st.caption(f"Positions: {', '.join(thesis.get('positions', []))}")
            with col2:
                conviction = thesis.get("conviction", 0)
                color = "🟢" if conviction > 70 else "🟡" if conviction > 40 else "🔴"
                st.write(f"{color} {conviction}%")
    else:
        st.info("No active theses")


def render_signposts_alerts(alerts):
    """Render signposts and alerts page."""
    st.header("Signposts & Alerts")

    # Today's alerts
    st.subheader(f"Today's Alerts ({len(alerts)})")

    if alerts:
        for alert in alerts[:10]:
            priority = alert.get("priority", "medium")
            icon = {"critical": "🔴", "high": "🟠", "medium": "🟡"}.get(priority, "⚪")

            with st.expander(f"{icon} {alert.get('symbol', '?')} - {alert.get('description', '')[:50]}"):
                st.write(f"**Price:** ${alert.get('price', 0):.2f}")
                st.write(f"**Level:** ${alert.get('level', 0):.2f}")
                st.write(f"**Action:** {alert.get('action', 'N/A')}")
                st.write(f"**Time:** {alert.get('timestamp', 'N/A')}")
    else:
        st.success("No alerts triggered today")

    st.divider()

    # All signposts
    st.subheader("Active Signposts")
    signposts = load_signposts()

    if signposts:
        df = pd.DataFrame(signposts)
        df["Direction"] = df["direction"].apply(lambda x: "📈" if x == "above" else "📉")
        df["Level"] = df["level"].apply(lambda x: f"${x:.2f}")

        st.dataframe(
            df[["symbol", "Direction", "Level", "description", "priority"]],
            use_container_width=True,
        )
    else:
        st.info("No signposts configured")


def render_sector_rotation():
    """Render sector rotation page."""
    st.header("Sector Rotation")

    sector_data = load_sector_data()

    if not sector_data:
        st.warning("No sector data available. Run sector rotation analysis.")

        if st.button("Run Analysis"):
            st.info("Run: PYTHONPATH=. python -c 'from src.synthesis.sector_rotation import *; import asyncio; asyncio.run(main())'")
        return

    # Sector rankings
    st.subheader("Sector Rankings")
    sectors = sector_data.get("sectors", {})

    if sectors:
        df = pd.DataFrame([
            {
                "Rank": v.get("rank", 0),
                "Sector": v.get("name", k),
                "Symbol": k,
                "Momentum": f"{v.get('momentum_score', 0):+.2f}",
                "RS vs SPY": f"{v.get('rs_vs_spy', 0):+.2f}%",
                "1D": f"{v.get('return_1d', 0):+.2f}%",
                "5D": f"{v.get('return_5d', 0):+.2f}%",
            }
            for k, v in sectors.items()
        ])
        df = df.sort_values("Rank")
        st.dataframe(df, use_container_width=True)

    # Rotation history
    st.subheader("Recent Rotation Signals")
    history = sector_data.get("history", [])

    if history:
        for signal in history[-5:]:
            st.write(f"**{signal.get('rotation_type', 'Unknown')}** - {signal.get('timestamp', '')[:10]}")
            st.caption(f"From: {signal.get('from_sectors', [])} → To: {signal.get('to_sectors', [])}")
    else:
        st.info("No rotation signals recorded")


def render_risk_management():
    """Render risk management page."""
    st.header("Risk Management")

    dd_state = load_drawdown_state()

    if not dd_state:
        st.warning("No drawdown data available.")
        return

    # Drawdown metrics
    col1, col2, col3 = st.columns(3)

    with col1:
        level = dd_state.get("current_level", "normal")
        color = {"normal": "🟢", "caution": "🟡", "warning": "🟠", "critical": "🔴", "emergency": "⛔"}.get(level, "⚪")
        st.metric("Protection Level", f"{color} {level.upper()}")

    with col2:
        peak = dd_state.get("peak_value", 0)
        st.metric("Peak Value", f"${peak:,.0f}")

    with col3:
        peak_date = dd_state.get("peak_date", "N/A")
        if peak_date and peak_date != "N/A":
            st.metric("Peak Date", peak_date[:10])

    st.divider()

    # Protection levels explanation
    st.subheader("Protection Levels")

    levels_df = pd.DataFrame([
        {"Level": "Normal", "Threshold": "0-5%", "Actions": "Full trading allowed"},
        {"Level": "Caution", "Threshold": "5-7.5%", "Actions": "Tighten stops, no new positions"},
        {"Level": "Warning", "Threshold": "7.5-10%", "Actions": "Reduce sizes 25%, close weakest"},
        {"Level": "Critical", "Threshold": "10-15%", "Actions": "Reduce to 50% invested"},
        {"Level": "Emergency", "Threshold": ">15%", "Actions": "Move to 100% cash"},
    ])

    st.table(levels_df)


def render_pending_actions():
    """Render pending actions page."""
    st.header("Pending Actions")

    # Pending trades
    st.subheader("Queued Trades")
    pending_trades = load_pending_trades()

    if pending_trades:
        for trade in pending_trades:
            with st.expander(f"{trade.get('action', '?')} {trade.get('quantity', 0)} {trade.get('symbol', '?')}"):
                st.write(f"**Reason:** {trade.get('reason', 'N/A')}")
                st.write(f"**Created:** {trade.get('created_at', 'N/A')}")
                st.write(f"**Expires:** {trade.get('expires_at', 'N/A')}")

                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"Approve {trade.get('trade_id', '')[:8]}", key=f"approve_{trade.get('trade_id')}"):
                        st.success("Trade approved! Run execution script to execute.")
                with col2:
                    if st.button(f"Reject {trade.get('trade_id', '')[:8]}", key=f"reject_{trade.get('trade_id')}"):
                        st.warning("Trade rejected")
    else:
        st.success("No pending trades")

    st.divider()

    # Quick actions
    st.subheader("Quick Actions")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Update State"):
            st.info("Run: PYTHONPATH=. python -c 'from src.synthesis.daemon import LiveDaemon; import asyncio; asyncio.run(LiveDaemon().update_now())'")

    with col2:
        if st.button("Check Signposts"):
            st.info("Run: PYTHONPATH=. python scripts/signpost_monitor.py --alerts")

    with col3:
        if st.button("Run Sector Analysis"):
            st.info("Run: PYTHONPATH=. python -m src.synthesis.sector_rotation")


if __name__ == "__main__":
    main()
