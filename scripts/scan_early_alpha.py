#!/usr/bin/env python3
"""
Scan social signals for early alpha opportunities.
Focus on early-stage mentions and convergence with statistical signals.
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any

def load_wsb_signals() -> Dict[str, Any]:
    """Load WSB signals from JSON."""
    wsb_path = Path('/home/nock/quant_results/social/wsb_signals.json')
    with open(wsb_path) as f:
        return json.load(f)

def load_thesis_suggestions() -> Dict[str, Any]:
    """Load thesis suggestions from JSON."""
    suggestions_path = Path('/home/nock/quant_results/suggestions/thesis_suggestions.json')
    with open(suggestions_path) as f:
        return json.load(f)

def analyze_early_signals(wsb_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Analyze early signals for actionable opportunities."""
    early = wsb_data.get('early_signals', [])

    # Filter out non-tradeable symbols
    non_tradeable = {'FAQ', 'USD', 'ATH', 'DD', 'CEO', 'IPO', 'WSB'}

    actionable = []
    for sig in early:
        symbol = sig['symbol']
        if symbol in non_tradeable or len(symbol) > 5:
            continue

        vintage = sig.get('signal_vintage', 0)
        phase = sig.get('current_phase', 'unknown')
        sentiment = sig.get('avg_sentiment', 0)
        upvotes = sig.get('total_upvotes', 0)
        mentions = sig.get('mention_count', 0)

        # Score the signal
        # Good vintage: 0-3 days (caught early)
        # Good sentiment: > 0.2
        # Good engagement: upvotes > 500
        vintage_score = max(0, 1 - (vintage / 7))  # Decays over 7 days
        sentiment_score = max(0, min(1, (sentiment + 1) / 2))  # Normalize -1 to 1
        engagement_score = min(1, upvotes / 2000)  # Normalize to 2k upvotes

        total_score = (vintage_score * 0.4 + sentiment_score * 0.3 + engagement_score * 0.3)

        actionable.append({
            'symbol': symbol,
            'vintage': vintage,
            'phase': phase,
            'mentions': mentions,
            'sentiment': sentiment,
            'upvotes': upvotes,
            'first_seen': sig.get('first_seen', 'Unknown')[:10],
            'score': total_score,
        })

    # Sort by score
    actionable.sort(key=lambda x: x['score'], reverse=True)
    return actionable

def check_convergence(social_symbols: List[str], suggestions: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Check for convergence between social and statistical signals."""
    sugg_list = suggestions.get('suggestions', [])

    convergent = []
    for sugg in sugg_list:
        symbol = sugg['symbol']
        in_social = symbol in social_symbols

        convergent.append({
            'symbol': symbol,
            'name': sugg['suggested_name'],
            'direction': sugg['direction'],
            'confidence': sugg['confidence_score'],
            'signal_count': sugg['signal_count'],
            'sources': sugg['signal_sources'],
            'status': sugg['status'],
            'in_social': in_social,
        })

    return convergent

def main():
    print("=== EARLY ALPHA DISCOVERY SCAN ===")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print()

    # Load data
    wsb_data = load_wsb_signals()
    suggestions = load_thesis_suggestions()

    print(f"WSB Data Updated: {wsb_data.get('updated_at', 'Unknown')}")
    print()

    # Analyze early signals
    actionable = analyze_early_signals(wsb_data)

    print(f"=== EARLY SOCIAL SIGNALS ===")
    print(f"Total early signals detected: {len(wsb_data.get('early_signals', []))}")
    print(f"Tradeable signals: {len(actionable)}\n")

    if actionable:
        print("TOP EARLY SIGNALS (by score):\n")
        for sig in actionable[:10]:  # Top 10
            print(f"{sig['symbol']}:")
            print(f"  First Seen: {sig['first_seen']}")
            print(f"  Vintage: {sig['vintage']} days (phase: {sig['phase']})")
            print(f"  Mentions: {sig['mentions']}")
            print(f"  Sentiment: {sig['sentiment']:+.2f}")
            print(f"  Upvotes: {sig['upvotes']:,}")
            print(f"  Score: {sig['score']:.3f}")
            print()
    else:
        print("No actionable early signals detected\n")

    # Check convergence
    social_symbols = [s['symbol'] for s in actionable]
    convergent = check_convergence(social_symbols, suggestions)

    print("=== MULTI-SIGNAL CONVERGENCE ===\n")
    if convergent:
        for conv in convergent:
            print(f"{conv['symbol']}: {conv['name']}")
            print(f"  Direction: {conv['direction']}")
            print(f"  Confidence: {conv['confidence']:.2f}")
            print(f"  Signal Count: {conv['signal_count']}")
            print(f"  Sources: {', '.join(conv['sources'])}")
            print(f"  Status: {conv['status']}")
            if conv['in_social']:
                print(f"  ** CONVERGENCE: Also in early social signals **")
            print()
    else:
        print("No multi-signal convergence detected\n")

    # Summary and recommendations
    print("=== ACTIONABLE THIS WEEK ===\n")

    # High-score early signals
    high_score = [s for s in actionable if s['score'] > 0.5]
    if high_score:
        print("HIGH-SCORE EARLY SIGNALS (score > 0.5):")
        for sig in high_score:
            print(f"  - {sig['symbol']}: Score {sig['score']:.2f}, "
                  f"Sentiment {sig['sentiment']:+.2f}, "
                  f"Vintage {sig['vintage']}d")
        print()

    # Multi-signal convergence
    multi_signal = [c for c in convergent if c['signal_count'] >= 3]
    if multi_signal:
        print("MULTI-SIGNAL CONVERGENCE (3+ sources):")
        for conv in multi_signal:
            convergence_note = " + SOCIAL" if conv['in_social'] else ""
            print(f"  - {conv['symbol']}: {conv['signal_count']} signals "
                  f"({', '.join(conv['sources'])}){convergence_note}")
            print(f"    {conv['direction'].upper()} @ {conv['confidence']:.2f} confidence")
        print()

    # Recommendations
    print("RECOMMENDATIONS:")
    if high_score or multi_signal:
        print("  1. Monitor high-score early signals for entry points")
        print("  2. Validate multi-signal convergence with statistical analysis")
        print("  3. Check for fundamental catalysts (earnings, news, events)")
        print("  4. Size positions conservatively (5-7%) until confirmation")
    else:
        print("  - No high-conviction early signals detected")
        print("  - Continue monitoring for emerging opportunities")

    print()

    # Save results
    output = {
        'timestamp': datetime.now().isoformat(),
        'early_signals': actionable,
        'convergence': convergent,
        'high_score_signals': high_score,
        'multi_signal_convergence': multi_signal,
    }

    output_path = Path('/home/nock/quant_results/alpha_discovery/early_alpha_scan.json')
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"Results saved to: {output_path}")

if __name__ == '__main__':
    main()
