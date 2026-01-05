#!/usr/bin/env python3
"""
Brainstorm: Creative Alpha Sources for January 2026

Unconventional and creative ideas for discovering trading alpha.
Focus on overlooked domains and contrarian thinking.
"""

import json
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AlphaIdea:
    """A brainstormed alpha idea."""

    category: str
    title: str
    description: str
    why_overlooked: str
    trading_approach: str
    catalyst_timing: str
    risks_downsides: str
    data_requirements: list[str] = field(default_factory=list)
    priority: float = 0.5  # 0-1

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "why_overlooked": self.why_overlooked,
            "trading_approach": self.trading_approach,
            "catalyst_timing": self.catalyst_timing,
            "risks_downsides": self.risks_downsides,
            "data_requirements": self.data_requirements,
            "priority": self.priority,
        }


# ============================================================================
# WEATHER & CLIMATE ALPHA
# ============================================================================

weather_ideas = [
    AlphaIdea(
        category="Weather & Climate",
        title="El Nino Crop Yield Prediction Cascade",
        description=(
            "El Nino patterns (currently NEUTRAL, monitoring for shift) affect precipitation "
            "in key agricultural regions. Wet El Nino years boost crop yields in Argentina "
            "(soybeans), India (monsoon rice), and reduce yields in Australia (drought). "
            "Creates 6-12 month forward predictability for agri-exposed stocks and commodity ETFs."
        ),
        why_overlooked=(
            "Weather data is available but requires sophisticated climate modeling. "
            "Most traders watch NOAA weekly updates casually. Few integrate probabilistic "
            "precipitation forecasts into systematic models. Lag of 6+ months hides the signal."
        ),
        trading_approach=(
            "1. Monitor NOAA Climate Prediction Center (CPC) monthly El Nino outlook\n"
            "2. When El Nino probability rises (>60% confidence next 3 months):\n"
            "   - Long ADR (Argentina) + soybean ETFs (SOYB) if drought fears in Australia\n"
            "   - Short ASX-listed farms, coal (heating demand drops)\n"
            "3. Model: Historical correlation of ENSO index vs. crop yields (6-month lag)\n"
            "4. Rebalance quarterly on updated NOAA forecasts"
        ),
        catalyst_timing=(
            "NOAA publishes monthly CPC outlook on ~8th of month. "
            "Seasonal signal strongest Dec-Feb for southern hemisphere summer crops. "
            "Jan 2026 watch: Early warning if 2026 becomes strong El Nino year."
        ),
        risks_downsides=(
            "- Climate models wrong (common 6+ months out)\n"
            "- Commodity prices already price in some El Nino expectations\n"
            "- Political disruptions (Argentina policy swings) override weather\n"
            "- Takes 6+ months to materialize; capital tied up\n"
            "- Drought resilience improves (irrigation tech); signal weakens over time"
        ),
        data_requirements=[
            "NOAA Climate Prediction Center ENSO Index (free, weekly)",
            "NOAA Precipitation forecasts",
            "Crop yields by country (USDA, FAO)",
            "Commodity ETF prices (SOYB, CORN, etc.)",
            "ADR prices (Argentina equity proxies)",
        ],
        priority=0.7,
    ),

    AlphaIdea(
        category="Weather & Climate",
        title="Extreme Weather Insurance Rotation Alpha",
        description=(
            "Insurers face massive payouts after extreme weather events (hurricanes, floods, wildfires). "
            "Tracking real-time weather severity indicators (NOAA hurricane season forecasts, "
            "wildfire acreage, extreme precipitation) lets you front-run insurance stock selloffs. "
            "Conversely, quiet weather seasons are underpriced by insurance shorts."
        ),
        why_overlooked=(
            "Insurance underwriting is complex; most traders buy/hold insurance stocks as defensive. "
            "Few track real-time weather severity metrics and correlate to insurer cash flows. "
            "Hurricane seasons are priced in general terms but not by month/week granularity."
        ),
        trading_approach=(
            "1. Subscribe to real-time wildfire tracking (InciWeb), hurricane intensity (NHC), flood risk (NOAA)\n"
            "2. Build severity index: acres burned + hurricane days + flood events in insured regions\n"
            "3. When severity spikes:\n"
            "   - Short reinsurers (RE, XL, RLI) ahead of loss announcements\n"
            "   - Long insurance brokers (AON, MMC) who gain market share\n"
            "4. Mean-revert when severity normalizes; insurance stocks bounce back"
        ),
        catalyst_timing=(
            "Immediate (weeks). Most losses disclosed within 30-60 days of events. "
            "Jan 2026: Hurricane season dormant, but wildfire season (CA) heating up."
        ),
        risks_downsides=(
            "- Reinsurance already has exposure; model may be priced in\n"
            "- Loss estimates subject to huge surprises (always worse than expected)\n"
            "- Legal/political interference (price controls after disasters)\n"
            "- Correlation breakdowns if interest rates spike (affects insurer assets)"
        ),
        data_requirements=[
            "NOAA real-time storm tracking",
            "InciWeb wildfire database (free)",
            "Insurance company daily prices",
            "Reinsurer daily prices",
        ],
        priority=0.6,
    ),
]


