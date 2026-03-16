"""Data Scout Agent - Autonomous data source discovery.

Discovers and evaluates potential alternative data sources for trading.
Requires human approval before integrating new data sources.

Features:
- Web search for alternative data sources
- Data quality assessment
- Alpha potential evaluation
- Integration proposal generation
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

import pandas as pd

from ..core import Symbol
from .base import (
    Agent,
    AgentCapabilities,
    AgentConfig,
    AgentMessage,
    AgentRole,
    AgentStatus,
    MessageType,
)

logger = logging.getLogger(__name__)


class DataSourceType(str, Enum):
    """Types of data sources."""

    API = "api"
    RSS_FEED = "rss_feed"
    WEB_SCRAPE = "web_scrape"
    DATABASE = "database"
    FILE = "file"
    STREAMING = "streaming"


class ApprovalStatus(str, Enum):
    """Approval status for discovered data sources."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEFERRED = "deferred"


@dataclass
class DataSourceProposal:
    """Proposal for a discovered data source."""

    proposal_id: str
    name: str
    source_type: DataSourceType
    url: str | None = None
    description: str = ""

    # Evaluation metrics
    estimated_alpha_potential: float = 0.0  # 0-1
    data_quality_score: float = 0.0  # 0-1
    latency_estimate: str = ""  # e.g., "real-time", "daily", "weekly"
    cost_estimate: str = ""  # e.g., "free", "$X/month"

    # Technical details
    update_frequency: str = ""
    historical_depth: str = ""
    symbols_covered: list[Symbol] = field(default_factory=list)
    required_credentials: bool = False

    # Approval workflow
    status: ApprovalStatus = ApprovalStatus.PENDING
    discovered_at: datetime = field(default_factory=datetime.now)
    reviewed_at: datetime | None = None
    reviewer_notes: str = ""

    # LLM reasoning
    discovery_reasoning: str = ""
    alpha_reasoning: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "proposal_id": self.proposal_id,
            "name": self.name,
            "source_type": self.source_type.value,
            "url": self.url,
            "description": self.description,
            "estimated_alpha_potential": self.estimated_alpha_potential,
            "data_quality_score": self.data_quality_score,
            "latency_estimate": self.latency_estimate,
            "cost_estimate": self.cost_estimate,
            "update_frequency": self.update_frequency,
            "historical_depth": self.historical_depth,
            "symbols_covered": self.symbols_covered,
            "required_credentials": self.required_credentials,
            "status": self.status.value,
            "discovered_at": self.discovered_at.isoformat(),
            "discovery_reasoning": self.discovery_reasoning,
            "alpha_reasoning": self.alpha_reasoning,
        }


@dataclass
class ScoutConfig(AgentConfig):
    """Configuration for data scout agent."""

    # Search settings
    search_queries: list[str] = field(default_factory=lambda: [
        "alternative data trading",
        "financial data API",
        "sentiment data finance",
        "options flow data",
        "insider trading data",
    ])
    max_proposals_per_run: int = 5
    min_alpha_potential: float = 0.3  # Minimum to propose

    # Approval settings
    require_approval: bool = False  # Fully autonomous
    auto_approve_threshold: float = 0.0  # Auto-approve all proposals

    # LLM settings
    use_llm_evaluation: bool = True
    llm_model: str = "claude-sonnet-4-20250514"

    def __post_init__(self):
        if self.role is None:
            self.role = AgentRole.DATA_SCOUT


