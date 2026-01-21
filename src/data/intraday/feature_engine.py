"""
Intraday Feature Engine

Provides real-time intraday features for day trading:
- VWAP (Volume Weighted Average Price)
- Opening Range Breakout (ORB)
- Volume Profile
- Intraday momentum indicators
- Market microstructure features

All features are designed for 1min, 5min, 15min timeframes.
"""

from dataclasses import dataclass, field
from datetime import datetime, time, date, timedelta
from typing import Optional, Tuple
from enum import Enum
import pandas as pd
import numpy as np


class MarketSession(Enum):
    """Trading session periods."""
    PRE_MARKET = "pre_market"
    OPENING_RANGE = "opening_range"  # First 15-30 min
    MORNING = "morning"
    MIDDAY = "midday"
    AFTERNOON = "afternoon"
    CLOSE = "close"  # Last 30 min
    AFTER_HOURS = "after_hours"


class ORBSignal(Enum):
    """Opening Range Breakout signal types."""
    BREAKOUT_UP = "breakout_up"
    BREAKOUT_DOWN = "breakout_down"
    FAILED_BREAKOUT_UP = "failed_breakout_up"
    FAILED_BREAKOUT_DOWN = "failed_breakout_down"
    RANGE_BOUND = "range_bound"
    NO_SIGNAL = "no_signal"


@dataclass
class VWAPData:
    """VWAP calculation results."""
    vwap: float
    upper_band_1: float  # +1 std dev
    upper_band_2: float  # +2 std dev
    lower_band_1: float  # -1 std dev
    lower_band_2: float  # -2 std dev
    std_dev: float

    # Price position
    current_price: float
    distance_from_vwap: float  # As percentage
    band_position: str  # "above_2", "above_1", "at_vwap", "below_1", "below_2"

    # Trend
    vwap_slope: float  # Rising/falling
    price_vs_vwap_trend: str  # "crossing_up", "crossing_down", "above", "below"


@dataclass
class OpeningRangeData:
    """Opening Range analysis results."""
    or_high: float
    or_low: float
    or_range: float
    or_midpoint: float
    or_range_pct: float  # Range as % of price

    # Current status
    current_price: float
    signal: ORBSignal
    breakout_strength: float  # 0-1, how far beyond OR

    # Historical context
    avg_or_range: float  # Average OR range for this symbol
    or_range_percentile: float  # Today's OR vs history


@dataclass
class VolumeProfileData:
    """Volume profile analysis."""
    poc: float  # Point of Control (highest volume price)
    value_area_high: float  # VAH - top of 70% volume
    value_area_low: float  # VAL - bottom of 70% volume

    # Current context
    current_price: float
    price_vs_poc: str  # "above", "below", "at"
    in_value_area: bool

    # Volume distribution
    high_volume_nodes: list[float]  # Price levels with high volume
    low_volume_nodes: list[float]  # Price levels with low volume (potential fast moves)


@dataclass
class IntradayMomentum:
    """Intraday momentum indicators."""
    # Rate of change
    roc_5min: float
    roc_15min: float
    roc_30min: float

    # Velocity and acceleration
    price_velocity: float  # Points per minute
    price_acceleration: float  # Change in velocity

    # Tick-based
    tick_trend: str  # "positive", "negative", "neutral"
    cumulative_tick: int  # If available

    # Breadth proxy
    sector_alignment: float  # -1 to 1, how aligned with sector


@dataclass
class IntradayFeatures:
    """
    Complete intraday feature set for a symbol at a point in time.
    """
    timestamp: datetime
    symbol: str
    timeframe: str

    # Core features
    vwap: VWAPData
    opening_range: OpeningRangeData
    volume_profile: VolumeProfileData
    momentum: IntradayMomentum

    # Session context
    session: MarketSession
    minutes_into_session: int
    minutes_remaining: int

    # Price levels
    premarket_high: Optional[float] = None
    premarket_low: Optional[float] = None
    previous_close: Optional[float] = None
    daily_high: float = 0.0
    daily_low: float = 0.0

    # Volume context
    relative_volume: float = 1.0  # vs average for this time of day
    cumulative_volume: int = 0
    volume_trend: str = "neutral"

    # Volatility
    intraday_atr: float = 0.0
    volatility_regime: str = "normal"  # "low", "normal", "high", "extreme"

    # ML-ready features
    feature_vector: dict = field(default_factory=dict)

    # Agent summary
    summary: str = ""
    trading_bias: str = "neutral"
    key_levels: list[Tuple[float, str]] = field(default_factory=list)