# ============================================================================
# SPORTS & ENTERTAINMENT ALPHA
# ============================================================================

sports_ideas = [
    AlphaIdea(
        category="Sports & Entertainment",
        title="NFL Playoff / Super Bowl Sentiment Flip",
        description=(
            "Equity markets exhibit measurable 'Super Bowl effect': markets tend to rally into SB (late Jan/early Feb) "
            "as retail/consumer sentiment improves (holiday euphoria, betting excitement). "
            "But post-SB (early Feb), the crash is real as weather worsens, seasonal depression hits, "
            "and earnings disappointments emerge. Consumer discretionary stocks lead the move."
        ),
        why_overlooked=(
            "The Super Bowl effect is documented academically (Moskowitz & Wertheim) but: "
            "1. Most traders think it's too obvious to work\n"
            "2. NFL is US-only; European/Asian traders ignore it\n"
            "3. Effect is small in magnitude (~0.5-1% rally) but high certainty\n"
            "4. Timing window is tight (1-2 weeks)"
        ),
        trading_approach=(
            "1. Sell risk (SPY/QQQ) on Jan 20-25 (week before Super Bowl LX on Feb 2, 2026)\n"
            "2. Rotate into staples (XLP) and shorts (SH, PSQ) for post-SB crash (Feb 3-10)\n"
            "3. Secondary angle: Bet on underdog Super Bowl teams' home states rallying (sentiment boost)\n"
            "   - If Kansas City favored: short KCP (Kansas City tech), long XLP (defensive)\n"
            "4. Use options to play the volatility spike around SB announcement of winner"
        ),
        catalyst_timing=(
            "Super Bowl LX: February 2, 2026. "
            "Pre-game rally: Jan 20-Feb 2\n"
            "Post-game crash: Feb 3-10\n"
            "Peak effect: Feb 4-6 (day after SB)"
        ),
        risks_downsides=(
            "- Effect is small and easily arbitraged\n"
            "- Market macro (Fed policy, earnings) may override seasonal signal\n"
            "- Post-SB timing can vary (weather, earnings surprises)\n"
            "- Doesn't work if market is already rallying on fundamentals"
        ),
        data_requirements=[
            "S&P 500, Russell 2000 prices",
            "Sector ETPs (XLP, XLV, XLK, XLI)",
            "Super Bowl date (fixed calendar)",
            "Retail sentiment indices",
        ],
        priority=0.4,
    ),

    AlphaIdea(
        category="Sports & Entertainment",
        title="Award Season Stock Volatility Widening",
        description=(
            "Golden Globes (early Jan), Oscars (late Feb/early Mar), Grammys (early Feb) drive entertainment stock volatility. "
            "Studios with major nominees (Disney, Paramount, Netflix) see option IV spike 2-3 weeks before awards, "
            "as investors hedge winner/loser uncertainty. Post-award, IV collapses. This is pure volatility mean-reversion."
        ),
        why_overlooked=(
            "Entertainment stocks (DIS, PARA, NFLX) are so large that the award-driven volatility is noise. "
            "Institutional traders don't short vol on awards shows (reputation risk). "
            "Timing is unpredictable (do they announce winners live or pre-award?)."
        ),
        trading_approach=(
            "1. Track major award nominations (Golden Globes winners announced Jan 5, 2026)\n"
            "2. 2 weeks pre-award: Buy 1 month straddles on studios with major nominees\n"
            "3. Hold until award is announced\n"
            "4. Sell straddle day after award (IV collapse)\n"
            "5. Profit from IV crush, regardless of stock direction"
        ),
        catalyst_timing=(
            "Jan 5: Golden Globes (early!)\n"
            "Feb 1: Grammys\n"
            "Mar 2: Oscars\n"
            "Volatility peak: 1-2 weeks pre-award"
        ),
        risks_downsides=(
            "- IV already elevated going into awards (market anticipates)\n"
            "- Earnings surprises around same time can override\n"
            "- Straddle costs are high; need big move to profit\n"
            "- Award outcomes are random; no edge to prediction"
        ),
        data_requirements=[
            "Entertainment stock implied vol (from options data providers)",
            "Award nomination lists (public)",
            "Straddle pricing",
        ],
        priority=0.35,
    ),
]


