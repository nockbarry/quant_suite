#!/usr/bin/env python3
"""Populate Knowledge Base with company and sector briefs.

Creates structured knowledge files for major positions and sectors.

Usage:
    PYTHONPATH=. python scripts/populate_knowledge_base.py
"""

import json
from datetime import datetime
from pathlib import Path

from src.knowledge.base import KnowledgeBase, CompanyBrief, SectorContext
from src.core.paths import paths


# Company data for major positions
COMPANY_DATA = {
    # Energy - Oilfield Services
    "SLB": {
        "name": "Schlumberger",
        "business_model": "World's largest oilfield services company providing technology, integrated project management, and information solutions",
        "moat": "Scale, proprietary technology, global footprint, long-term contracts",
        "earnings_quality": "Cyclical with oil prices, but diversified globally",
        "management_view": "Strong execution, disciplined capital allocation",
        "sector": "Energy",
        "market_cap_tier": "large",
        "key_risks": ["Oil price volatility", "Energy transition long-term", "Geopolitical exposure"],
        "key_catalysts": ["Venezuela reopening", "Middle East spending", "Offshore cycle"],
        "sector_position": "Market leader",
        "typical_volatility": "medium",
        "earnings_behavior": "Beats expectations in upcycles, can disappoint in downturns",
        "correlation_notes": "High correlation to oil prices, XLE, and OXY",
        "best_setups": "Buy on pullbacks during oil price strength, sell into euphoria",
        "avoid_when": "Oil breaking below $60, energy sector in downtrend",
    },
    "HAL": {
        "name": "Halliburton",
        "business_model": "Oilfield services focused on drilling and completion, more North America exposed than SLB",
        "moat": "Technology leadership in fracking, strong customer relationships",
        "earnings_quality": "More cyclical than SLB due to NA focus",
        "management_view": "Aggressive, focused on shareholder returns",
        "sector": "Energy",
        "market_cap_tier": "large",
        "key_risks": ["US shale production plateau", "Oil price collapse", "Competition"],
        "key_catalysts": ["NA drilling activity", "International expansion", "Venezuela"],
        "sector_position": "Strong #2 player",
        "typical_volatility": "high",
        "earnings_behavior": "Can have violent moves on earnings, especially with guidance",
        "correlation_notes": "Very high correlation to oil, higher beta than SLB",
        "best_setups": "Oversold bounces when oil stabilizes",
        "avoid_when": "Oil in freefall, US rig count declining sharply",
    },
    # Tankers
    "FRO": {
        "name": "Frontline",
        "business_model": "Largest crude oil tanker company, owns VLCCs and Suezmax vessels",
        "moat": "Scale, modern fleet, low operating costs",
        "earnings_quality": "Highly volatile, spot rate dependent",
        "management_view": "Aggressive on fleet expansion, good at timing cycles",
        "sector": "Energy",
        "market_cap_tier": "mid",
        "key_risks": ["Tanker rate collapse", "Fleet oversupply", "Oil demand decline"],
        "key_catalysts": ["Geopolitical disruptions", "OPEC production increases", "Sanctions"],
        "sector_position": "Market leader in crude tankers",
        "typical_volatility": "very high",
        "earnings_behavior": "Beats huge when rates spike, can go to zero earnings in weak markets",
        "correlation_notes": "Inversely correlated to oil in short-term (high prices = less shipping)",
        "best_setups": "Buy when geopolitical events disrupt normal shipping routes",
        "avoid_when": "Tanker oversupply, rates at historic lows",
    },
    # Tech
    "NVDA": {
        "name": "NVIDIA",
        "business_model": "Designs GPUs for gaming, data centers, AI training and inference",
        "moat": "CUDA ecosystem, AI hardware dominance, software moat",
        "earnings_quality": "High growth but can be lumpy, hyperscaler dependent",
        "management_view": "Jensen Huang is visionary but can overpromise",
        "sector": "Technology",
        "market_cap_tier": "mega",
        "key_risks": ["Competition from AMD/custom chips", "China restrictions", "AI bubble burst"],
        "key_catalysts": ["AI infrastructure buildout", "New chip generations", "Inference growth"],
        "sector_position": "Dominant market leader",
        "typical_volatility": "very high",
        "earnings_behavior": "Massive moves on earnings, guidance is key",
        "correlation_notes": "Moves with AI sentiment, QQQ beta ~1.5",
        "best_setups": "Buy on 20%+ pullbacks when AI thesis intact",
        "avoid_when": "Valuation extreme, competition narrative building",
    },
    "MSFT": {
        "name": "Microsoft",
        "business_model": "Enterprise software (Office, Azure cloud), AI integration, gaming",
        "moat": "Ecosystem lock-in, enterprise relationships, AI integration",
        "earnings_quality": "Very consistent, cloud growth provides visibility",
        "management_view": "Satya Nadella has executed flawlessly",
        "sector": "Technology",
        "market_cap_tier": "mega",
        "key_risks": ["Cloud slowdown", "AI monetization questions", "Regulatory"],
        "key_catalysts": ["Azure growth", "Copilot adoption", "Gaming growth"],
        "sector_position": "Dominant across multiple categories",
        "typical_volatility": "low",
        "earnings_behavior": "Steady beats, rarely big surprises",
        "correlation_notes": "Moves with QQQ but lower beta, quality flight",
        "best_setups": "Buy on broad market selloffs",
        "avoid_when": "Tech euphoria at peak, cloud concerns emerging",
    },
    # Utilities / Nuclear
    "CEG": {
        "name": "Constellation Energy",
        "business_model": "Largest US nuclear fleet, clean energy generation",
        "moat": "Nuclear assets irreplaceable, long-term hyperscaler contracts",
        "earnings_quality": "Stable with upside from AI datacenter deals",
        "management_view": "Opportunistic, capitalizing on AI power demand",
        "sector": "Utilities",
        "market_cap_tier": "large",
        "key_risks": ["Nuclear regulation", "Power price volatility", "Construction risks"],
        "key_catalysts": ["AI datacenter contracts", "Microsoft deal expansion", "Capacity payments"],
        "sector_position": "Nuclear leader",
        "typical_volatility": "medium",
        "earnings_behavior": "Can surprise on contract announcements",
        "correlation_notes": "Inverse to interest rates, AI datacenter theme",
        "best_setups": "Buy on pullbacks when AI power demand thesis strong",
        "avoid_when": "Nuclear safety concerns, rising interest rates",
    },
    # Gold
    "GLD": {
        "name": "SPDR Gold Trust",
        "business_model": "ETF holding physical gold bullion",
        "moat": "Liquidity, largest gold ETF",
        "earnings_quality": "N/A - tracks gold price",
        "management_view": "N/A - passive ETF",
        "sector": "Precious Metals",
        "market_cap_tier": "large",
        "key_risks": ["Dollar strength", "Real rate increases", "Crypto competition"],
        "key_catalysts": ["De-dollarization", "Central bank buying", "Geopolitical risk"],
        "sector_position": "Market leader ETF",
        "typical_volatility": "medium",
        "earnings_behavior": "N/A",
        "correlation_notes": "Inverse to real rates, USD, flight to safety",
        "best_setups": "Buy on geopolitical escalation, rate cut expectations",
        "avoid_when": "Strong USD, rising real rates",
    },
}

