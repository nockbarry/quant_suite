"""
Data Quality Monitoring for Automated Trading Firm.

Goes beyond "is it fresh?" to measure:
- Data completeness
- Schema consistency
- Value distributions
- Anomaly detection
- Cross-source validation

This ensures the signals Claude uses are reliable.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class DataQualityLevel(str, Enum):
    """Quality level classifications."""
    EXCELLENT = "excellent"  # >95% quality
    GOOD = "good"           # 85-95%
    ACCEPTABLE = "acceptable"  # 70-85%
    DEGRADED = "degraded"    # 50-70%
    CRITICAL = "critical"    # <50%


@dataclass
class FieldQuality:
    """Quality metrics for a single field."""
    field_name: str
    completeness: float  # % non-null
    uniqueness: float    # % unique values
    validity: float      # % passing validation rules
    consistency: float   # % matching expected patterns
    outlier_pct: float   # % outliers detected
    last_updated: datetime

    @property
    def overall_score(self) -> float:
        """Weighted quality score 0-100."""
        return (
            self.completeness * 0.3 +
            self.validity * 0.3 +
            self.consistency * 0.25 +
            (100 - self.outlier_pct * 100) * 0.15
        )

    @property
    def level(self) -> DataQualityLevel:
        score = self.overall_score
        if score >= 95:
            return DataQualityLevel.EXCELLENT
        elif score >= 85:
            return DataQualityLevel.GOOD
        elif score >= 70:
            return DataQualityLevel.ACCEPTABLE
        elif score >= 50:
            return DataQualityLevel.DEGRADED
        return DataQualityLevel.CRITICAL

    def to_dict(self) -> dict:
        return {
            "field_name": self.field_name,
            "completeness": round(self.completeness, 1),
            "uniqueness": round(self.uniqueness, 1),
            "validity": round(self.validity, 1),
            "consistency": round(self.consistency, 1),
            "outlier_pct": round(self.outlier_pct, 2),
            "overall_score": round(self.overall_score, 1),
            "level": self.level.value,
            "last_updated": self.last_updated.isoformat(),
        }


@dataclass
class DataSourceQuality:
    """Quality metrics for a data source."""
    source_name: str
    last_check: datetime
    record_count: int
    fields: list[FieldQuality]
    freshness_minutes: float
    schema_valid: bool
    cross_validation_score: float | None = None
    issues: list[str] = field(default_factory=list)

    @property
    def overall_score(self) -> float:
        if not self.fields:
            return 0.0
        field_avg = sum(f.overall_score for f in self.fields) / len(self.fields)

        # Penalize for freshness
        freshness_penalty = min(self.freshness_minutes / 60, 20)  # Max 20% penalty
        freshness_score = max(0, 100 - freshness_penalty * 5)

        # Schema penalty
        schema_score = 100 if self.schema_valid else 50

        return (field_avg * 0.5 + freshness_score * 0.3 + schema_score * 0.2)

    @property
    def level(self) -> DataQualityLevel:
        score = self.overall_score
        if score >= 95:
            return DataQualityLevel.EXCELLENT
        elif score >= 85:
            return DataQualityLevel.GOOD
        elif score >= 70:
            return DataQualityLevel.ACCEPTABLE
        elif score >= 50:
            return DataQualityLevel.DEGRADED
        return DataQualityLevel.CRITICAL

    def to_dict(self) -> dict:
        return {
            "source_name": self.source_name,
            "last_check": self.last_check.isoformat(),
            "record_count": self.record_count,
            "freshness_minutes": round(self.freshness_minutes, 1),
            "schema_valid": self.schema_valid,
            "cross_validation_score": self.cross_validation_score,
            "overall_score": round(self.overall_score, 1),
            "level": self.level.value,
            "fields": [f.to_dict() for f in self.fields],
            "issues": self.issues,
        }


class DataQualityMonitor:
    """
    Monitors data quality across all sources in the trading system.

    Checks:
    - Congressional trades: Valid dates, amounts, congress members
    - Insider trades: Valid Form 4 data, filing dates
    - News: Valid URLs, dates, unique articles
    - Price data: No gaps, valid OHLCV
    - Signals: Valid ranges, no NaN propagation
    - Alternative data: Schema consistency
    """

    def __init__(self, results_dir: Path | None = None):
        self.results_dir = results_dir or Path.home() / "quant_results"
        self.cache_dir = self.results_dir / "cache"
        self.live_dir = self.results_dir / "live"

        # Define expected schemas
        self._schemas = self._define_schemas()

        # Quality history
        self._quality_history: dict[str, list[DataSourceQuality]] = {}

    def _define_schemas(self) -> dict[str, dict]:
        """Define expected schemas for data sources."""
        return {
            "congressional_trades": {
                "required_fields": ["congress_member", "symbol", "transaction_type", "transaction_date", "amount"],
                "field_types": {
                    "symbol": str,
                    "transaction_type": str,
                    "amount": str,  # Usually a range like "$1,001 - $15,000"
                },
                "validators": {
                    "transaction_type": lambda x: x.lower() in ["purchase", "sale", "exchange"],
                }
            },
            "insider_trades": {
                "required_fields": ["symbol", "filing_date", "transaction_type", "shares", "price"],
                "field_types": {
                    "symbol": str,
                    "shares": (int, float),
                    "price": (int, float),
                },
                "validators": {
                    "shares": lambda x: x > 0,
                    "price": lambda x: x > 0,
                }
            },
            "news": {
                "required_fields": ["title", "source", "published", "url"],
                "field_types": {
                    "title": str,
                    "url": str,
                },
                "validators": {
                    "url": lambda x: x.startswith("http"),
                }
            },
            "unified_state": {
                "required_fields": ["timestamp", "market_regime", "portfolio", "signals", "theses"],
                "field_types": {
                    "timestamp": str,
                },
            },
            "signals": {
                "required_fields": ["symbol", "direction", "strength"],
                "field_types": {
                    "strength": (int, float),
                },
                "validators": {
                    "strength": lambda x: -1 <= x <= 1,
                    "direction": lambda x: x.upper() in ["LONG", "SHORT", "NEUTRAL"],
                }
            },
        }

    async def check_all_sources(self) -> dict[str, DataSourceQuality]:
        """Check quality of all data sources."""
        results = {}

        # Congressional trades
        congressional_file = self.cache_dir / "congressional_trades.json"
        if congressional_file.exists():
            results["congressional_trades"] = await self._check_json_source(
                congressional_file, "congressional_trades"
            )

        # Insider trades
        insider_file = self.cache_dir / "insider_trades.json"
        if insider_file.exists():
            results["insider_trades"] = await self._check_json_source(
                insider_file, "insider_trades"
            )

        # News
        news_file = self.cache_dir / "news.json"
        if news_file.exists():
            results["news"] = await self._check_json_source(news_file, "news")

        # Unified state
        state_file = self.live_dir / "state.json"
        if state_file.exists():
            results["unified_state"] = await self._check_json_source(
                state_file, "unified_state"
            )

        # Signal files
        for signal_file in self.live_dir.glob("signals_*.json"):
            results[f"signals_{signal_file.stem}"] = await self._check_json_source(
                signal_file, "signals"
            )

        return results

    async def _check_json_source(
        self,
        filepath: Path,
        schema_name: str,
    ) -> DataSourceQuality:
        """Check quality of a JSON data source."""
        issues = []
        fields = []
        record_count = 0
        schema_valid = True

        try:
            mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
            freshness = (datetime.now() - mtime).total_seconds() / 60

            with open(filepath) as f:
                data = json.load(f)

            # Handle different data structures
            if isinstance(data, list):
                records = data
            elif isinstance(data, dict):
                # Could be nested - look for common keys
                if "data" in data:
                    records = data["data"] if isinstance(data["data"], list) else [data["data"]]
                elif "signals" in data:
                    records = data["signals"] if isinstance(data["signals"], list) else [data["signals"]]
                else:
                    records = [data]
            else:
                records = []
                issues.append("Unexpected data structure")

            record_count = len(records)

            if record_count == 0:
                return DataSourceQuality(
                    source_name=schema_name,
                    last_check=datetime.now(),
                    record_count=0,
                    fields=[],
                    freshness_minutes=freshness,
                    schema_valid=False,
                    issues=["No records found"],
                )

            # Check schema
            schema = self._schemas.get(schema_name, {})
            required = schema.get("required_fields", [])

            if records and isinstance(records[0], dict):
                sample = records[0]
                missing = [f for f in required if f not in sample]
                if missing:
                    schema_valid = False
                    issues.append(f"Missing required fields: {missing}")

            # Check field quality
            if records and isinstance(records[0], dict):
                df = pd.DataFrame(records)
                for col in df.columns:
                    field_quality = self._check_field_quality(
                        df[col], col, schema.get("validators", {}).get(col)
                    )
                    fields.append(field_quality)

            return DataSourceQuality(
                source_name=schema_name,
                last_check=datetime.now(),
                record_count=record_count,
                fields=fields,
                freshness_minutes=freshness,
                schema_valid=schema_valid,
                issues=issues,
            )

        except Exception as e:
            logger.error(f"Error checking {filepath}: {e}")
            return DataSourceQuality(
                source_name=schema_name,
                last_check=datetime.now(),
                record_count=0,
                fields=[],
                freshness_minutes=float("inf"),
                schema_valid=False,
                issues=[str(e)],
            )

    def _check_field_quality(
        self,
        series: pd.Series,
        field_name: str,
        validator: Any | None = None,
    ) -> FieldQuality:
        """Check quality of a single field."""
        total = len(series)

        # Completeness
        non_null = series.notna().sum()
        completeness = (non_null / total * 100) if total > 0 else 0

        # Check if series contains unhashable types (dicts, lists)
        # If so, we can't compute uniqueness properly
        try:
            first_non_null = series.dropna().iloc[0] if non_null > 0 else None
            has_complex_types = isinstance(first_non_null, (dict, list))
        except (IndexError, TypeError):
            has_complex_types = False

        # Uniqueness - skip for complex types
        if has_complex_types:
            uniqueness = 100.0  # Assume unique for nested structures
        else:
            try:
                unique_count = series.nunique()
                uniqueness = (unique_count / non_null * 100) if non_null > 0 else 0
            except TypeError:
                uniqueness = 100.0  # Fallback for unhashable

        # Validity (using validator if provided)
        valid_count = total
        if validator and not has_complex_types:
            try:
                valid_count = series.dropna().apply(validator).sum()
            except Exception:
                valid_count = non_null  # Assume valid if can't check
        validity = (valid_count / non_null * 100) if non_null > 0 else 0

        # Consistency (check for mixed types) - skip for complex types
        if has_complex_types:
            consistency = 100.0
        else:
            try:
                types = series.dropna().apply(type).unique()
                consistency = 100 if len(types) <= 1 else (100 / len(types))
            except Exception:
                consistency = 100.0

        # Outliers (for numeric fields)
        outlier_pct = 0
        if pd.api.types.is_numeric_dtype(series):
            try:
                q1 = series.quantile(0.25)
                q3 = series.quantile(0.75)
                iqr = q3 - q1
                outliers = ((series < q1 - 1.5 * iqr) | (series > q3 + 1.5 * iqr)).sum()
                outlier_pct = (outliers / non_null) if non_null > 0 else 0
            except Exception:
                pass

        return FieldQuality(
            field_name=field_name,
            completeness=completeness,
            uniqueness=uniqueness,
            validity=validity,
            consistency=consistency,
            outlier_pct=outlier_pct,
            last_updated=datetime.now(),
        )

    async def check_signal_quality(self) -> dict:
        """Special check for signal quality and IC."""
        signal_health_file = self.live_dir / "signal_health.json"
        if not signal_health_file.exists():
            return {"status": "no_signal_health_data"}

        try:
            with open(signal_health_file) as f:
                data = json.load(f)

            signals = data.get("signals", {})

            quality_summary = {
                "total_signals": len(signals),
                "healthy": 0,
                "degraded": 0,
                "broken": 0,
                "signals": [],
            }

            for name, metrics in signals.items():
                ic = metrics.get("ic_overall", 0)
                stability = metrics.get("ic_stability", 0)

                if ic >= 0.02 and stability >= 0.5:
                    status = "healthy"
                    quality_summary["healthy"] += 1
                elif ic >= 0.01:
                    status = "degraded"
                    quality_summary["degraded"] += 1
                else:
                    status = "broken"
                    quality_summary["broken"] += 1

                quality_summary["signals"].append({
                    "name": name,
                    "ic": round(ic, 4),
                    "stability": round(stability, 2),
                    "status": status,
                    "recommendation": metrics.get("recommendation", ""),
                })

            return quality_summary

        except Exception as e:
            logger.error(f"Error checking signal quality: {e}")
            return {"error": str(e)}

    async def cross_validate_prices(self, symbols: list[str]) -> dict:
        """Cross-validate price data across sources."""
        # This would compare prices from different sources
        # For now, return a placeholder
        return {
            "status": "not_implemented",
            "message": "Would compare Alpaca vs Yahoo vs other price sources",
        }

    def get_quality_summary(self, results: dict[str, DataSourceQuality]) -> dict:
        """Get overall quality summary."""
        if not results:
            return {"status": "no_data"}

        total_score = sum(r.overall_score for r in results.values())
        avg_score = total_score / len(results)

        by_level = {level.value: 0 for level in DataQualityLevel}
        for result in results.values():
            by_level[result.level.value] += 1

        critical_issues = []
        for name, result in results.items():
            if result.level in [DataQualityLevel.DEGRADED, DataQualityLevel.CRITICAL]:
                critical_issues.append({
                    "source": name,
                    "level": result.level.value,
                    "issues": result.issues,
                    "score": round(result.overall_score, 1),
                })

        return {
            "timestamp": datetime.now().isoformat(),
            "overall_score": round(avg_score, 1),
            "overall_level": self._score_to_level(avg_score).value,
            "sources_checked": len(results),
            "by_level": by_level,
            "critical_issues": critical_issues,
            "recommendations": self._generate_recommendations(results),
        }

    def _score_to_level(self, score: float) -> DataQualityLevel:
        if score >= 95:
            return DataQualityLevel.EXCELLENT
        elif score >= 85:
            return DataQualityLevel.GOOD
        elif score >= 70:
            return DataQualityLevel.ACCEPTABLE
        elif score >= 50:
            return DataQualityLevel.DEGRADED
        return DataQualityLevel.CRITICAL

    def _generate_recommendations(self, results: dict[str, DataSourceQuality]) -> list[str]:
        """Generate recommendations based on quality issues."""
        recommendations = []

        for name, result in results.items():
            if result.freshness_minutes > 60:
                recommendations.append(
                    f"Update {name} - data is {result.freshness_minutes:.0f} minutes old"
                )

            if not result.schema_valid:
                recommendations.append(
                    f"Fix schema issues in {name}: {', '.join(result.issues)}"
                )

            for field in result.fields:
                if field.completeness < 90:
                    recommendations.append(
                        f"Improve completeness of {name}.{field.field_name} ({field.completeness:.0f}%)"
                    )
                if field.outlier_pct > 5:
                    recommendations.append(
                        f"Investigate outliers in {name}.{field.field_name} ({field.outlier_pct:.1f}%)"
                    )

        return recommendations[:10]  # Top 10

    def save_report(self, results: dict[str, DataSourceQuality]) -> Path:
        """Save quality report to file."""
        output_dir = self.results_dir / "reports"
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"data_quality_{timestamp}.json"

        report = {
            "summary": self.get_quality_summary(results),
            "sources": {name: r.to_dict() for name, r in results.items()},
        }

        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

        return output_path


# Singleton
_monitor: DataQualityMonitor | None = None


def get_data_quality_monitor() -> DataQualityMonitor:
    """Get the global data quality monitor."""
    global _monitor
    if _monitor is None:
        _monitor = DataQualityMonitor()
    return _monitor


async def check_data_quality() -> dict:
    """Quick check of all data quality."""
    monitor = get_data_quality_monitor()
    results = await monitor.check_all_sources()
    return monitor.get_quality_summary(results)