# ============================================================================
# POLITICAL & POLICY CALENDAR
# ============================================================================

political_ideas = [
    AlphaIdea(
        category="Political & Policy",
        title="Debt Ceiling Crisis Premium / Resolution Rally",
        description=(
            "US faces debt ceiling crisis potential in 2026 (government runs out of borrowing authority). "
            "Historically: 2-3 weeks before crisis resolution, risk premia spike (bond spreads widen, VIX rises). "
            "But once resolution is announced, risk unwinds violently (gold down, equities up, USD up). "
            "The resolution date is binary but predictable within narrow windows."
        ),
        why_overlooked=(
            "Debt ceiling is political theater; market professionals know it always gets resolved. "
            "But retail traders panic every time. Timing of resolution announcement varies, "
            "making it hard to profit on the exact day. Consensus is 'nothing to worry about,' "
            "so vol stays compressed until last minute."
        ),
        trading_approach=(
            "1. Calendar watch: Debt ceiling 'X-date' typically forecasted by Treasury (TreasuryDirect)\n"
            "2. 2-3 weeks pre-X-date: Buy gold (GLD) and VIX call spreads\n"
            "3. 1 week pre-X-date: Add short duration bonds (SHV calls or long-duration bond puts)\n"
            "4. On resolution announcement:\n"
            "   - Sell gold (profit)\n"
            "   - Buy 3x QQQ (tech rally on less tail risk)\n"
            "   - Close out VIX shorts\n"
            "5. Effect typically lasts 3-5 days"
        ),
        catalyst_timing=(
            "Debt ceiling X-date typically June-August 2026 (need to monitor Treasury announcements). "
            "But heightened political gridlock could shift it. "
            "Watch for Congressional leadership disagreements in Jan-Mar as signal of crisis odds."
        ),
        risks_downsides=(
            "- Resolution date uncertain; may need to roll hedges\n"
            "- Fed policy changes could override political noise\n"
            "- Actual default is possible (tail risk, but non-zero)\n"
            "- Market already prices crisis premium; edge is small"
        ),
        data_requirements=[
            "Treasury X-date estimates (TreasuryDirect, Congressional Budget Office)",
            "Gold prices",
            "VIX futures",
            "Bond yields",
        ],
        priority=0.5,
    ),

    AlphaIdea(
        category="Political & Policy",
        title="Government Shutdown Tax Withholding Disruption",
        description=(
            "If US government shuts down mid-year, IRS operations are disrupted. Tax refunds delay, "
            "e-filing systems go offline. This reduces retail investor liquidity when they need it most "
            "(tax season = capital deployment time). Small-cap retail-sensitive stocks (online brokers, "
            "retail banks) see selling pressure during shutdowns."
        ),
        why_overlooked=(
            "Shutdowns are assumed 'non-events' by market pros. But retail traders aren't compensated "
            "for illiquidity; they panic-sell whatever they can. E-trade, Charles Schwab see outflows. "
            "This is too micro-level for institutional traders but real for retail-facing stocks."
        ),
        trading_approach=(
            "1. Monitor Congressional calendar for authorization deadlines (typically Sept, Dec)\n"
            "2. If shutdown looks likely (>50% bets on prediction markets):\n"
            "   - Short ETRADE, SCHW (online brokers lose deposits)\n"
            "   - Short UPWK (Upwork; freelancers don't file taxes, cut spending)\n"
            "3. Long after shutdown ends (confidence returns, deployment resumes)\n"
            "4. Effect typically 2-3 days, small magnitude (~2-3%)"
        ),
        catalyst_timing=(
            "Shutdowns more likely Sept/Oct (fiscal year end) and Dec (holiday gridlock). "
            "But Jan 2026: Monitor if 2025 budget disputes carry over."
        ),
        risks_downsides=(
            "- Regulatory risk: SEC might close markets during shutdown\n"
            "- Market might correctly price in effects; edge is tiny\n"
            "- Other macro factors dominate (Fed policy, earnings)\n"
            "- Retail flows data is proprietary; hard to verify hypothesis"
        ),
        data_requirements=[
            "Congressional calendar",
            "Shutdown prediction markets",
            "Broker customer deposit data (regulatory filings)",
            "ETRADE, SCHW, UPWK stock prices",
        ],
        priority=0.35,
    ),
]


# ============================================================================
# SUPPLY CHAIN & LOGISTICS ALPHA
# ============================================================================

