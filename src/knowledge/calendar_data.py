"""Calendar Data - 2026 Events and Predictions.

Comprehensive calendar data for market events, expert predictions,
and Claude's market outlook.

Created: 2026-01-20
"""

from datetime import date
from src.knowledge.market_calendar import EventCategory, EventImpact


def get_fed_events_2026() -> list[dict]:
    """Federal Reserve events for 2026."""
    return [
        # FOMC Meetings 2026
        {
            "id": "fomc_2026_01",
            "title": "FOMC Meeting",
            "date": date(2026, 1, 28),
            "end_date": date(2026, 1, 29),
            "category": EventCategory.FED,
            "impact": EventImpact.CRITICAL,
            "description": "First FOMC meeting of 2026. Expected to hold rates at 4.25-4.50%. "
                          "Watch for updated dot plot and economic projections.",
            "time": "14:00 ET",
            "symbols_affected": ["SPY", "QQQ", "TLT", "GLD", "DXY"],
            "sectors_affected": ["financials", "real_estate", "utilities"],
            "source": "Federal Reserve",
        },
        {
            "id": "fomc_2026_03",
            "title": "FOMC Meeting + SEP",
            "date": date(2026, 3, 17),
            "end_date": date(2026, 3, 18),
            "category": EventCategory.FED,
            "impact": EventImpact.CRITICAL,
            "description": "FOMC with Summary of Economic Projections (dot plot). "
                          "Key meeting for 2026 rate path clarity. Potential first cut signals.",
            "time": "14:00 ET",
            "symbols_affected": ["SPY", "QQQ", "TLT", "GLD", "DXY"],
            "sectors_affected": ["financials", "real_estate", "utilities", "tech"],
            "source": "Federal Reserve",
        },
        {
            "id": "fomc_2026_05",
            "title": "FOMC Meeting",
            "date": date(2026, 5, 5),
            "end_date": date(2026, 5, 6),
            "category": EventCategory.FED,
            "impact": EventImpact.CRITICAL,
            "description": "May FOMC. Markets pricing potential rate cut.",
            "time": "14:00 ET",
            "symbols_affected": ["SPY", "QQQ", "TLT", "GLD"],
            "sectors_affected": ["financials", "real_estate"],
            "source": "Federal Reserve",
        },
        {
            "id": "fomc_2026_06",
            "title": "FOMC Meeting + SEP",
            "date": date(2026, 6, 16),
            "end_date": date(2026, 6, 17),
            "category": EventCategory.FED,
            "impact": EventImpact.CRITICAL,
            "description": "June FOMC with updated projections. Critical for H2 outlook.",
            "time": "14:00 ET",
            "symbols_affected": ["SPY", "QQQ", "TLT", "GLD", "DXY"],
            "sectors_affected": ["financials", "real_estate", "utilities"],
            "source": "Federal Reserve",
        },
        {
            "id": "fomc_2026_07",
            "title": "FOMC Meeting",
            "date": date(2026, 7, 28),
            "end_date": date(2026, 7, 29),
            "category": EventCategory.FED,
            "impact": EventImpact.CRITICAL,
            "description": "July FOMC. Summer meeting before Jackson Hole.",
            "time": "14:00 ET",
            "symbols_affected": ["SPY", "QQQ", "TLT"],
            "sectors_affected": ["financials"],
            "source": "Federal Reserve",
        },
        {
            "id": "jackson_hole_2026",
            "title": "Jackson Hole Symposium",
            "date": date(2026, 8, 27),
            "end_date": date(2026, 8, 29),
            "category": EventCategory.FED,
            "impact": EventImpact.CRITICAL,
            "description": "Annual Jackson Hole Economic Symposium. Fed Chair speech Friday AM. "
                          "Major policy signals often delivered here.",
            "time": "10:00 ET",
            "symbols_affected": ["SPY", "QQQ", "TLT", "GLD", "DXY"],
            "sectors_affected": ["all"],
            "source": "Federal Reserve Bank of Kansas City",
        },
        {
            "id": "fomc_2026_09",
            "title": "FOMC Meeting + SEP",
            "date": date(2026, 9, 15),
            "end_date": date(2026, 9, 16),
            "category": EventCategory.FED,
            "impact": EventImpact.CRITICAL,
            "description": "September FOMC with projections. Pre-election positioning.",
            "time": "14:00 ET",
            "symbols_affected": ["SPY", "QQQ", "TLT", "GLD"],
            "sectors_affected": ["financials", "real_estate"],
            "source": "Federal Reserve",
        },
        {
            "id": "fomc_2026_11",
            "title": "FOMC Meeting",
            "date": date(2026, 11, 3),
            "end_date": date(2026, 11, 4),
            "category": EventCategory.FED,
            "impact": EventImpact.CRITICAL,
            "description": "November FOMC. Day before midterm elections.",
            "time": "14:00 ET",
            "symbols_affected": ["SPY", "QQQ", "TLT"],
            "sectors_affected": ["financials"],
            "source": "Federal Reserve",
        },
        {
            "id": "fomc_2026_12",
            "title": "FOMC Meeting + SEP",
            "date": date(2026, 12, 15),
            "end_date": date(2026, 12, 16),
            "category": EventCategory.FED,
            "impact": EventImpact.CRITICAL,
            "description": "Final FOMC of 2026 with projections. Sets tone for 2027.",
            "time": "14:00 ET",
            "symbols_affected": ["SPY", "QQQ", "TLT", "GLD"],
            "sectors_affected": ["financials", "real_estate"],
            "source": "Federal Reserve",
        },
    ]


