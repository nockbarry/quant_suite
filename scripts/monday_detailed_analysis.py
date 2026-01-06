#!/usr/bin/env python3
"""
Detailed Technical Analysis for Top Opportunities

Provides deeper analysis on the top trade ideas including:
- Detailed technical setup
- Risk/reward ratios
- Position sizing recommendations
- Confluence factors
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf


def calculate_technical_indicators(df):
    """Calculate comprehensive technical indicators."""
    # Price action
    df['SMA_20'] = df['Close'].rolling(20).mean()
    df['SMA_50'] = df['Close'].rolling(50).mean()
    df['SMA_200'] = df['Close'].rolling(200).mean()

    # Bollinger Bands
    df['BB_std'] = df['Close'].rolling(20).std()
    df['BB_upper'] = df['SMA_20'] + 2 * df['BB_std']
    df['BB_lower'] = df['SMA_20'] - 2 * df['BB_std']
    df['BB_pct'] = (df['Close'] - df['BB_lower']) / (df['BB_upper'] - df['BB_lower'])

    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # MACD
    ema_12 = df['Close'].ewm(span=12).mean()
    ema_26 = df['Close'].ewm(span=26).mean()
    df['MACD'] = ema_12 - ema_26
    df['MACD_signal'] = df['MACD'].ewm(span=9).mean()
    df['MACD_hist'] = df['MACD'] - df['MACD_signal']

    # Volume
    df['Volume_SMA_20'] = df['Volume'].rolling(20).mean()
    df['Volume_ratio'] = df['Volume'] / df['Volume_SMA_20']

    # ATR
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    df['ATR'] = ranges.max(axis=1).rolling(14).mean()

    return df


def analyze_setup(symbol, direction):
    """Deep dive analysis on a specific setup."""

    print(f"\n{'='*80}")
    print(f"DETAILED ANALYSIS: {symbol} - {direction.upper()}")
    print(f"{'='*80}")

    # Fetch extended data
    ticker = yf.Ticker(symbol)
    df = ticker.history(period="1y")

    if df.empty:
        print(f"No data available for {symbol}")
        return None

    # Calculate all indicators
    df = calculate_technical_indicators(df)

    # Latest values
    latest = df.iloc[-1]
    prev = df.iloc[-2]

    print(f"\nCurrent Price: ${latest['Close']:.2f}")
    print(f"Previous Close: ${prev['Close']:.2f}")
    print(f"Change: {((latest['Close']/prev['Close']-1)*100):+.2f}%")

    print(f"\n--- MOVING AVERAGES ---")
    print(f"SMA(20): ${latest['SMA_20']:.2f} ({((latest['Close']/latest['SMA_20']-1)*100):+.1f}%)")
    print(f"SMA(50): ${latest['SMA_50']:.2f} ({((latest['Close']/latest['SMA_50']-1)*100):+.1f}%)")
    print(f"SMA(200): ${latest['SMA_200']:.2f} ({((latest['Close']/latest['SMA_200']-1)*100):+.1f}%)")

    # Trend determination
    if latest['SMA_20'] > latest['SMA_50'] > latest['SMA_200']:
        trend = "STRONG UPTREND"
    elif latest['SMA_20'] < latest['SMA_50'] < latest['SMA_200']:
        trend = "STRONG DOWNTREND"
    elif latest['SMA_20'] > latest['SMA_50']:
        trend = "Uptrend"
    elif latest['SMA_20'] < latest['SMA_50']:
        trend = "Downtrend"
    else:
        trend = "Neutral/Choppy"

    print(f"Trend: {trend}")

    print(f"\n--- MOMENTUM INDICATORS ---")
    print(f"RSI(14): {latest['RSI']:.1f}")
    if latest['RSI'] < 30:
        rsi_signal = "OVERSOLD"
    elif latest['RSI'] > 70:
        rsi_signal = "OVERBOUGHT"
    elif latest['RSI'] < 40:
        rsi_signal = "Weak"
    elif latest['RSI'] > 60:
        rsi_signal = "Strong"
    else:
        rsi_signal = "Neutral"
    print(f"RSI Signal: {rsi_signal}")

    print(f"\nMACD: {latest['MACD']:.2f}")
    print(f"Signal: {latest['MACD_signal']:.2f}")
    print(f"Histogram: {latest['MACD_hist']:.2f}")

    if latest['MACD'] > latest['MACD_signal'] and prev['MACD'] < prev['MACD_signal']:
        macd_signal = "BULLISH CROSSOVER"
    elif latest['MACD'] < latest['MACD_signal'] and prev['MACD'] > prev['MACD_signal']:
        macd_signal = "BEARISH CROSSOVER"
    elif latest['MACD'] > latest['MACD_signal']:
        macd_signal = "Bullish"
    else:
        macd_signal = "Bearish"
    print(f"MACD Signal: {macd_signal}")

    print(f"\n--- BOLLINGER BANDS ---")
    print(f"Upper Band: ${latest['BB_upper']:.2f}")
    print(f"Middle (SMA20): ${latest['SMA_20']:.2f}")
    print(f"Lower Band: ${latest['BB_lower']:.2f}")
    print(f"BB Position: {latest['BB_pct']*100:.1f}%")

    if latest['BB_pct'] > 1.0:
        bb_signal = "ABOVE UPPER BAND (Overbought)"
    elif latest['BB_pct'] < 0.0:
        bb_signal = "BELOW LOWER BAND (Oversold)"
    elif latest['BB_pct'] > 0.8:
        bb_signal = "Near Upper Band"
    elif latest['BB_pct'] < 0.2:
        bb_signal = "Near Lower Band"
    else:
        bb_signal = "Middle Range"
    print(f"BB Signal: {bb_signal}")

    print(f"\n--- VOLATILITY & VOLUME ---")
    print(f"ATR(14): ${latest['ATR']:.2f} ({(latest['ATR']/latest['Close']*100):.1f}% of price)")
    print(f"Volume: {latest['Volume']:,.0f}")
    print(f"Avg Volume(20): {latest['Volume_SMA_20']:,.0f}")
    print(f"Volume Ratio: {latest['Volume_ratio']:.2f}x")

    # Calculate volatility
    returns = df['Close'].pct_change().dropna()
    daily_vol = returns.std()
    annual_vol = daily_vol * np.sqrt(252)
    print(f"Daily Volatility: {daily_vol*100:.2f}%")
    print(f"Annual Volatility: {annual_vol*100:.1f}%")

    print(f"\n--- SUPPORT & RESISTANCE ---")
    # Recent swing highs/lows
    high_20d = df['High'].tail(20).max()
    low_20d = df['Low'].tail(20).min()
    high_60d = df['High'].tail(60).max()
    low_60d = df['Low'].tail(60).min()

    print(f"20-day High: ${high_20d:.2f}")
    print(f"20-day Low: ${low_20d:.2f}")
    print(f"60-day High: ${high_60d:.2f}")
    print(f"60-day Low: ${low_60d:.2f}")

    print(f"\n--- TRADE SETUP ANALYSIS ---")

    if direction.lower() == "short":
        # Short setup analysis
        print("\nSHORT SETUP FACTORS:")

        confluence = []

        # Price above BB upper
        if latest['BB_pct'] > 0.95:
            print("  [+] Price at/above upper Bollinger Band")
            confluence.append("BB_high")

        # Overbought RSI
        if latest['RSI'] > 65:
            print(f"  [+] RSI overbought at {latest['RSI']:.0f}")
            confluence.append("RSI_high")

        # Extended from moving averages
        pct_above_ma20 = (latest['Close'] / latest['SMA_20'] - 1) * 100
        if pct_above_ma20 > 5:
            print(f"  [+] Extended {pct_above_ma20:.1f}% above MA(20)")
            confluence.append("extended_MA")

        # Recent parabolic move
        week_return = (latest['Close'] / df['Close'].iloc[-5] - 1) * 100
        if week_return > 5:
            print(f"  [+] Parabolic 5-day move: {week_return:+.1f}%")
            confluence.append("parabolic")

        # Volume declining on rally
        if latest['Volume_ratio'] < 0.8 and latest['Close'] > prev['Close']:
            print("  [+] Volume declining on rally (weak move)")
            confluence.append("vol_decline")

        # Calculate short levels
        entry = latest['Close'] * 0.998  # Wait for slight pullback
        stop = latest['Close'] + 1.5 * latest['ATR']
        target1 = latest['SMA_20']
        target2 = latest['SMA_20'] - latest['BB_std']

        risk = stop - entry
        reward1 = entry - target1
        reward2 = entry - target2

    else:  # LONG
        # Long setup analysis
        print("\nLONG SETUP FACTORS:")

        confluence = []

        # Price below BB lower
        if latest['BB_pct'] < 0.05:
            print("  [+] Price at/below lower Bollinger Band")
            confluence.append("BB_low")

        # Oversold RSI
        if latest['RSI'] < 35:
            print(f"  [+] RSI oversold at {latest['RSI']:.0f}")
            confluence.append("RSI_low")

        # Extended below moving averages
        pct_below_ma20 = (latest['Close'] / latest['SMA_20'] - 1) * 100
        if pct_below_ma20 < -5:
            print(f"  [+] Extended {abs(pct_below_ma20):.1f}% below MA(20)")
            confluence.append("extended_MA")

        # Recent capitulation move
        week_return = (latest['Close'] / df['Close'].iloc[-5] - 1) * 100
        if week_return < -5:
            print(f"  [+] Capitulation 5-day move: {week_return:.1f}%")
            confluence.append("capitulation")

        # Volume increasing on decline
        if latest['Volume_ratio'] > 1.2 and latest['Close'] < prev['Close']:
            print("  [+] Volume increasing on decline (potential selling climax)")
            confluence.append("vol_spike")

        # Calculate long levels
        entry = latest['Close'] * 1.002  # Wait for slight bounce
        stop = latest['Close'] - 1.5 * latest['ATR']
        target1 = latest['SMA_20']
        target2 = latest['SMA_20'] + latest['BB_std']

        risk = entry - stop
        reward1 = target1 - entry
        reward2 = target2 - entry

    print(f"\n--- TRADE PLAN ---")
    print(f"Entry: ${entry:.2f}")
    print(f"Stop Loss: ${stop:.2f}")
    print(f"Target 1: ${target1:.2f}")
    print(f"Target 2: ${target2:.2f}")
    print(f"\nRisk: ${risk:.2f} ({(risk/entry*100):.1f}%)")
    print(f"Reward 1: ${reward1:.2f} ({(reward1/entry*100):.1f}%)")
    print(f"Reward 2: ${reward2:.2f} ({(reward2/entry*100):.1f}%)")
    print(f"\nRisk/Reward Ratio (Target 1): {(reward1/risk):.2f}")
    print(f"Risk/Reward Ratio (Target 2): {(reward2/risk):.2f}")

    print(f"\n--- POSITION SIZING (for $10,000 account) ---")
    # Risk 1% of account per trade
    account_size = 10000
    risk_per_trade = account_size * 0.01  # $100

    shares = int(risk_per_trade / risk)
    position_value = shares * entry
    position_pct = position_value / account_size * 100

    print(f"Risk per trade: ${risk_per_trade:.2f} (1% of account)")
    print(f"Shares: {shares}")
    print(f"Position value: ${position_value:.2f} ({position_pct:.1f}% of account)")
    print(f"Max loss if stopped: ${shares * risk:.2f}")
    print(f"Potential profit (Target 1): ${shares * reward1:.2f}")
    print(f"Potential profit (Target 2): ${shares * reward2:.2f}")

    print(f"\n--- CONFLUENCE SCORE ---")
    print(f"Factors supporting this trade: {len(confluence)}")
    for factor in confluence:
        print(f"  - {factor}")

    if len(confluence) >= 3:
        rating = "HIGH PROBABILITY"
    elif len(confluence) >= 2:
        rating = "MODERATE PROBABILITY"
    else:
        rating = "LOW PROBABILITY"

    print(f"\nTrade Rating: {rating}")

    return {
        'symbol': symbol,
        'direction': direction,
        'entry': entry,
        'stop': stop,
        'target1': target1,
        'target2': target2,
        'risk_reward_1': reward1/risk,
        'risk_reward_2': reward2/risk,
        'shares': shares,
        'confluence_factors': len(confluence),
        'rating': rating,
        'indicators': {
            'rsi': latest['RSI'],
            'bb_pct': latest['BB_pct'],
            'volume_ratio': latest['Volume_ratio'],
            'trend': trend,
        }
    }


async def main():
    """Analyze top setups in detail."""

    print("="*80)
    print("MONDAY TRADING PLAYBOOK - DETAILED TECHNICAL ANALYSIS")
    print("="*80)
    print(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Load the scan results
    scan_dir = Path.home() / "quant_results" / "alpha_discovery"
    latest_scan = sorted(scan_dir.glob("monday_scan_*.json"))[-1]

    with open(latest_scan, 'r') as f:
        scan_data = json.load(f)

    print(f"\nUsing scan results from: {latest_scan.name}")
    print(f"Total trade ideas: {len(scan_data['trade_ideas'])}")

    # Analyze top 5 setups in detail
    top_ideas = scan_data['trade_ideas'][:5]

    detailed_analysis = []

    for idea in top_ideas:
        try:
            analysis = analyze_setup(idea['symbol'], idea['direction'])
            if analysis:
                detailed_analysis.append(analysis)
        except Exception as e:
            print(f"Error analyzing {idea['symbol']}: {e}")

    # Summary table
    print("\n" + "="*80)
    print("TRADE SUMMARY TABLE")
    print("="*80)
    print(f"{'Symbol':<8} {'Dir':<6} {'Entry':<10} {'Stop':<10} {'Target1':<10} {'R:R':<8} {'Rating':<20}")
    print("-"*80)

    for analysis in detailed_analysis:
        print(f"{analysis['symbol']:<8} "
              f"{analysis['direction']:<6} "
              f"${analysis['entry']:<9.2f} "
              f"${analysis['stop']:<9.2f} "
              f"${analysis['target1']:<9.2f} "
              f"{analysis['risk_reward_1']:<7.2f} "
              f"{analysis['rating']:<20}")

    # Save detailed analysis
    output_file = scan_dir / f"detailed_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(detailed_analysis, f, indent=2, default=str)

    print(f"\n{'='*80}")
    print(f"Detailed analysis saved to: {output_file}")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())