supply_chain_ideas = [
    AlphaIdea(
        category="Supply Chain & Logistics",
        title="Port Congestion -> Shipping Cost Lead-Lag Alpha",
        description=(
            "Real-time port congestion data (average wait times, queue depth) leads shipping cost indices "
            "(Drewry Container Index, Shanghai FX) by 1-2 weeks. When LA/Long Beach ports jam up, "
            "ocean freight rates spike as shippers divert to less-congested routes. "
            "This creates profitable short-term correlations with trucking (XRT), shipping (SPXC), and importers."
        ),
        why_overlooked=(
            "Port data is fragmented (each port reports separately; no unified index). "
            "Shipping indices lag by 1+ week, so real-time traders miss the signal. "
            "Consensus assumes 'ports are always congested'; no urgency. "
            "Correlation is high but timing window narrow (1-2 days of tradeable alpha)."
        ),
        trading_approach=(
            "1. Build real-time port monitoring dashboard:\n"
            "   - LA/Long Beach port authority queue depth (published daily)\n"
            "   - Singapore (Jurong Port), Rotterdam queues\n"
            "2. When LA queue depth spikes >30% above 20-day avg:\n"
            "   - Front-run shipping cost indices by longing SPXC (shipping ETF), FDX (diversion to FedEx)\n"
            "   - Short retailers (XRT) who get cost pass-throughs\n"
            "3. Unwind 1-2 weeks when shipping indices publish\n"
            "4. Hedge with short ocean freight company calls"
        ),
        catalyst_timing=(
            "Real-time signal; optimal holding period 3-7 days. "
            "Jan 2026: Post-holiday logistics reset; ports normalizing from peak season."
        ),
        risks_downsides=(
            "- Port authorities may change reporting (less transparency)\n"
            "- Alternative routes (rail, air freight) absorb congestion\n"
            "- Supply chain more resilient post-COVID; signal weakening\n"
            "- Shipping indices still lag by 1+ week; hard to front-run precisely"
        ),
        data_requirements=[
            "LA/Long Beach port queue data (Port Authority, public)",
            "Singapore, Rotterdam port data",
            "Drewry Container Index (paid, but lagging)",
            "Shipping company prices (SPXC, DCIX, FDX)",
            "Retailer prices (XRT, RH, etc.)",
        ],
        priority=0.6,
    ),

    AlphaIdea(
        category="Supply Chain & Logistics",
        title="Semiconductor Equipment Lead-Lag Supply Chain",
        description=(
            "Semi equipment orders (ASML, LRCX, KLAC, AMAT) lead actual chip production by 6-9 months. "
            "And chip production leads memory (DRAM/NAND) price changes by 3-6 months. "
            "Monitor SEMI equipment billings index and order books to predict semiconductor cycle turns "
            "and memory price shocks that hit end-markets 9+ months later."
        ),
        why_overlooked=(
            "Semi equipment cycle is well-known but lagged by months. "
            "Most traders only look backward at quarterly earnings. "
            "Equipment OEMs are cyclical 'trader traps'; professionals avoid buying on euphoria. "
            "But forward guidance is predictive if you read earnings calls carefully."
        ),
        trading_approach=(
            "1. Subscribe to SEMI Equipment Billings Index (free, monthly)\n"
            "2. Track guidance from ASML, LRCX on order books (quarterly earnings)\n"
            "3. If Equipment Billings up >10% YoY:\n"
            "   - 6 months later: Anticipate DRAM/NAND price declines (supply expansion)\n"
            "   - Front-run by shorting memory stocks (MU, SK Hynix ADR) 3-6 months ahead\n"
            "   - Long NAND-consumers if prices fall (SSDs, cloud storage)\n"
            "4. Conversely, if orders collapse, be long memory on supply shock fears 6 months later"
        ),
        catalyst_timing=(
            "SEMI billings = monthly leading indicator. "
            "Lag to chip production: 6-9 months. "
            "Lag to end-market impact: 9-15 months. "
            "Jan 2026: Watch 2026 billings forecasts as signal of late-2026/2027 memory gluts."
        ),
        risks_downsides=(
            "- Lags so long that macro regime changes (Fed policy, recession) overwhelm signal\n"
            "- Equipment OEMs can manipulate billings (channel stuffing, order cancellations)\n"
            "- Memory prices volatile; driven by spot supply shocks, not just cycle\n"
            "- Requires holding 6-9 months; capital-inefficient"
        ),
        data_requirements=[
            "SEMI Equipment Billings Index (free, monthly)",
            "ASML, LRCX, KLAC, AMAT earnings transcripts",
            "DRAM/NAND spot prices (Dramexchange, TrendForce)",
            "Memory stock prices (MU, SK Hynix)",
        ],
        priority=0.65,
    ),
]


# ============================================================================
# SOCIAL TRENDS & DEMOGRAPHIC SHIFTS
# ============================================================================