def get_economic_events_2026() -> list[dict]:
    """Major economic releases for 2026."""
    events = []

    # CPI Releases (monthly, ~13th of each month)
    cpi_dates = [
        (date(2026, 1, 14), "December 2025"),
        (date(2026, 2, 12), "January 2026"),
        (date(2026, 3, 11), "February 2026"),
        (date(2026, 4, 10), "March 2026"),
        (date(2026, 5, 13), "April 2026"),
        (date(2026, 6, 10), "May 2026"),
        (date(2026, 7, 14), "June 2026"),
        (date(2026, 8, 12), "July 2026"),
        (date(2026, 9, 11), "August 2026"),
        (date(2026, 10, 13), "September 2026"),
        (date(2026, 11, 12), "October 2026"),
        (date(2026, 12, 10), "November 2026"),
    ]

    for cpi_date, period in cpi_dates:
        events.append({
            "id": f"cpi_{cpi_date.isoformat()}",
            "title": f"CPI Report ({period})",
            "date": cpi_date,
            "category": EventCategory.ECONOMIC,
            "impact": EventImpact.CRITICAL,
            "description": f"Consumer Price Index for {period}. Core CPI most watched. "
                          "Directly impacts Fed rate decisions.",
            "time": "08:30 ET",
            "symbols_affected": ["SPY", "QQQ", "TLT", "GLD", "DXY"],
            "sectors_affected": ["all"],
            "source": "Bureau of Labor Statistics",
            "recurring": True,
            "recurrence_rule": "monthly",
        })

    # Jobs Reports (first Friday of month)
    jobs_dates = [
        (date(2026, 1, 9), "December 2025"),
        (date(2026, 2, 6), "January 2026"),
        (date(2026, 3, 6), "February 2026"),
        (date(2026, 4, 3), "March 2026"),
        (date(2026, 5, 1), "April 2026"),
        (date(2026, 6, 5), "May 2026"),
        (date(2026, 7, 2), "June 2026"),
        (date(2026, 8, 7), "July 2026"),
        (date(2026, 9, 4), "August 2026"),
        (date(2026, 10, 2), "September 2026"),
        (date(2026, 11, 6), "October 2026"),
        (date(2026, 12, 4), "November 2026"),
    ]

    for jobs_date, period in jobs_dates:
        events.append({
            "id": f"nfp_{jobs_date.isoformat()}",
            "title": f"Non-Farm Payrolls ({period})",
            "date": jobs_date,
            "category": EventCategory.ECONOMIC,
            "impact": EventImpact.CRITICAL,
            "description": f"Employment report for {period}. NFP, unemployment rate, wages. "
                          "Key Fed input for labor market conditions.",
            "time": "08:30 ET",
            "symbols_affected": ["SPY", "QQQ", "TLT", "XLF"],
            "sectors_affected": ["all"],
            "source": "Bureau of Labor Statistics",
            "recurring": True,
            "recurrence_rule": "monthly",
        })

    # GDP Releases (quarterly)
    gdp_dates = [
        (date(2026, 1, 30), "Q4 2025 Advance", "advance"),
        (date(2026, 2, 26), "Q4 2025 Second", "second"),
        (date(2026, 3, 26), "Q4 2025 Third", "third"),
        (date(2026, 4, 30), "Q1 2026 Advance", "advance"),
        (date(2026, 5, 28), "Q1 2026 Second", "second"),
        (date(2026, 6, 25), "Q1 2026 Third", "third"),
        (date(2026, 7, 30), "Q2 2026 Advance", "advance"),
        (date(2026, 8, 27), "Q2 2026 Second", "second"),
        (date(2026, 9, 24), "Q2 2026 Third", "third"),
        (date(2026, 10, 29), "Q3 2026 Advance", "advance"),
        (date(2026, 11, 25), "Q3 2026 Second", "second"),
        (date(2026, 12, 23), "Q3 2026 Third", "third"),
    ]

    for gdp_date, period, estimate_type in gdp_dates:
        impact = EventImpact.HIGH if estimate_type == "advance" else EventImpact.MEDIUM
        events.append({
            "id": f"gdp_{gdp_date.isoformat()}",
            "title": f"GDP {period}",
            "date": gdp_date,
            "category": EventCategory.ECONOMIC,
            "impact": impact,
            "description": f"GDP {estimate_type} estimate for {period.split()[0]}. "
                          "Advance estimates are most market-moving.",
            "time": "08:30 ET",
            "symbols_affected": ["SPY", "QQQ", "TLT"],
            "sectors_affected": ["all"],
            "source": "Bureau of Economic Analysis",
            "recurring": True,
            "recurrence_rule": "quarterly",
        })

    # ISM Manufacturing/Services (monthly)
    for month in range(1, 13):
        # Manufacturing - first business day
        ism_mfg_date = date(2026, month, 3 if month not in [1] else 5)
        events.append({
            "id": f"ism_mfg_{ism_mfg_date.isoformat()}",
            "title": f"ISM Manufacturing PMI",
            "date": ism_mfg_date,
            "category": EventCategory.ECONOMIC,
            "impact": EventImpact.HIGH,
            "description": "ISM Manufacturing Index. Above 50 = expansion. "
                          "Leading indicator for industrial production.",
            "time": "10:00 ET",
            "symbols_affected": ["XLI", "CAT", "DE"],
            "sectors_affected": ["industrials", "materials"],
            "source": "Institute for Supply Management",
            "recurring": True,
            "recurrence_rule": "monthly",
        })

    return events


