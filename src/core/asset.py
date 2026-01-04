"""Asset and Universe definitions."""

from dataclasses import dataclass, field
from typing import Any

from .types import AssetType, Symbol


@dataclass(frozen=True)
class Asset:
    """Represents a tradeable asset."""

    symbol: Symbol
    asset_type: AssetType
    exchange: str | None = None
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    currency: str = "USD"
    min_quantity: float = 1.0
    tick_size: float = 0.01
    metadata: dict[str, Any] = field(default_factory=dict)

    def __hash__(self) -> int:
        return hash((self.symbol, self.asset_type))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Asset):
            return NotImplemented
        return self.symbol == other.symbol and self.asset_type == other.asset_type

    @classmethod
    def equity(cls, symbol: str, **kwargs: Any) -> "Asset":
        """Create an equity asset."""
        return cls(symbol=symbol, asset_type=AssetType.EQUITY, **kwargs)

    @classmethod
    def crypto(cls, symbol: str, **kwargs: Any) -> "Asset":
        """Create a crypto asset."""
        return cls(symbol=symbol, asset_type=AssetType.CRYPTO, **kwargs)

    @classmethod
    def etf(cls, symbol: str, **kwargs: Any) -> "Asset":
        """Create an ETF asset."""
        return cls(symbol=symbol, asset_type=AssetType.ETF, **kwargs)


@dataclass
class Universe:
    """A collection of assets that strategies can trade."""

    name: str
    assets: list[Asset] = field(default_factory=list)
    description: str = ""

    def __len__(self) -> int:
        return len(self.assets)

    def __iter__(self):
        return iter(self.assets)

    def __contains__(self, item: Asset | str) -> bool:
        if isinstance(item, str):
            return any(a.symbol == item for a in self.assets)
        return item in self.assets

    @property
    def symbols(self) -> list[str]:
        """Get list of all symbols in universe."""
        return [a.symbol for a in self.assets]

    def filter_by_type(self, asset_type: AssetType) -> "Universe":
        """Return a new universe filtered by asset type."""
        return Universe(
            name=f"{self.name}_{asset_type.value}",
            assets=[a for a in self.assets if a.asset_type == asset_type],
        )

    def filter_by_sector(self, sector: str) -> "Universe":
        """Return a new universe filtered by sector."""
        return Universe(
            name=f"{self.name}_{sector}",
            assets=[a for a in self.assets if a.sector == sector],
        )

    def add(self, asset: Asset) -> None:
        """Add an asset to the universe."""
        if asset not in self.assets:
            self.assets.append(asset)

    def remove(self, asset: Asset) -> None:
        """Remove an asset from the universe."""
        self.assets = [a for a in self.assets if a != asset]

    @classmethod
    def from_symbols(
        cls,
        name: str,
        symbols: list[str],
        asset_type: AssetType = AssetType.EQUITY,
    ) -> "Universe":
        """Create a universe from a list of symbols."""
        assets = [Asset(symbol=s, asset_type=asset_type) for s in symbols]
        return cls(name=name, assets=assets)


# Pre-defined universes
SP500_TOP_50 = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK.B", "UNH", "JNJ",
    "XOM", "JPM", "V", "PG", "MA", "HD", "CVX", "MRK", "ABBV", "LLY",
    "PEP", "KO", "AVGO", "COST", "TMO", "MCD", "WMT", "CSCO", "ACN", "ABT",
    "DHR", "NEE", "VZ", "ADBE", "CRM", "TXN", "CMCSA", "NKE", "PM", "WFC",
    "BMY", "RTX", "UPS", "QCOM", "HON", "ORCL", "LOW", "INTC", "AMD", "AMGN",
]

MAJOR_ETFS = ["SPY", "QQQ", "IWM", "DIA", "TLT", "GLD", "USO", "VXX", "XLF", "XLE"]

MAJOR_CRYPTO = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