class IntradayFeatureEngine:
    """
    Calculates real-time intraday features for day trading.
    """

    # Market hours (ET)
    MARKET_OPEN = time(9, 30)
    MARKET_CLOSE = time(16, 0)
    OPENING_RANGE_END = time(9, 45)  # 15-min OR by default

    def __init__(self, opening_range_minutes: int = 15):
        self.opening_range_minutes = opening_range_minutes
        self.or_end_time = time(
            9, 30 + opening_range_minutes
        ) if opening_range_minutes < 30 else time(10, opening_range_minutes - 30)

    def get_session(self, dt: datetime) -> MarketSession:
        """Determine current market session."""
        t = dt.time()

        if t < time(9, 30):
            return MarketSession.PRE_MARKET
        elif t < self.or_end_time:
            return MarketSession.OPENING_RANGE
        elif t < time(11, 30):
            return MarketSession.MORNING
        elif t < time(14, 0):
            return MarketSession.MIDDAY
        elif t < time(15, 30):
            return MarketSession.AFTERNOON
        elif t < time(16, 0):
            return MarketSession.CLOSE
        else:
            return MarketSession.AFTER_HOURS

    def calculate_vwap(self, df: pd.DataFrame) -> VWAPData:
        """
        Calculate VWAP and bands for intraday data.
        Expects DataFrame with 'High', 'Low', 'Close', 'Volume' columns.
        """
        if len(df) < 2:
            current = float(df.iloc[-1]['Close']) if len(df) > 0 else 0
            return VWAPData(
                vwap=current, upper_band_1=current, upper_band_2=current,
                lower_band_1=current, lower_band_2=current, std_dev=0,
                current_price=current, distance_from_vwap=0, band_position="at_vwap",
                vwap_slope=0, price_vs_vwap_trend="at"
            )

        # Typical price
        typical_price = (df['High'] + df['Low'] + df['Close']) / 3

        # Cumulative VWAP
        cumulative_tp_vol = (typical_price * df['Volume']).cumsum()
        cumulative_vol = df['Volume'].cumsum()

        vwap_series = cumulative_tp_vol / cumulative_vol
        vwap = float(vwap_series.iloc[-1])

        # Standard deviation bands
        squared_diff = ((typical_price - vwap_series) ** 2 * df['Volume']).cumsum()
        variance = squared_diff / cumulative_vol
        std_dev = float(np.sqrt(variance.iloc[-1]))

        current_price = float(df.iloc[-1]['Close'])

        # Band position
        if current_price > vwap + 2 * std_dev:
            band_position = "above_2"
        elif current_price > vwap + std_dev:
            band_position = "above_1"
        elif current_price < vwap - 2 * std_dev:
            band_position = "below_2"
        elif current_price < vwap - std_dev:
            band_position = "below_1"
        else:
            band_position = "at_vwap"

        # VWAP slope (last 10 periods)
        if len(vwap_series) >= 10:
            vwap_slope = float(vwap_series.iloc[-1] - vwap_series.iloc[-10])
        else:
            vwap_slope = 0

        # Price vs VWAP trend
        if len(df) >= 3:
            prev_close = float(df.iloc[-2]['Close'])
            prev_vwap = float(vwap_series.iloc[-2])
            was_above = prev_close > prev_vwap
            is_above = current_price > vwap

            if not was_above and is_above:
                trend = "crossing_up"
            elif was_above and not is_above:
                trend = "crossing_down"
            elif is_above:
                trend = "above"
            else:
                trend = "below"
        else:
            trend = "above" if current_price > vwap else "below"

        return VWAPData(
            vwap=vwap,
            upper_band_1=vwap + std_dev,
            upper_band_2=vwap + 2 * std_dev,
            lower_band_1=vwap - std_dev,
            lower_band_2=vwap - 2 * std_dev,
            std_dev=std_dev,
            current_price=current_price,
            distance_from_vwap=(current_price - vwap) / vwap * 100 if vwap > 0 else 0,
            band_position=band_position,
            vwap_slope=vwap_slope,
            price_vs_vwap_trend=trend,
        )

    def calculate_opening_range(
        self,
        df: pd.DataFrame,
        historical_or_ranges: Optional[list[float]] = None
    ) -> OpeningRangeData:
        """
        Calculate Opening Range and breakout status.
        df should contain only today's data, starting from market open.
        """
        if len(df) < 1:
            return OpeningRangeData(
                or_high=0, or_low=0, or_range=0, or_midpoint=0, or_range_pct=0,
                current_price=0, signal=ORBSignal.NO_SIGNAL, breakout_strength=0,
                avg_or_range=0, or_range_percentile=0
            )

        # Filter to opening range period
        or_mask = pd.Series([True] * len(df))  # Default all True
        if hasattr(df.index[0], 'time'):
            or_mask = df.index.map(lambda x: x.time() <= self.or_end_time)

        or_data = df[or_mask]

        if len(or_data) < 1:
            # OR not formed yet, use available data
            or_data = df

        or_high = float(or_data['High'].max())
        or_low = float(or_data['Low'].min())
        or_range = or_high - or_low
        or_midpoint = (or_high + or_low) / 2

        current_price = float(df.iloc[-1]['Close'])
        or_range_pct = or_range / or_midpoint * 100 if or_midpoint > 0 else 0

        # Determine signal
        signal = ORBSignal.RANGE_BOUND
        breakout_strength = 0

        if current_price > or_high:
            # Check if we previously broke out and came back
            if len(df) > len(or_data):
                post_or = df[~or_mask] if len(df[~or_mask]) > 0 else df
                if len(post_or) > 1:
                    # Was above OR high, now back in range?
                    prev_above = float(post_or.iloc[-2]['Close']) > or_high if len(post_or) >= 2 else False
                    if current_price <= or_high and prev_above:
                        signal = ORBSignal.FAILED_BREAKOUT_UP
                    else:
                        signal = ORBSignal.BREAKOUT_UP
                        breakout_strength = (current_price - or_high) / or_range if or_range > 0 else 0
                else:
                    signal = ORBSignal.BREAKOUT_UP
                    breakout_strength = (current_price - or_high) / or_range if or_range > 0 else 0
            else:
                signal = ORBSignal.BREAKOUT_UP
                breakout_strength = (current_price - or_high) / or_range if or_range > 0 else 0

        elif current_price < or_low:
            if len(df) > len(or_data):
                post_or = df[~or_mask] if len(df[~or_mask]) > 0 else df
                if len(post_or) > 1:
                    prev_below = float(post_or.iloc[-2]['Close']) < or_low if len(post_or) >= 2 else False
                    if current_price >= or_low and prev_below:
                        signal = ORBSignal.FAILED_BREAKOUT_DOWN
                    else:
                        signal = ORBSignal.BREAKOUT_DOWN
                        breakout_strength = (or_low - current_price) / or_range if or_range > 0 else 0
                else:
                    signal = ORBSignal.BREAKOUT_DOWN
                    breakout_strength = (or_low - current_price) / or_range if or_range > 0 else 0
            else:
                signal = ORBSignal.BREAKOUT_DOWN
                breakout_strength = (or_low - current_price) / or_range if or_range > 0 else 0

        # Historical context
        avg_or_range = np.mean(historical_or_ranges) if historical_or_ranges else or_range
        if historical_or_ranges:
            or_range_percentile = sum(1 for r in historical_or_ranges if r <= or_range) / len(historical_or_ranges)
        else:
            or_range_percentile = 0.5

        return OpeningRangeData(
            or_high=or_high,
            or_low=or_low,
            or_range=or_range,
            or_midpoint=or_midpoint,
            or_range_pct=or_range_pct,
            current_price=current_price,
            signal=signal,
            breakout_strength=min(1.0, breakout_strength),
            avg_or_range=avg_or_range,
            or_range_percentile=or_range_percentile,
        )

    def calculate_volume_profile(
        self,
        df: pd.DataFrame,
        num_bins: int = 20
    ) -> VolumeProfileData:
        """
        Calculate volume profile for the session.
        """
        if len(df) < 5:
            current = float(df.iloc[-1]['Close']) if len(df) > 0 else 0
            return VolumeProfileData(
                poc=current, value_area_high=current, value_area_low=current,
                current_price=current, price_vs_poc="at", in_value_area=True,
                high_volume_nodes=[], low_volume_nodes=[]
            )

        # Price range
        price_high = df['High'].max()
        price_low = df['Low'].min()
        price_range = price_high - price_low

        if price_range == 0:
            current = float(df.iloc[-1]['Close'])
            return VolumeProfileData(
                poc=current, value_area_high=current, value_area_low=current,
                current_price=current, price_vs_poc="at", in_value_area=True,
                high_volume_nodes=[], low_volume_nodes=[]
            )

        # Create price bins
        bin_size = price_range / num_bins
        bins = np.linspace(price_low, price_high, num_bins + 1)
        bin_centers = (bins[:-1] + bins[1:]) / 2

        # Distribute volume to bins
        volume_at_price = np.zeros(num_bins)

        for _, row in df.iterrows():
            # Distribute candle's volume across its range
            candle_low = row['Low']
            candle_high = row['High']
            candle_volume = row['Volume']

            for i, (bin_low, bin_high) in enumerate(zip(bins[:-1], bins[1:])):
                # Overlap between candle and bin
                overlap_low = max(candle_low, bin_low)
                overlap_high = min(candle_high, bin_high)

                if overlap_high > overlap_low:
                    overlap_pct = (overlap_high - overlap_low) / (candle_high - candle_low) if candle_high > candle_low else 1
                    volume_at_price[i] += candle_volume * overlap_pct

        # Point of Control (highest volume)
        poc_idx = np.argmax(volume_at_price)
        poc = float(bin_centers[poc_idx])

        # Value Area (70% of volume)
        total_volume = volume_at_price.sum()
        target_volume = total_volume * 0.7

        # Start from POC and expand outward
        va_low_idx = poc_idx
        va_high_idx = poc_idx
        current_volume = volume_at_price[poc_idx]

        while current_volume < target_volume:
            # Add whichever side has more volume
            low_vol = volume_at_price[va_low_idx - 1] if va_low_idx > 0 else 0
            high_vol = volume_at_price[va_high_idx + 1] if va_high_idx < num_bins - 1 else 0

            if low_vol >= high_vol and va_low_idx > 0:
                va_low_idx -= 1
                current_volume += low_vol
            elif va_high_idx < num_bins - 1:
                va_high_idx += 1
                current_volume += high_vol
            else:
                break

        value_area_high = float(bins[va_high_idx + 1])
        value_area_low = float(bins[va_low_idx])

        current_price = float(df.iloc[-1]['Close'])

        # High/low volume nodes
        avg_volume = volume_at_price.mean()
        high_volume_nodes = [float(bin_centers[i]) for i in range(num_bins) if volume_at_price[i] > avg_volume * 1.5]
        low_volume_nodes = [float(bin_centers[i]) for i in range(num_bins) if volume_at_price[i] < avg_volume * 0.5]

        return VolumeProfileData(
            poc=poc,
            value_area_high=value_area_high,
            value_area_low=value_area_low,
            current_price=current_price,
            price_vs_poc="above" if current_price > poc * 1.001 else "below" if current_price < poc * 0.999 else "at",
            in_value_area=value_area_low <= current_price <= value_area_high,
            high_volume_nodes=high_volume_nodes[:5],  # Top 5
            low_volume_nodes=low_volume_nodes[:5],
        )

    def calculate_momentum(self, df: pd.DataFrame) -> IntradayMomentum:
        """Calculate intraday momentum indicators."""
        if len(df) < 30:
            return IntradayMomentum(
                roc_5min=0, roc_15min=0, roc_30min=0,
                price_velocity=0, price_acceleration=0,
                tick_trend="neutral", cumulative_tick=0,
                sector_alignment=0
            )

        closes = df['Close']

        # Rate of change
        roc_5 = (closes.iloc[-1] / closes.iloc[-5] - 1) * 100 if len(df) >= 5 else 0
        roc_15 = (closes.iloc[-1] / closes.iloc[-15] - 1) * 100 if len(df) >= 15 else 0
        roc_30 = (closes.iloc[-1] / closes.iloc[-30] - 1) * 100 if len(df) >= 30 else 0

        # Velocity (points per minute, assuming 1-min data)
        if len(df) >= 5:
            velocity = float(closes.iloc[-1] - closes.iloc[-5]) / 5
        else:
            velocity = 0

        # Acceleration
        if len(df) >= 10:
            prev_velocity = float(closes.iloc[-5] - closes.iloc[-10]) / 5
            acceleration = velocity - prev_velocity
        else:
            acceleration = 0

        # Tick trend (proxy from price direction)
        if len(df) >= 10:
            up_moves = sum(1 for i in range(-10, 0) if closes.iloc[i] > closes.iloc[i-1])
            down_moves = 10 - up_moves
            tick_trend = "positive" if up_moves > 6 else "negative" if down_moves > 6 else "neutral"
        else:
            tick_trend = "neutral"

        return IntradayMomentum(
            roc_5min=float(roc_5),
            roc_15min=float(roc_15),
            roc_30min=float(roc_30),
            price_velocity=float(velocity),
            price_acceleration=float(acceleration),
            tick_trend=tick_trend,
            cumulative_tick=0,  # Would need tick data
            sector_alignment=0,  # Would need sector data
        )

    def calculate_features(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str = "1min",
        premarket_data: Optional[pd.DataFrame] = None,
        previous_close: Optional[float] = None,
        historical_or_ranges: Optional[list[float]] = None,
    ) -> IntradayFeatures:
        """
        Calculate complete intraday feature set.
        """
        if len(df) < 1:
            return self._empty_features(symbol, timeframe)

        # Current timestamp
        timestamp = df.index[-1] if hasattr(df.index[-1], 'time') else datetime.now()

        # Session
        session = self.get_session(timestamp)

        # Calculate all components
        vwap_data = self.calculate_vwap(df)
        or_data = self.calculate_opening_range(df, historical_or_ranges)
        volume_profile = self.calculate_volume_profile(df)
        momentum = self.calculate_momentum(df)

        # Session timing
        market_open_dt = datetime.combine(timestamp.date(), self.MARKET_OPEN)
        market_close_dt = datetime.combine(timestamp.date(), self.MARKET_CLOSE)
        minutes_into = int((timestamp - market_open_dt).total_seconds() / 60) if timestamp >= market_open_dt else 0
        minutes_remaining = int((market_close_dt - timestamp).total_seconds() / 60) if timestamp <= market_close_dt else 0

        # Premarket levels
        pm_high = float(premarket_data['High'].max()) if premarket_data is not None and len(premarket_data) > 0 else None
        pm_low = float(premarket_data['Low'].min()) if premarket_data is not None and len(premarket_data) > 0 else None

        # Daily high/low
        daily_high = float(df['High'].max())
        daily_low = float(df['Low'].min())

        # Relative volume
        avg_session_volume = df['Volume'].mean() * len(df)  # Rough estimate
        actual_volume = int(df['Volume'].sum())
        relative_volume = actual_volume / avg_session_volume if avg_session_volume > 0 else 1.0

        # Volatility regime
        if len(df) >= 20:
            returns = df['Close'].pct_change().dropna()
            vol = returns.std() * np.sqrt(390)  # Annualized from 1-min
            if vol > 0.4:
                vol_regime = "extreme"
            elif vol > 0.25:
                vol_regime = "high"
            elif vol < 0.1:
                vol_regime = "low"
            else:
                vol_regime = "normal"

            intraday_atr = float(returns.abs().mean() * df['Close'].mean())
        else:
            vol_regime = "normal"
            intraday_atr = 0

        # Volume trend
        if len(df) >= 20:
            recent_vol = df['Volume'].tail(10).mean()
            earlier_vol = df['Volume'].head(10).mean()
            if recent_vol > earlier_vol * 1.5:
                vol_trend = "increasing"
            elif recent_vol < earlier_vol * 0.7:
                vol_trend = "decreasing"
            else:
                vol_trend = "stable"
        else:
            vol_trend = "neutral"

        # Build feature object
        features = IntradayFeatures(
            timestamp=timestamp,
            symbol=symbol,
            timeframe=timeframe,
            vwap=vwap_data,
            opening_range=or_data,
            volume_profile=volume_profile,
            momentum=momentum,
            session=session,
            minutes_into_session=max(0, minutes_into),
            minutes_remaining=max(0, minutes_remaining),
            premarket_high=pm_high,
            premarket_low=pm_low,
            previous_close=previous_close,
            daily_high=daily_high,
            daily_low=daily_low,
            relative_volume=relative_volume,
            cumulative_volume=actual_volume,
            volume_trend=vol_trend,
            intraday_atr=intraday_atr,
            volatility_regime=vol_regime,
        )

        # Generate ML feature vector
        features.feature_vector = self._generate_feature_vector(features)

        # Generate summary and key levels
        features.summary = self._generate_summary(features)
        features.trading_bias = self._determine_bias(features)
        features.key_levels = self._identify_key_levels(features)

        return features

    def _empty_features(self, symbol: str, timeframe: str) -> IntradayFeatures:
        """Return empty feature set."""
        return IntradayFeatures(
            timestamp=datetime.now(),
            symbol=symbol,
            timeframe=timeframe,
            vwap=VWAPData(0, 0, 0, 0, 0, 0, 0, 0, "unknown", 0, "unknown"),
            opening_range=OpeningRangeData(0, 0, 0, 0, 0, 0, ORBSignal.NO_SIGNAL, 0, 0, 0),
            volume_profile=VolumeProfileData(0, 0, 0, 0, "unknown", False, [], []),
            momentum=IntradayMomentum(0, 0, 0, 0, 0, "neutral", 0, 0),
            session=MarketSession.PRE_MARKET,
            minutes_into_session=0,
            minutes_remaining=0,
        )

    def _generate_feature_vector(self, f: IntradayFeatures) -> dict:
        """Generate ML-ready feature vector."""
        return {
            # VWAP features
            "vwap_distance": f.vwap.distance_from_vwap,
            "vwap_band": {"below_2": -2, "below_1": -1, "at_vwap": 0, "above_1": 1, "above_2": 2}.get(f.vwap.band_position, 0),
            "vwap_slope": f.vwap.vwap_slope,
            "vwap_crossing_up": 1 if f.vwap.price_vs_vwap_trend == "crossing_up" else 0,
            "vwap_crossing_down": 1 if f.vwap.price_vs_vwap_trend == "crossing_down" else 0,

            # OR features
            "or_signal": {
                ORBSignal.BREAKOUT_UP.value: 2,
                ORBSignal.BREAKOUT_DOWN.value: -2,
                ORBSignal.FAILED_BREAKOUT_UP.value: -1,
                ORBSignal.FAILED_BREAKOUT_DOWN.value: 1,
                ORBSignal.RANGE_BOUND.value: 0,
                ORBSignal.NO_SIGNAL.value: 0,
            }.get(f.opening_range.signal.value, 0),
            "or_breakout_strength": f.opening_range.breakout_strength,
            "or_range_percentile": f.opening_range.or_range_percentile,

            # Volume profile
            "poc_distance": (f.vwap.current_price - f.volume_profile.poc) / f.volume_profile.poc * 100 if f.volume_profile.poc > 0 else 0,
            "in_value_area": 1 if f.volume_profile.in_value_area else 0,

            # Momentum
            "roc_5min": f.momentum.roc_5min,
            "roc_15min": f.momentum.roc_15min,
            "roc_30min": f.momentum.roc_30min,
            "price_velocity": f.momentum.price_velocity,
            "price_acceleration": f.momentum.price_acceleration,
            "tick_trend": {"positive": 1, "negative": -1, "neutral": 0}.get(f.momentum.tick_trend, 0),

            # Session
            "session": {
                MarketSession.OPENING_RANGE.value: 1,
                MarketSession.MORNING.value: 2,
                MarketSession.MIDDAY.value: 3,
                MarketSession.AFTERNOON.value: 4,
                MarketSession.CLOSE.value: 5,
            }.get(f.session.value, 0),
            "minutes_into_session": f.minutes_into_session,
            "minutes_remaining": f.minutes_remaining,

            # Volume
            "relative_volume": f.relative_volume,
            "volume_trend": {"increasing": 1, "decreasing": -1, "stable": 0, "neutral": 0}.get(f.volume_trend, 0),

            # Volatility
            "intraday_atr": f.intraday_atr,
            "volatility_regime": {"low": -1, "normal": 0, "high": 1, "extreme": 2}.get(f.volatility_regime, 0),

            # Price levels
            "dist_from_daily_high": (f.vwap.current_price - f.daily_high) / f.daily_high * 100 if f.daily_high > 0 else 0,
            "dist_from_daily_low": (f.vwap.current_price - f.daily_low) / f.daily_low * 100 if f.daily_low > 0 else 0,
        }

    def _generate_summary(self, f: IntradayFeatures) -> str:
        """Generate human-readable summary."""
        parts = []

        # Session context
        parts.append(f"{f.symbol} {f.session.value.replace('_', ' ').title()}")
        parts.append(f"{f.minutes_into_session}min in, {f.minutes_remaining}min left")

        # VWAP
        parts.append(f"VWAP: {f.vwap.band_position.replace('_', ' ')} ({f.vwap.distance_from_vwap:+.2f}%)")

        # OR status
        if f.opening_range.signal != ORBSignal.NO_SIGNAL:
            parts.append(f"OR: {f.opening_range.signal.value.replace('_', ' ')}")

        # Volume
        if f.relative_volume > 1.5:
            parts.append(f"High volume ({f.relative_volume:.1f}x)")
        elif f.relative_volume < 0.5:
            parts.append(f"Low volume ({f.relative_volume:.1f}x)")

        # Momentum
        if abs(f.momentum.roc_15min) > 1:
            direction = "up" if f.momentum.roc_15min > 0 else "down"
            parts.append(f"Momentum {direction} {abs(f.momentum.roc_15min):.1f}%")

        # Volatility
        if f.volatility_regime in ["high", "extreme"]:
            parts.append(f"⚠️ {f.volatility_regime.upper()} volatility")

        return " | ".join(parts)

    def _determine_bias(self, f: IntradayFeatures) -> str:
        """Determine trading bias from features."""
        score = 0

        # VWAP
        if f.vwap.price_vs_vwap_trend == "crossing_up":
            score += 2
        elif f.vwap.price_vs_vwap_trend == "crossing_down":
            score -= 2
        elif f.vwap.price_vs_vwap_trend == "above":
            score += 1
        elif f.vwap.price_vs_vwap_trend == "below":
            score -= 1

        # OR
        if f.opening_range.signal == ORBSignal.BREAKOUT_UP:
            score += 2
        elif f.opening_range.signal == ORBSignal.BREAKOUT_DOWN:
            score -= 2
        elif f.opening_range.signal == ORBSignal.FAILED_BREAKOUT_UP:
            score -= 1
        elif f.opening_range.signal == ORBSignal.FAILED_BREAKOUT_DOWN:
            score += 1

        # Momentum
        if f.momentum.roc_15min > 0.5:
            score += 1
        elif f.momentum.roc_15min < -0.5:
            score -= 1

        if score >= 3:
            return "strongly bullish"
        elif score >= 1:
            return "bullish"
        elif score <= -3:
            return "strongly bearish"
        elif score <= -1:
            return "bearish"
        return "neutral"

    def _identify_key_levels(self, f: IntradayFeatures) -> list[Tuple[float, str]]:
        """Identify key price levels."""
        levels = []

        # VWAP
        levels.append((f.vwap.vwap, "VWAP"))
        levels.append((f.vwap.upper_band_1, "VWAP +1σ"))
        levels.append((f.vwap.lower_band_1, "VWAP -1σ"))

        # OR levels
        levels.append((f.opening_range.or_high, "OR High"))
        levels.append((f.opening_range.or_low, "OR Low"))

        # Volume profile
        levels.append((f.volume_profile.poc, "POC"))
        levels.append((f.volume_profile.value_area_high, "VAH"))
        levels.append((f.volume_profile.value_area_low, "VAL"))

        # Daily levels
        levels.append((f.daily_high, "Day High"))
        levels.append((f.daily_low, "Day Low"))

        # Premarket
        if f.premarket_high:
            levels.append((f.premarket_high, "PM High"))
        if f.premarket_low:
            levels.append((f.premarket_low, "PM Low"))

        # Previous close
        if f.previous_close:
            levels.append((f.previous_close, "Prev Close"))

        # Sort by price and remove duplicates
        levels = sorted(set(levels), key=lambda x: x[0])
        return levels