def get_earnings_events_2026() -> list[dict]:
    """Major earnings seasons and key reports for 2026."""
    return [
        # Q4 2025 Earnings Season
        {
            "id": "earnings_q4_2025_start",
            "title": "Q4 2025 Earnings Season Begins",
            "date": date(2026, 1, 13),
            "category": EventCategory.EARNINGS,
            "impact": EventImpact.HIGH,
            "description": "Q4 2025 earnings kick off with major banks. "
                          "JPM, WFC, C typically report first.",
            "symbols_affected": ["JPM", "WFC", "C", "BAC", "GS"],
            "sectors_affected": ["financials"],
            "source": "Corporate calendars",
        },
        {
            "id": "earnings_mega_tech_q4_2025",
            "title": "Mega-Cap Tech Earnings Week",
            "date": date(2026, 1, 27),
            "end_date": date(2026, 1, 30),
            "category": EventCategory.EARNINGS,
            "impact": EventImpact.CRITICAL,
            "description": "MSFT, META, TSLA, AAPL, AMZN report Q4. "
                          "These 5 drive major index moves.",
            "symbols_affected": ["MSFT", "META", "TSLA", "AAPL", "AMZN", "GOOGL", "NVDA"],
            "sectors_affected": ["tech"],
            "source": "Corporate calendars",
        },
        {
            "id": "nvda_q4_2025",
            "title": "NVIDIA Q4 Earnings",
            "date": date(2026, 2, 26),
            "category": EventCategory.EARNINGS,
            "impact": EventImpact.CRITICAL,
            "description": "NVIDIA Q4 FY26 earnings. AI bellwether. "
                          "Data center revenue and guidance crucial.",
            "time": "16:20 ET",
            "symbols_affected": ["NVDA", "AMD", "AVGO", "SMCI", "ARM"],
            "sectors_affected": ["tech", "semiconductors"],
            "source": "NVIDIA IR",
        },
        # Q1 2026 Earnings Season
        {
            "id": "earnings_q1_2026_start",
            "title": "Q1 2026 Earnings Season Begins",
            "date": date(2026, 4, 13),
            "category": EventCategory.EARNINGS,
            "impact": EventImpact.HIGH,
            "description": "Q1 2026 earnings kick off with banks.",
            "symbols_affected": ["JPM", "WFC", "C", "BAC"],
            "sectors_affected": ["financials"],
            "source": "Corporate calendars",
        },
        {
            "id": "earnings_mega_tech_q1_2026",
            "title": "Mega-Cap Tech Earnings Week",
            "date": date(2026, 4, 28),
            "end_date": date(2026, 4, 30),
            "category": EventCategory.EARNINGS,
            "impact": EventImpact.CRITICAL,
            "description": "Major tech earnings for Q1 2026.",
            "symbols_affected": ["MSFT", "META", "TSLA", "AAPL", "AMZN", "GOOGL"],
            "sectors_affected": ["tech"],
            "source": "Corporate calendars",
        },
        {
            "id": "nvda_q1_2026",
            "title": "NVIDIA Q1 FY27 Earnings",
            "date": date(2026, 5, 28),
            "category": EventCategory.EARNINGS,
            "impact": EventImpact.CRITICAL,
            "description": "NVIDIA Q1 FY27 earnings. AI demand trajectory.",
            "time": "16:20 ET",
            "symbols_affected": ["NVDA", "AMD", "AVGO", "SMCI"],
            "sectors_affected": ["tech", "semiconductors"],
            "source": "NVIDIA IR",
        },
        # Q2 2026 Earnings Season
        {
            "id": "earnings_q2_2026_start",
            "title": "Q2 2026 Earnings Season Begins",
            "date": date(2026, 7, 13),
            "category": EventCategory.EARNINGS,
            "impact": EventImpact.HIGH,
            "description": "Q2 2026 earnings kick off.",
            "symbols_affected": ["JPM", "WFC", "C"],
            "sectors_affected": ["financials"],
            "source": "Corporate calendars",
        },
        {
            "id": "earnings_mega_tech_q2_2026",
            "title": "Mega-Cap Tech Earnings Week",
            "date": date(2026, 7, 28),
            "end_date": date(2026, 7, 30),
            "category": EventCategory.EARNINGS,
            "impact": EventImpact.CRITICAL,
            "description": "Major tech earnings for Q2 2026.",
            "symbols_affected": ["MSFT", "META", "TSLA", "AAPL", "AMZN", "GOOGL"],
            "sectors_affected": ["tech"],
            "source": "Corporate calendars",
        },
        {
            "id": "nvda_q2_2026",
            "title": "NVIDIA Q2 FY27 Earnings",
            "date": date(2026, 8, 27),
            "category": EventCategory.EARNINGS,
            "impact": EventImpact.CRITICAL,
            "description": "NVIDIA Q2 FY27 earnings.",
            "time": "16:20 ET",
            "symbols_affected": ["NVDA", "AMD", "AVGO"],
            "sectors_affected": ["tech", "semiconductors"],
            "source": "NVIDIA IR",
        },
        # Q3 2026 Earnings Season
        {
            "id": "earnings_q3_2026_start",
            "title": "Q3 2026 Earnings Season Begins",
            "date": date(2026, 10, 12),
            "category": EventCategory.EARNINGS,
            "impact": EventImpact.HIGH,
            "description": "Q3 2026 earnings kick off. Pre-election reports.",
            "symbols_affected": ["JPM", "WFC", "C"],
            "sectors_affected": ["financials"],
            "source": "Corporate calendars",
        },
        {
            "id": "earnings_mega_tech_q3_2026",
            "title": "Mega-Cap Tech Earnings Week",
            "date": date(2026, 10, 27),
            "end_date": date(2026, 10, 29),
            "category": EventCategory.EARNINGS,
            "impact": EventImpact.CRITICAL,
            "description": "Major tech earnings for Q3 2026. Week before midterms.",
            "symbols_affected": ["MSFT", "META", "TSLA", "AAPL", "AMZN", "GOOGL"],
            "sectors_affected": ["tech"],
            "source": "Corporate calendars",
        },
        {
            "id": "nvda_q3_2026",
            "title": "NVIDIA Q3 FY27 Earnings",
            "date": date(2026, 11, 19),
            "category": EventCategory.EARNINGS,
            "impact": EventImpact.CRITICAL,
            "description": "NVIDIA Q3 FY27 earnings. Post-midterm report.",
            "time": "16:20 ET",
            "symbols_affected": ["NVDA", "AMD", "AVGO"],
            "sectors_affected": ["tech", "semiconductors"],
            "source": "NVIDIA IR",
        },
    ]