social_ideas = [
    AlphaIdea(
        category="Social Trends",
        title="Viral Product TikTok-to-IPO Momentum",
        description=(
            "Products that go viral on TikTok (e.g., Dyson hair dryer 2023, Lululemon bag 2022) "
            "see massive retail demand spikes 2-4 weeks before street consensus catches on. "
            "If the company is public or has a parent company, stock can rally 5-15% in the window "
            "before sell-side analysts even mention it in notes. By the time equity research catches up, "
            "the move is mostly over."
        ),
        why_overlooked=(
            "Equity research doesn't monitor TikTok trends (generational divide). "
            "Most traders think TikTok trends are fads, too hard to quantify. "
            "Retail investors ARE the signal, but professionals underestimate retail impact. "
            "Effect is real for mid-cap consumer discretionary."
        ),
        trading_approach=(
            "1. Subscribe to TikTok trend tracking (e.g., TikTok Discover, trend aggregators)\n"
            "2. Set alerts for product mentions spiking (>1M mentions in 1 week)\n"
            "3. When product goes viral:\n"
            "   - Identify parent company (LVMH for Dyson, LULU for bags)\n"
            "   - Front-run by buying 2-4 week calls\n"
            "   - Ride the 5-10% pop as retail demand hits store/online\n"
            "4. Sell calls when company mentions trend in earnings (signal dissipates)\n"
            "5. Secondary: Short competitor brands as market share shifts"
        ),
        catalyst_timing=(
            "Real-time. Viral trend typically lasts 2-6 weeks. "
            "Stock move lags trend onset by 1-2 weeks. "
            "Optimal entry: Week 2-3 of trend; exit before earnings mentions it."
        ),
        risks_downsides=(
            "- Retail hype can reverse suddenly (TikTok bans, privacy concerns)\n"
            "- Competition disrupts trends (everyone copies, original brand loses edge)\n"
            "- Stock valuation already high for trendsetters; limited room to run\n"
            "- Product quality issues emerge (e.g., Dyson hair dryer overheating stories)\n"
            "- Requires monitoring TikTok constantly; time-intensive"
        ),
        data_requirements=[
            "TikTok trend monitoring (manual or via APIs)",
            "TikTok Discover/For You Page aggregators",
            "Product search volume (Google Trends, Amazon Best Sellers)",
            "Company earnings transcripts",
            "Stock prices (LVMH, LULU, etc.)",
        ],
        priority=0.55,
    ),

    AlphaIdea(
        category="Social Trends",
        title="Generational Wealth Transfer & Philanthropic Giving Shocks",
        description=(
            "Baby boomer wealth transfer to Gen X/millennials (estimated $30T+ over next 20 years) "
            "creates discrete charitable giving shocks. When high-net-worth individuals pass away, "
            "their estates fund charitable foundations in months following death. "
            "This drives sudden inflows to specific cause areas (climate, health, education) "
            "and creates predictable capital allocation patterns for ESG/impact funds."
        ),
        why_overlooked=(
            "Philanthropic flows are not systematically tracked by equity researchers. "
            "Hedge funds don't front-run estate settlements. "
            "Gives too much credit to slow-moving charity; market assumes ESG already priced in. "
            "But discrete foundations launching with multi-billion mandates can move mid-caps."
        ),
        trading_approach=(
            "1. Monitor high-net-worth obituaries (Bloomberg, Forbes, philanthropy databases)\n"
            "2. Estimate estate size and likely charitable focus (public giving history)\n"
            "3. When major philanthropist dies:\n"
            "   - Identify likely beneficiary organizations and their portfolio companies\n"
            "   - Buy small-cap / mid-cap ESG/climate/health stocks that align\n"
            "   - Estate settlements finalized in 6-12 months; foundation capital deployed\n"
            "4. Ride the capital allocation wave for 6-24 months\n"
            "5. Diversify by tracking multiple philanthropists; create portfolio of bets"
        ),
        catalyst_timing=(
            "Highly uncertain. Death dates not predictable. "
            "But estate settlements = 6-12 months. Foundation giving = 1-3 years post-settlement. "
            "Jan 2026: Some 2025 Q4 deaths will settle in 2026; track for 2026-2027 impact."
        ),
        risks_downsides=(
            "- Timing completely unpredictable\n"
            "- Estate disputes delay capital deployment\n"
            "- Philanthropist's heirs may have different priorities\n"
            "- Market has already priced ESG trends; incremental giving not a shock\n"
            "- Requires identifying specific philanthropist intentions (private data)\n"
            "- Illiquid micro-cap stocks; hard to exit position"
        ),
        data_requirements=[
            "High-net-worth obituaries (Bloomberg, newspapers)",
            "Philanthropic giving databases (Foundation Center, GiveWell)",
            "Estate size estimates (public records, news articles)",
            "Company stock prices (ESG, climate, health mid/small-caps)",
        ],
        priority=0.3,
    ),
]