# Sector data
SECTOR_DATA = {
    "Energy": {
        "current_cycle_position": "mid-cycle recovery",
        "cycle_sensitivity": "Very high - tied to oil prices and global growth",
        "key_drivers": ["Oil price", "OPEC decisions", "Geopolitical events", "US shale production"],
        "leading_indicators": ["Rig count", "Tanker rates", "Refinery margins", "Crack spreads"],
        "correlations": {
            "Technology": "Low correlation",
            "Financials": "Moderate positive",
            "Utilities": "Moderate negative",
        },
        "rotation_patterns": "Money flows in during inflation scares, out during recession fears",
        "current_assessment": "Benefiting from tight supply, geopolitical premium, and AI power demand for natural gas",
        "relative_strength": "Outperforming YTD on Venezuela/Middle East developments",
        "leaders": ["XOM", "CVX", "SLB", "HAL", "OXY"],
        "laggards": ["BP", "SHEL", "refiners in oversupply"],
        "what_works_here": "Momentum strategies during oil rallies, mean reversion during panic selloffs",
        "what_to_avoid": "Catching falling knives on oil collapses, overleveraged E&Ps",
    },
    "Technology": {
        "current_cycle_position": "late-cycle with AI secular growth",
        "cycle_sensitivity": "Moderate - growth can offset cycle",
        "key_drivers": ["AI adoption", "Cloud spending", "Consumer electronics", "Enterprise software"],
        "leading_indicators": ["Semiconductor orders", "Cloud revenue growth", "VC funding"],
        "correlations": {
            "Energy": "Low correlation",
            "Financials": "Moderate positive",
            "Consumer Discretionary": "High positive",
        },
        "rotation_patterns": "Leads in risk-on, lags in risk-off, AI is current secular driver",
        "current_assessment": "AI theme driving megacap outperformance, concentration risk",
        "relative_strength": "Outperforming on AI infrastructure buildout",
        "leaders": ["NVDA", "MSFT", "GOOGL", "META", "AAPL"],
        "laggards": ["Legacy hardware", "Non-AI software"],
        "what_works_here": "Momentum on AI names, quality on megacaps",
        "what_to_avoid": "Catching falling knives on growth disappointments, crowded trades",
    },
    "Utilities": {
        "current_cycle_position": "Transitioning - traditional defensive + AI power demand",
        "cycle_sensitivity": "Low traditionally, but AI demand adds growth component",
        "key_drivers": ["Interest rates", "Power demand", "Renewable transition", "AI datacenter growth"],
        "leading_indicators": ["10Y Treasury yield", "Power prices", "Datacenter announcements"],
        "correlations": {
            "Technology": "Historically negative, now positive via AI",
            "Financials": "Negative (rate sensitivity)",
            "Energy": "Moderate positive",
        },
        "rotation_patterns": "Flight to safety during volatility, now has AI growth theme",
        "current_assessment": "Nuclear renaissance driven by AI power demand, CEG leading",
        "relative_strength": "Outperforming due to AI datacenter theme",
        "leaders": ["CEG", "VST", "NEE", "ETR"],
        "laggards": ["Traditional regulated utilities without AI exposure"],
        "what_works_here": "Nuclear/AI power plays, buy on rate spike selloffs",
        "what_to_avoid": "Overleveraged utilities, no AI datacenter exposure",
    },
    "Precious Metals": {
        "current_cycle_position": "Bull market - de-dollarization theme",
        "cycle_sensitivity": "Counter-cyclical, safe haven",
        "key_drivers": ["Real interest rates", "USD strength", "Central bank buying", "Geopolitical risk"],
        "leading_indicators": ["TIPS yields", "DXY", "Central bank purchases", "ETF flows"],
        "correlations": {
            "Technology": "Low to negative",
            "Financials": "Negative",
            "Energy": "Moderate positive (inflation)",
        },
        "rotation_patterns": "Flows in during uncertainty, out during risk-on",
        "current_assessment": "Secular bull driven by de-dollarization and central bank diversification",
        "relative_strength": "Strong on geopolitical tensions and central bank buying",
        "leaders": ["GLD", "GDX", "NEM", "AEM"],
        "laggards": ["Silver miners", "junior explorers"],
        "what_works_here": "Buy dips during geopolitical escalation, momentum during breakouts",
        "what_to_avoid": "Chasing after parabolic moves, overleveraged miners",
    },
}