def get_political_events_2026() -> list[dict]:
    """Political and geopolitical events for 2026."""
    return [
        # US Political Events
        {
            "id": "debt_ceiling_2026",
            "title": "Debt Ceiling Deadline (Est.)",
            "date": date(2026, 3, 15),
            "category": EventCategory.POLITICAL,
            "impact": EventImpact.HIGH,
            "description": "Estimated debt ceiling deadline. Treasury extraordinary measures "
                          "expected to run out. Market volatility likely if unresolved.",
            "symbols_affected": ["SPY", "TLT", "DXY"],
            "sectors_affected": ["all"],
            "source": "Treasury/CBO estimates",
        },
        {
            "id": "state_of_union_2026",
            "title": "State of the Union Address",
            "date": date(2026, 2, 3),
            "category": EventCategory.POLITICAL,
            "impact": EventImpact.MEDIUM,
            "description": "President's State of the Union. Watch for economic policy signals, "
                          "infrastructure, energy, trade policy mentions.",
            "time": "21:00 ET",
            "symbols_affected": ["SPY"],
            "sectors_affected": ["all"],
            "source": "White House",
        },
        {
            "id": "midterm_primaries_2026",
            "title": "Primary Season Begins",
            "date": date(2026, 3, 3),
            "end_date": date(2026, 6, 9),
            "category": EventCategory.POLITICAL,
            "impact": EventImpact.MEDIUM,
            "description": "2026 midterm primary season. Watch for policy positioning "
                          "on taxes, healthcare, energy, tech regulation.",
            "sectors_affected": ["healthcare", "energy", "tech"],
            "source": "Various state election offices",
        },
        {
            "id": "midterm_elections_2026",
            "title": "US Midterm Elections",
            "date": date(2026, 11, 3),
            "category": EventCategory.POLITICAL,
            "impact": EventImpact.CRITICAL,
            "description": "2026 US Midterm Elections. All House seats + 1/3 Senate. "
                          "Potential policy shift. Historical pattern: rally into year-end "
                          "regardless of outcome once uncertainty resolves.",
            "symbols_affected": ["SPY", "QQQ", "XLF", "XLE", "XLV"],
            "sectors_affected": ["all"],
            "source": "US Congress",
        },
        {
            "id": "budget_deadline_2026",
            "title": "Federal Budget Deadline",
            "date": date(2026, 9, 30),
            "category": EventCategory.POLITICAL,
            "impact": EventImpact.HIGH,
            "description": "End of fiscal year. Government shutdown risk if no budget/CR passed.",
            "symbols_affected": ["SPY", "TLT"],
            "sectors_affected": ["defense", "healthcare"],
            "source": "Congressional calendar",
        },
        # Geopolitical Events
        {
            "id": "china_npc_2026",
            "title": "China National People's Congress",
            "date": date(2026, 3, 5),
            "end_date": date(2026, 3, 15),
            "category": EventCategory.GEOPOLITICAL,
            "impact": EventImpact.HIGH,
            "description": "Annual NPC meeting. GDP targets, stimulus measures, "
                          "tech/property policy. Major driver for emerging markets.",
            "symbols_affected": ["FXI", "KWEB", "BABA", "JD", "PDD"],
            "sectors_affected": ["emerging_markets", "tech", "commodities"],
            "source": "Chinese government",
        },
        {
            "id": "opec_meeting_2026_06",
            "title": "OPEC+ Meeting",
            "date": date(2026, 6, 1),
            "category": EventCategory.GEOPOLITICAL,
            "impact": EventImpact.HIGH,
            "description": "OPEC+ production decision. Oil supply and price direction.",
            "symbols_affected": ["USO", "XLE", "XOM", "CVX", "SLB", "HAL"],
            "sectors_affected": ["energy"],
            "source": "OPEC",
        },
        {
            "id": "opec_meeting_2026_12",
            "title": "OPEC+ Meeting",
            "date": date(2026, 12, 4),
            "category": EventCategory.GEOPOLITICAL,
            "impact": EventImpact.HIGH,
            "description": "OPEC+ year-end production decision. Sets 2027 supply.",
            "symbols_affected": ["USO", "XLE", "XOM", "CVX"],
            "sectors_affected": ["energy"],
            "source": "OPEC",
        },
        {
            "id": "g20_summit_2026",
            "title": "G20 Summit",
            "date": date(2026, 11, 21),
            "end_date": date(2026, 11, 22),
            "category": EventCategory.GEOPOLITICAL,
            "impact": EventImpact.MEDIUM,
            "description": "G20 Leaders Summit (South Africa hosting). Trade, climate, "
                          "AI regulation discussions.",
            "symbols_affected": ["SPY", "EEM"],
            "sectors_affected": ["all"],
            "source": "G20",
        },
        # Trade/Tariff Events
        {
            "id": "china_tariff_review_2026",
            "title": "China Tariff Review (Est.)",
            "date": date(2026, 2, 15),
            "category": EventCategory.GEOPOLITICAL,
            "impact": EventImpact.HIGH,
            "description": "Potential review of Trump-era China tariffs. "
                          "Impact on supply chains, retail, manufacturing.",
            "symbols_affected": ["FXI", "KWEB", "WMT", "TGT", "AMZN"],
            "sectors_affected": ["retail", "industrials", "tech"],
            "source": "USTR estimates",
        },
    ]