# ============================================================================
# CONTRARIAN / NARRATIVE FLIPS
# ============================================================================

contrarian_ideas = [
    AlphaIdea(
        category="Contrarian Plays",
        title="Energy Crisis Narrative Collapse = Nuclear Boom",
        description=(
            "2024-2025 narrative: 'Energy crisis, AI demands electricity, grid fails, need renewables ASAP.' "
            "Consensus long: ICLN (clean energy), RNWM (renewables). But in Jan 2026, "
            "as nuclear renaissance becomes undeniable (SMRs coming, bill passed, utilities pivoting), "
            "the trade will flip. Nuclear (URA, CCJ) will outperform. "
            "First: nuclear uranium will surge. Second: utilities pivoting to nuclear will rally."
        ),
        why_overlooked=(
            "Nuclear is taboo among ESG crowd (environmental fears persist, legacy damage). "
            "ICLN index doesn't include nuclear; passive capital flows ignore it. "
            "Narrative inertia: 'nuclear = bad' persists even after policy shifts. "
            "Flip happens suddenly when opinion leaders (Bill Gates, Obama) endorse nuclear."
        ),
        trading_approach=(
            "1. Pair trade: Long URA (uranium ETF), short ICLN (clean energy ETF)\n"
            "2. Enter Jan 2026 when:\n"
            "   - SMR announcements accumulate\n"
            "   - Uranium spot prices break above $50/lb (currently ~$75, but monitor trend)\n"
            "   - Political endorsements of nuclear increase\n"
            "3. Hold 12-24 months as narrative flips\n"
            "4. Secondary: Long utility stocks pivoting to nuclear (DUK, NEE if they announce SMR partnerships)\n"
            "5. Short ICLN if position sizes become extreme"
        ),
        catalyst_timing=(
            "Gradual over 12-18 months, not binary event. "
            "Catalysts: SMR approvals, utility earnings calls mentioning nuclear, uranium contracts. "
            "Jan 2026: Early phase of narrative flip; 12+ months runway."
        ),
        risks_downsides=(
            "- SMRs delayed again; tech not as revolutionary as hyped\n"
            "- Political opposition resurges (NIMBY protests, safety concerns)\n"
            "- Uranium price collapses on demand shock (oversupply)\n"
            "- ICLN already includes some nuclear-adjacent names; rotation not clean\n"
            "- Long duration trade; capital tied up 12-24 months"
        ),
        data_requirements=[
            "URA, CCJ uranium stock prices",
            "ICLN clean energy ETF price",
            "Uranium spot prices (Trading Economics, Cameco reporting)",
            "Utility earnings transcripts (DUK, NEE, EXC)",
            "SMR approval news (DOE, NRC)",
        ],
        priority=0.6,
    ),

    AlphaIdea(
        category="Contrarian Plays",
        title="Remote Work Bubble Collapse -> Office Real Estate Shock",
        description=(
            "Narrative 2020-2024: 'Remote work is permanent, offices dead, WFH stocks boom (ZOOM, etc.).' "
            "But in 2026, cracks are visible: RTO (return to office) mandates widespread, "
            "office occupancy normalizing, commercial real estate not in freefall. "
            "The crowd-pleasing trade (Zoom, remote work ETFs) becomes overcrowded; early exit signals are burning. "
            "Contrarian: REITs and office landlords will stabilize earlier than feared."
        ),
        why_overlooked=(
            "Remote work narrative has 4-year inertia. Consensus so strong it blinds traders. "
            "Tech workers loud about WFH preferences, but they're 10% of workforce. "
            "Most workers WANT offices (social, career progression). But narrative says opposite. "
            "Contrarian bet here is high Sharpe: market will be shocked by normalization."
        ),
        trading_approach=(
            "1. Short Zoom (ZM) and ZOOM-adjacent (WORK, etc.) on technical breaks\n"
            "2. Long office REITs (IRM for data centers, SL for office, VNO for NYC)\n"
            "3. Long CBRE (commercial real estate services) on earnings surprises\n"
            "4. Hedge with short bonds (BND) as REIT yields compress on normalization\n"
            "5. Timeframe: 18-36 months as narrative flips gradually"
        ),
        catalyst_timing=(
            "Gradual flip: RTO mandates already in effect (Jan 2026), "
            "earnings reports showing office demand stabilizing (Q1 2026 earnings). "
            "Narrative tipping point: mid-2026 when Wall Street acknowledges overcorrection."
        ),
        risks_downsides=(
            "- Recession hits; office demand collapses again\n"
            "- Zoom finds new growth narrative (AI features, market expansion)\n"
            "- REITs face rising rates; cap rates expand (prices down even with stable occupancy)\n"
            "- Tech industry stays distributed (Bay Area tech exodus continues)\n"
            "- Structural change real: offices DON'T fully recover (lower equilibrium)"
        ),
        data_requirements=[
            "ZM, WORK stock prices",
            "REIT prices (VNO, SLG, IRM, CBRE)",
            "Office occupancy data (CoStar, Zillow)",
            "RTO announcements (company press releases)",
            "Earnings surprises for REITs and Zoom",
        ],
        priority=0.55,
    ),
]


