"""Knowledge Base - Persistent understanding of companies and sectors.

Stores MY perspective and understanding, not just research data.
This is knowledge I generate once and reference repeatedly.

Files stored as YAML in ~/quant_results/knowledge/
- companies/{SYMBOL}.yaml
- sectors/{SECTOR}.yaml
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
import json
import logging

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class CompanyBrief:
    """My understanding of a company."""

    symbol: str
    name: str
    updated: datetime

    # Business understanding
    business_model: str  # What they do, how they make money
    moat: str  # Competitive advantages
    earnings_quality: str  # Consistent, volatile, cyclical, etc.
    management_view: str  # My assessment of management
    sector: str
    market_cap_tier: str  # mega, large, mid, small, micro

    # Key dynamics
    key_risks: list[str] = field(default_factory=list)
    key_catalysts: list[str] = field(default_factory=list)
    sector_position: str = ""  # Leader, follower, niche player, etc.

    # Trading notes
    typical_volatility: str = ""  # low, medium, high
    earnings_behavior: str = ""  # How it typically reacts to earnings
    correlation_notes: str = ""  # What it correlates with
    best_setups: str = ""  # What setups work well for this stock
    avoid_when: str = ""  # Conditions when I shouldn't trade it

    # Valuation context
    valuation_notes: str = ""  # Current valuation context
    historical_range: str = ""  # Where it typically trades

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "updated": self.updated.isoformat(),
            "business_model": self.business_model,
            "moat": self.moat,
            "earnings_quality": self.earnings_quality,
            "management_view": self.management_view,
            "sector": self.sector,
            "market_cap_tier": self.market_cap_tier,
            "key_risks": self.key_risks,
            "key_catalysts": self.key_catalysts,
            "sector_position": self.sector_position,
            "typical_volatility": self.typical_volatility,
            "earnings_behavior": self.earnings_behavior,
            "correlation_notes": self.correlation_notes,
            "best_setups": self.best_setups,
            "avoid_when": self.avoid_when,
            "valuation_notes": self.valuation_notes,
            "historical_range": self.historical_range,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CompanyBrief":
        return cls(
            symbol=data["symbol"],
            name=data["name"],
            updated=datetime.fromisoformat(data["updated"]),
            business_model=data["business_model"],
            moat=data["moat"],
            earnings_quality=data["earnings_quality"],
            management_view=data["management_view"],
            sector=data["sector"],
            market_cap_tier=data["market_cap_tier"],
            key_risks=data.get("key_risks", []),
            key_catalysts=data.get("key_catalysts", []),
            sector_position=data.get("sector_position", ""),
            typical_volatility=data.get("typical_volatility", ""),
            earnings_behavior=data.get("earnings_behavior", ""),
            correlation_notes=data.get("correlation_notes", ""),
            best_setups=data.get("best_setups", ""),
            avoid_when=data.get("avoid_when", ""),
            valuation_notes=data.get("valuation_notes", ""),
            historical_range=data.get("historical_range", ""),
        )

    def to_yaml(self) -> str:
        """Serialize to YAML."""
        if not HAS_YAML:
            return json.dumps(self.to_dict(), indent=2)
        return yaml.dump(self.to_dict(), default_flow_style=False, sort_keys=False)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> "CompanyBrief":
        """Deserialize from YAML."""
        if not HAS_YAML:
            data = json.loads(yaml_str)
        else:
            data = yaml.safe_load(yaml_str)
        return cls.from_dict(data)

    def get_summary(self) -> str:
        """Get a brief summary for LLM context."""
        lines = [
            f"## {self.symbol} - {self.name}",
            f"**Sector:** {self.sector} | **Position:** {self.sector_position}",
            f"**Business:** {self.business_model}",
            f"**Moat:** {self.moat}",
            f"**Earnings Quality:** {self.earnings_quality}",
        ]

        if self.key_catalysts:
            lines.append(f"**Catalysts:** {', '.join(self.key_catalysts)}")

        if self.key_risks:
            lines.append(f"**Risks:** {', '.join(self.key_risks)}")

        if self.best_setups:
            lines.append(f"**Best Setups:** {self.best_setups}")

        return "\n".join(lines)


@dataclass
class SectorContext:
    """My understanding of a sector."""

    sector: str
    updated: datetime

    # Cycle dynamics
    current_cycle_position: str  # early, mid, late cycle
    cycle_sensitivity: str  # How sensitive to economic cycle

    # Key drivers
    key_drivers: list[str] = field(default_factory=list)
    leading_indicators: list[str] = field(default_factory=list)

    # Relationships
    correlations: dict[str, str] = field(default_factory=dict)  # sector -> relationship
    rotation_patterns: str = ""  # When money rotates in/out

    # Current assessment
    current_assessment: str = ""
    relative_strength: str = ""  # vs. market

    # Key stocks
    leaders: list[str] = field(default_factory=list)
    laggards: list[str] = field(default_factory=list)

    # What works
    what_works_here: str = ""
    what_to_avoid: str = ""

    def to_dict(self) -> dict:
        return {
            "sector": self.sector,
            "updated": self.updated.isoformat(),
            "current_cycle_position": self.current_cycle_position,
            "cycle_sensitivity": self.cycle_sensitivity,
            "key_drivers": self.key_drivers,
            "leading_indicators": self.leading_indicators,
            "correlations": self.correlations,
            "rotation_patterns": self.rotation_patterns,
            "current_assessment": self.current_assessment,
            "relative_strength": self.relative_strength,
            "leaders": self.leaders,
            "laggards": self.laggards,
            "what_works_here": self.what_works_here,
            "what_to_avoid": self.what_to_avoid,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SectorContext":
        return cls(
            sector=data["sector"],
            updated=datetime.fromisoformat(data["updated"]),
            current_cycle_position=data["current_cycle_position"],
            cycle_sensitivity=data["cycle_sensitivity"],
            key_drivers=data.get("key_drivers", []),
            leading_indicators=data.get("leading_indicators", []),
            correlations=data.get("correlations", {}),
            rotation_patterns=data.get("rotation_patterns", ""),
            current_assessment=data.get("current_assessment", ""),
            relative_strength=data.get("relative_strength", ""),
            leaders=data.get("leaders", []),
            laggards=data.get("laggards", []),
            what_works_here=data.get("what_works_here", ""),
            what_to_avoid=data.get("what_to_avoid", ""),
        )

    def to_yaml(self) -> str:
        """Serialize to YAML."""
        if not HAS_YAML:
            return json.dumps(self.to_dict(), indent=2)
        return yaml.dump(self.to_dict(), default_flow_style=False, sort_keys=False)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> "SectorContext":
        """Deserialize from YAML."""
        if not HAS_YAML:
            data = json.loads(yaml_str)
        else:
            data = yaml.safe_load(yaml_str)
        return cls.from_dict(data)

    def get_summary(self) -> str:
        """Get a brief summary for LLM context."""
        lines = [
            f"## {self.sector}",
            f"**Cycle Position:** {self.current_cycle_position}",
            f"**Relative Strength:** {self.relative_strength}",
            f"**Current Assessment:** {self.current_assessment}",
        ]

        if self.key_drivers:
            lines.append(f"**Key Drivers:** {', '.join(self.key_drivers)}")

        if self.leaders:
            lines.append(f"**Leaders:** {', '.join(self.leaders)}")

        if self.what_works_here:
            lines.append(f"**What Works:** {self.what_works_here}")

        return "\n".join(lines)


class KnowledgeBase:
    """
    Manages persistent knowledge about companies and sectors.

    Files stored in ~/quant_results/knowledge/
    - companies/{SYMBOL}.yaml
    - sectors/{SECTOR}.yaml
    """

    def __init__(self, knowledge_dir: Optional[Path] = None):
        """Initialize knowledge base.

        Args:
            knowledge_dir: Base directory for knowledge files.
                          Defaults to paths.knowledge.
        """
        self.base_dir = knowledge_dir or paths.knowledge
        self.companies_dir = self.base_dir / "companies"
        self.sectors_dir = self.base_dir / "sectors"

        # Ensure directories exist
        self.companies_dir.mkdir(parents=True, exist_ok=True)
        self.sectors_dir.mkdir(parents=True, exist_ok=True)

        # Cache
        self._company_cache: dict[str, CompanyBrief] = {}
        self._sector_cache: dict[str, SectorContext] = {}

    # === Company Methods ===

    def get_company(self, symbol: str) -> Optional[CompanyBrief]:
        """Get company brief by symbol."""
        symbol = symbol.upper()

        if symbol in self._company_cache:
            return self._company_cache[symbol]

        filepath = self._get_company_filepath(symbol)
        if not filepath.exists():
            return None

        brief = self._load_company(filepath)
        if brief:
            self._company_cache[symbol] = brief
        return brief

    def save_company(self, brief: CompanyBrief) -> None:
        """Save a company brief and sync to DB."""
        brief.updated = datetime.now()
        filepath = self._get_company_filepath(brief.symbol)

        if HAS_YAML:
            content = brief.to_yaml()
        else:
            content = json.dumps(brief.to_dict(), indent=2)

        with open(filepath, "w") as f:
            f.write(content)

        self._company_cache[brief.symbol] = brief
        logger.info(f"Saved company brief: {brief.symbol}")

        # Sync to DB
        try:
            from src.db.write_api import athena_db
            athena_db.upsert_company(brief.to_dict())
        except Exception as e:
            logger.warning(f"DB sync failed for company {brief.symbol}: {e}")

    def create_company(
        self,
        symbol: str,
        name: str,
        business_model: str,
        moat: str,
        earnings_quality: str,
        management_view: str,
        sector: str,
        market_cap_tier: str = "large",
        **kwargs,
    ) -> CompanyBrief:
        """Create and save a new company brief."""
        brief = CompanyBrief(
            symbol=symbol.upper(),
            name=name,
            updated=datetime.now(),
            business_model=business_model,
            moat=moat,
            earnings_quality=earnings_quality,
            management_view=management_view,
            sector=sector,
            market_cap_tier=market_cap_tier,
            **kwargs,
        )
        self.save_company(brief)
        return brief

    def list_companies(self) -> list[str]:
        """List all companies with briefs."""
        symbols = []
        for filepath in self.companies_dir.glob("*.*"):
            if filepath.suffix in [".yaml", ".json"]:
                symbols.append(filepath.stem.upper())
        return sorted(symbols)

    def delete_company(self, symbol: str) -> bool:
        """Delete a company brief."""
        symbol = symbol.upper()
        filepath = self._get_company_filepath(symbol)

        if filepath.exists():
            filepath.unlink()
            self._company_cache.pop(symbol, None)
            return True
        return False

    # === Sector Methods ===

    def get_sector(self, sector: str) -> Optional[SectorContext]:
        """Get sector context."""
        sector = sector.lower()

        if sector in self._sector_cache:
            return self._sector_cache[sector]

        filepath = self._get_sector_filepath(sector)
        if not filepath.exists():
            return None

        context = self._load_sector(filepath)
        if context:
            self._sector_cache[sector] = context
        return context

    def save_sector(self, context: SectorContext) -> None:
        """Save a sector context and sync to DB."""
        context.updated = datetime.now()
        filepath = self._get_sector_filepath(context.sector)

        if HAS_YAML:
            content = context.to_yaml()
        else:
            content = json.dumps(context.to_dict(), indent=2)

        with open(filepath, "w") as f:
            f.write(content)

        self._sector_cache[context.sector.lower()] = context
        logger.info(f"Saved sector context: {context.sector}")

        # Sync to DB
        try:
            from src.db.write_api import athena_db
            athena_db.upsert_sector(context.to_dict())
        except Exception as e:
            logger.warning(f"DB sync failed for sector {context.sector}: {e}")

    def create_sector(
        self,
        sector: str,
        current_cycle_position: str,
        cycle_sensitivity: str,
        **kwargs,
    ) -> SectorContext:
        """Create and save a new sector context."""
        context = SectorContext(
            sector=sector,
            updated=datetime.now(),
            current_cycle_position=current_cycle_position,
            cycle_sensitivity=cycle_sensitivity,
            **kwargs,
        )
        self.save_sector(context)
        return context

    def list_sectors(self) -> list[str]:
        """List all sectors with context."""
        sectors = []
        for filepath in self.sectors_dir.glob("*.*"):
            if filepath.suffix in [".yaml", ".json"]:
                sectors.append(filepath.stem)
        return sorted(sectors)

    def delete_sector(self, sector: str) -> bool:
        """Delete a sector context."""
        sector = sector.lower()
        filepath = self._get_sector_filepath(sector)

        if filepath.exists():
            filepath.unlink()
            self._sector_cache.pop(sector, None)
            return True
        return False

    # === Query Methods ===

    def get_companies_in_sector(self, sector: str) -> list[CompanyBrief]:
        """Get all companies in a sector."""
        briefs = []
        for symbol in self.list_companies():
            brief = self.get_company(symbol)
            if brief and brief.sector.lower() == sector.lower():
                briefs.append(brief)
        return briefs

    def get_context_for_trade(self, symbol: str) -> dict:
        """
        Get all relevant context for a trade.

        Returns:
            Dict with company brief and sector context.
        """
        brief = self.get_company(symbol)
        sector_context = None

        if brief:
            sector_context = self.get_sector(brief.sector)

        return {
            "company": brief.to_dict() if brief else None,
            "sector": sector_context.to_dict() if sector_context else None,
            "summary": self._build_trade_context_summary(brief, sector_context),
        }

    def _build_trade_context_summary(
        self,
        brief: Optional[CompanyBrief],
        sector: Optional[SectorContext],
    ) -> str:
        """Build a summary for trading context."""
        lines = []

        if brief:
            lines.append(brief.get_summary())
            lines.append("")

        if sector:
            lines.append(sector.get_summary())

        if not lines:
            return "No knowledge available for this symbol."

        return "\n".join(lines)

    # === Private Methods ===

    def _get_company_filepath(self, symbol: str) -> Path:
        """Get filepath for company brief."""
        ext = ".yaml" if HAS_YAML else ".json"
        return self.companies_dir / f"{symbol.upper()}{ext}"

    def _get_sector_filepath(self, sector: str) -> Path:
        """Get filepath for sector context."""
        ext = ".yaml" if HAS_YAML else ".json"
        return self.sectors_dir / f"{sector.lower()}{ext}"

    def _load_company(self, filepath: Path) -> Optional[CompanyBrief]:
        """Load company brief from file."""
        try:
            with open(filepath, "r") as f:
                content = f.read()

            if filepath.suffix == ".yaml" and HAS_YAML:
                return CompanyBrief.from_yaml(content)
            else:
                data = json.loads(content)
                return CompanyBrief.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load company from {filepath}: {e}")
            return None

    def _load_sector(self, filepath: Path) -> Optional[SectorContext]:
        """Load sector context from file."""
        try:
            with open(filepath, "r") as f:
                content = f.read()

            if filepath.suffix == ".yaml" and HAS_YAML:
                return SectorContext.from_yaml(content)
            else:
                data = json.loads(content)
                return SectorContext.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load sector from {filepath}: {e}")
            return None