def get_market_structure_events_2026() -> list[dict]:
    """Market structure events for 2026."""
    events = []

    # Options Expiration (Monthly OpEx - 3rd Friday)
    opex_dates = [
        date(2026, 1, 16), date(2026, 2, 20), date(2026, 3, 20),
        date(2026, 4, 17), date(2026, 5, 15), date(2026, 6, 19),
        date(2026, 7, 17), date(2026, 8, 21), date(2026, 9, 18),
        date(2026, 10, 16), date(2026, 11, 20), date(2026, 12, 18),
    ]

    # Triple/Quadruple Witching (quarterly)
    witching_dates = [
        date(2026, 3, 20), date(2026, 6, 19),
        date(2026, 9, 18), date(2026, 12, 18),
    ]

    for opex in opex_dates:
        is_witching = opex in witching_dates
        events.append({
            "id": f"opex_{opex.isoformat()}",
            "title": "Quadruple Witching" if is_witching else "Monthly Options Expiration",
            "date": opex,
            "category": EventCategory.MARKET_STRUCTURE,
            "impact": EventImpact.HIGH if is_witching else EventImpact.MEDIUM,
            "description": ("Quarterly expiration of stock index futures, stock index options, "
                          "stock options, and single stock futures. Expect elevated volume and volatility."
                          if is_witching else
                          "Monthly options expiration. Pin risk and gamma effects."),
            "symbols_affected": ["SPY", "QQQ", "IWM"],
            "sectors_affected": ["all"],
            "source": "Market calendar",
            "recurring": True,
            "recurrence_rule": "monthly",
        })

    # Index Rebalancing
    events.extend([
        {
            "id": "sp500_rebalance_2026_03",
            "title": "S&P 500 Quarterly Rebalance",
            "date": date(2026, 3, 20),
            "category": EventCategory.MARKET_STRUCTURE,
            "impact": EventImpact.MEDIUM,
            "description": "S&P 500 quarterly rebalancing. Additions/deletions take effect.",
            "symbols_affected": ["SPY"],
            "sectors_affected": ["all"],
            "source": "S&P Dow Jones Indices",
        },
        {
            "id": "sp500_rebalance_2026_06",
            "title": "S&P 500 Quarterly Rebalance",
            "date": date(2026, 6, 19),
            "category": EventCategory.MARKET_STRUCTURE,
            "impact": EventImpact.MEDIUM,
            "description": "S&P 500 quarterly rebalancing.",
            "symbols_affected": ["SPY"],
            "sectors_affected": ["all"],
            "source": "S&P Dow Jones Indices",
        },
        {
            "id": "sp500_rebalance_2026_09",
            "title": "S&P 500 Quarterly Rebalance",
            "date": date(2026, 9, 18),
            "category": EventCategory.MARKET_STRUCTURE,
            "impact": EventImpact.MEDIUM,
            "description": "S&P 500 quarterly rebalancing.",
            "symbols_affected": ["SPY"],
            "sectors_affected": ["all"],
            "source": "S&P Dow Jones Indices",
        },
        {
            "id": "sp500_rebalance_2026_12",
            "title": "S&P 500 Quarterly Rebalance",
            "date": date(2026, 12, 18),
            "category": EventCategory.MARKET_STRUCTURE,
            "impact": EventImpact.MEDIUM,
            "description": "S&P 500 quarterly rebalancing. Year-end index changes.",
            "symbols_affected": ["SPY"],
            "sectors_affected": ["all"],
            "source": "S&P Dow Jones Indices",
        },
        {
            "id": "russell_recon_2026",
            "title": "Russell Reconstitution",
            "date": date(2026, 6, 26),
            "category": EventCategory.MARKET_STRUCTURE,
            "impact": EventImpact.HIGH,
            "description": "Annual Russell index reconstitution. Significant flows into "
                          "additions, out of deletions. Small caps most affected.",
            "symbols_affected": ["IWM", "IWO", "IWN"],
            "sectors_affected": ["all"],
            "source": "FTSE Russell",
        },
    ])

    # Tax-Related Events
    events.extend([
        {
            "id": "tax_loss_selling_2026_start",
            "title": "Tax-Loss Selling Season Begins",
            "date": date(2026, 10, 15),
            "category": EventCategory.MARKET_STRUCTURE,
            "impact": EventImpact.MEDIUM,
            "description": "Tax-loss harvesting season intensifies. Pressure on YTD losers.",
            "sectors_affected": ["all"],
            "source": "Market pattern",
        },
        {
            "id": "tax_loss_selling_2026_peak",
            "title": "Tax-Loss Selling Peak",
            "date": date(2026, 12, 15),
            "end_date": date(2026, 12, 23),
            "category": EventCategory.MARKET_STRUCTURE,
            "impact": EventImpact.HIGH,
            "description": "Peak tax-loss selling period. Last chance for 2026 tax year.",
            "sectors_affected": ["all"],
            "source": "Market pattern",
        },
        {
            "id": "santa_rally_2026",
            "title": "Santa Claus Rally Period",
            "date": date(2026, 12, 24),
            "end_date": date(2027, 1, 2),
            "category": EventCategory.MARKET_STRUCTURE,
            "impact": EventImpact.MEDIUM,
            "description": "Historical Santa Claus Rally period. Low volume, positive bias. "
                          "'If Santa Claus should fail to call, bears may come to Broad and Wall.'",
            "symbols_affected": ["SPY", "QQQ"],
            "sectors_affected": ["all"],
            "source": "Yale Hirsch / Stock Trader's Almanac",
        },
    ])

    # Market Holidays (US)
    holidays = [
        (date(2026, 1, 1), "New Year's Day"),
        (date(2026, 1, 19), "MLK Day"),
        (date(2026, 2, 16), "Presidents Day"),
        (date(2026, 4, 3), "Good Friday"),
        (date(2026, 5, 25), "Memorial Day"),
        (date(2026, 6, 19), "Juneteenth"),
        (date(2026, 7, 3), "Independence Day (Observed)"),
        (date(2026, 9, 7), "Labor Day"),
        (date(2026, 11, 26), "Thanksgiving"),
        (date(2026, 12, 25), "Christmas"),
    ]

    for hol_date, hol_name in holidays:
        events.append({
            "id": f"holiday_{hol_date.isoformat()}",
            "title": f"Market Closed: {hol_name}",
            "date": hol_date,
            "category": EventCategory.MARKET_STRUCTURE,
            "impact": EventImpact.LOW,
            "description": f"US equity markets closed for {hol_name}.",
            "sectors_affected": ["all"],
            "source": "NYSE",
        })

    return events