# ============================================================================
# CORRELATION BREAKDOWNS & REGIME SHIFTS
# ============================================================================

correlation_ideas = [
    AlphaIdea(
        category="Correlation Breakdowns",
        title="Tech-Growth Decoupling from Mega-Cap AI",
        description=(
            "2023-2025: Tech rally = AI rally = Magnificent 7 + Nasdaq. "
            "But in 2026, AI hype matures; capex cycles normalize. "
            "Mega-cap AI plays (NVDA, MSFT, GOOGL) mature, while smaller AI-adjacent plays "
            "(AI software companies, AI chip designers, robotics) are still in early growth. "
            "Correlation between tech mega-cap and growth-tech breaks down. "
            "Growth-tech outperforms Mag 7 in Q2-Q3 2026."
        ),
        why_overlooked=(
            "Consensus assumes 'all tech up together' as long as AI theme exists. "
            "But growth cycles diverge: mega-caps cyclical (high capex saturation), "
            "while mid/small-cap AI plays still in expansion phase. "
            "This divergence is overlooked because mega-cap dominates sentiment."
        ),
        trading_approach=(
            "1. Pair trade: Long AI growth-plays ETF (e.g., LSPD, or custom basket of small-cap AI: "
            "DDOG, UPST, OPENAI-if-public, robotics like ISRG), short QQQ (Nasdaq mega-cap)\n"
            "2. Or construct pairs within Nasdaq:\n"
            "   - Long: CRWD, DDOG, SNPS, CDNS (enterprise AI software, semi design tools)\n"
            "   - Short: NVDA, MSFT, GOOGL (mega-cap AI)\n"
            "3. Entry Jan 2026 as earnings reveal mega-cap AI slowdown\n"
            "4. Hold through Q2-Q3 2026 as growth-tech outperforms\n"
            "5. Exit when correlation normalizes again (~Q4 2026)"
        ),
        catalyst_timing=(
            "Q4 2025 / Q1 2026 earnings season reveals mega-cap AI capex deceleration. "
            "Q2-Q3 2026: Growth-tech earnings beat (delayed AWS slowdown not yet priced in). "
            "Optimal holding window: 6-9 months."
        ),
        risks_downsides=(
            "- AI hype extends longer than expected; mega-caps keep rallying\n"
            "- Growth-tech collapses on recession fears (more cyclical than mega-cap)\n"
            "- Mega-cap concentration persists (passive flows maintain correlation)\n"
            "- Earnings-driven surprise direction opposite (mega-cap beats, growth misses)\n"
            "- Duration too long; multiple compression hits growth-tech hardest"
        ),
        data_requirements=[
            "QQQ mega-cap prices (NVDA, MSFT, GOOGL, TSLA, etc.)",
            "Growth-tech ETF prices or custom basket (DDOG, CRWD, UPST, SNPS)",
            "Earnings calendars and surprise data",
            "AI capex spending by mega-cap (earnings transcripts)",
        ],
        priority=0.65,
    ),

    AlphaIdea(
        category="Correlation Breakdowns",
        title="Credit Spreads / Equity Divergence (Earnings vs. Bond Market)",
        description=(
            "In early 2026, equity market may price in optimism (earnings beats, fed cuts), "
            "while credit market (bonds, CDS) prices in recession risk (spreads widen). "
            "This divergence is a regime-shift signal. When equities and credit decouple, "
            "credit is usually right (bonds price fundamentals better than equities). "
            "Position for equity downside if spreads widen significantly."
        ),
        why_overlooked=(
            "Most equity traders ignore bond markets. Credit analysts don't move equities directly. "
            "But when divergence occurs (high-yield spreads widen, investment-grade spreads widen), "
            "it's a leading indicator of equity selloff (2-4 weeks later). "
            "Professionals know this, but retail traders ignore bonds."
        ),
        trading_approach=(
            "1. Monitor HY (high-yield) OAS and IG (investment-grade) OAS daily\n"
            "2. Set alert: If HY OAS widens >50bps in 2 weeks:\n"
            "   - Short equities (SPY, QQQ call spreads)\n"
            "   - Buy long-duration bonds (TLT calls)\n"
            "   - Buy hedge (VIX calls)\n"
            "3. Rationale: Credit market repricing default risk; equities will follow\n"
            "4. Hold 3-8 weeks as equity repricing occurs\n"
            "5. Exit when HY OAS stabilizes"
        ),
        catalyst_timing=(
            "Real-time monitoring; 2-4 week lead time before equity selloff. "
            "Jan 2026: Watch credit markets closely; any early stress signals Q1 volatility."
        ),
        risks_downsides=(
            "- Credit spreads widen on technical flows (Treasury yield spikes), not fundamentals\n"
            "- Equity market diverges and rallies anyway (narrative override)\n"
            "- Fed backstop (new QE) re-compresses spreads\n"
            "- Data lagged (spreads reported with 1-2 day delay)\n"
            "- Over-weighting credit signals as infallible"
        ),
        data_requirements=[
            "HY OAS index (ICE BofA High Yield OAS)",
            "IG OAS index (ICE BofA Investment Grade OAS)",
            "VIX, VIX term structure",
            "TLT (long-duration Treasuries)",
            "SPY, QQQ prices",
        ],
        priority=0.7,
    ),
]


