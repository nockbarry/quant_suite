"""Weather data source for weather-based trading strategies.

Weather can impact various sectors:
- Agriculture (crop yields)
- Energy (heating/cooling demand)
- Retail (foot traffic)
- Construction (work days)
- Transportation (delays)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import httpx
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class WeatherData:
    """Weather data point."""

    location: str
    timestamp: datetime
    temperature: float  # Celsius
    temperature_feels_like: float | None = None
    humidity: float | None = None  # 0-100%
    precipitation: float | None = None  # mm
    wind_speed: float | None = None  # m/s
    cloud_cover: float | None = None  # 0-100%
    pressure: float | None = None  # hPa
    conditions: str | None = None  # e.g., "Clear", "Rain", "Snow"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "location": self.location,
            "timestamp": self.timestamp,
            "temperature": self.temperature,
            "temperature_feels_like": self.temperature_feels_like,
            "humidity": self.humidity,
            "precipitation": self.precipitation,
            "wind_speed": self.wind_speed,
            "cloud_cover": self.cloud_cover,
            "pressure": self.pressure,
            "conditions": self.conditions,
            **self.metadata,
        }


@dataclass
class LocationConfig:
    """Configuration for a location."""

    name: str
    lat: float
    lon: float
    timezone: str = "UTC"
    sector_relevance: list[str] = field(default_factory=list)


# Major financial/economic centers
MAJOR_LOCATIONS = {
    "new_york": LocationConfig("New York", 40.7128, -74.0060, "America/New_York", ["finance", "retail"]),
    "chicago": LocationConfig("Chicago", 41.8781, -87.6298, "America/Chicago", ["agriculture", "finance"]),
    "los_angeles": LocationConfig("Los Angeles", 34.0522, -118.2437, "America/Los_Angeles", ["retail", "entertainment"]),
    "houston": LocationConfig("Houston", 29.7604, -95.3698, "America/Chicago", ["energy", "oil"]),
    "london": LocationConfig("London", 51.5074, -0.1278, "Europe/London", ["finance"]),
    "tokyo": LocationConfig("Tokyo", 35.6762, 139.6503, "Asia/Tokyo", ["finance", "manufacturing"]),
    "shanghai": LocationConfig("Shanghai", 31.2304, 121.4737, "Asia/Shanghai", ["manufacturing", "shipping"]),
    "frankfurt": LocationConfig("Frankfurt", 50.1109, 8.6821, "Europe/Berlin", ["finance"]),
    "dubai": LocationConfig("Dubai", 25.2048, 55.2708, "Asia/Dubai", ["energy", "finance"]),
    "singapore": LocationConfig("Singapore", 1.3521, 103.8198, "Asia/Singapore", ["finance", "shipping"]),
}

# US agricultural regions
AGRICULTURAL_REGIONS = {
    "corn_belt": LocationConfig("Des Moines", 41.5868, -93.6250, "America/Chicago", ["agriculture", "corn"]),
    "wheat_belt": LocationConfig("Wichita", 37.6872, -97.3301, "America/Chicago", ["agriculture", "wheat"]),
    "california_central": LocationConfig("Fresno", 36.7378, -119.7871, "America/Los_Angeles", ["agriculture", "fruits"]),
    "florida": LocationConfig("Orlando", 28.5383, -81.3792, "America/New_York", ["agriculture", "citrus", "tourism"]),
    "texas_plains": LocationConfig("Lubbock", 33.5779, -101.8552, "America/Chicago", ["agriculture", "cotton"]),
}


class WeatherDataSource:
    """
    Weather data source using Open-Meteo API.

    Open-Meteo is a free, open-source weather API that doesn't require
    an API key for non-commercial use.
    """

    name = "weather"
    BASE_URL = "https://api.open-meteo.com/v1"

    def __init__(
        self,
        locations: dict[str, LocationConfig] | None = None,
        include_major_cities: bool = True,
        include_agricultural: bool = True,
    ):
        """
        Initialize weather data source.

        Args:
            locations: Custom locations to track
            include_major_cities: Include major financial centers
            include_agricultural: Include US agricultural regions
        """
        self.locations = {}

        if include_major_cities:
            self.locations.update(MAJOR_LOCATIONS)

        if include_agricultural:
            self.locations.update(AGRICULTURAL_REGIONS)

        if locations:
            self.locations.update(locations)

        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={"User-Agent": "QuantSuite/1.0"},
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def fetch_current(
        self,
        location_key: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
    ) -> WeatherData | None:
        """
        Fetch current weather for a location.

        Args:
            location_key: Key from configured locations
            lat: Latitude (if not using location_key)
            lon: Longitude (if not using location_key)

        Returns:
            WeatherData object or None
        """
        if location_key:
            if location_key not in self.locations:
                logger.warning(f"Unknown location: {location_key}")
                return None
            loc = self.locations[location_key]
            lat, lon = loc.lat, loc.lon
            location_name = loc.name
        elif lat is not None and lon is not None:
            location_name = f"{lat:.2f},{lon:.2f}"
        else:
            logger.error("Must provide location_key or lat/lon")
            return None

        client = await self._get_client()

        try:
            response = await client.get(
                f"{self.BASE_URL}/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,apparent_temperature,"
                              "precipitation,weather_code,cloud_cover,pressure_msl,wind_speed_10m",
                    "timezone": "auto",
                },
            )
            response.raise_for_status()
            data = response.json()

            current = data.get("current", {})

            return WeatherData(
                location=location_name,
                timestamp=datetime.fromisoformat(current.get("time", datetime.now().isoformat())),
                temperature=current.get("temperature_2m", 0),
                temperature_feels_like=current.get("apparent_temperature"),
                humidity=current.get("relative_humidity_2m"),
                precipitation=current.get("precipitation"),
                wind_speed=current.get("wind_speed_10m"),
                cloud_cover=current.get("cloud_cover"),
                pressure=current.get("pressure_msl"),
                conditions=self._decode_weather_code(current.get("weather_code", 0)),
            )

        except Exception as e:
            logger.error(f"Weather fetch error for {location_name}: {e}")
            return None

    async def fetch_historical(
        self,
        location_key: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        """
        Fetch historical weather data.

        Args:
            location_key: Key from configured locations
            lat: Latitude
            lon: Longitude
            start: Start date
            end: End date

        Returns:
            DataFrame with daily weather data
        """
        if location_key:
            if location_key not in self.locations:
                logger.warning(f"Unknown location: {location_key}")
                return pd.DataFrame()
            loc = self.locations[location_key]
            lat, lon = loc.lat, loc.lon
            location_name = loc.name
        elif lat is not None and lon is not None:
            location_name = f"{lat:.2f},{lon:.2f}"
        else:
            return pd.DataFrame()

        end = end or datetime.now()
        start = start or (end - timedelta(days=365))

        client = await self._get_client()

        try:
            response = await client.get(
                f"{self.BASE_URL}/archive",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "start_date": start.strftime("%Y-%m-%d"),
                    "end_date": end.strftime("%Y-%m-%d"),
                    "daily": "temperature_2m_max,temperature_2m_min,temperature_2m_mean,"
                            "precipitation_sum,rain_sum,snowfall_sum,"
                            "wind_speed_10m_max,weather_code",
                    "timezone": "auto",
                },
            )
            response.raise_for_status()
            data = response.json()

            daily = data.get("daily", {})

            if not daily.get("time"):
                return pd.DataFrame()

            df = pd.DataFrame({
                "date": pd.to_datetime(daily["time"]),
                "temp_max": daily.get("temperature_2m_max"),
                "temp_min": daily.get("temperature_2m_min"),
                "temp_mean": daily.get("temperature_2m_mean"),
                "precipitation": daily.get("precipitation_sum"),
                "rain": daily.get("rain_sum"),
                "snow": daily.get("snowfall_sum"),
                "wind_max": daily.get("wind_speed_10m_max"),
                "weather_code": daily.get("weather_code"),
            })

            df["location"] = location_name
            df = df.set_index("date")

            # Add derived features
            df["temp_range"] = df["temp_max"] - df["temp_min"]
            df["conditions"] = df["weather_code"].apply(self._decode_weather_code)

            return df

        except Exception as e:
            logger.error(f"Historical weather fetch error: {e}")
            return pd.DataFrame()

    async def fetch_all_locations(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict[str, pd.DataFrame]:
        """
        Fetch historical data for all configured locations.

        Args:
            start: Start date
            end: End date

        Returns:
            Dict mapping location keys to DataFrames
        """
        results = {}

        # Rate limiting
        semaphore = asyncio.Semaphore(3)

        async def fetch_with_limit(key: str) -> tuple[str, pd.DataFrame]:
            async with semaphore:
                df = await self.fetch_historical(key, start=start, end=end)
                await asyncio.sleep(0.5)  # Rate limiting
                return key, df

        tasks = [fetch_with_limit(key) for key in self.locations]
        task_results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in task_results:
            if isinstance(result, tuple):
                key, df = result
                if not df.empty:
                    results[key] = df

        return results

    def _decode_weather_code(self, code: int | None) -> str:
        """Decode WMO weather code to description."""
        if code is None:
            return "Unknown"

        codes = {
            0: "Clear",
            1: "Mainly Clear",
            2: "Partly Cloudy",
            3: "Overcast",
            45: "Fog",
            48: "Depositing Rime Fog",
            51: "Light Drizzle",
            53: "Moderate Drizzle",
            55: "Dense Drizzle",
            61: "Slight Rain",
            63: "Moderate Rain",
            65: "Heavy Rain",
            71: "Slight Snow",
            73: "Moderate Snow",
            75: "Heavy Snow",
            77: "Snow Grains",
            80: "Slight Rain Showers",
            81: "Moderate Rain Showers",
            82: "Violent Rain Showers",
            85: "Slight Snow Showers",
            86: "Heavy Snow Showers",
            95: "Thunderstorm",
            96: "Thunderstorm with Hail",
            99: "Thunderstorm with Heavy Hail",
        }

        return codes.get(code, f"Code {code}")


class WeatherFeatureEngine:
    """
    Creates trading-relevant features from weather data.
    """

    @staticmethod
    def compute_heating_degree_days(temps: pd.Series, base: float = 18.0) -> pd.Series:
        """
        Compute Heating Degree Days (HDD).

        HDD measures energy demand for heating.

        Args:
            temps: Temperature series (Celsius)
            base: Base temperature (18C/65F typical)

        Returns:
            HDD series
        """
        return (base - temps).clip(lower=0)

    @staticmethod
    def compute_cooling_degree_days(temps: pd.Series, base: float = 18.0) -> pd.Series:
        """
        Compute Cooling Degree Days (CDD).

        CDD measures energy demand for cooling.

        Args:
            temps: Temperature series (Celsius)
            base: Base temperature

        Returns:
            CDD series
        """
        return (temps - base).clip(lower=0)

    @staticmethod
    def compute_growing_degree_days(
        temp_min: pd.Series,
        temp_max: pd.Series,
        base: float = 10.0,
        cap: float = 30.0,
    ) -> pd.Series:
        """
        Compute Growing Degree Days (GDD).

        GDD measures accumulated heat for crop growth.

        Args:
            temp_min: Minimum temperature series
            temp_max: Maximum temperature series
            base: Base temperature for growth
            cap: Maximum effective temperature

        Returns:
            GDD series
        """
        temp_avg = (temp_min.clip(lower=base, upper=cap) +
                    temp_max.clip(lower=base, upper=cap)) / 2
        return (temp_avg - base).clip(lower=0)

    @staticmethod
    def compute_weather_anomaly(
        values: pd.Series,
        window: int = 30,
    ) -> pd.Series:
        """
        Compute weather anomaly (deviation from rolling mean).

        Args:
            values: Weather metric series
            window: Rolling window for baseline

        Returns:
            Anomaly series (z-scores)
        """
        rolling_mean = values.rolling(window).mean()
        rolling_std = values.rolling(window).std()
        return (values - rolling_mean) / rolling_std.clip(lower=0.01)

    @staticmethod
    def compute_extreme_weather_indicator(
        weather_codes: pd.Series,
        extreme_codes: list[int] | None = None,
    ) -> pd.Series:
        """
        Create binary indicator for extreme weather events.

        Args:
            weather_codes: WMO weather code series
            extreme_codes: Codes to consider extreme

        Returns:
            Binary series (1 = extreme weather)
        """
        if extreme_codes is None:
            # Heavy rain, heavy snow, thunderstorms
            extreme_codes = [65, 75, 82, 86, 95, 96, 99]

        return weather_codes.isin(extreme_codes).astype(int)

    @staticmethod
    def add_all_features(df: pd.DataFrame) -> pd.DataFrame:
        """
        Add all weather-derived features to DataFrame.

        Args:
            df: DataFrame with weather columns

        Returns:
            DataFrame with added features
        """
        df = df.copy()

        # Temperature features
        if "temp_mean" in df.columns:
            df["hdd"] = WeatherFeatureEngine.compute_heating_degree_days(df["temp_mean"])
            df["cdd"] = WeatherFeatureEngine.compute_cooling_degree_days(df["temp_mean"])
            df["temp_anomaly"] = WeatherFeatureEngine.compute_weather_anomaly(df["temp_mean"])

        if "temp_min" in df.columns and "temp_max" in df.columns:
            df["gdd"] = WeatherFeatureEngine.compute_growing_degree_days(
                df["temp_min"], df["temp_max"]
            )

        # Precipitation features
        if "precipitation" in df.columns:
            df["precip_anomaly"] = WeatherFeatureEngine.compute_weather_anomaly(df["precipitation"])
            df["dry_day"] = (df["precipitation"] < 1).astype(int)
            df["wet_day"] = (df["precipitation"] >= 10).astype(int)

        # Extreme weather
        if "weather_code" in df.columns:
            df["extreme_weather"] = WeatherFeatureEngine.compute_extreme_weather_indicator(
                df["weather_code"]
            )

        # Rolling aggregates
        for col in ["temp_mean", "precipitation"]:
            if col in df.columns:
                df[f"{col}_7d_avg"] = df[col].rolling(7).mean()
                df[f"{col}_30d_avg"] = df[col].rolling(30).mean()

        # Cumulative degree days (seasonal)
        for col in ["hdd", "cdd", "gdd"]:
            if col in df.columns:
                df[f"{col}_cumsum"] = df[col].cumsum()

        return df


def get_sector_locations(sector: str) -> list[str]:
    """
    Get relevant locations for a sector.

    Args:
        sector: Sector name (e.g., "energy", "agriculture")

    Returns:
        List of location keys
    """
    all_locations = {**MAJOR_LOCATIONS, **AGRICULTURAL_REGIONS}

    return [
        key for key, config in all_locations.items()
        if sector.lower() in [s.lower() for s in config.sector_relevance]
    ]