def get_expert_predictions_2026() -> list[dict]:
    """Expert and institutional predictions for 2026."""
    return [
        # Fed Policy Predictions
        {
            "id": "pred_fed_cuts_2026_gs",
            "title": "Goldman: 2 Rate Cuts in 2026",
            "prediction": "Federal Reserve will cut rates twice in 2026, starting in Q2. "
                         "Terminal rate of 3.75-4.00% by year end.",
            "source": "goldman_sachs",
            "source_detail": "Jan Hatzius, Chief Economist",
            "made_date": date(2026, 1, 15),
            "target_date": date(2026, 12, 31),
            "category": EventCategory.FED,
            "confidence": 0.70,
            "direction": "neutral",
            "reasoning": "Inflation trajectory, labor market cooling, global growth concerns",
            "key_assumptions": [
                "Core PCE falls to 2.3% by mid-2026",
                "Unemployment rises to 4.5%",
                "No recession",
            ],
            "invalidation_triggers": [
                "Inflation reaccelerates above 3%",
                "Labor market remains tight (unemployment < 4%)",
            ],
        },
        {
            "id": "pred_fed_cuts_2026_jpm",
            "title": "JPMorgan: 3 Rate Cuts in 2026",
            "prediction": "Fed cuts 3 times in 2026, 75bps total. First cut in March, "
                         "followed by June and September.",
            "source": "jpmorgan",
            "source_detail": "Michael Feroli, Chief US Economist",
            "made_date": date(2026, 1, 10),
            "target_date": date(2026, 12, 31),
            "category": EventCategory.FED,
            "confidence": 0.65,
            "direction": "bullish",
            "reasoning": "Growth slowdown, inflation normalization, employment softening",
            "key_assumptions": [
                "GDP growth slows to 1.5%",
                "No financial stability concerns",
            ],
        },
        # Market Level Predictions
        {
            "id": "pred_sp500_target_2026_gs",
            "title": "Goldman: S&P 500 Year-End Target 6500",
            "prediction": "S&P 500 reaches 6500 by end of 2026, representing ~8% upside "
                         "from current levels.",
            "source": "goldman_sachs",
            "source_detail": "David Kostin, Chief US Equity Strategist",
            "made_date": date(2026, 1, 8),
            "target_date": date(2026, 12, 31),
            "category": EventCategory.CUSTOM,
            "confidence": 0.60,
            "symbols": ["SPY"],
            "direction": "bullish",
            "target_price": 6500,
            "reasoning": "Earnings growth, AI productivity gains, rate cuts supportive",
            "key_assumptions": [
                "EPS growth of 9%",
                "P/E multiple stable at 21x",
                "No recession",
            ],
        },
        {
            "id": "pred_sp500_target_2026_ms",
            "title": "Morgan Stanley: S&P 500 Year-End 5800",
            "prediction": "S&P 500 ends 2026 at 5800, relatively flat from current levels. "
                         "Valuations stretched, earnings growth fully priced.",
            "source": "morgan_stanley",
            "source_detail": "Mike Wilson, Chief US Equity Strategist",
            "made_date": date(2026, 1, 12),
            "target_date": date(2026, 12, 31),
            "category": EventCategory.CUSTOM,
            "confidence": 0.55,
            "symbols": ["SPY"],
            "direction": "neutral",
            "target_price": 5800,
            "reasoning": "Multiple compression, margin pressure, election uncertainty",
            "key_assumptions": [
                "Valuations compress",
                "EPS growth disappoints",
            ],
        },
        # Sector Predictions
        {
            "id": "pred_ai_spending_2026",
            "title": "AI Capex Continues Surge",
            "prediction": "Hyperscaler AI capex grows 40%+ in 2026. NVDA, AMD, AVGO "
                         "primary beneficiaries. Supply constraints persist.",
            "source": "multiple",
            "source_detail": "Consensus: Bank of America, Morgan Stanley, Goldman",
            "made_date": date(2026, 1, 5),
            "target_date": date(2026, 6, 30),
            "category": EventCategory.SECTOR,
            "confidence": 0.80,
            "symbols": ["NVDA", "AMD", "AVGO", "MSFT", "GOOGL", "META", "AMZN"],
            "sectors": ["tech", "semiconductors"],
            "direction": "bullish",
            "reasoning": "AI arms race, enterprise adoption, infrastructure buildout",
            "key_assumptions": [
                "No major AI regulatory restrictions",
                "Enterprise AI adoption accelerates",
            ],
        },
        {
            "id": "pred_energy_2026",
            "title": "Oil Range-Bound $70-90",
            "prediction": "WTI crude trades in $70-90 range through 2026. "
                         "OPEC+ manages supply, demand growth modest.",
            "source": "energy_consensus",
            "source_detail": "EIA, Goldman, JPMorgan consensus",
            "made_date": date(2026, 1, 10),
            "target_date": date(2026, 12, 31),
            "category": EventCategory.SECTOR,
            "confidence": 0.65,
            "symbols": ["USO", "XLE", "XOM", "CVX"],
            "sectors": ["energy"],
            "direction": "neutral",
            "target_range": (70, 90),
            "reasoning": "OPEC+ discipline, US production, China demand uncertainty",
            "key_assumptions": [
                "No major geopolitical disruption",
                "OPEC+ maintains cohesion",
            ],
            "invalidation_triggers": [
                "Middle East conflict escalation",
                "China stimulus surprise",
                "US SPR releases",
            ],
        },
        # Economic Predictions
        {
            "id": "pred_recession_2026",
            "title": "No Recession in 2026",
            "prediction": "US avoids recession in 2026. GDP growth of 1.5-2.0%. "
                         "Soft landing achieved.",
            "source": "fed_consensus",
            "source_detail": "Federal Reserve, IMF, major banks",
            "made_date": date(2026, 1, 1),
            "target_date": date(2026, 12, 31),
            "category": EventCategory.ECONOMIC,
            "confidence": 0.70,
            "direction": "neutral",
            "reasoning": "Consumer resilience, labor market normalization, inflation contained",
            "key_assumptions": [
                "No major financial crisis",
                "Fed engineers soft landing",
            ],
            "invalidation_triggers": [
                "Credit crisis",
                "Major bank failure",
                "Unemployment spike above 5.5%",
            ],
        },
        {
            "id": "pred_inflation_2026",
            "title": "Inflation Reaches 2.5% by Mid-2026",
            "prediction": "Core PCE falls to 2.5% by June 2026, approaching Fed's target. "
                         "Shelter inflation finally eases.",
            "source": "fed_consensus",
            "made_date": date(2026, 1, 1),
            "target_date": date(2026, 6, 30),
            "category": EventCategory.ECONOMIC,
            "confidence": 0.60,
            "direction": "neutral",
            "reasoning": "Shelter lag effect, goods disinflation, services moderating",
            "key_assumptions": [
                "Rent inflation continues falling",
                "No energy shock",
            ],
        },
        # Geopolitical Predictions
        {
            "id": "pred_china_stimulus_2026",
            "title": "China Announces Major Stimulus",
            "prediction": "China announces significant fiscal stimulus package in Q1 2026 "
                         "to support property sector and consumer spending.",
            "source": "macro_analysts",
            "source_detail": "Multiple: Gavekal, Rhodium Group",
            "made_date": date(2026, 1, 15),
            "target_date": date(2026, 3, 31),
            "category": EventCategory.GEOPOLITICAL,
            "confidence": 0.70,
            "symbols": ["FXI", "KWEB", "BABA", "EEM", "FCX", "CLF"],
            "sectors": ["emerging_markets", "materials"],
            "direction": "bullish",
            "reasoning": "Economic targets require support, property crisis ongoing, deflation risk",
            "key_assumptions": [
                "NPC sets ambitious GDP target",
                "Property stabilization prioritized",
            ],
        },
    ]


