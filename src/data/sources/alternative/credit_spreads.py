"""Credit Spreads Data Source - FRED HY OAS and Credit Stress Indicators.

Credit spreads are leading indicators of equity weakness:
- HY OAS (High Yield Option-Adjusted Spread) widening precedes SPX drops
- IG spreads measure investment grade stress
- Credit leads equity by 1-3 weeks typically

Data Source: FRED (Federal Reserve Economic Data)
- Free, reliable, daily updates
- Series: BAMLH0A0HYM2 (ICE BofA HY OAS)

Created: 2026-01-20
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class CreditSpreadData:
    """Credit spread data point."""

    timestamp: datetime
    hy_oas: float  # High Yield OAS in basis points
    hy_oas_zscore: Optional[float] = None  # Z-score vs 30-day rolling
    hy_oas_change_1d: Optional[float] = None  # 1-day change in bps
    hy_oas_change_5d: Optional[float] = None  # 5-day change in bps
    hy_oas_percentile: Optional[float] = None  # Historical percentile (0-100)

    ig_oas: Optional[float] = None  # Investment Grade OAS

    stress_signal: str = "neutral"  # "stress", "elevated", "neutral", "complacent"
    equity_warning: bool = False  # True if credit is warning

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "hy_oas": self.hy_oas,
            "hy_oas_zscore": self.hy_oas_zscore,
            "hy_oas_change_1d": self.hy_oas_change_1d,
            "hy_oas_change_5d": self.hy_oas_change_5d,
            "hy_oas_percentile": self.hy_oas_percentile,
            "ig_oas": self.ig_oas,
            "stress_signal": self.stress_signal,
            "equity_warning": self.equity_warning,
        }


class FREDCreditSpreads:
    """Fetch credit spread data from FRED.

    Uses FRED's free API (no key required for basic access).

    Key series:
    - BAMLH0A0HYM2: ICE BofA US High Yield Index Option-Adjusted Spread
    - BAMLC0A0CM: ICE BofA US Corporate Index Option-Adjusted Spread (IG)
    """

    BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

    # FRED series IDs
    HY_OAS_SERIES = "BAMLH0A0HYM2"  # High Yield OAS
    IG_OAS_SERIES = "BAMLC0A0CM"    # Investment Grade OAS

    # Historical thresholds (based on typical ranges)
    HY_STRESS_THRESHOLD = 500     # Above 500 bps = stress
    HY_ELEVATED_THRESHOLD = 400   # Above 400 bps = elevated
    HY_COMPLACENT_THRESHOLD = 300 # Below 300 bps = complacent

    def __init__(self, api_key: Optional[str] = None):
        """Initialize FRED client.

        Args:
            api_key: FRED API key. If None, uses limited access (fine for daily updates).
        """
        self.api_key = api_key
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def fetch_series(
        self,
        series_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """Fetch a FRED series.

        Args:
            series_id: FRED series ID
            start_date: Start date for data
            end_date: End date for data

        Returns:
            DataFrame with date and value columns
        """
        # FRED API requires an API key - check if we have one
        if not self.api_key:
            # Try to load from config
            try:
                import yaml
                config_path = Path(__file__).parent.parent.parent.parent.parent / "config" / "credentials.yaml"
                if config_path.exists():
                    with open(config_path) as f:
                        creds = yaml.safe_load(f)
                    self.api_key = creds.get("fred", {}).get("api_key")
            except Exception:
                pass

        if not self.api_key:
            logger.warning("FRED API key not configured. Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html")
            return pd.DataFrame()

        client = await self._get_client()

        end_date = end_date or datetime.now()
        start_date = start_date or (end_date - timedelta(days=365))

        params = {
            "series_id": series_id,
            "observation_start": start_date.strftime("%Y-%m-%d"),
            "observation_end": end_date.strftime("%Y-%m-%d"),
            "file_type": "json",
            "api_key": self.api_key,
        }

        try:
            response = await client.get(self.BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()

            observations = data.get("observations", [])

            if not observations:
                return pd.DataFrame()

            df = pd.DataFrame(observations)
            df["date"] = pd.to_datetime(df["date"])
            df["value"] = pd.to_numeric(df["value"], errors="coerce")
            df = df.dropna(subset=["value"])
            df = df.set_index("date")

            return df[["value"]]

        except Exception as e:
            logger.error(f"FRED fetch failed for {series_id}: {e}")
            return pd.DataFrame()

    async def get_current_spreads(self) -> Optional[CreditSpreadData]:
        """Get current credit spread data with analysis.

        Returns:
            CreditSpreadData with current spreads and signals
        """
        # Fetch HY OAS
        hy_df = await self.fetch_series(
            self.HY_OAS_SERIES,
            start_date=datetime.now() - timedelta(days=365),
        )

        if hy_df.empty:
            logger.warning("No HY OAS data available")
            return None

        # Get latest value
        latest_hy = float(hy_df["value"].iloc[-1])
        latest_date = hy_df.index[-1]

        # Calculate metrics
        hy_series = hy_df["value"]

        # Z-score vs 30-day rolling mean
        rolling_mean = hy_series.rolling(30).mean()
        rolling_std = hy_series.rolling(30).std()
        if len(hy_series) >= 30:
            zscore = (latest_hy - rolling_mean.iloc[-1]) / rolling_std.iloc[-1]
        else:
            zscore = None

        # Changes
        change_1d = latest_hy - hy_series.iloc[-2] if len(hy_series) >= 2 else None
        change_5d = latest_hy - hy_series.iloc[-5] if len(hy_series) >= 5 else None

        # Historical percentile
        percentile = (hy_series < latest_hy).sum() / len(hy_series) * 100

        # Fetch IG OAS
        ig_df = await self.fetch_series(
            self.IG_OAS_SERIES,
            start_date=datetime.now() - timedelta(days=30),
        )
        ig_oas = float(ig_df["value"].iloc[-1]) if not ig_df.empty else None

        # Determine stress signal
        if latest_hy >= self.HY_STRESS_THRESHOLD:
            stress_signal = "stress"
        elif latest_hy >= self.HY_ELEVATED_THRESHOLD:
            stress_signal = "elevated"
        elif latest_hy <= self.HY_COMPLACENT_THRESHOLD:
            stress_signal = "complacent"
        else:
            stress_signal = "neutral"

        # Equity warning: HY spread widening rapidly
        equity_warning = False
        if zscore and zscore > 1.5:
            equity_warning = True
        if change_5d and change_5d > 50:  # 50 bps widening in 5 days
            equity_warning = True

        return CreditSpreadData(
            timestamp=datetime.now(),
            hy_oas=latest_hy,
            hy_oas_zscore=zscore,
            hy_oas_change_1d=change_1d,
            hy_oas_change_5d=change_5d,
            hy_oas_percentile=percentile,
            ig_oas=ig_oas,
            stress_signal=stress_signal,
            equity_warning=equity_warning,
        )

    async def get_historical(self, days: int = 252) -> pd.DataFrame:
        """Get historical credit spread data.

        Args:
            days: Number of days of history

        Returns:
            DataFrame with HY and IG OAS
        """
        start = datetime.now() - timedelta(days=days)

        hy_df = await self.fetch_series(self.HY_OAS_SERIES, start_date=start)
        ig_df = await self.fetch_series(self.IG_OAS_SERIES, start_date=start)

        # Combine
        df = pd.DataFrame()
        if not hy_df.empty:
            df["hy_oas"] = hy_df["value"]
        if not ig_df.empty:
            df["ig_oas"] = ig_df["value"]

        if not df.empty:
            df["hy_ig_ratio"] = df["hy_oas"] / df["ig_oas"] if "ig_oas" in df.columns else None

            # Add features
            df["hy_oas_sma20"] = df["hy_oas"].rolling(20).mean()
            df["hy_oas_zscore"] = (df["hy_oas"] - df["hy_oas"].rolling(30).mean()) / df["hy_oas"].rolling(30).std()
            df["hy_oas_pct_change_5d"] = df["hy_oas"].pct_change(5) * 100

        return df


# Convenience function
async def get_credit_spreads() -> Optional[CreditSpreadData]:
    """Quick function to get current credit spreads."""
    source = FREDCreditSpreads()
    try:
        return await source.get_current_spreads()
    finally:
        await source.close()


if __name__ == "__main__":
    async def main():
        source = FREDCreditSpreads()
        try:
            data = await source.get_current_spreads()
            if data:
                print(f"HY OAS: {data.hy_oas:.1f} bps")
                print(f"Z-score: {data.hy_oas_zscore:.2f}" if data.hy_oas_zscore else "Z-score: N/A")
                print(f"5d Change: {data.hy_oas_change_5d:+.1f} bps" if data.hy_oas_change_5d else "5d Change: N/A")
                print(f"Percentile: {data.hy_oas_percentile:.1f}%")
                print(f"Signal: {data.stress_signal}")
                print(f"Equity Warning: {data.equity_warning}")
        finally:
            await source.close()

    asyncio.run(main())
