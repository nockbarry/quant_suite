"""LLM Agent - Claude API integration for trading analysis.

Provides LLM-powered agents for:
- Market analysis and interpretation
- News sentiment analysis
- Signal generation with reasoning
- Strategy suggestions
- Data source evaluation
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import pandas as pd

from ..core import Direction, Signal, SignalType, Symbol
from .base import (
    Agent,
    AgentCapabilities,
    AgentConfig,
    AgentMessage,
    AgentRole,
    AnalystAgent,
    MessageType,
    SignalGeneratorAgent,
)

logger = logging.getLogger(__name__)


# Check for anthropic library
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logger.warning("anthropic library not installed. Install with: pip install anthropic")


class LLMModel(str, Enum):
    """Supported LLM models."""

    CLAUDE_OPUS = "claude-opus-4-5-20251101"
    CLAUDE_SONNET = "claude-sonnet-4-20250514"
    CLAUDE_HAIKU = "claude-3-5-haiku-20241022"
    CLAUDE_3_OPUS = "claude-3-opus-20240229"
    CLAUDE_3_SONNET = "claude-3-sonnet-20240229"


class AnalysisType(str, Enum):
    """Types of analysis the LLM can perform."""

    MARKET_OVERVIEW = "market_overview"
    TECHNICAL_ANALYSIS = "technical_analysis"
    NEWS_SENTIMENT = "news_sentiment"
    SIGNAL_GENERATION = "signal_generation"
    RISK_ASSESSMENT = "risk_assessment"
    STRATEGY_EVALUATION = "strategy_evaluation"
    DATA_SOURCE_EVALUATION = "data_source_evaluation"


@dataclass
class LLMAgentConfig(AgentConfig):
    """Configuration for LLM agents."""

    model: LLMModel = LLMModel.CLAUDE_SONNET
    api_key: str | None = None  # Will use ANTHROPIC_API_KEY env var if None
    max_tokens: int = 2048
    temperature: float = 0.3  # Lower for more deterministic outputs

    # System prompt customization
    system_prompt: str | None = None
    persona: str = "quantitative trading analyst"

    # Output settings
    require_structured_output: bool = True
    include_reasoning: bool = True

    # Rate limiting
    requests_per_minute: int = 20
    retry_attempts: int = 3
    retry_delay: float = 1.0

    def __post_init__(self):
        if self.role is None:
            self.role = AgentRole.ANALYST


class ClaudeClient:
    """
    Client for Claude API interactions.

    Handles:
    - API authentication
    - Rate limiting
    - Retry logic
    - Response parsing
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: LLMModel = LLMModel.CLAUDE_SONNET,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ):
        """
        Initialize Claude client.

        Args:
            api_key: Anthropic API key (uses env var if not provided)
            model: Model to use
            max_tokens: Maximum response tokens
            temperature: Sampling temperature
        """
        if not ANTHROPIC_AVAILABLE:
            raise ImportError(
                "anthropic library not installed. "
                "Install with: pip install anthropic"
            )

        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "API key required. Set ANTHROPIC_API_KEY environment variable "
                "or pass api_key parameter."
            )

        self.model = model.value
        self.max_tokens = max_tokens
        self.temperature = temperature

        self._client = anthropic.Anthropic(api_key=self.api_key)
        self._async_client = anthropic.AsyncAnthropic(api_key=self.api_key)
        self.last_usage: dict | None = None  # Populated after each generate() call

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """
        Generate a response from Claude.

        Args:
            prompt: User prompt
            system: System prompt
            max_tokens: Override default max tokens
            temperature: Override default temperature

        Returns:
            Generated response text
        """
        messages = [{"role": "user", "content": prompt}]

        response = await self._async_client.messages.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            temperature=temperature or self.temperature,
            system=system or "",
            messages=messages,
        )

        self.last_usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "model": self.model,
        }

        return response.content[0].text

    async def generate_json(
        self,
        prompt: str,
        system: str | None = None,
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Generate a JSON response from Claude.

        Args:
            prompt: User prompt
            system: System prompt
            schema: Expected JSON schema (for guidance)

        Returns:
            Parsed JSON response
        """
        # Add JSON instruction to prompt
        json_prompt = prompt
        if schema:
            json_prompt += f"\n\nRespond with JSON matching this schema: {json.dumps(schema)}"
        else:
            json_prompt += "\n\nRespond with valid JSON only."

        response = await self.generate(json_prompt, system)

        # Parse JSON from response
        try:
            # Try to extract JSON from response
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0].strip()
            else:
                json_str = response.strip()

            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            return {"raw_response": response, "error": str(e)}


class LLMAnalystAgent(AnalystAgent):
    """
    LLM-powered analyst agent.

    Provides market analysis, insights, and recommendations
    without generating direct trading signals.
    """

    name: str = "llm_analyst"
    description: str = "Claude-powered market analyst"

    DEFAULT_SYSTEM_PROMPT = """You are an expert quantitative trading analyst with deep knowledge of:
- Technical analysis and chart patterns
- Fundamental analysis and valuation
- Market microstructure
- Quantitative trading strategies
- Risk management

Analyze the provided data objectively and provide actionable insights.
Be concise but thorough. Support claims with data when possible.
Express uncertainty appropriately - don't overstate confidence."""

    def __init__(
        self,
        config: LLMAgentConfig | None = None,
        **kwargs: Any,
    ):
        """
        Initialize LLM analyst agent.

        Args:
            config: LLM agent configuration
            **kwargs: Additional parameters
        """
        config = config or LLMAgentConfig(
            name="llm_analyst",
            role=AgentRole.ANALYST,
        )
        super().__init__(config=config, **kwargs)

        self._llm_config: LLMAgentConfig = config  # type: ignore
        self._client: ClaudeClient | None = None

    def _define_capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            can_analyze=True,
            can_generate_signals=False,
            supports_async=True,
        )

    def _ensure_client(self) -> ClaudeClient:
        """Ensure Claude client is initialized."""
        if self._client is None:
            self._client = ClaudeClient(
                api_key=self._llm_config.api_key,
                model=self._llm_config.model,
                max_tokens=self._llm_config.max_tokens,
                temperature=self._llm_config.temperature,
            )
        return self._client

    def _get_system_prompt(self) -> str:
        """Get system prompt for analysis."""
        if self._llm_config.system_prompt:
            return self._llm_config.system_prompt
        return self.DEFAULT_SYSTEM_PROMPT

    async def analyze(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        query: str | None = None,
    ) -> dict[str, Any]:
        """
        Analyze market data using Claude.

        Args:
            data: Market data to analyze
            query: Specific question to answer

        Returns:
            Analysis results
        """
        client = self._ensure_client()

        # Prepare data summary
        data_summary = self._prepare_data_summary(data)

        # Build prompt
        if query:
            prompt = f"""Analyze the following market data and answer this question:

Question: {query}

Data Summary:
{data_summary}"""
        else:
            prompt = f"""Provide a comprehensive market analysis based on this data:

Data Summary:
{data_summary}

Include:
1. Current market conditions
2. Key technical levels
3. Trend analysis
4. Notable patterns or anomalies
5. Risk factors to consider"""

        # Generate analysis
        if self._llm_config.require_structured_output:
            schema = {
                "summary": "Brief overview",
                "conditions": "Current market conditions",
                "technical_levels": {"support": [], "resistance": []},
                "trend": "Trend direction and strength",
                "patterns": [],
                "risks": [],
                "recommendation": "Overall recommendation",
                "confidence": "Confidence level (0-1)",
            }
            result = await client.generate_json(
                prompt,
                system=self._get_system_prompt(),
                schema=schema,
            )
        else:
            response = await client.generate(
                prompt,
                system=self._get_system_prompt(),
            )
            result = {"analysis": response}

        result["timestamp"] = datetime.now().isoformat()
        result["query"] = query

        return result

    def _prepare_data_summary(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
    ) -> str:
        """Prepare a text summary of the data for LLM."""
        if isinstance(data, dict):
            summaries = []
            for symbol, df in data.items():
                summaries.append(f"=== {symbol} ===\n{self._summarize_df(df)}")
            return "\n\n".join(summaries)
        else:
            return self._summarize_df(data)

    def _summarize_df(self, df: pd.DataFrame) -> str:
        """Create a text summary of a DataFrame."""
        lines = []

        # Time range
        if hasattr(df.index, "min"):
            lines.append(f"Period: {df.index.min()} to {df.index.max()}")
            lines.append(f"Bars: {len(df)}")

        # Price summary
        if "close" in df.columns:
            lines.append(f"\nPrice:")
            lines.append(f"  Current: {df['close'].iloc[-1]:.2f}")
            lines.append(f"  High (period): {df['close'].max():.2f}")
            lines.append(f"  Low (period): {df['close'].min():.2f}")
            lines.append(f"  Change: {(df['close'].iloc[-1] / df['close'].iloc[0] - 1) * 100:.2f}%")

        # Recent price action (last 5 bars)
        if len(df) >= 5:
            recent = df.tail(5)
            lines.append(f"\nRecent closes (last 5): {recent['close'].tolist()}")

        # Volume if available
        if "volume" in df.columns:
            lines.append(f"\nVolume:")
            lines.append(f"  Recent avg: {df['volume'].tail(20).mean():.0f}")
            lines.append(f"  Last: {df['volume'].iloc[-1]:.0f}")

        # Technical indicators if present
        tech_cols = [c for c in df.columns if any(
            c.startswith(p) for p in ["rsi", "macd", "sma", "ema", "bb_", "atr"]
        )]
        if tech_cols:
            lines.append(f"\nTechnical Indicators (latest):")
            for col in tech_cols[:10]:  # Limit to 10
                val = df[col].iloc[-1]
                if pd.notna(val):
                    lines.append(f"  {col}: {val:.4f}")

        return "\n".join(lines)