def get_claude_predictions_2026() -> list[dict]:
    """Claude's market predictions with reasoning."""
    return [
        # Market Structure Predictions
        {
            "id": "claude_market_breadth_2026",
            "title": "Market Breadth Improves H2 2026",
            "prediction": "The narrow market leadership (Magnificent 7 dominance) broadens "
                         "in the second half of 2026. Equal-weight S&P 500 outperforms "
                         "cap-weighted by 5%+ from July-December.",
            "source": "claude",
            "made_date": date(2026, 1, 20),
            "target_date": date(2026, 12, 31),
            "category": EventCategory.CUSTOM,
            "confidence": 0.65,
            "symbols": ["RSP", "SPY"],
            "direction": "bullish",
            "reasoning": (
                "1. Valuation gap between mega-caps and rest of market at historical extremes\n"
                "2. Rate cuts historically benefit smaller companies more (financing cost sensitive)\n"
                "3. AI capex beneficiaries expanding beyond NVDA to broader ecosystem\n"
                "4. Mean reversion in relative performance typically occurs within 18-24 months"
            ),
            "key_assumptions": [
                "Fed cuts rates at least once",
                "No recession",
                "AI adoption broadens beyond hyperscalers",
            ],
            "invalidation_triggers": [
                "Recession occurs, flight to quality",
                "Mega-cap earnings massively outperform",
                "Credit tightens significantly",
            ],
        },
        {
            "id": "claude_vix_regime_2026",
            "title": "VIX Elevated Through H1, Normalizes H2",
            "prediction": "VIX averages above 18 in H1 2026 due to election uncertainty and "
                         "Fed transition, then normalizes to 14-16 range in H2 after "
                         "midterms resolve uncertainty.",
            "source": "claude",
            "made_date": date(2026, 1, 20),
            "target_date": date(2026, 12, 31),
            "category": EventCategory.MARKET_STRUCTURE,
            "confidence": 0.60,
            "symbols": ["VIX", "UVXY", "SVXY"],
            "direction": "neutral",
            "reasoning": (
                "1. Midterm election years historically show elevated volatility through October\n"
                "2. Fed policy transition creates uncertainty\n"
                "3. Post-election volatility crush is consistent pattern\n"
                "4. Geopolitical risks remain but are known factors"
            ),
            "key_assumptions": [
                "No major geopolitical shock",
                "Election proceeds normally",
            ],
        },
        # Sector Predictions
        {
            "id": "claude_semis_cycle_2026",
            "title": "Semi Cycle Peak Q2-Q3 2026",
            "prediction": "Semiconductor cycle peaks in Q2-Q3 2026. SOX outperforms through "
                         "May, then consolidates. Memory recovers fastest (MU, SK Hynix), "
                         "while AI semis (NVDA) show slower growth rates but remain strong.",
            "source": "claude",
            "made_date": date(2026, 1, 20),
            "target_date": date(2026, 9, 30),
            "category": EventCategory.SECTOR,
            "confidence": 0.55,
            "symbols": ["SMH", "NVDA", "AMD", "MU", "AVGO", "QCOM"],
            "sectors": ["semiconductors"],
            "direction": "neutral",
            "reasoning": (
                "1. Memory cycle bottomed late 2025, recovery underway\n"
                "2. AI demand remains strong but growth rate decelerating\n"
                "3. Inventory digestion for non-AI chips completing\n"
                "4. Auto/industrial demand recovering from trough\n"
                "5. Classic semiconductor cycle timing suggests mid-year peak"
            ),
            "key_assumptions": [
                "No major supply chain disruption",
                "China demand doesn't collapse further",
            ],
            "invalidation_triggers": [
                "AI demand acceleration above expectations",
                "Major geopolitical restriction on chip trade",
            ],
        },
        {
            "id": "claude_energy_thesis_2026",
            "title": "Energy Value Trap Until Q3",
            "prediction": "Energy sector (XLE) underperforms S&P 500 through Q3 2026 "
                         "despite reasonable valuations. Oil service names underperform "
                         "E&Ps. Tactical opportunity emerges Q4 with winter demand.",
            "source": "claude",
            "made_date": date(2026, 1, 20),
            "target_date": date(2026, 10, 31),
            "category": EventCategory.SECTOR,
            "confidence": 0.50,
            "symbols": ["XLE", "XOP", "OIH", "SLB", "HAL", "XOM", "CVX"],
            "sectors": ["energy"],
            "direction": "bearish",
            "reasoning": (
                "1. OPEC+ supply discipline weakening, member compliance declining\n"
                "2. US production growth continues\n"
                "3. China demand uncertainty persists\n"
                "4. Transition to renewables accelerating investment allocation\n"
                "5. Election uncertainty on energy policy"
            ),
            "key_assumptions": [
                "No major supply disruption",
                "OPEC+ cohesion weakens",
            ],
            "invalidation_triggers": [
                "Middle East conflict escalation",
                "China stimulus bigger than expected",
                "OPEC+ surprise cut",
            ],
        },
        # Macro Predictions
        {
            "id": "claude_dollar_2026",
            "title": "Dollar Weakens 5-8% Against Majors",
            "prediction": "DXY declines 5-8% in 2026 as Fed cuts while ECB/BOJ normalize. "
                         "EUR/USD reaches 1.15, USD/JPY falls below 140.",
            "source": "claude",
            "made_date": date(2026, 1, 20),
            "target_date": date(2026, 12, 31),
            "category": EventCategory.ECONOMIC,
            "confidence": 0.55,
            "symbols": ["UUP", "FXE", "FXY", "EEM"],
            "direction": "bearish",
            "reasoning": (
                "1. Fed cutting while others hold/tighten reduces yield advantage\n"
                "2. Twin deficit concerns resurface\n"
                "3. Mean reversion from decade of strength\n"
                "4. Emerging market flows improve with weaker dollar"
            ),
            "key_assumptions": [
                "Fed cuts more than ECB",
                "BOJ continues normalization",
                "No flight to safety event",
            ],
            "invalidation_triggers": [
                "Global recession (safety bid)",
                "Fed stays higher for longer than others",
                "Geopolitical crisis",
            ],
        },
        {
            "id": "claude_real_estate_2026",
            "title": "Commercial Real Estate Stabilizes Q2",
            "prediction": "Commercial real estate (ex-office) finds bottom in Q2 2026. "
                         "REITs (VNQ) outperform from March-December as rate cuts boost "
                         "values and financing costs ease.",
            "source": "claude",
            "made_date": date(2026, 1, 20),
            "target_date": date(2026, 12, 31),
            "category": EventCategory.SECTOR,
            "confidence": 0.60,
            "symbols": ["VNQ", "IYR", "XLRE", "SPG", "PLD", "AMT"],
            "sectors": ["real_estate"],
            "direction": "bullish",
            "reasoning": (
                "1. Rate cuts directly benefit rate-sensitive REITs\n"
                "2. Distressed sales creating buying opportunities\n"
                "3. Industrial/data center demand remains strong\n"
                "4. Residential multifamily benefiting from housing shortage\n"
                "5. Office pain isolated, not systemic"
            ),
            "key_assumptions": [
                "Fed cuts at least 50bps",
                "No major bank CRE crisis",
            ],
            "invalidation_triggers": [
                "Rates stay high longer",
                "Regional bank failures from CRE exposure",
                "Recession hits occupancy",
            ],
        },
        # Event-Specific Predictions
        {
            "id": "claude_midterm_pattern_2026",
            "title": "Classic Midterm Rally Pattern Holds",
            "prediction": "Markets follow historical midterm pattern: weakness/chop through "
                         "October, strong rally November-December regardless of outcome. "
                         "SPY +8-12% from October low to year-end.",
            "source": "claude",
            "made_date": date(2026, 1, 20),
            "target_date": date(2026, 12, 31),
            "category": EventCategory.POLITICAL,
            "confidence": 0.70,
            "symbols": ["SPY", "QQQ", "IWM"],
            "direction": "bullish",
            "reasoning": (
                "1. Midterm year pattern is one of most reliable seasonal effects\n"
                "2. Uncertainty removal is the key driver, not the outcome\n"
                "3. Since 1950, Q4 of midterm years average +8%\n"
                "4. Corporate buyback blackouts end post-election\n"
                "5. Tax-loss selling reversal in December"
            ),
            "key_assumptions": [
                "Election proceeds without major disruption",
                "No recession",
            ],
            "invalidation_triggers": [
                "Contested election",
                "Recession begins",
                "Major geopolitical event",
            ],
        },
        {
            "id": "claude_ai_bubble_2026",
            "title": "AI Not a Bubble But Rotation Within",
            "prediction": "AI theme continues but leadership rotates. Pure-play AI (NVDA) "
                         "consolidates while AI beneficiaries (enterprise software, industrials "
                         "with AI applications) outperform. NVDA +10-20%, AI software +30-40%.",
            "source": "claude",
            "made_date": date(2026, 1, 20),
            "target_date": date(2026, 12, 31),
            "category": EventCategory.SECTOR,
            "confidence": 0.60,
            "symbols": ["NVDA", "CRM", "NOW", "PLTR", "AI", "PATH"],
            "sectors": ["tech"],
            "direction": "bullish",
            "reasoning": (
                "1. AI infrastructure buildout continues but growth rate decelerates\n"
                "2. Focus shifts to AI applications and monetization\n"
                "3. Enterprise AI adoption accelerates\n"
                "4. Stock picker's market within AI theme\n"
                "5. Not a bubble - actual revenue/earnings growth supports valuations"
            ),
            "key_assumptions": [
                "AI delivers productivity gains",
                "Enterprise adoption continues",
                "No major regulatory restrictions",
            ],
        },
    ]
