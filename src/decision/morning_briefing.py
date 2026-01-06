"""
Morning Briefing Generator for pre-market research.

Generates structured briefings combining:
- Overnight news and market events
- Pre-market price action
- Portfolio context
- Alternative data signals
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import json
import yaml

from src.core.paths import paths


@dataclass
class NewsItem:
    """A news item affecting the market or specific symbols."""
    headline: str
    source: str
    time: datetime
    symbols_affected: list[str]
    sentiment: str  # bullish, bearish, neutral
    importance: str  # high, medium, low
    summary: Optional[str] = None


@dataclass
class PreMarketData:
    """Pre-market market state."""
    sp500_futures_pct: float
    nasdaq_futures_pct: float
    vix: float
    major_movers: list[dict]  # [{symbol, change_pct, reason}]


@dataclass
class PortfolioExposure:
    """Current portfolio state for context."""
    total_equity: float
    cash: float
    sector_breakdown: dict[str, float]  # sector -> percentage
    positions_with_news: list[str]
    top_positions: list[dict]  # [{symbol, value, pct_of_portfolio}]


@dataclass
class AlternativeSignals:
    """Alternative data signals (expand as sources are added)."""
    congressional_trades: list[dict] = field(default_factory=list)
    prediction_markets: list[dict] = field(default_factory=list)
    inverse_cramer: list[dict] = field(default_factory=list)


@dataclass
class MorningBriefing:
    """Complete morning briefing for trading decisions."""
    date: str
    generated_at: datetime
    market_sentiment: str  # bullish, bearish, neutral, mixed

    overnight_news: list[NewsItem]
    pre_market: Optional[PreMarketData]
    portfolio_exposure: Optional[PortfolioExposure]
    alternative_signals: AlternativeSignals

    focus_areas: list[str]
    risk_warnings: list[str]

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "date": self.date,
            "generated_at": self.generated_at.isoformat(),
            "market_sentiment": self.market_sentiment,
            "overnight_news": [
                {
                    "headline": n.headline,
                    "source": n.source,
                    "time": n.time.isoformat(),
                    "symbols_affected": n.symbols_affected,
                    "sentiment": n.sentiment,
                    "importance": n.importance,
                    "summary": n.summary,
                }
                for n in self.overnight_news
            ],
            "pre_market": {
                "sp500_futures": f"{self.pre_market.sp500_futures_pct:+.1f}%",
                "nasdaq_futures": f"{self.pre_market.nasdaq_futures_pct:+.1f}%",
                "vix": self.pre_market.vix,
                "major_movers": self.pre_market.major_movers,
            } if self.pre_market else None,
            "portfolio_exposure": {
                "total_equity": self.portfolio_exposure.total_equity,
                "cash": self.portfolio_exposure.cash,
                "sector_breakdown": self.portfolio_exposure.sector_breakdown,
                "positions_with_news": self.portfolio_exposure.positions_with_news,
                "top_positions": self.portfolio_exposure.top_positions,
            } if self.portfolio_exposure else None,
            "alternative_signals": {
                "congressional_trades": self.alternative_signals.congressional_trades,
                "prediction_markets": self.alternative_signals.prediction_markets,
                "inverse_cramer": self.alternative_signals.inverse_cramer,
            },
            "focus_areas": self.focus_areas,
            "risk_warnings": self.risk_warnings,
        }

    def save(self, output_dir: str | Path | None = None) -> Path:
        """Save briefing to JSON file."""
        output_path = Path(output_dir) if output_dir else paths.briefings
        output_path.mkdir(parents=True, exist_ok=True)

        filename = f"briefing_{self.date}.json"
        filepath = output_path / filename

        with open(filepath, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

        return filepath

    def to_markdown(self) -> str:
        """Generate markdown summary for display."""
        lines = [
            f"# Morning Briefing - {self.date}",
            f"*Generated: {self.generated_at.strftime('%H:%M ET')}*",
            "",
            f"## Market Sentiment: {self.market_sentiment.upper()}",
            "",
        ]

        # Pre-market section
        if self.pre_market:
            lines.extend([
                "## Pre-Market Overview",
                f"- S&P 500 Futures: {self.pre_market.sp500_futures_pct:+.1f}%",
                f"- Nasdaq Futures: {self.pre_market.nasdaq_futures_pct:+.1f}%",
                f"- VIX: {self.pre_market.vix:.1f}",
                "",
            ])

            if self.pre_market.major_movers:
                lines.append("### Major Movers")
                for mover in self.pre_market.major_movers[:5]:
                    lines.append(f"- **{mover['symbol']}**: {mover['change_pct']} - {mover.get('reason', 'N/A')}")
                lines.append("")

        # Overnight news
        if self.overnight_news:
            lines.extend([
                "## Overnight News",
                "",
            ])
            for news in self.overnight_news[:5]:
                importance_icon = "!!" if news.importance == "high" else "!"
                lines.append(f"- [{importance_icon}] **{news.headline}** ({news.source})")
                if news.symbols_affected:
                    lines.append(f"  - Affects: {', '.join(news.symbols_affected)}")
                if news.summary:
                    lines.append(f"  - {news.summary}")
            lines.append("")

        # Portfolio context
        if self.portfolio_exposure:
            lines.extend([
                "## Portfolio Context",
                f"- Total Equity: ${self.portfolio_exposure.total_equity:,.2f}",
                f"- Cash: ${self.portfolio_exposure.cash:,.2f}",
                "",
            ])

            if self.portfolio_exposure.sector_breakdown:
                lines.append("### Sector Exposure")
                for sector, pct in sorted(self.portfolio_exposure.sector_breakdown.items(),
                                          key=lambda x: x[1], reverse=True):
                    lines.append(f"- {sector}: {pct:.1f}%")
                lines.append("")

            if self.portfolio_exposure.positions_with_news:
                lines.append(f"### Positions With News: {', '.join(self.portfolio_exposure.positions_with_news)}")
                lines.append("")

        # Alternative signals
        if any([self.alternative_signals.congressional_trades,
                self.alternative_signals.prediction_markets,
                self.alternative_signals.inverse_cramer]):
            lines.append("## Alternative Signals")

            if self.alternative_signals.congressional_trades:
                lines.append("### Congressional Trades")
                for trade in self.alternative_signals.congressional_trades[:3]:
                    lines.append(f"- {trade}")

            if self.alternative_signals.prediction_markets:
                lines.append("### Prediction Market Shifts")
                for pm in self.alternative_signals.prediction_markets[:3]:
                    lines.append(f"- {pm}")

            if self.alternative_signals.inverse_cramer:
                lines.append("### Inverse Cramer Signals")
                for sig in self.alternative_signals.inverse_cramer[:3]:
                    lines.append(f"- {sig}")

            lines.append("")

        # Focus areas
        if self.focus_areas:
            lines.extend([
                "## Today's Focus",
                "",
            ])
            for focus in self.focus_areas:
                lines.append(f"1. {focus}")
            lines.append("")

        # Risk warnings
        if self.risk_warnings:
            lines.extend([
                "## Risk Warnings",
                "",
            ])
            for warning in self.risk_warnings:
                lines.append(f"- {warning}")
            lines.append("")

        return "\n".join(lines)


class MorningBriefingGenerator:
    """
    Generates morning briefings by aggregating multiple data sources.

    Note: This class provides structure and utilities. The actual research
    is done by Claude Code using web search and the skill prompt.
    """

    def __init__(
        self,
        credentials_path: str = "/home/nock/projects/quant_suite/config/credentials.yaml",
        output_dir: str | Path | None = None,
    ):
        self.credentials_path = Path(credentials_path)
        self.output_dir = Path(output_dir) if output_dir else paths.briefings
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def get_portfolio_state(self) -> Optional[PortfolioExposure]:
        """Fetch current portfolio state from Alpaca."""
        try:
            from alpaca.trading.client import TradingClient

            with open(self.credentials_path) as f:
                creds = yaml.safe_load(f)

            client = TradingClient(
                creds["alpaca"]["api_key"],
                creds["alpaca"]["secret_key"],
                paper=True,
            )

            account = client.get_account()
            positions = client.get_all_positions()

            # Calculate sector breakdown (simplified)
            sector_map = {
                "SLB": "energy", "HAL": "energy", "XLE": "energy", "VLO": "energy",
                "OIH": "energy", "PSX": "energy", "MPC": "energy", "BKR": "energy",
                "NVDA": "tech", "AMD": "tech", "AAPL": "tech", "MSFT": "tech",
                "QQQ": "tech", "SPY": "broad", "IWM": "small_cap",
                "GLD": "commodities", "GDX": "commodities",
            }

            total_value = float(account.equity)
            sector_values = {}
            top_positions = []

            for pos in positions:
                symbol = pos.symbol[:10] if len(pos.symbol) > 10 else pos.symbol  # Trim options
                value = float(pos.market_value)
                pct = (value / total_value) * 100

                sector = sector_map.get(symbol, "other")
                sector_values[sector] = sector_values.get(sector, 0) + pct

                if len(pos.symbol) <= 10:  # Only stocks
                    top_positions.append({
                        "symbol": symbol,
                        "value": value,
                        "pct_of_portfolio": pct,
                    })

            top_positions.sort(key=lambda x: x["pct_of_portfolio"], reverse=True)

            return PortfolioExposure(
                total_equity=total_value,
                cash=float(account.cash),
                sector_breakdown=sector_values,
                positions_with_news=[],  # Populated by Claude during research
                top_positions=top_positions[:10],
            )

        except Exception as e:
            print(f"Error fetching portfolio: {e}")
            return None

    async def generate(
        self,
        overnight_news: Optional[list[NewsItem]] = None,
        pre_market: Optional[PreMarketData] = None,
        focus_areas: Optional[list[str]] = None,
        risk_warnings: Optional[list[str]] = None,
    ) -> MorningBriefing:
        """
        Generate a morning briefing.

        Note: News and pre-market data should be provided by Claude Code
        after web research. This method structures the data.
        """
        today = datetime.now().strftime("%Y-%m-%d")

        # Get portfolio state
        portfolio = await self.get_portfolio_state()

        # Determine market sentiment based on inputs
        sentiment = "neutral"
        if pre_market:
            if pre_market.sp500_futures_pct > 0.5:
                sentiment = "bullish"
            elif pre_market.sp500_futures_pct < -0.5:
                sentiment = "bearish"
            elif pre_market.vix > 20:
                sentiment = "fearful"

        return MorningBriefing(
            date=today,
            generated_at=datetime.now(),
            market_sentiment=sentiment,
            overnight_news=overnight_news or [],
            pre_market=pre_market,
            portfolio_exposure=portfolio,
            alternative_signals=AlternativeSignals(),
            focus_areas=focus_areas or [],
            risk_warnings=risk_warnings or [],
        )

    @staticmethod
    def load_briefing(date: str, briefings_dir: str | Path | None = None) -> Optional[dict]:
        """Load a saved briefing by date."""
        filepath = (Path(briefings_dir) if briefings_dir else paths.briefings) / f"briefing_{date}.json"
        if filepath.exists():
            with open(filepath) as f:
                return json.load(f)
        return None

    @staticmethod
    def get_latest_briefing(briefings_dir: str | Path | None = None) -> Optional[dict]:
        """Get the most recent briefing."""
        briefings_path = Path(briefings_dir) if briefings_dir else paths.briefings
        if not briefings_path.exists():
            return None

        files = sorted(briefings_path.glob("briefing_*.json"), reverse=True)
        if files:
            with open(files[0]) as f:
                return json.load(f)
        return None