class LLMSignalAgent(SignalGeneratorAgent):
    """
    LLM-powered signal generation agent.

    Uses Claude to analyze data and generate trading signals
    with reasoning and confidence levels.
    """

    name: str = "llm_signal_agent"
    description: str = "Claude-powered signal generator"

    SIGNAL_SYSTEM_PROMPT = """You are an expert quantitative trading system that generates trading signals.

For each asset, analyze the provided data and determine:
1. Signal direction (long, short, or no_signal)
2. Signal strength (-1 to 1, where -1 is strong short, 1 is strong long)
3. Confidence level (0 to 1)
4. Brief reasoning for the signal

Be conservative - only generate signals when there's clear evidence.
Consider risk and avoid overconfidence.
Output must be valid JSON."""

    def __init__(
        self,
        universe: list[Symbol],
        config: LLMAgentConfig | None = None,
        **kwargs: Any,
    ):
        """
        Initialize LLM signal agent.

        Args:
            universe: List of symbols to generate signals for
            config: LLM agent configuration
            **kwargs: Additional parameters
        """
        config = config or LLMAgentConfig(
            name="llm_signal_agent",
            role=AgentRole.SIGNAL_GENERATOR,
        )
        super().__init__(universe=universe, config=config, **kwargs)

        self._llm_config: LLMAgentConfig = config  # type: ignore
        self._client: ClaudeClient | None = None

    def _define_capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            can_generate_signals=True,
            can_analyze=True,
            supports_async=True,
            supported_symbols=self.universe,
        )

    def _ensure_client(self) -> ClaudeClient:
        """Ensure Claude client is initialized."""
        if self._client is None:
            self._client = ClaudeClient(
                api_key=self._llm_config.api_key,
                model=self._llm_config.model,
                max_tokens=self._llm_config.max_tokens,
                temperature=self._llm_config.temperature,
            )
        return self._client

    async def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
    ) -> list[Signal]:
        """
        Generate signals using Claude analysis.

        Args:
            data: Market data
            timestamp: Current timestamp

        Returns:
            List of generated signals
        """
        timestamp = timestamp or datetime.now()
        client = self._ensure_client()

        # Prepare data for each symbol
        if isinstance(data, pd.DataFrame):
            data_dict = {self.universe[0]: data}
        else:
            data_dict = data

        signals = []

        for symbol in self.universe:
            if symbol not in data_dict:
                continue

            df = data_dict[symbol]
            signal = await self._generate_signal_for_symbol(
                client, symbol, df, timestamp
            )
            if signal is not None:
                signals.append(signal)

        return signals

    async def _generate_signal_for_symbol(
        self,
        client: ClaudeClient,
        symbol: Symbol,
        df: pd.DataFrame,
        timestamp: datetime,
    ) -> Signal | None:
        """Generate signal for a single symbol."""

        # Prepare data summary
        data_summary = self._prepare_signal_data(df)

        prompt = f"""Analyze the following market data for {symbol} and generate a trading signal.

Data:
{data_summary}

Respond with JSON:
{{
    "symbol": "{symbol}",
    "direction": "long" | "short" | "no_signal",
    "strength": <float from -1 to 1>,
    "confidence": <float from 0 to 1>,
    "reasoning": "<brief explanation>",
    "key_factors": ["factor1", "factor2", ...]
}}"""

        try:
            result = await client.generate_json(
                prompt,
                system=self.SIGNAL_SYSTEM_PROMPT,
            )

            direction_str = result.get("direction", "no_signal")
            if direction_str == "no_signal":
                return None

            direction = Direction.LONG if direction_str == "long" else Direction.SHORT
            strength = float(result.get("strength", 0))
            confidence = float(result.get("confidence", 0.5))

            # Ensure strength matches direction
            if direction == Direction.SHORT and strength > 0:
                strength = -strength
            elif direction == Direction.LONG and strength < 0:
                strength = -strength

            signal_type = (
                SignalType.ENTRY_LONG if direction == Direction.LONG
                else SignalType.ENTRY_SHORT
            )

            return self.create_signal(
                symbol=symbol,
                direction=direction,
                strength=strength,
                confidence=confidence,
                signal_type=signal_type,
                metadata={
                    "reasoning": result.get("reasoning", ""),
                    "key_factors": result.get("key_factors", []),
                    "model": self._llm_config.model.value,
                },
            )

        except Exception as e:
            logger.error(f"Signal generation failed for {symbol}: {e}")
            return None

    def _prepare_signal_data(self, df: pd.DataFrame) -> str:
        """Prepare data summary for signal generation."""
        lines = []

        # Recent prices (last 20 bars)
        recent = df.tail(20)

        lines.append("Recent Price Action (last 20 bars):")
        for idx, row in recent.iterrows():
            if "close" in row:
                line = f"  {idx}: O={row.get('open', 'N/A'):.2f} H={row.get('high', 'N/A'):.2f} L={row.get('low', 'N/A'):.2f} C={row['close']:.2f}"
                if "volume" in row:
                    line += f" V={row['volume']:.0f}"
                lines.append(line)

        # Key metrics
        if len(df) >= 20:
            lines.append(f"\nKey Metrics:")
            lines.append(f"  20-bar return: {(df['close'].iloc[-1] / df['close'].iloc[-20] - 1) * 100:.2f}%")
            lines.append(f"  20-bar volatility: {df['close'].pct_change().tail(20).std() * 100:.2f}%")

        # Technical indicators if available
        tech_cols = ["rsi_14", "macd", "macd_signal", "bb_pct", "atr_14"]
        available = [c for c in tech_cols if c in df.columns]
        if available:
            lines.append(f"\nTechnical Indicators (current):")
            for col in available:
                val = df[col].iloc[-1]
                if pd.notna(val):
                    lines.append(f"  {col}: {val:.4f}")

        return "\n".join(lines)


