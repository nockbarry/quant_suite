"""Centralized path configuration for quant_suite.

All output directories should be accessed through this module to enable
portability and custom output locations via environment variable.

Usage:
    from src.core.paths import paths

    # Access directories
    briefings_dir = paths.briefings
    decisions_dir = paths.decisions

    # Or with custom base
    from src.core.paths import PathConfig
    custom_paths = PathConfig("/data/trading/results")

Environment Variable:
    QUANT_RESULTS_DIR - Override default ~/quant_results location
"""

import os
from pathlib import Path
from typing import Optional


# Environment variable for custom results location
RESULTS_BASE = os.environ.get(
    "QUANT_RESULTS_DIR",
    str(Path.home() / "quant_results")
)


class PathConfig:
    """Centralized output path configuration.

    Provides property-based access to all output directories,
    creating them on first access if they don't exist.
    """

    def __init__(self, base_dir: Optional[str] = None):
        """Initialize path configuration.

        Args:
            base_dir: Base directory for all outputs.
                     Defaults to QUANT_RESULTS_DIR env var or ~/quant_results
        """
        self.base = Path(base_dir or RESULTS_BASE)
        self._ensure_base()

    def _ensure_base(self) -> None:
        """Ensure base directory exists."""
        self.base.mkdir(parents=True, exist_ok=True)

    def _ensure_dir(self, path: Path) -> Path:
        """Ensure directory exists and return it."""
        path.mkdir(parents=True, exist_ok=True)
        return path

    # === Core Directories ===

    @property
    def briefings(self) -> Path:
        """Morning briefings and daily summaries."""
        return self._ensure_dir(self.base / "briefings")

    @property
    def decisions(self) -> Path:
        """Trading decision logs with reasoning."""
        return self._ensure_dir(self.base / "decisions")

    @property
    def trades(self) -> Path:
        """Trade execution records."""
        return self._ensure_dir(self.base / "trades")

    @property
    def trading_logs(self) -> Path:
        """Detailed trading session logs."""
        return self._ensure_dir(self.base / "trading_logs")

    # === Research Directories ===

    @property
    def research(self) -> Path:
        """Research base directory."""
        return self._ensure_dir(self.base / "research")

    @property
    def comprehensive_research(self) -> Path:
        """Full research cycle outputs."""
        return self._ensure_dir(self.base / "comprehensive_research")

    @property
    def research_sessions(self) -> Path:
        """Text research session data."""
        return self._ensure_dir(self.base / "research_sessions")

    @property
    def research_cycles(self) -> Path:
        """Research cycle tracking."""
        return self._ensure_dir(self.base / "research_cycles")

    @property
    def research_reports(self) -> Path:
        """Research analysis reports."""
        return self._ensure_dir(self.base / "research_reports")

    @property
    def strategy_reports(self) -> Path:
        """Strategy documentation and reports."""
        return self._ensure_dir(self.base / "strategy_reports")

    @property
    def research_tracker(self) -> Path:
        """Research progress tracking."""
        return self._ensure_dir(self.base / "research_tracker")

    # === Alpha Discovery ===

    @property
    def alpha_discovery(self) -> Path:
        """Alpha discovery scan results."""
        return self._ensure_dir(self.base / "alpha_discovery")

    @property
    def alpha_hunt(self) -> Path:
        """Alpha hunting session outputs."""
        return self._ensure_dir(self.base / "alpha_hunt")

    @property
    def macro_research(self) -> Path:
        """Macro and geopolitical research."""
        return self._ensure_dir(self.base / "macro_research")

    @property
    def regime_reports(self) -> Path:
        """Market regime analysis reports."""
        return self._ensure_dir(self.base / "regime_reports")

    # === Validation ===

    @property
    def validation_reports(self) -> Path:
        """Strategy validation reports."""
        return self._ensure_dir(self.base / "validation_reports")

    @property
    def critic_reports(self) -> Path:
        """Critic agent safety validation."""
        return self._ensure_dir(self.base / "critic_reports")

    @property
    def options_validation(self) -> Path:
        """Options strategy validation."""
        return self._ensure_dir(self.base / "options_validation")

    @property
    def options_backtest(self) -> Path:
        """Options backtest results."""
        return self._ensure_dir(self.base / "options_backtest")

    @property
    def options_strategies(self) -> Path:
        """Options strategy outputs."""
        return self._ensure_dir(self.base / "options_strategies")

    @property
    def options_analysis(self) -> Path:
        """Options analysis (IV, Greeks)."""
        return self._ensure_dir(self.base / "options_analysis")

    @property
    def institutional_flow(self) -> Path:
        """Institutional flow analysis."""
        return self._ensure_dir(self.base / "institutional_flow")

    # === Visualization ===

    @property
    def plots(self) -> Path:
        """Strategy and analysis plots."""
        return self._ensure_dir(self.base / "plots")

    @property
    def visualizations(self) -> Path:
        """General visualizations (legacy, prefer plots)."""
        return self._ensure_dir(self.base / "visualizations")

    # === Production ===

    @property
    def promotions(self) -> Path:
        """Strategy promotion records."""
        return self._ensure_dir(self.base / "promotions")

    @property
    def paper_trading(self) -> Path:
        """Paper trading outputs."""
        return self._ensure_dir(self.base / "paper_trading")

    @property
    def pdt(self) -> Path:
        """PDT compliance tracking."""
        return self._ensure_dir(self.base / "pdt")

    @property
    def performance_reports(self) -> Path:
        """Performance analytics."""
        return self._ensure_dir(self.base / "performance_reports")

    # === Text Research ===

    @property
    def text_corpus(self) -> Path:
        """Text research corpus storage."""
        return self._ensure_dir(self.base / "text_corpus")

    @property
    def embeddings_cache(self) -> Path:
        """Embedding vectors cache."""
        return self._ensure_dir(self.base / "embeddings_cache")

    # === Data ===

    @property
    def scraped_data(self) -> Path:
        """Scraped alternative data."""
        return self._ensure_dir(self.base / "scraped_data")

    @property
    def minute_data(self) -> Path:
        """Cached minute-level price data."""
        return self._ensure_dir(self.base / "minute_data")

    @property
    def daily_data(self) -> Path:
        """Cached daily price data."""
        return self._ensure_dir(self.base / "daily_data")

    # === Sessions & Experiments ===

    @property
    def sessions(self) -> Path:
        """Session-based research data."""
        return self._ensure_dir(self.base / "sessions")

    @property
    def experiments(self) -> Path:
        """Experimental strategy tests."""
        return self._ensure_dir(self.base / "experiments")

    @property
    def agent_runs(self) -> Path:
        """Agent execution logs."""
        return self._ensure_dir(self.base / "agent_runs")

    # === Daily Operations ===

    @property
    def daily_reports(self) -> Path:
        """Daily operation reports."""
        return self._ensure_dir(self.base / "daily_reports")

    @property
    def daily_reviews(self) -> Path:
        """Daily review summaries."""
        return self._ensure_dir(self.base / "daily_reviews")

    @property
    def daily_runs(self) -> Path:
        """Daily signal generation runs."""
        return self._ensure_dir(self.base / "daily_runs")

    # === Scheduler & Operations ===

    @property
    def scheduler(self) -> Path:
        """Scheduler coordination files."""
        return self._ensure_dir(self.base / "scheduler")

    @property
    def logs(self) -> Path:
        """Application logs."""
        return self._ensure_dir(self.base / "logs")

    @property
    def intelligence(self) -> Path:
        """Intelligence and calibration data."""
        return self._ensure_dir(self.base / "intelligence")

    @property
    def suggestions(self) -> Path:
        """Thesis suggestions."""
        return self._ensure_dir(self.base / "suggestions")

    @property
    def social(self) -> Path:
        """Social sentiment data (WSB, Stocktwits)."""
        return self._ensure_dir(self.base / "social")

    @property
    def signal_provenance(self) -> Path:
        """Signal provenance tracking."""
        return self._ensure_dir(self.base / "signal_provenance")

    @property
    def signal_quality(self) -> Path:
        """Signal quality metrics."""
        return self._ensure_dir(self.base / "signal_quality")

    @property
    def full_research(self) -> Path:
        """Full research cycle outputs."""
        return self._ensure_dir(self.base / "full_research")

    @property
    def accounts(self) -> Path:
        """Trading account data."""
        return self._ensure_dir(self.base / "accounts")

    @property
    def war(self) -> Path:
        """War/geopolitical dashboard data."""
        return self._ensure_dir(self.base / "war")

    @property
    def parallel(self) -> Path:
        """Multi-instance parallel data."""
        return self._ensure_dir(self.base / "parallel")

    @property
    def risk_reports(self) -> Path:
        """Risk and stress test reports."""
        return self._ensure_dir(self.base / "risk_reports")

    @property
    def system_reviews(self) -> Path:
        """Weekly system review reports."""
        return self._ensure_dir(self.base / "system_reviews")

    @property
    def upgrades(self) -> Path:
        """Autonomous upgrade proposals and history."""
        return self._ensure_dir(self.base / "upgrades")

    # === Archive ===

    @property
    def archive(self) -> Path:
        """Archived historical data."""
        return self._ensure_dir(self.base / "archive")

    # === Live State (Unified State Engine) ===

    @property
    def live(self) -> Path:
        """Live state directory - THE source of truth."""
        return self._ensure_dir(self.base / "live")

    @property
    def live_state(self) -> Path:
        """Unified state JSON file."""
        return self.live / "state.json"

    @property
    def live_research(self) -> Path:
        """Pre-computed research files for quick access."""
        return self._ensure_dir(self.live / "research")

    # === Knowledge Base ===

    @property
    def theses(self) -> Path:
        """Investment thesis tracking."""
        return self._ensure_dir(self.base / "theses")

    @property
    def learnings(self) -> Path:
        """Trade learnings and patterns."""
        return self._ensure_dir(self.base / "learnings")

    @property
    def knowledge(self) -> Path:
        """Persistent knowledge base."""
        return self._ensure_dir(self.base / "knowledge")

    @property
    def knowledge_companies(self) -> Path:
        """Company briefs."""
        return self._ensure_dir(self.knowledge / "companies")

    @property
    def knowledge_sectors(self) -> Path:
        """Sector context."""
        return self._ensure_dir(self.knowledge / "sectors")

    # === Real-Time Data ===

    @property
    def realtime(self) -> Path:
        """Real-time data base directory."""
        return self._ensure_dir(self.base / "realtime")

    @property
    def realtime_news(self) -> Path:
        """Live news updates."""
        return self._ensure_dir(self.realtime / "news")

    @property
    def realtime_technicals(self) -> Path:
        """Intraday technical snapshots."""
        return self._ensure_dir(self.realtime / "technicals")

    @property
    def realtime_alerts(self) -> Path:
        """Alert history and state."""
        return self._ensure_dir(self.realtime / "alerts")

    @property
    def realtime_breadth(self) -> Path:
        """Market breadth snapshots."""
        return self._ensure_dir(self.realtime / "breadth")

    @property
    def realtime_sentiment(self) -> Path:
        """Sentiment indicator snapshots."""
        return self._ensure_dir(self.realtime / "sentiment")

    @property
    def realtime_open_assessments(self) -> Path:
        """Morning open assessments."""
        return self._ensure_dir(self.realtime / "open_assessments")

    # === Helpers ===

    def dated_file(self, directory: Path, prefix: str, ext: str = "json") -> Path:
        """Generate a dated filename in a directory.

        Args:
            directory: Target directory
            prefix: Filename prefix (e.g., "briefing", "decisions")
            ext: File extension without dot

        Returns:
            Path like directory/prefix_2026-01-06.ext
        """
        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d")
        return directory / f"{prefix}_{date_str}.{ext}"

    def timestamped_file(self, directory: Path, prefix: str, ext: str = "json") -> Path:
        """Generate a timestamped filename in a directory.

        Args:
            directory: Target directory
            prefix: Filename prefix
            ext: File extension without dot

        Returns:
            Path like directory/prefix_2026-01-06_143022.ext
        """
        from datetime import datetime
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        return directory / f"{prefix}_{ts}.{ext}"

    def __repr__(self) -> str:
        return f"PathConfig(base='{self.base}')"


# Global instance for convenient imports
paths = PathConfig()