# ============================================================================
# SUMMARY & LOGGING
# ============================================================================

def main():
    """Log all brainstormed ideas to session tracker."""
    from workflows.research.session_tracker import get_tracker

    tracker = get_tracker()

    all_ideas = [
        *weather_ideas,
        *sports_ideas,
        *political_ideas,
        *supply_chain_ideas,
        *social_ideas,
        *contrarian_ideas,
        *correlation_ideas,
    ]

    print("=" * 80)
    print("BRAINSTORM SESSION: CREATIVE ALPHA SOURCES FOR JANUARY 2026")
    print("=" * 80)
    print()

    # Log each idea
    for idea in all_ideas:
        tracker.log_insight(
            title=idea.title,
            description=idea.description,
            category="strategy",
            evidence={
                "why_overlooked": idea.why_overlooked,
                "trading_approach": idea.trading_approach,
                "catalyst_timing": idea.catalyst_timing,
                "risks": idea.risks_downsides,
                "data_requirements": idea.data_requirements,
                "priority": idea.priority,
            },
            session_id="brainstorm_jan_2026",
            tags=[idea.category.lower().replace(" ", "_"), "creative", "unconventional"],
            confidence=idea.priority,
        )

    # Print summary
    print(f"\nTotal Ideas Generated: {len(all_ideas)}\n")

    by_category = {}
    for idea in all_ideas:
        if idea.category not in by_category:
            by_category[idea.category] = []
        by_category[idea.category].append(idea)

    for category in sorted(by_category.keys()):
        ideas = by_category[category]
        print(f"\n{category.upper()} ({len(ideas)} ideas)")
        print("-" * 80)
        for idea in ideas:
            print(f"\n  {idea.title}")
            print(f"    Priority: {idea.priority:.1%}")
            print(f"    Why overlooked: {idea.why_overlooked[:80]}...")
            print(f"    Trading: {idea.trading_approach.split(chr(10))[0]}...")

    # Print top ideas by priority
    print("\n" + "=" * 80)
    print("TOP IDEAS BY PRIORITY")
    print("=" * 80)
    top_ideas = sorted(all_ideas, key=lambda x: x.priority, reverse=True)[:5]
    for i, idea in enumerate(top_ideas, 1):
        print(f"\n{i}. {idea.title} ({idea.priority:.1%} priority)")
        print(f"   Category: {idea.category}")
        print(f"   Catalyst: {idea.catalyst_timing.split(chr(10))[0]}")
        print(f"   Data needs: {', '.join(idea.data_requirements[:2])}...")

    # Export to JSON
    output_file = "/home/nock/quant_results/brainstorm_alpha_jan_2026.json"
    with open(output_file, "w") as f:
        json.dump(
            {
                "session": "brainstorm_jan_2026",
                "date": datetime.now().isoformat(),
                "total_ideas": len(all_ideas),
                "ideas": [idea.to_dict() for idea in all_ideas],
                "by_category": {
                    cat: [idea.to_dict() for idea in ideas]
                    for cat, ideas in by_category.items()
                },
            },
            f,
            indent=2,
        )
    print(f"\n\nFull results saved to: {output_file}")
    print(f"Session tracker updated: /home/nock/quant_results/research_tracker/insights.json")


if __name__ == "__main__":
    main()
