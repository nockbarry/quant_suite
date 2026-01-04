"""
Session management for Claude Code analysis workflows.

Provides automatic artifact storage, session indexing, and result persistence.
All outputs are saved to ~/quant_results/ for easy viewing.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
import json
import hashlib

import pandas as pd


@dataclass
class SessionConfig:
    """Configuration for an analysis session."""

    name: str  # Descriptive name, e.g., "mcpt_momentum_tech"
    session_type: Literal["screen", "backtest", "mcpt", "full_analysis"]
    symbols: list[str] = field(default_factory=list)
    description: str = ""
    tags: list[str] = field(default_factory=list)

    # Output settings
    output_base: Path = field(default_factory=lambda: Path.home() / "quant_results")
    save_html: bool = True
    save_charts: bool = True
    save_data: bool = True


@dataclass
class SessionResult:
    """Container for completed session results."""

    session_id: str
    session_path: Path
    config: SessionConfig
    metrics: dict[str, Any]
    artifacts: list[str]  # List of saved file paths
    interpretation: str  # Claude's written analysis
    created_at: datetime
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            "session_id": self.session_id,
            "session_path": str(self.session_path),
            "config": {
                "name": self.config.name,
                "session_type": self.config.session_type,
                "symbols": self.config.symbols,
                "description": self.config.description,
                "tags": self.config.tags,
            },
            "metrics": self.metrics,
            "artifacts": self.artifacts,
            "interpretation": self.interpretation,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionResult":
        """Deserialize from dictionary."""
        config = SessionConfig(
            name=data["config"]["name"],
            session_type=data["config"]["session_type"],
            symbols=data["config"].get("symbols", []),
            description=data["config"].get("description", ""),
            tags=data["config"].get("tags", []),
        )
        return cls(
            session_id=data["session_id"],
            session_path=Path(data["session_path"]),
            config=config,
            metrics=data.get("metrics", {}),
            artifacts=data.get("artifacts", []),
            interpretation=data.get("interpretation", ""),
            created_at=datetime.fromisoformat(data["created_at"]),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
        )


class Session:
    """
    Active analysis session with artifact management.

    Provides methods for saving charts, data, and reports to persistent storage.

    Usage:
        session = SessionManager.create("momentum_scan", "screen", ["AAPL", "NVDA"])
        session.save_chart(fig, "equity_curve")
        session.save_data(df, "results")
        session.save_html_report(html_content)
        result = session.complete(metrics, interpretation)
    """

    def __init__(self, manager: "SessionManager", config: SessionConfig):
        self.manager = manager
        self.config = config
        self.session_id = manager._generate_session_id(config.name)
        self.session_path = manager.output_base / "sessions" / self.session_id
        self.created_at = datetime.now()
        self.artifacts: list[str] = []

        self._setup_session_directory()

    def _setup_session_directory(self) -> None:
        """Create session directory structure."""
        self.session_path.mkdir(parents=True, exist_ok=True)
        (self.session_path / "charts").mkdir(exist_ok=True)
        (self.session_path / "data").mkdir(exist_ok=True)

    def save_chart(
        self,
        fig,  # matplotlib.figure.Figure
        name: str,
        format: str = "png",
        dpi: int = 150,
    ) -> Path:
        """
        Save a matplotlib figure to the session.

        Args:
            fig: Matplotlib figure object
            name: Chart name (without extension)
            format: Image format (png, pdf, svg)
            dpi: Resolution for raster formats

        Returns:
            Path to the saved chart file
        """
        chart_path = self.session_path / "charts" / f"{name}.{format}"
        fig.savefig(chart_path, format=format, dpi=dpi, bbox_inches="tight")
        self.artifacts.append(str(chart_path))
        return chart_path

    def save_data(
        self,
        data: pd.DataFrame | dict[str, Any] | list,
        name: str,
        format: Literal["csv", "json", "parquet"] = "csv",
    ) -> Path:
        """
        Save data to the session.

        Args:
            data: DataFrame, dictionary, or list to save
            name: Data file name (without extension)
            format: Output format

        Returns:
            Path to the saved data file
        """
        data_path = self.session_path / "data" / f"{name}.{format}"

        if isinstance(data, pd.DataFrame):
            if format == "csv":
                data.to_csv(data_path, index=True)
            elif format == "json":
                data.to_json(data_path, orient="records", date_format="iso", indent=2)
            elif format == "parquet":
                data.to_parquet(data_path)
        else:
            # Dictionary or list
            with open(data_path, "w") as f:
                json.dump(data, f, indent=2, default=str)

        self.artifacts.append(str(data_path))
        return data_path

    def save_html_report(self, html_content: str) -> Path:
        """
        Save HTML report to the session.

        Args:
            html_content: HTML string

        Returns:
            Path to the saved report
        """
        report_path = self.session_path / "report.html"
        report_path.write_text(html_content)
        self.artifacts.append(str(report_path))
        return report_path

    def complete(
        self,
        metrics: dict[str, Any],
        interpretation: str,
    ) -> SessionResult:
        """
        Complete the session and save the index.

        This should be called when all analysis is done.

        Args:
            metrics: Summary metrics from the analysis
            interpretation: Claude's written interpretation of results

        Returns:
            SessionResult with all artifacts and metadata
        """
        result = SessionResult(
            session_id=self.session_id,
            session_path=self.session_path,
            config=self.config,
            metrics=metrics,
            artifacts=self.artifacts,
            interpretation=interpretation,
            created_at=self.created_at,
            completed_at=datetime.now(),
        )

        # Save session index.json
        index_path = self.session_path / "index.json"
        with open(index_path, "w") as f:
            json.dump(result.to_dict(), f, indent=2)

        # Save interpretation as markdown
        interp_path = self.session_path / "interpretation.md"
        interp_path.write_text(f"# Analysis Interpretation\n\n{interpretation}")

        # Update global sessions index
        self._update_global_index(result)

        return result

    def _update_global_index(self, result: SessionResult) -> None:
        """Update the global sessions index for easy lookup."""
        index_path = self.manager.output_base / "index" / "sessions.json"

        if index_path.exists():
            with open(index_path) as f:
                sessions = json.load(f)
        else:
            sessions = []

        # Add new session at the beginning
        sessions.insert(0, {
            "session_id": result.session_id,
            "name": result.config.name,
            "session_type": result.config.session_type,
            "symbols": result.config.symbols,
            "tags": result.config.tags,
            "created_at": result.created_at.isoformat(),
            "completed_at": result.completed_at.isoformat() if result.completed_at else None,
            "path": str(result.session_path),
            "metrics_summary": {
                k: v for k, v in result.metrics.items()
                if isinstance(v, (int, float, bool, str)) and k in [
                    "sharpe_ratio", "total_return", "p_value", "is_significant",
                    "stocks_screened", "stocks_passing"
                ]
            },
        })

        # Keep last 1000 sessions
        sessions = sessions[:1000]

        with open(index_path, "w") as f:
            json.dump(sessions, f, indent=2)


class SessionManager:
    """
    Manages analysis sessions with automatic artifact storage.

    The primary interface for Claude Code to create and manage sessions.

    Usage:
        # Create a new session
        session = SessionManager.create("mcpt_analysis", "mcpt", ["AAPL", "NVDA"])

        # Or use instance methods
        manager = SessionManager()
        sessions = manager.list_sessions(limit=10)
        old_session = manager.load_session("2026-01-02_mcpt_a1b2c3")
    """

    def __init__(self, output_base: Path | None = None):
        self.output_base = output_base or Path.home() / "quant_results"
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create output directory structure if needed."""
        (self.output_base / "sessions").mkdir(parents=True, exist_ok=True)
        (self.output_base / "index").mkdir(exist_ok=True)

    def _generate_session_id(self, name: str) -> str:
        """Generate a unique session ID."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        # Create short hash from name + timestamp for uniqueness
        hash_input = f"{name}{datetime.now().isoformat()}"
        hash_suffix = hashlib.md5(hash_input.encode()).hexdigest()[:6]
        # Clean name for filesystem
        clean_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)[:30]
        return f"{date_str}_{clean_name}_{hash_suffix}"

    @classmethod
    def create(
        cls,
        name: str,
        session_type: Literal["screen", "backtest", "mcpt", "full_analysis"],
        symbols: list[str] | None = None,
        description: str = "",
        tags: list[str] | None = None,
        **kwargs,
    ) -> Session:
        """
        Create a new analysis session.

        This is the main entry point for Claude Code to start a new analysis.

        Args:
            name: Descriptive session name (e.g., "momentum_tech_scan")
            session_type: Type of analysis
            symbols: List of symbols being analyzed
            description: Optional longer description
            tags: Optional tags for filtering
            **kwargs: Additional SessionConfig parameters

        Returns:
            Session instance ready for use

        Example:
            session = SessionManager.create(
                name="mcpt_sma_crossover",
                session_type="mcpt",
                symbols=["AAPL", "NVDA", "TSLA"],
                description="Testing SMA crossover significance"
            )
        """
        config = SessionConfig(
            name=name,
            session_type=session_type,
            symbols=symbols or [],
            description=description,
            tags=tags or [],
            **kwargs,
        )
        manager = cls(config.output_base)
        return Session(manager, config)

    def list_sessions(
        self,
        session_type: str | None = None,
        tag: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        List recent sessions.

        Args:
            session_type: Filter by session type
            tag: Filter by tag
            limit: Maximum number of sessions to return

        Returns:
            List of session summaries (newest first)
        """
        index_path = self.output_base / "index" / "sessions.json"
        if not index_path.exists():
            return []

        with open(index_path) as f:
            sessions = json.load(f)

        # Apply filters
        if session_type:
            sessions = [s for s in sessions if s.get("session_type") == session_type]
        if tag:
            sessions = [s for s in sessions if tag in s.get("tags", [])]

        return sessions[:limit]

    def load_session(self, session_id: str) -> SessionResult | None:
        """
        Load a previous session's results.

        Args:
            session_id: The session ID to load

        Returns:
            SessionResult if found, None otherwise
        """
        session_path = self.output_base / "sessions" / session_id
        index_path = session_path / "index.json"

        if not index_path.exists():
            return None

        with open(index_path) as f:
            data = json.load(f)

        return SessionResult.from_dict(data)

    def get_session_path(self, session_id: str) -> Path | None:
        """Get the path to a session's directory."""
        session_path = self.output_base / "sessions" / session_id
        return session_path if session_path.exists() else None


# Convenience functions for quick access

def create_session(
    name: str,
    session_type: Literal["screen", "backtest", "mcpt", "full_analysis"],
    symbols: list[str] | None = None,
    **kwargs,
) -> Session:
    """Quick session creation - main entry point for Claude Code."""
    return SessionManager.create(name, session_type, symbols, **kwargs)


def list_sessions(limit: int = 20, session_type: str | None = None) -> list[dict]:
    """List recent analysis sessions."""
    manager = SessionManager()
    return manager.list_sessions(session_type=session_type, limit=limit)


def load_session(session_id: str) -> SessionResult | None:
    """Load a previous session's results."""
    manager = SessionManager()
    return manager.load_session(session_id)


def get_results_dir() -> Path:
    """Get the path to the results directory."""
    return Path.home() / "quant_results"