def populate_companies(kb: KnowledgeBase) -> int:
    """Populate company briefs."""
    count = 0
    for symbol, data in COMPANY_DATA.items():
        try:
            brief = kb.create_company(
                symbol=symbol,
                name=data["name"],
                business_model=data["business_model"],
                moat=data["moat"],
                earnings_quality=data["earnings_quality"],
                management_view=data["management_view"],
                sector=data["sector"],
                market_cap_tier=data["market_cap_tier"],
                key_risks=data.get("key_risks", []),
                key_catalysts=data.get("key_catalysts", []),
                sector_position=data.get("sector_position", ""),
                typical_volatility=data.get("typical_volatility", "medium"),
                earnings_behavior=data.get("earnings_behavior", ""),
                correlation_notes=data.get("correlation_notes", ""),
                best_setups=data.get("best_setups", ""),
                avoid_when=data.get("avoid_when", ""),
            )
            print(f"  Created company brief: {symbol}")
            count += 1
        except Exception as e:
            print(f"  Failed to create {symbol}: {e}")

    return count


def populate_sectors(kb: KnowledgeBase) -> int:
    """Populate sector contexts."""
    count = 0
    for sector, data in SECTOR_DATA.items():
        try:
            context = kb.create_sector(
                sector=sector,
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
            print(f"  Created sector context: {sector}")
            count += 1
        except Exception as e:
            print(f"  Failed to create {sector}: {e}")

    return count


def main():
    """Populate the knowledge base."""
    print("=" * 60)
    print("POPULATING KNOWLEDGE BASE")
    print("=" * 60)
    print()

    kb = KnowledgeBase()

    print("Creating company briefs...")
    company_count = populate_companies(kb)
    print(f"  Created {company_count} company briefs")
    print()

    print("Creating sector contexts...")
    sector_count = populate_sectors(kb)
    print(f"  Created {sector_count} sector contexts")
    print()

    print("=" * 60)
    print("KNOWLEDGE BASE SUMMARY")
    print("=" * 60)
    print(f"Companies: {len(kb.list_companies())}")
    print(f"Sectors: {len(kb.list_sectors())}")
    print(f"Location: {kb.base_dir}")
    print()

    # Test retrieval
    print("Testing retrieval...")
    slb = kb.get_company("SLB")
    if slb:
        print(f"  SLB: {slb.business_model[:50]}...")
    energy = kb.get_sector("Energy")
    if energy:
        print(f"  Energy: {energy.current_assessment[:50]}...")

    print()
    print("Done!")


if __name__ == "__main__":
    main()