class DataScoutAgent(Agent):
    """
    Agent for discovering alternative data sources.

    Searches for potential data sources, evaluates them, and
    proposes them for human approval before integration.

    This agent doesn't generate trading signals directly - it
    helps expand the data infrastructure.
    """

    name: str = "data_scout"
    description: str = "Discovers alternative data sources for trading"

    def __init__(
        self,
        config: ScoutConfig | None = None,
        on_proposal: Callable[[DataSourceProposal], None] | None = None,
        **kwargs: Any,
    ):
        """
        Initialize data scout agent.

        Args:
            config: Scout configuration
            on_proposal: Callback when new proposal is ready
            **kwargs: Additional parameters
        """
        config = config or ScoutConfig(name="data_scout")
        super().__init__(config=config, **kwargs)

        self._scout_config: ScoutConfig = config  # type: ignore
        self._proposals: dict[str, DataSourceProposal] = {}
        self._on_proposal = on_proposal

        # Known data sources (to avoid duplicates)
        self._known_sources: set[str] = set()

        # LLM client for evaluation
        self._llm_client = None

    def _define_capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            can_discover_data=True,
            can_analyze=True,
            requires_approval=True,
            supports_async=True,
        )

    async def run(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame] | None = None,
        context: dict[str, Any] | None = None,
    ) -> list:
        """
        Execute data discovery.

        Args:
            data: Not used by this agent
            context: Optional context with search parameters

        Returns:
            List of proposals (empty for this agent type)
        """
        try:
            self.state.status = AgentStatus.RUNNING

            # Get search queries
            queries = self._scout_config.search_queries
            if context and "queries" in context:
                queries = context["queries"]

            # Search for data sources
            discovered = await self._search_for_sources(queries)

            # Evaluate and filter
            proposals = []
            for source_info in discovered:
                if self._is_known_source(source_info):
                    continue

                proposal = await self._evaluate_source(source_info)

                if proposal.estimated_alpha_potential >= self._scout_config.min_alpha_potential:
                    proposals.append(proposal)
                    self._proposals[proposal.proposal_id] = proposal

                    # Notify via callback
                    if self._on_proposal:
                        self._on_proposal(proposal)

                    # Send message
                    await self.send_message(AgentMessage(
                        message_type=MessageType.DATA,
                        payload={
                            "type": "data_source_proposal",
                            "proposal": proposal.to_dict(),
                        },
                    ))

                if len(proposals) >= self._scout_config.max_proposals_per_run:
                    break

            self.state.record_run()
            logger.info(f"Data scout found {len(proposals)} proposals")

            return []  # Data scout doesn't return signals

        except Exception as e:
            self.state.record_error(str(e))
            logger.error(f"Data scout error: {e}")
            return []

        finally:
            self.state.status = AgentStatus.IDLE

    async def _search_for_sources(
        self,
        queries: list[str],
    ) -> list[dict[str, Any]]:
        """
        Search for potential data sources.

        This is a simplified implementation. In production, this would
        integrate with web search APIs or use the LLM for discovery.
        """
        discovered = []

        # Predefined data source templates for demonstration
        templates = [
            {
                "name": "Unusual Whales Options Flow",
                "source_type": DataSourceType.API,
                "url": "https://unusualwhales.com",
                "description": "Options flow and unusual activity data",
                "update_frequency": "real-time",
                "cost_estimate": "$99/month",
            },
            {
                "name": "Quiver Quantitative",
                "source_type": DataSourceType.API,
                "url": "https://www.quiverquant.com",
                "description": "Alternative data including Congress trades, lobbying, government contracts",
                "update_frequency": "daily",
                "cost_estimate": "free tier available",
            },
            {
                "name": "Alternative.me Fear & Greed Index",
                "source_type": DataSourceType.API,
                "url": "https://alternative.me/crypto/fear-and-greed-index/",
                "description": "Crypto market sentiment indicator",
                "update_frequency": "daily",
                "cost_estimate": "free",
            },
            {
                "name": "Finviz Stock Screener",
                "source_type": DataSourceType.WEB_SCRAPE,
                "url": "https://finviz.com",
                "description": "Stock screener with technical and fundamental data",
                "update_frequency": "real-time",
                "cost_estimate": "free (basic)",
            },
            {
                "name": "SEC EDGAR Filings",
                "source_type": DataSourceType.API,
                "url": "https://www.sec.gov/cgi-bin/browse-edgar",
                "description": "SEC filings including 13F, 10K, 8K",
                "update_frequency": "as filed",
                "cost_estimate": "free",
            },
            {
                "name": "FRED Economic Data",
                "source_type": DataSourceType.API,
                "url": "https://fred.stlouisfed.org",
                "description": "Federal Reserve economic data",
                "update_frequency": "varies by series",
                "cost_estimate": "free",
            },
            {
                "name": "Stocktwits Social Sentiment",
                "source_type": DataSourceType.API,
                "url": "https://stocktwits.com",
                "description": "Social media sentiment from traders",
                "update_frequency": "real-time",
                "cost_estimate": "free tier available",
            },
            {
                "name": "Satellite Imagery (Planet Labs)",
                "source_type": DataSourceType.API,
                "url": "https://www.planet.com",
                "description": "Satellite imagery for supply chain analysis",
                "update_frequency": "daily",
                "cost_estimate": "enterprise pricing",
            },
        ]

        # Filter based on queries (simple keyword matching)
        for template in templates:
            for query in queries:
                keywords = query.lower().split()
                text = f"{template['name']} {template['description']}".lower()

                if any(kw in text for kw in keywords):
                    discovered.append(template)
                    break

        return discovered

    def _is_known_source(self, source_info: dict[str, Any]) -> bool:
        """Check if source is already known."""
        name = source_info.get("name", "")
        url = source_info.get("url", "")

        key = f"{name}:{url}"
        if key in self._known_sources:
            return True

        self._known_sources.add(key)
        return False

    async def _evaluate_source(
        self,
        source_info: dict[str, Any],
    ) -> DataSourceProposal:
        """Evaluate a potential data source."""
        from uuid import uuid4

        proposal_id = str(uuid4())

        # Basic evaluation (heuristic-based)
        alpha_potential = self._estimate_alpha_potential(source_info)
        quality_score = self._estimate_quality(source_info)

        # Use LLM for detailed evaluation if enabled
        discovery_reasoning = ""
        alpha_reasoning = ""

        if self._scout_config.use_llm_evaluation:
            try:
                llm_eval = await self._llm_evaluate(source_info)
                alpha_potential = llm_eval.get("alpha_potential", alpha_potential)
                quality_score = llm_eval.get("quality_score", quality_score)
                discovery_reasoning = llm_eval.get("discovery_reasoning", "")
                alpha_reasoning = llm_eval.get("alpha_reasoning", "")
            except Exception as e:
                logger.warning(f"LLM evaluation failed: {e}")

        return DataSourceProposal(
            proposal_id=proposal_id,
            name=source_info.get("name", "Unknown"),
            source_type=source_info.get("source_type", DataSourceType.API),
            url=source_info.get("url"),
            description=source_info.get("description", ""),
            estimated_alpha_potential=alpha_potential,
            data_quality_score=quality_score,
            latency_estimate=source_info.get("update_frequency", "unknown"),
            cost_estimate=source_info.get("cost_estimate", "unknown"),
            update_frequency=source_info.get("update_frequency", ""),
            discovery_reasoning=discovery_reasoning,
            alpha_reasoning=alpha_reasoning,
        )

    def _estimate_alpha_potential(self, source_info: dict[str, Any]) -> float:
        """Heuristic estimate of alpha potential."""
        score = 0.5  # Base score

        description = source_info.get("description", "").lower()
        name = source_info.get("name", "").lower()
        text = f"{name} {description}"

        # High alpha keywords
        high_alpha = ["sentiment", "flow", "insider", "unusual", "alternative", "satellite"]
        for kw in high_alpha:
            if kw in text:
                score += 0.1

        # Medium alpha keywords
        medium_alpha = ["options", "congress", "lobbying", "social"]
        for kw in medium_alpha:
            if kw in text:
                score += 0.05

        # Real-time data bonus
        if source_info.get("update_frequency") == "real-time":
            score += 0.1

        return min(1.0, score)

    def _estimate_quality(self, source_info: dict[str, Any]) -> float:
        """Heuristic estimate of data quality."""
        score = 0.5

        # API is generally higher quality than scraping
        source_type = source_info.get("source_type")
        if source_type == DataSourceType.API:
            score += 0.2
        elif source_type == DataSourceType.WEB_SCRAPE:
            score -= 0.1

        # Free sources may have lower quality
        cost = source_info.get("cost_estimate", "").lower()
        if "free" in cost:
            score -= 0.05
        elif "enterprise" in cost:
            score += 0.1

        return max(0.0, min(1.0, score))

    async def _llm_evaluate(
        self,
        source_info: dict[str, Any],
    ) -> dict[str, Any]:
        """Use LLM to evaluate data source."""

        # Lazy import to avoid dependency issues
        try:
            from .llm_agent import ClaudeClient, ANTHROPIC_AVAILABLE
            if not ANTHROPIC_AVAILABLE:
                return {}
        except ImportError:
            return {}

        if self._llm_client is None:
            try:
                self._llm_client = ClaudeClient(
                    model=self._scout_config.llm_model,
                    max_tokens=1024,
                    temperature=0.3,
                )
            except Exception:
                return {}

        prompt = f"""Evaluate this data source for quantitative trading:

Name: {source_info.get('name')}
Type: {source_info.get('source_type')}
URL: {source_info.get('url')}
Description: {source_info.get('description')}
Update Frequency: {source_info.get('update_frequency')}
Cost: {source_info.get('cost_estimate')}

Provide evaluation as JSON:
{{
    "alpha_potential": <0-1, likelihood of generating alpha>,
    "quality_score": <0-1, data quality assessment>,
    "discovery_reasoning": "<why this source was selected>",
    "alpha_reasoning": "<how this could generate alpha>",
    "risks": ["risk1", "risk2"],
    "recommended_use_cases": ["use1", "use2"]
}}"""

        try:
            result = await self._llm_client.generate_json(prompt)
            return result
        except Exception as e:
            logger.warning(f"LLM evaluation failed: {e}")
            return {}

    # Approval workflow methods

    def get_pending_proposals(self) -> list[DataSourceProposal]:
        """Get all pending proposals."""
        return [
            p for p in self._proposals.values()
            if p.status == ApprovalStatus.PENDING
        ]

    def approve_proposal(
        self,
        proposal_id: str,
        reviewer_notes: str = "",
    ) -> bool:
        """Approve a proposal."""
        if proposal_id not in self._proposals:
            return False

        proposal = self._proposals[proposal_id]
        proposal.status = ApprovalStatus.APPROVED
        proposal.reviewed_at = datetime.now()
        proposal.reviewer_notes = reviewer_notes

        logger.info(f"Approved proposal: {proposal.name}")
        return True

    def reject_proposal(
        self,
        proposal_id: str,
        reviewer_notes: str = "",
    ) -> bool:
        """Reject a proposal."""
        if proposal_id not in self._proposals:
            return False

        proposal = self._proposals[proposal_id]
        proposal.status = ApprovalStatus.REJECTED
        proposal.reviewed_at = datetime.now()
        proposal.reviewer_notes = reviewer_notes

        logger.info(f"Rejected proposal: {proposal.name}")
        return True

    def defer_proposal(
        self,
        proposal_id: str,
        reviewer_notes: str = "",
    ) -> bool:
        """Defer a proposal for later review."""
        if proposal_id not in self._proposals:
            return False

        proposal = self._proposals[proposal_id]
        proposal.status = ApprovalStatus.DEFERRED
        proposal.reviewer_notes = reviewer_notes

        return True

    def get_approved_proposals(self) -> list[DataSourceProposal]:
        """Get all approved proposals."""
        return [
            p for p in self._proposals.values()
            if p.status == ApprovalStatus.APPROVED
        ]

    def generate_integration_code(
        self,
        proposal_id: str,
    ) -> str | None:
        """Generate integration code for an approved proposal."""
        if proposal_id not in self._proposals:
            return None

        proposal = self._proposals[proposal_id]
        if proposal.status != ApprovalStatus.APPROVED:
            return None

        # Generate template code based on source type
        if proposal.source_type == DataSourceType.API:
            return self._generate_api_template(proposal)
        elif proposal.source_type == DataSourceType.RSS_FEED:
            return self._generate_rss_template(proposal)
        elif proposal.source_type == DataSourceType.WEB_SCRAPE:
            return self._generate_scrape_template(proposal)
        else:
            return self._generate_generic_template(proposal)

    def _generate_api_template(self, proposal: DataSourceProposal) -> str:
        """Generate API integration template."""
        return f'''"""Integration for {proposal.name}

Auto-generated by DataScoutAgent
URL: {proposal.url}
"""

import aiohttp
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class {proposal.name.replace(" ", "")}Data:
    """Data from {proposal.name}."""
    timestamp: datetime
    data: dict[str, Any]


class {proposal.name.replace(" ", "")}Source:
    """Data source for {proposal.name}."""

    BASE_URL = "{proposal.url}"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def fetch(self, endpoint: str, params: dict | None = None) -> dict:
        """Fetch data from API."""
        session = await self._get_session()

        headers = {{}}
        if self.api_key:
            headers["Authorization"] = f"Bearer {{self.api_key}}"

        async with session.get(
            f"{{self.BASE_URL}}/{{endpoint}}",
            params=params,
            headers=headers,
        ) as response:
            response.raise_for_status()
            return await response.json()

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None
'''

    def _generate_rss_template(self, proposal: DataSourceProposal) -> str:
        """Generate RSS feed integration template."""
        return f'''"""RSS Feed Integration for {proposal.name}

Auto-generated by DataScoutAgent
URL: {proposal.url}
"""

import feedparser
from dataclasses import dataclass
from datetime import datetime


@dataclass
class FeedItem:
    title: str
    link: str
    published: datetime
    summary: str


class {proposal.name.replace(" ", "")}Feed:
    """RSS feed source for {proposal.name}."""

    FEED_URL = "{proposal.url}"

    def fetch_items(self, limit: int = 50) -> list[FeedItem]:
        """Fetch items from RSS feed."""
        feed = feedparser.parse(self.FEED_URL)

        items = []
        for entry in feed.entries[:limit]:
            items.append(FeedItem(
                title=entry.get("title", ""),
                link=entry.get("link", ""),
                published=datetime.now(),  # Parse from entry
                summary=entry.get("summary", ""),
            ))

        return items
'''

    def _generate_scrape_template(self, proposal: DataSourceProposal) -> str:
        """Generate web scrape template."""
        return f'''"""Web Scraper for {proposal.name}

Auto-generated by DataScoutAgent
URL: {proposal.url}

NOTE: Ensure scraping is allowed by the website's robots.txt and ToS.
"""

import aiohttp
from bs4 import BeautifulSoup
from dataclasses import dataclass
from datetime import datetime


class {proposal.name.replace(" ", "")}Scraper:
    """Web scraper for {proposal.name}."""

    BASE_URL = "{proposal.url}"

    def __init__(self):
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def fetch_page(self, url: str) -> str:
        """Fetch HTML content."""
        session = await self._get_session()
        async with session.get(url) as response:
            return await response.text()

    async def parse(self, html: str) -> dict:
        """Parse HTML content. Customize this method."""
        soup = BeautifulSoup(html, "html.parser")
        # Add custom parsing logic here
        return {{"raw_html": html[:1000]}}

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None
'''

    def _generate_generic_template(self, proposal: DataSourceProposal) -> str:
        """Generate generic template."""
        return f'''"""Data Source: {proposal.name}

Auto-generated by DataScoutAgent
URL: {proposal.url}
Type: {proposal.source_type.value}
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


class {proposal.name.replace(" ", "")}Source:
    """Data source for {proposal.name}."""

    def __init__(self):
        pass

    def fetch(self) -> dict[str, Any]:
        """Fetch data. Implement based on source type."""
        raise NotImplementedError("Implement data fetching logic")
'''
