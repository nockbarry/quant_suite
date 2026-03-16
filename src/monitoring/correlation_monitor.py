"""
Portfolio Correlation Monitor.

Tracks position correlations to prevent hidden concentration risk.
A portfolio with 10 "different" stocks that all correlate at 0.9 is
effectively just one position.

Features:
- Real-time correlation matrix
- Effective diversification score
- Cluster detection (highly correlated groups)
- Correlation regime tracking
- Alerts on concentration
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from src.core.paths import paths
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class CorrelationLevel(str, Enum):
    """Correlation level classifications."""
    NONE = "none"           # 0 - 0.2
    LOW = "low"             # 0.2 - 0.4
    MODERATE = "moderate"   # 0.4 - 0.6
    HIGH = "high"           # 0.6 - 0.8
    VERY_HIGH = "very_high"  # 0.8 - 1.0


@dataclass
class CorrelationPair:
    """Correlation between two positions."""
    symbol1: str
    symbol2: str
    correlation: float
    level: CorrelationLevel
    weight1: float  # Portfolio weight
    weight2: float
    combined_weight: float
    risk_contribution: float

    def to_dict(self) -> dict:
        return {
            "pair": f"{self.symbol1}/{self.symbol2}",
            "correlation": round(self.correlation, 3),
            "level": self.level.value,
            "combined_weight": round(self.combined_weight, 4),
            "risk_contribution": round(self.risk_contribution, 4),
        }


@dataclass
class CorrelationCluster:
    """Group of highly correlated positions."""
    cluster_id: int
    symbols: list[str]
    avg_correlation: float
    combined_weight: float
    effective_positions: float  # Diversification-adjusted

    def to_dict(self) -> dict:
        return {
            "cluster_id": self.cluster_id,
            "symbols": self.symbols,
            "avg_correlation": round(self.avg_correlation, 3),
            "combined_weight": round(self.combined_weight, 4),
            "effective_positions": round(self.effective_positions, 2),
        }


@dataclass
class PortfolioCorrelationStatus:
    """Complete correlation status for portfolio."""
    timestamp: datetime
    positions: list[str]
    correlation_matrix: dict[str, dict[str, float]]
    high_correlations: list[CorrelationPair]
    clusters: list[CorrelationCluster]

    # Diversification metrics
    effective_n: float  # Effective number of bets
    diversification_ratio: float  # 1 = perfect, 0 = no diversification
    concentration_risk: float  # 0-1 scale

    # Alerts
    issues: list[str]

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "positions": self.positions,
            "n_positions": len(self.positions),
            "effective_n": round(self.effective_n, 2),
            "diversification_ratio": round(self.diversification_ratio, 3),
            "concentration_risk": round(self.concentration_risk, 3),
            "high_correlations": [p.to_dict() for p in self.high_correlations],
            "clusters": [c.to_dict() for c in self.clusters],
            "issues": self.issues,
        }


class CorrelationMonitor:
    """
    Monitors portfolio correlations for hidden concentration risk.

    Key concepts:
    - Effective N: If all positions perfectly correlate, effective N = 1
    - Diversification Ratio: Portfolio vol / weighted avg vol
    - Clusters: Groups of highly correlated positions
    """

    def __init__(
        self,
        results_dir: Path | None = None,
        lookback_days: int = 60,
        high_corr_threshold: float = 0.7,
    ):
        self.results_dir = results_dir or paths.base
        self.lookback_days = lookback_days
        self.high_corr_threshold = high_corr_threshold

        # Cache
        self._returns_cache: dict[str, pd.Series] = {}
        self._cache_date: datetime | None = None

    async def analyze_portfolio(
        self,
        positions: list[dict],
        returns_data: pd.DataFrame | None = None,
    ) -> PortfolioCorrelationStatus:
        """
        Analyze portfolio correlations.

        Args:
            positions: List of position dicts with 'symbol' and 'market_value'
            returns_data: Optional pre-computed returns DataFrame

        Returns:
            Complete correlation status
        """
        if not positions:
            return PortfolioCorrelationStatus(
                timestamp=datetime.now(),
                positions=[],
                correlation_matrix={},
                high_correlations=[],
                clusters=[],
                effective_n=0,
                diversification_ratio=1.0,
                concentration_risk=0,
                issues=["No positions"],
            )

        symbols = [p["symbol"] for p in positions]
        total_value = sum(p.get("market_value", 0) for p in positions)
        weights = {
            p["symbol"]: p.get("market_value", 0) / total_value if total_value > 0 else 0
            for p in positions
        }

        # Get or compute returns
        if returns_data is not None:
            returns = returns_data[symbols].dropna()
        else:
            returns = await self._fetch_returns(symbols)

        if returns.empty or len(returns) < 20:
            return PortfolioCorrelationStatus(
                timestamp=datetime.now(),
                positions=symbols,
                correlation_matrix={},
                high_correlations=[],
                clusters=[],
                effective_n=len(symbols),
                diversification_ratio=1.0,
                concentration_risk=0,
                issues=["Insufficient return data"],
            )

        # Compute correlation matrix
        corr_matrix = returns.corr()

        # Convert to dict format
        corr_dict = {
            sym1: {sym2: corr_matrix.loc[sym1, sym2] for sym2 in symbols}
            for sym1 in symbols
        }

        # Find high correlation pairs
        high_pairs = self._find_high_correlations(corr_matrix, weights)

        # Find clusters
        clusters = self._find_clusters(corr_matrix, weights)

        # Calculate diversification metrics
        effective_n = self._calculate_effective_n(corr_matrix, weights)
        div_ratio = self._calculate_diversification_ratio(returns, weights)
        concentration = self._calculate_concentration_risk(corr_matrix, weights, clusters)

        # Generate issues
        issues = self._generate_issues(high_pairs, clusters, effective_n, len(symbols))

        return PortfolioCorrelationStatus(
            timestamp=datetime.now(),
            positions=symbols,
            correlation_matrix=corr_dict,
            high_correlations=high_pairs,
            clusters=clusters,
            effective_n=effective_n,
            diversification_ratio=div_ratio,
            concentration_risk=concentration,
            issues=issues,
        )

    async def _fetch_returns(self, symbols: list[str]) -> pd.DataFrame:
        """Fetch historical returns for symbols."""
        try:
            import yfinance as yf

            end = datetime.now()
            start = end - timedelta(days=self.lookback_days + 10)

            data = yf.download(
                symbols,
                start=start,
                end=end,
                progress=False,
            )["Adj Close"]

            if isinstance(data, pd.Series):
                data = data.to_frame()

            returns = data.pct_change().dropna()
            return returns

        except Exception as e:
            logger.error(f"Error fetching returns: {e}")
            return pd.DataFrame()

    def _classify_correlation(self, corr: float) -> CorrelationLevel:
        """Classify correlation level."""
        corr = abs(corr)
        if corr < 0.2:
            return CorrelationLevel.NONE
        elif corr < 0.4:
            return CorrelationLevel.LOW
        elif corr < 0.6:
            return CorrelationLevel.MODERATE
        elif corr < 0.8:
            return CorrelationLevel.HIGH
        return CorrelationLevel.VERY_HIGH

    def _find_high_correlations(
        self,
        corr_matrix: pd.DataFrame,
        weights: dict[str, float],
    ) -> list[CorrelationPair]:
        """Find highly correlated position pairs."""
        pairs = []
        symbols = corr_matrix.columns.tolist()

        for i, sym1 in enumerate(symbols):
            for sym2 in symbols[i + 1:]:
                corr = corr_matrix.loc[sym1, sym2]
                if abs(corr) >= self.high_corr_threshold:
                    w1 = weights.get(sym1, 0)
                    w2 = weights.get(sym2, 0)
                    combined = w1 + w2

                    # Risk contribution = combined weight * correlation factor
                    risk = combined * (1 + abs(corr)) / 2

                    pairs.append(CorrelationPair(
                        symbol1=sym1,
                        symbol2=sym2,
                        correlation=corr,
                        level=self._classify_correlation(corr),
                        weight1=w1,
                        weight2=w2,
                        combined_weight=combined,
                        risk_contribution=risk,
                    ))

        # Sort by risk contribution
        pairs.sort(key=lambda p: p.risk_contribution, reverse=True)
        return pairs

    def _find_clusters(
        self,
        corr_matrix: pd.DataFrame,
        weights: dict[str, float],
    ) -> list[CorrelationCluster]:
        """Find clusters of highly correlated positions."""
        symbols = corr_matrix.columns.tolist()
        n = len(symbols)

        if n < 2:
            return []

        # Simple clustering: group symbols with avg correlation > threshold
        clusters = []
        assigned = set()

        for i, sym1 in enumerate(symbols):
            if sym1 in assigned:
                continue

            cluster_symbols = [sym1]
            assigned.add(sym1)

            for sym2 in symbols[i + 1:]:
                if sym2 in assigned:
                    continue

                # Check correlation with all current cluster members
                corrs = [corr_matrix.loc[s, sym2] for s in cluster_symbols]
                avg_corr = np.mean(corrs)

                if avg_corr >= self.high_corr_threshold:
                    cluster_symbols.append(sym2)
                    assigned.add(sym2)

            if len(cluster_symbols) > 1:
                # Calculate cluster metrics
                cluster_corrs = []
                for i, s1 in enumerate(cluster_symbols):
                    for s2 in cluster_symbols[i + 1:]:
                        cluster_corrs.append(corr_matrix.loc[s1, s2])

                avg_corr = np.mean(cluster_corrs) if cluster_corrs else 0
                combined_weight = sum(weights.get(s, 0) for s in cluster_symbols)

                # Effective positions = N / (1 + (N-1) * avg_corr)
                n_cluster = len(cluster_symbols)
                effective_n = n_cluster / (1 + (n_cluster - 1) * avg_corr) if avg_corr > 0 else n_cluster

                clusters.append(CorrelationCluster(
                    cluster_id=len(clusters) + 1,
                    symbols=cluster_symbols,
                    avg_correlation=avg_corr,
                    combined_weight=combined_weight,
                    effective_positions=effective_n,
                ))

        return clusters

    def _calculate_effective_n(
        self,
        corr_matrix: pd.DataFrame,
        weights: dict[str, float],
    ) -> float:
        """
        Calculate effective number of bets.

        Accounts for correlation to show true diversification.
        N positions that all correlate = effective 1 position.
        """
        symbols = corr_matrix.columns.tolist()
        n = len(symbols)

        if n <= 1:
            return n

        # Calculate average pairwise correlation
        corrs = []
        for i, sym1 in enumerate(symbols):
            for sym2 in symbols[i + 1:]:
                corrs.append(corr_matrix.loc[sym1, sym2])

        avg_corr = np.mean(corrs) if corrs else 0

        # Effective N = N / (1 + (N-1) * avg_corr)
        if avg_corr >= 1:
            return 1.0
        effective_n = n / (1 + (n - 1) * max(0, avg_corr))
        return effective_n

    def _calculate_diversification_ratio(
        self,
        returns: pd.DataFrame,
        weights: dict[str, float],
    ) -> float:
        """
        Calculate diversification ratio.

        DR = weighted avg of individual vols / portfolio vol
        DR = 1 means no diversification benefit (perfect correlation)
        DR > 1 means diversification is working
        """
        symbols = returns.columns.tolist()

        # Individual volatilities
        vols = returns.std()

        # Portfolio volatility
        weight_vec = np.array([weights.get(s, 0) for s in symbols])
        weight_vec = weight_vec / weight_vec.sum() if weight_vec.sum() > 0 else weight_vec

        cov_matrix = returns.cov()
        port_var = np.dot(weight_vec, np.dot(cov_matrix, weight_vec))
        port_vol = np.sqrt(port_var) if port_var > 0 else 0

        # Weighted average vol
        weighted_vol = np.dot(weight_vec, vols)

        if port_vol > 0:
            return weighted_vol / port_vol
        return 1.0

    def _calculate_concentration_risk(
        self,
        corr_matrix: pd.DataFrame,
        weights: dict[str, float],
        clusters: list[CorrelationCluster],
    ) -> float:
        """
        Calculate concentration risk score (0-1).

        Considers:
        - High correlations
        - Cluster weights
        - Effective diversification
        """
        symbols = corr_matrix.columns.tolist()
        n = len(symbols)

        if n <= 1:
            return 0

        # Factor 1: Average high correlation
        high_corrs = []
        for i, sym1 in enumerate(symbols):
            for sym2 in symbols[i + 1:]:
                corr = corr_matrix.loc[sym1, sym2]
                if abs(corr) >= 0.5:  # Include moderate+ correlations
                    high_corrs.append(abs(corr))

        avg_high_corr = np.mean(high_corrs) if high_corrs else 0
        corr_factor = avg_high_corr * (len(high_corrs) / (n * (n - 1) / 2)) if n > 1 else 0

        # Factor 2: Cluster concentration
        cluster_factor = 0
        for cluster in clusters:
            if cluster.combined_weight > 0.35:  # Single cluster > 35% portfolio
                cluster_factor = max(cluster_factor, cluster.combined_weight - 0.35)

        # Factor 3: Effective N vs actual N
        effective_n = self._calculate_effective_n(corr_matrix, weights)
        n_ratio = 1 - (effective_n / n) if n > 0 else 0

        # Weighted combination
        concentration = (
            corr_factor * 0.4 +
            cluster_factor * 0.3 +
            n_ratio * 0.3
        )

        return min(1.0, concentration)

    def _generate_issues(
        self,
        high_pairs: list[CorrelationPair],
        clusters: list[CorrelationCluster],
        effective_n: float,
        actual_n: int,
    ) -> list[str]:
        """Generate human-readable issues."""
        issues = []

        # Check effective diversification
        if actual_n > 0 and effective_n < actual_n * 0.5:
            issues.append(
                f"Low effective diversification: {effective_n:.1f} effective positions "
                f"vs {actual_n} actual ({effective_n/actual_n:.0%})"
            )

        # Check high correlations
        very_high = [p for p in high_pairs if p.level == CorrelationLevel.VERY_HIGH]
        if very_high:
            pairs_str = ", ".join(f"{p.symbol1}/{p.symbol2}" for p in very_high[:3])
            issues.append(f"Very high correlations (>0.8): {pairs_str}")

        # Check cluster concentration
        for cluster in clusters:
            if cluster.combined_weight > 0.35:
                symbols_str = ", ".join(cluster.symbols[:4])
                if len(cluster.symbols) > 4:
                    symbols_str += f"... (+{len(cluster.symbols) - 4} more)"
                issues.append(
                    f"Cluster {cluster.cluster_id} is {cluster.combined_weight:.0%} of portfolio: "
                    f"{symbols_str} (ρ={cluster.avg_correlation:.2f})"
                )

        return issues

    def save_status(self, status: PortfolioCorrelationStatus) -> Path:
        """Save correlation status to file."""
        output_dir = self.results_dir / "live"
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / "correlation_status.json"

        with open(output_path, "w") as f:
            json.dump(status.to_dict(), f, indent=2)

        return output_path


async def check_portfolio_correlation(positions: list[dict]) -> dict:
    """Quick check of portfolio correlations."""
    monitor = CorrelationMonitor()
    status = await monitor.analyze_portfolio(positions)
    return status.to_dict()
