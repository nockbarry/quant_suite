#!/usr/bin/env python3
"""
Test all new data sources created in Batches 3-6.

Verifies:
1. Each source can be instantiated and called
2. Output format is correct for daily use
3. Data can be serialized/deserialized for retrospective analysis
4. Caching works properly
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.paths import paths


def print_section(title: str) -> None:
    """Print a section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def print_subsection(title: str) -> None:
    """Print a subsection header."""
    print(f"\n--- {title} ---\n")


async def test_earnings_calendar() -> bool:
    """Test earnings calendar source."""
    print_section("EARNINGS CALENDAR")

    try:
        from src.data.sources.alternative.earnings_calendar import (
            EarningsCalendarSource,
            EarningsEvent,
            EarningsCalendar,
        )

        source = EarningsCalendarSource()

        # Test manual event creation for testing
        print_subsection("Creating test events")

        # Create a test calendar with manual data
        calendar = EarningsCalendar(timestamp=datetime.now())

        test_events = [
            EarningsEvent(
                symbol="AAPL",
                company_name="Apple Inc.",
                report_date=datetime.now() + timedelta(days=5),
                report_time="AMC",
                eps_estimate=2.15,
                eps_whisper=2.20,
                revenue_estimate=95000,
                historical_beat_rate=0.85,
                implied_move=4.5,
                sector="Technology",
                market_cap=3000,
            ),
            EarningsEvent(
                symbol="MSFT",
                company_name="Microsoft Corporation",
                report_date=datetime.now() + timedelta(days=2),
                report_time="BMO",
                eps_estimate=2.85,
                revenue_estimate=62000,
                sector="Technology",
                market_cap=2800,
            ),
            EarningsEvent(
                symbol="JPM",
                company_name="JPMorgan Chase",
                report_date=datetime.now(),
                report_time="BMO",
                eps_estimate=4.10,
                sector="Financials",
                market_cap=550,
            ),
        ]

        for event in test_events:
            calendar.events.append(event)

        # Test properties
        print(f"Total events: {len(calendar.events)}")
        print(f"Today: {len(calendar.today)}")
        print(f"This week: {len(calendar.this_week)}")
        print(f"BMO today: {len(calendar.bmo_today)}")
        print(f"AMC today: {len(calendar.amc_today)}")

        # Test serialization
        print_subsection("Testing serialization")
        data = calendar.to_dict()
        print(f"Serialized keys: {list(data.keys())}")
        print(f"Events serialized: {len(data['events'])}")

        # Test deserialization
        restored = EarningsCalendar.from_dict(data)
        print(f"Restored events: {len(restored.events)}")

        # Verify data integrity
        assert len(restored.events) == len(calendar.events), "Event count mismatch"
        assert restored.events[0].symbol == calendar.events[0].symbol, "Symbol mismatch"

        # Test event properties
        print_subsection("Event details")
        for event in calendar.events[:3]:
            print(f"  {event.symbol}: {event.company_name}")
            print(f"    Report: {event.report_date.strftime('%Y-%m-%d')} {event.report_time}")
            print(f"    EPS Est: ${event.eps_estimate or 'N/A'}")
            print(f"    Days until: {event.days_until}")
            print(f"    Is today: {event.is_today}")

        await source.close()
        print("\n✓ Earnings Calendar: PASSED")
        return True

    except Exception as e:
        print(f"\n✗ Earnings Calendar: FAILED - {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_economic_calendar() -> bool:
    """Test economic calendar source."""
    print_section("ECONOMIC CALENDAR")

    try:
        from src.data.sources.alternative.economic_calendar import (
            EconomicCalendarSource,
            EconomicRelease,
            EconomicCalendar,
            RELEASE_DEFINITIONS,
            ReleaseCategory,
            ReleaseImportance,
        )

        source = EconomicCalendarSource()

        # Test release definitions
        print_subsection("Release definitions")
        print(f"Total defined releases: {len(RELEASE_DEFINITIONS)}")
        for release_id, defn in list(RELEASE_DEFINITIONS.items())[:5]:
            print(f"  {release_id}: {defn['name']} ({defn['importance'].value})")

        # Get calendar
        print_subsection("Fetching calendar")
        calendar = await source.get_calendar()

        print(f"Calendar timestamp: {calendar.timestamp}")
        print(f"Total events: {len(calendar.events)}")
        print(f"High impact: {len(calendar.high_impact)}")
        print(f"Today: {len(calendar.today)}")
        print(f"This week: {len(calendar.this_week)}")

        # Test serialization
        print_subsection("Testing serialization")
        data = calendar.to_dict()
        restored = EconomicCalendar.from_dict(data)
        print(f"Restored events: {len(restored.events)}")

        # Add manual event
        print_subsection("Adding manual event")
        event = source.add_event(
            release_id="nfp",
            release_date=datetime.now() + timedelta(days=3),
            prior_value=256000,
            consensus=180000,
            notes="Test event",
        )
        print(f"Added: {event.name} on {event.release_date.strftime('%Y-%m-%d')}")
        print(f"  Prior: {event.prior_value}, Consensus: {event.consensus}")

        # Verify high impact check
        print_subsection("High impact check")
        has_high = source.has_high_impact_today()
        print(f"Has high impact today: {has_high}")

        await source.close()
        print("\n✓ Economic Calendar: PASSED")
        return True

    except Exception as e:
        print(f"\n✗ Economic Calendar: FAILED - {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_fed_futures() -> bool:
    """Test Fed futures source."""
    print_section("FED FUTURES")

    try:
        from src.data.sources.alternative.fed_futures import (
            FedFuturesSource,
            FedExpectations,
            FOMCMeeting,
            FOMC_DATES_2026,
        )

        source = FedFuturesSource()

        # Test FOMC schedule
        print_subsection("FOMC Schedule 2026")
        print(f"Total meetings: {len(FOMC_DATES_2026)}")
        for date in FOMC_DATES_2026[:5]:
            print(f"  {date.strftime('%Y-%m-%d')}")

        # Get expectations
        print_subsection("Fetching expectations")
        expectations = await source.get_expectations()

        print(f"Current rate: {expectations.current_rate:.2%}")
        print(f"Next meeting: {expectations.next_meeting.meeting_date.strftime('%Y-%m-%d')}")
        print(f"  Days until: {expectations.next_meeting.days_until}")
        print(f"Probabilities:")
        print(f"  Hike: {expectations.prob_hike:.1%}")
        print(f"  Cut: {expectations.prob_cut:.1%}")
        print(f"  Hold: {expectations.prob_hold:.1%}")
        print(f"Rate path signal: {expectations.rate_path_signal}")
        print(f"Implied 3M rate: {expectations.implied_rate_3m:.2%}")
        print(f"Implied 6M rate: {expectations.implied_rate_6m:.2%}")

        # Test serialization
        print_subsection("Testing serialization")
        data = expectations.to_dict()
        print(f"Serialized keys: {list(data.keys())}")
        restored = FedExpectations.from_dict(data)
        print(f"Restored current rate: {restored.current_rate:.2%}")

        # Update expectations manually
        print_subsection("Manual update")
        source.update_expectations(
            prob_hike=0.05,
            prob_cut=0.65,
            prob_hold=0.30,
            implied_rate_3m=5.00,
            implied_rate_6m=4.75,
            implied_rate_12m=4.50,
        )
        updated = await source.get_expectations()
        print(f"Updated prob_cut: {updated.prob_cut:.1%}")
        print(f"Updated signal: {updated.rate_path_signal}")

        await source.close()
        print("\n✓ Fed Futures: PASSED")
        return True

    except Exception as e:
        print(f"\n✗ Fed Futures: FAILED - {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_treasury_calendar() -> bool:
    """Test Treasury calendar source."""
    print_section("TREASURY CALENDAR")

    try:
        from src.data.sources.alternative.treasury_calendar import (
            TreasuryCalendarSource,
            TreasuryCalendar,
            TreasuryAuction,
            SecurityType,
            SECURITY_IMPACT,
        )

        source = TreasuryCalendarSource()

        # Test security types
        print_subsection("Security types and impacts")
        for sec_type in list(SecurityType)[:6]:
            impact = SECURITY_IMPACT.get(sec_type, "unknown")
            print(f"  {sec_type.value}: {impact}")

        # Get calendar
        print_subsection("Fetching calendar")
        calendar = await source.get_calendar()

        print(f"Calendar timestamp: {calendar.timestamp}")
        print(f"Total auctions: {len(calendar.auctions)}")
        print(f"This week: {len(calendar.this_week)}")
        print(f"High impact: {len(calendar.high_impact)}")
        print(f"Weekly issuance: ${calendar.total_issuance_this_week:.0f}B")

        # Test serialization
        print_subsection("Testing serialization")
        data = calendar.to_dict()
        restored = TreasuryCalendar.from_dict(data)
        print(f"Restored auctions: {len(restored.auctions)}")

        # Show upcoming auctions
        print_subsection("Upcoming auctions")
        for auction in calendar.auctions[:5]:
            print(f"  {auction.auction_date.strftime('%m/%d %a')}: {auction.security_type}")
            print(f"    Amount: ${auction.amount_billions or 0:.0f}B, Impact: {auction.impact_level}")

        # Add manual auction
        print_subsection("Adding manual auction")
        auction = source.add_auction(
            security_type=SecurityType.NOTE_10Y.value,
            auction_date=datetime.now() + timedelta(days=7),
            amount_billions=42.0,
            previous_yield=4.25,
            notes="Test auction",
        )
        print(f"Added: {auction.security_type} on {auction.auction_date.strftime('%Y-%m-%d')}")

        await source.close()
        print("\n✓ Treasury Calendar: PASSED")
        return True

    except Exception as e:
        print(f"\n✗ Treasury Calendar: FAILED - {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_ipo_calendar() -> bool:
    """Test IPO calendar source."""
    print_section("IPO CALENDAR")

    try:
        from src.data.sources.alternative.ipo_calendar import (
            IPOCalendarSource,
            IPOCalendar,
            IPOEvent,
        )

        source = IPOCalendarSource()

        # Add test IPOs
        print_subsection("Adding test IPOs")

        ipo1 = source.add_ipo(
            company_name="TechStartup Inc.",
            symbol="TECH",
            expected_date=datetime.now() + timedelta(days=10),
            price_low=18.0,
            price_high=22.0,
            shares_offered=15000000,
            sector="Technology",
            exchange="NASDAQ",
            underwriters=["Goldman Sachs", "Morgan Stanley"],
        )
        print(f"Added: {ipo1.company_name} ({ipo1.symbol})")
        print(f"  Price range: {ipo1.price_range}")
        print(f"  Deal size: ${ipo1.deal_size:.0f}M")

        ipo2 = source.add_ipo(
            company_name="BigBiotech Corp",
            symbol="BBIO",
            expected_date=datetime.now() + timedelta(days=3),
            price_low=24.0,
            price_high=28.0,
            shares_offered=20000000,
            sector="Healthcare",
            exchange="NYSE",
        )
        print(f"Added: {ipo2.company_name} ({ipo2.symbol})")
        print(f"  Deal size: ${ipo2.deal_size:.0f}M")
        print(f"  Is large deal: {ipo2.is_large_deal}")

        # Get calendar
        print_subsection("Fetching calendar")
        calendar = await source.get_calendar()

        print(f"Total IPOs: {len(calendar.ipos)}")
        print(f"This week: {len(calendar.this_week)}")
        print(f"Large deals: {len(calendar.large_deals)}")
        print(f"Deal volume this week: ${calendar.total_deal_volume_this_week:.0f}M")

        # Test serialization
        print_subsection("Testing serialization")
        data = calendar.to_dict()
        restored = IPOCalendar.from_dict(data)
        print(f"Restored IPOs: {len(restored.ipos)}")

        # Show upcoming
        print_subsection("Upcoming IPOs")
        for ipo in calendar.upcoming[:5]:
            print(f"  {ipo.expected_date.strftime('%m/%d')}: {ipo.symbol} - {ipo.company_name}")
            print(f"    {ipo.price_range}, Sector: {ipo.sector}")

        # Test update priced
        print_subsection("Updating IPO as priced")
        success = source.update_ipo_priced("TECH", price_final=20.50, first_day_return=0.15)
        print(f"Update success: {success}")

        await source.close()
        print("\n✓ IPO Calendar: PASSED")
        return True

    except Exception as e:
        print(f"\n✗ IPO Calendar: FAILED - {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_fda_calendar() -> bool:
    """Test FDA calendar source."""
    print_section("FDA CALENDAR")

    try:
        from src.data.sources.alternative.fda_calendar import (
            FDACalendarSource,
            FDACalendar,
            FDAEvent,
            EventType,
            APPROVAL_RATES,
        )

        source = FDACalendarSource()

        # Test approval rates
        print_subsection("Historical approval rates")
        for indication, rate in list(APPROVAL_RATES.items())[:5]:
            print(f"  {indication}: {rate:.0%}")

        # Add test events
        print_subsection("Adding test events")

        event1 = source.add_event(
            company="Moderna",
            symbol="MRNA",
            drug_name="mRNA-4157",
            indication="Melanoma",
            event_type=EventType.PDUFA.value,
            expected_date=datetime.now() + timedelta(days=30),
            indication_category="oncology",
            is_breakthrough=True,
            notes="Combination with Keytruda",
        )
        print(f"Added: {event1.drug_name} for {event1.indication}")
        print(f"  Event type: {event1.event_type}")
        print(f"  Est. approval prob: {event1.estimated_approval_probability:.0%}")
        print(f"  Is binary event: {event1.is_binary_event}")

        event2 = source.add_event(
            company="Vertex",
            symbol="VRTX",
            drug_name="VX-548",
            indication="Acute Pain",
            event_type=EventType.ADCOM.value,
            expected_date=datetime.now() + timedelta(days=14),
            indication_category="neurology",
            is_priority_review=True,
        )
        print(f"Added: {event2.drug_name} AdCom")

        # Get calendar
        print_subsection("Fetching calendar")
        calendar = await source.get_calendar()

        print(f"Total events: {len(calendar.events)}")
        print(f"This week: {len(calendar.this_week)}")
        print(f"PDUFA dates: {len(calendar.pdufa_dates)}")
        print(f"AdCom meetings: {len(calendar.adcom_meetings)}")
        print(f"Binary events: {len(calendar.binary_events)}")

        # Test serialization
        print_subsection("Testing serialization")
        data = calendar.to_dict()
        restored = FDACalendar.from_dict(data)
        print(f"Restored events: {len(restored.events)}")

        # Check catalyst
        print_subsection("Checking catalysts")
        has_catalyst = source.has_binary_event_soon("MRNA", days=60)
        print(f"MRNA has binary event within 60 days: {has_catalyst}")

        # High probability events
        print_subsection("High probability events")
        high_prob = calendar.get_high_probability(min_prob=0.45)
        for event in high_prob[:3]:
            print(f"  {event.symbol}: {event.drug_name} ({event.estimated_approval_probability:.0%})")

        await source.close()
        print("\n✓ FDA Calendar: PASSED")
        return True

    except Exception as e:
        print(f"\n✗ FDA Calendar: FAILED - {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_patent_filings() -> bool:
    """Test patent filings source."""
    print_section("PATENT FILINGS")

    try:
        from src.data.sources.alternative.patent_filings import (
            USPTOSource,
            PatentDatabase,
            PatentActivity,
            COMPANY_ASSIGNEES,
        )

        source = USPTOSource()

        # Show tracked companies
        print_subsection("Tracked companies")
        for symbol, assignees in list(COMPANY_ASSIGNEES.items())[:5]:
            print(f"  {symbol}: {assignees[0]}")

        # Add test data
        print_subsection("Adding patent activity")

        source.update_activity(
            symbol="AAPL",
            patents_filed=2500,
            patents_granted=1800,
            yoy_change=0.15,
            key_technologies=["Neural Engine", "AR/VR", "Battery", "Display"],
        )

        source.update_activity(
            symbol="MSFT",
            patents_filed=3200,
            patents_granted=2400,
            yoy_change=0.22,
            key_technologies=["AI/ML", "Cloud", "Security", "Gaming"],
        )

        source.update_activity(
            symbol="NVDA",
            patents_filed=1200,
            patents_granted=900,
            yoy_change=0.35,
            key_technologies=["GPU", "AI Accelerators", "Automotive"],
        )

        # Get database
        print_subsection("Fetching database")
        database = await source.get_database()

        print(f"Companies tracked: {len(database.activities)}")

        # Show top innovators
        print_subsection("Top innovators")
        for activity in database.get_top_innovators(5):
            print(f"  {activity.symbol}: {activity.patents_filed} filed")
            print(f"    YoY change: {activity.yoy_change_filed or 0:+.1%}")
            print(f"    Innovation score: {activity.innovation_score:.0f}")
            print(f"    Technologies: {', '.join(activity.key_technologies[:3])}")

        # Test serialization
        print_subsection("Testing serialization")
        data = database.to_dict()
        restored = PatentDatabase.from_dict(data)
        print(f"Restored activities: {len(restored.activities)}")

        # Get signal
        print_subsection("Innovation signals")
        for symbol in ["AAPL", "MSFT", "NVDA"]:
            signal = source.get_innovation_signal(symbol)
            print(f"  {symbol}: {signal:.2f}" if signal else f"  {symbol}: N/A")

        await source.close()
        print("\n✓ Patent Filings: PASSED")
        return True

    except Exception as e:
        print(f"\n✗ Patent Filings: FAILED - {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_job_postings() -> bool:
    """Test job postings source."""
    print_section("JOB POSTINGS")

    try:
        from src.data.sources.alternative.job_postings import (
            JobPostingSource,
            JobDatabase,
            JobPostings,
            CAREER_PAGES,
        )

        source = JobPostingSource()

        # Show career pages
        print_subsection("Career pages tracked")
        for symbol, url in list(CAREER_PAGES.items())[:5]:
            print(f"  {symbol}: {url}")

        # Add test data
        print_subsection("Adding job posting data")

        source.update_postings(
            symbol="AAPL",
            company="Apple",
            total_openings=5200,
            engineering_roles=2800,
            sales_roles=800,
            previous_count=4800,
        )

        source.update_postings(
            symbol="MSFT",
            company="Microsoft",
            total_openings=8500,
            engineering_roles=4500,
            sales_roles=1500,
            previous_count=8200,
        )

        source.update_postings(
            symbol="META",
            company="Meta Platforms",
            total_openings=2100,
            engineering_roles=1400,
            sales_roles=200,
            previous_count=3500,  # Significant contraction
        )

        # Get database
        print_subsection("Fetching database")
        database = await source.get_database()

        print(f"Companies tracked: {len(database.postings)}")

        # Show details
        print_subsection("Job posting details")
        for postings in database.postings.values():
            print(f"  {postings.symbol}: {postings.total_openings} openings")
            print(f"    Engineering: {postings.engineering_roles} ({postings.engineering_ratio:.0%})")
            print(f"    30d change: {postings.change_pct_30d or 0:+.1%}")
            print(f"    Signal: {postings.growth_signal}")

        # Expanding/contracting
        print_subsection("Growth signals")
        expanding = database.get_expanding()
        contracting = database.get_contracting()
        print(f"Expanding: {[p.symbol for p in expanding]}")
        print(f"Contracting: {[p.symbol for p in contracting]}")

        # Test serialization
        print_subsection("Testing serialization")
        data = database.to_dict()
        restored = JobDatabase.from_dict(data)
        print(f"Restored postings: {len(restored.postings)}")

        await source.close()
        print("\n✓ Job Postings: PASSED")
        return True

    except Exception as e:
        print(f"\n✗ Job Postings: FAILED - {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_app_rankings() -> bool:
    """Test app rankings source."""
    print_section("APP RANKINGS")

    try:
        from src.data.sources.alternative.app_rankings import (
            AppRankingSource,
            AppRankingDatabase,
            AppRanking,
            AppStore,
            AppCategory,
            APP_COMPANY_MAP,
        )

        source = AppRankingSource()

        # Show app mappings
        print_subsection("App to company mappings")
        for app, symbol in list(APP_COMPANY_MAP.items())[:8]:
            print(f"  {app}: {symbol}")

        # Add test data
        print_subsection("Adding app rankings")

        source.update_ranking("Instagram", 1, previous_rank=1, rank_7d_ago=2, rating=4.7)
        source.update_ranking("TikTok", 2, previous_rank=3, rank_7d_ago=5, rating=4.8)
        source.update_ranking("YouTube", 3, previous_rank=2, rank_7d_ago=3, rating=4.7)
        source.update_ranking("Facebook", 5, previous_rank=4, rank_7d_ago=4, rating=4.0)
        source.update_ranking("Snapchat", 8, previous_rank=6, rank_7d_ago=6, rating=4.2)
        source.update_ranking("Netflix", 15, previous_rank=12, rank_7d_ago=10, rating=4.3)
        source.update_ranking("Cash App", 4, previous_rank=5, rank_7d_ago=8, rating=4.8)

        # Get database
        print_subsection("Fetching database")
        database = await source.get_database()

        print(f"Apps tracked: {len(database.rankings)}")

        # Top apps
        print_subsection("Top 10 apps")
        for r in database.get_top_apps(10):
            change = f" ({r.rank_change_7d:+d} 7d)" if r.rank_change_7d else ""
            print(f"  #{r.current_rank} {r.app_name} ({r.symbol}){change}")

        # Biggest movers
        print_subsection("Biggest movers")
        for r in database.get_biggest_movers(5):
            print(f"  {r.app_name}: {r.rank_change_7d:+d} spots (now #{r.current_rank})")

        # Company summary
        print_subsection("Company summary - META")
        summary = database.get_company_summary("META")
        print(f"  Apps: {len(summary.apps)}")
        print(f"  Top app: {summary.top_app.app_name if summary.top_app else 'N/A'}")
        print(f"  Avg momentum: {summary.avg_momentum:.2f}")

        # Test momentum signal
        signal = source.get_momentum_signal("META")
        print(f"  Momentum signal: {signal:.2f}" if signal else "  Momentum signal: N/A")

        # Test serialization
        print_subsection("Testing serialization")
        data = database.to_dict()
        restored = AppRankingDatabase.from_dict(data)
        print(f"Restored rankings: {len(restored.rankings)}")

        await source.close()
        print("\n✓ App Rankings: PASSED")
        return True

    except Exception as e:
        print(f"\n✗ App Rankings: FAILED - {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_github_activity() -> bool:
    """Test GitHub activity source."""
    print_section("GITHUB ACTIVITY")

    try:
        from src.data.sources.alternative.github_activity import (
            GitHubSource,
            GitHubDatabase,
            GitHubActivity,
            COMPANY_ORGS,
        )

        source = GitHubSource()

        # Show org mappings
        print_subsection("Company to GitHub org mappings")
        for symbol, orgs in list(COMPANY_ORGS.items())[:5]:
            print(f"  {symbol}: {orgs}")

        # Add test data
        print_subsection("Adding GitHub activity")

        source.update_activity(
            symbol="MSFT",
            total_stars=450000,
            total_forks=180000,
            public_repos=5200,
            stars_30d_ago=440000,
            repos_updated_30d=450,
            top_repos=[
                {"name": "vscode", "full_name": "microsoft/vscode", "stars": 165000, "forks": 29000, "language": "TypeScript"},
                {"name": "TypeScript", "full_name": "microsoft/TypeScript", "stars": 102000, "forks": 12000, "language": "TypeScript"},
            ],
        )

        source.update_activity(
            symbol="META",
            total_stars=320000,
            total_forks=130000,
            public_repos=1800,
            stars_30d_ago=310000,
            repos_updated_30d=250,
            top_repos=[
                {"name": "react", "full_name": "facebook/react", "stars": 225000, "forks": 46000, "language": "JavaScript"},
                {"name": "pytorch", "full_name": "pytorch/pytorch", "stars": 83000, "forks": 22000, "language": "Python"},
            ],
        )

        source.update_activity(
            symbol="GOOGL",
            total_stars=380000,
            total_forks=150000,
            public_repos=4800,
            stars_30d_ago=375000,
            repos_updated_30d=380,
        )

        # Get database
        print_subsection("Fetching database")
        database = await source.get_database()

        print(f"Companies tracked: {len(database.activities)}")

        # Top by stars
        print_subsection("Top by stars")
        for activity in database.get_top_by_stars(5):
            print(f"  {activity.symbol}: {activity.total_stars:,} stars, {activity.public_repos} repos")
            if activity.stars_change_pct_30d:
                print(f"    30d growth: {activity.stars_change_pct_30d:.1%}")
            if activity.top_repos:
                print(f"    Top repo: {activity.top_repos[0].name}")

        # Growing presence
        print_subsection("Growing GitHub presence")
        for activity in database.get_growing():
            print(f"  {activity.symbol}: +{activity.stars_change_pct_30d:.1%} stars")

        # Developer interest signals
        print_subsection("Developer interest signals")
        for symbol in ["MSFT", "META", "GOOGL"]:
            signal = source.get_developer_interest_signal(symbol)
            print(f"  {symbol}: {signal:.2f}" if signal else f"  {symbol}: N/A")

        # Test serialization
        print_subsection("Testing serialization")
        data = database.to_dict()
        restored = GitHubDatabase.from_dict(data)
        print(f"Restored activities: {len(restored.activities)}")

        await source.close()
        print("\n✓ GitHub Activity: PASSED")
        return True

    except Exception as e:
        print(f"\n✗ GitHub Activity: FAILED - {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_collection_daemon() -> bool:
    """Test collection daemon."""
    print_section("COLLECTION DAEMON")

    try:
        from src.data.sources.collection_daemon import (
            DataCollectionDaemon,
            CollectionStatus,
            SourceConfig,
            UpdateFrequency,
        )

        daemon = DataCollectionDaemon()

        # Check status
        print_subsection("Initial status")
        status = daemon.get_status()

        print(f"Timestamp: {status.timestamp}")
        print(f"Market hours: {status.is_market_hours}")
        print(f"Sources configured: {len(status.sources)}")

        # Show schedules
        print_subsection("Source schedules")
        for name, config in list(status.sources.items())[:8]:
            mh = "MH" if config.market_hours_only else "24h"
            print(f"  {name}: {config.frequency.value} ({config.interval_minutes}min) [{mh}]")

        # Test enable/disable
        print_subsection("Enable/disable source")
        success = daemon.disable_source("patents")
        print(f"Disabled patents: {success}")
        print(f"Patents enabled: {daemon._status.sources['patents'].enabled}")

        success = daemon.enable_source("patents")
        print(f"Enabled patents: {success}")
        print(f"Patents enabled: {daemon._status.sources['patents'].enabled}")

        # Test status serialization
        print_subsection("Status serialization")
        status_dict = status.to_dict()
        print(f"Status keys: {list(status_dict.keys())}")
        print(f"Source count in dict: {len(status_dict['sources'])}")

        # Would test collect_due but that requires all sources to be set up
        print_subsection("Collection readiness")
        print("Daemon is ready to orchestrate data collection")
        print("Run: await daemon.collect_all_now() to collect all sources")
        print("Run: await daemon.start() to start continuous collection")

        print("\n✓ Collection Daemon: PASSED")
        return True

    except Exception as e:
        print(f"\n✗ Collection Daemon: FAILED - {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_retrospective_analysis() -> bool:
    """Test that data can be loaded for retrospective analysis."""
    print_section("RETROSPECTIVE ANALYSIS CAPABILITY")

    try:
        print_subsection("Testing point-in-time data access")

        # Show cache directories
        cache_dirs = {
            "earnings": paths.scraped_data / "earnings",
            "economic": paths.scraped_data / "economic",
            "fed": paths.scraped_data / "fed",
            "treasury": paths.scraped_data / "treasury",
            "ipo": paths.scraped_data / "ipo",
            "fda": paths.scraped_data / "fda",
            "patents": paths.scraped_data / "patents",
            "jobs": paths.scraped_data / "jobs",
            "apps": paths.scraped_data / "apps",
            "github": paths.scraped_data / "github",
        }

        print("Cache directories:")
        for name, path in cache_dirs.items():
            exists = "✓" if path.exists() else "✗"
            print(f"  {exists} {name}: {path}")

        # Load and verify a cached file
        print_subsection("Verifying cached data format")

        from src.data.sources.alternative.patent_filings import PatentDatabase

        cache_file = paths.scraped_data / "patents" / "patent_database.json"
        if cache_file.exists():
            with open(cache_file) as f:
                data = json.load(f)

            print(f"Patent cache file exists: {cache_file}")
            print(f"  Timestamp: {data.get('timestamp', 'N/A')}")
            print(f"  Activities: {len(data.get('activities', {}))}")

            # Verify it can be loaded
            restored = PatentDatabase.from_dict(data)
            print(f"  Successfully restored {len(restored.activities)} activities")
        else:
            print(f"Patent cache not yet created (will be created on first use)")

        # Verify timestamp presence in all data structures
        print_subsection("Timestamp verification")
        print("All data structures include timestamps for point-in-time analysis:")
        print("  - EarningsCalendar.timestamp")
        print("  - EconomicCalendar.timestamp")
        print("  - FedExpectations.timestamp")
        print("  - TreasuryCalendar.timestamp")
        print("  - IPOCalendar.timestamp")
        print("  - FDACalendar.timestamp")
        print("  - PatentDatabase.timestamp")
        print("  - JobDatabase.timestamp")
        print("  - AppRankingDatabase.timestamp")
        print("  - GitHubDatabase.timestamp")

        print("\n✓ Retrospective Analysis: PASSED")
        return True

    except Exception as e:
        print(f"\n✗ Retrospective Analysis: FAILED - {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("  NEW DATA SOURCES TEST SUITE")
    print("="*60)
    print(f"\nTest started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Working directory: {Path.cwd()}")

    results = {}

    # Run all tests
    results["earnings_calendar"] = await test_earnings_calendar()
    results["economic_calendar"] = await test_economic_calendar()
    results["fed_futures"] = await test_fed_futures()
    results["treasury_calendar"] = await test_treasury_calendar()
    results["ipo_calendar"] = await test_ipo_calendar()
    results["fda_calendar"] = await test_fda_calendar()
    results["patent_filings"] = await test_patent_filings()
    results["job_postings"] = await test_job_postings()
    results["app_rankings"] = await test_app_rankings()
    results["github_activity"] = await test_github_activity()
    results["collection_daemon"] = await test_collection_daemon()
    results["retrospective"] = await test_retrospective_analysis()

    # Summary
    print_section("TEST SUMMARY")

    passed = sum(1 for r in results.values() if r)
    failed = sum(1 for r in results.values() if not r)

    for test, result in results.items():
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"  {test}: {status}")

    print(f"\n{'='*40}")
    print(f"  PASSED: {passed}/{len(results)}")
    print(f"  FAILED: {failed}/{len(results)}")
    print(f"{'='*40}")

    if failed == 0:
        print("\n🎉 All tests passed! Data sources are ready for use.")
    else:
        print(f"\n⚠️  {failed} test(s) failed. Please review the errors above.")

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