class LLMNewsAnalystAgent(AnalystAgent):
    """
    LLM agent specialized for news sentiment analysis.

    Analyzes news articles and extracts:
    - Sentiment (bullish/bearish/neutral)
    - Key entities and topics
    - Potential market impact
    - Trading relevance
    """

    name: str = "llm_news_analyst"
    description: str = "Claude-powered news sentiment analyst"

    NEWS_SYSTEM_PROMPT = """You are an expert financial news analyst specializing in:
- Extracting market-relevant information from news
- Sentiment analysis for trading
- Identifying potential market-moving events
- Assessing news credibility and impact

Analyze news articles objectively. Consider both immediate and delayed market impacts.
Be skeptical of overly promotional or alarming content."""

    def __init__(
        self,
        config: LLMAgentConfig | None = None,
        **kwargs: Any,
    ):
        config = config or LLMAgentConfig(
            name="llm_news_analyst",
            role=AgentRole.ANALYST,
        )
        super().__init__(config=config, **kwargs)
        self._llm_config: LLMAgentConfig = config  # type: ignore
        self._client: ClaudeClient | None = None

    def _define_capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            can_analyze=True,
            supports_async=True,
            required_data=["news"],
        )

    def _ensure_client(self) -> ClaudeClient:
        if self._client is None:
            self._client = ClaudeClient(
                api_key=self._llm_config.api_key,
                model=self._llm_config.model,
                max_tokens=self._llm_config.max_tokens,
                temperature=self._llm_config.temperature,
            )
        return self._client

    async def analyze(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        query: str | None = None,
    ) -> dict[str, Any]:
        """
        Analyze news articles.

        Args:
            data: DataFrame with news articles (columns: title, content, source, timestamp)
            query: Optional specific question

        Returns:
            Analysis results with sentiment and insights
        """
        client = self._ensure_client()

        # Extract news text
        if isinstance(data, pd.DataFrame):
            news_text = self._extract_news_text(data)
        else:
            news_text = str(data)

        prompt = f"""Analyze the following news articles for trading relevance:

{news_text}

Provide analysis as JSON:
{{
    "overall_sentiment": "bullish" | "bearish" | "neutral",
    "sentiment_score": <-1 to 1>,
    "confidence": <0 to 1>,
    "key_themes": ["theme1", "theme2"],
    "mentioned_symbols": ["SYM1", "SYM2"],
    "market_impact": "high" | "medium" | "low",
    "time_horizon": "immediate" | "short_term" | "long_term",
    "summary": "<brief summary>",
    "trading_implications": "<implications for trading>"
}}"""

        result = await client.generate_json(
            prompt,
            system=self.NEWS_SYSTEM_PROMPT,
        )

        result["timestamp"] = datetime.now().isoformat()
        return result

    def _extract_news_text(self, df: pd.DataFrame) -> str:
        """Extract news text from DataFrame."""
        lines = []

        for _, row in df.iterrows():
            title = row.get("title", "")
            content = row.get("content", row.get("body", ""))
            source = row.get("source", "Unknown")
            timestamp = row.get("timestamp", row.get("published_at", ""))

            lines.append(f"--- Article ({source}, {timestamp}) ---")
            lines.append(f"Title: {title}")
            if content:
                # Truncate long content
                if len(content) > 1000:
                    content = content[:1000] + "..."
                lines.append(f"Content: {content}")
            lines.append("")

        return "\n".join(lines)


