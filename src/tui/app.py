"""Athena TUI — Main Textual App with 6-panel layout and 30s auto-refresh."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Footer, Header

from src.tui.panels.agents import AgentsPanel
from src.tui.panels.events import EventsPanel
from src.tui.panels.portfolio import PortfolioPanel
from src.tui.panels.signals import SignalsPanel
from src.tui.panels.system import SystemPanel
from src.tui.panels.theses import ThesesPanel

CSS = """
Screen {
    background: $surface;
}

#main-area {
    height: 1fr;
}

#left-col {
    width: 1fr;
}

#right-col {
    width: 1fr;
}

.panel {
    border: solid $primary;
    padding: 0 1;
    overflow-y: auto;
    height: 1fr;
}

#events-panel {
    height: 8;
    border: solid $primary;
    padding: 0 1;
    overflow-y: auto;
}

Footer {
    dock: bottom;
}

Header {
    dock: top;
}
"""


class AthenaApp(App):
    """Athena Trading System — Terminal Dashboard."""

    TITLE = "ATHENA"
    SUB_TITLE = "Trading Intelligence"
    CSS = CSS

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("a", "focus_agents", "Agents"),
        Binding("p", "focus_portfolio", "Portfolio"),
        Binding("s", "focus_signals", "Signals"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-area"):
            with Vertical(id="left-col"):
                yield AgentsPanel(id="agents-panel", classes="panel")
                yield SystemPanel(id="system-panel", classes="panel")
            with Vertical(id="right-col"):
                yield PortfolioPanel(id="portfolio-panel", classes="panel")
                yield SignalsPanel(id="signals-panel", classes="panel")
                yield ThesesPanel(id="theses-panel", classes="panel")
        yield EventsPanel(id="events-panel")
        yield Footer()

    def on_mount(self) -> None:
        """Start auto-refresh timer."""
        self.set_interval(30, self.refresh_panels)
        self.call_later(self.refresh_panels)

    def refresh_panels(self) -> None:
        """Refresh all panels."""
        for panel_id in (
            "#agents-panel", "#system-panel", "#portfolio-panel",
            "#signals-panel", "#theses-panel", "#events-panel",
        ):
            try:
                panel = self.query_one(panel_id)
                if hasattr(panel, "refresh_data"):
                    panel.refresh_data()
            except Exception:
                pass

    def action_refresh(self) -> None:
        """Manual refresh (r key)."""
        self.refresh_panels()
        self.notify("Refreshed all panels")

    def action_focus_agents(self) -> None:
        self.query_one("#agents-panel").focus()

    def action_focus_portfolio(self) -> None:
        self.query_one("#portfolio-panel").focus()

    def action_focus_signals(self) -> None:
        self.query_one("#signals-panel").focus()