# Factory function
def create_llm_agent(
    agent_type: str,
    universe: list[Symbol] | None = None,
    api_key: str | None = None,
    model: LLMModel = LLMModel.CLAUDE_SONNET,
    **kwargs: Any,
) -> Agent:
    """
    Factory function to create LLM agents.

    Args:
        agent_type: Type of agent ('analyst', 'signal', 'news')
        universe: List of symbols (for signal agents)
        api_key: Anthropic API key
        model: LLM model to use
        **kwargs: Additional agent parameters

    Returns:
        Configured LLM agent
    """
    config = LLMAgentConfig(
        name=f"llm_{agent_type}",
        role=AgentRole.ANALYST if agent_type != "signal" else AgentRole.SIGNAL_GENERATOR,
        api_key=api_key,
        model=model,
        **{k: v for k, v in kwargs.items() if k in LLMAgentConfig.__dataclass_fields__},
    )

    agents = {
        "analyst": LLMAnalystAgent,
        "signal": LLMSignalAgent,
        "news": LLMNewsAnalystAgent,
    }

    if agent_type not in agents:
        raise ValueError(f"Unknown agent type: {agent_type}. Available: {list(agents.keys())}")

    agent_class = agents[agent_type]

    if agent_type == "signal":
        if universe is None:
            raise ValueError("universe required for signal agent")
        return agent_class(universe=universe, config=config)
    else:
        return agent_class(config=config)
