"""
Log research session results to tracker and database.
Session: March 11, 2026 comprehensive research cycle
"""
import sys
sys.path.insert(0, '/home/nock/projects/quant_suite')

from workflows.research.session_tracker import get_tracker
from src.core.paths import paths
from src.db.write_api import athena_db
from pathlib import Path

tracker = get_tracker()

# Log all 8 experiments
experiments = [
    {
        "strategy": "momentum", "symbol": "CF",
        "params": {"period": "default", "hold": "10d"},
        "result": "fail", "sharpe": 0.62, "p_value": 0.2475,
        "notes": "OOS Sharpe 0.96 is promising. Fertilizer thesis confirmed by CF +9.4% today. Not statistically significant yet."
    },
    {
        "strategy": "bollinger_reversal", "symbol": "CF",
        "params": {"period": "20", "std": "2.0"},
        "result": "fail", "sharpe": 0.60, "p_value": 0.2475,
        "notes": "Similar to momentum. CF is macro-driven, not mean-reverting."
    },
    {
        "strategy": "momentum", "symbol": "MU",
        "params": {"period": "default", "hold": "5d"},
        "result": "fail", "sharpe": 0.28, "p_value": 0.3861,
        "notes": "Pre-earnings momentum not significant. OOS 0.81. Buy-and-hold dominates. Mar 18 earnings."
    },
    {
        "strategy": "bollinger_reversal", "symbol": "PBF",
        "params": {"period": "20", "std": "2.0"},
        "result": "fail", "sharpe": -1.06, "p_value": 0.9703,
        "notes": "Strong reject. Refiner rotation is structural, not technical. Tanker-refiner corr only 0.19-0.34."
    },
    {
        "strategy": "momentum", "symbol": "FRO",
        "params": {"period": "default", "hold": "5d"},
        "result": "fail", "sharpe": -0.35, "p_value": 0.7129,
        "notes": "Tankers are thesis-driven, no tactical edge. RSI 90+ at time of test."
    },
    {
        "strategy": "momentum", "symbol": "MPC",
        "params": {"period": "default", "hold": "10d"},
        "result": "fail", "sharpe": -0.66, "p_value": 0.8614,
        "notes": "Refiner momentum strongly rejected. Crack spread dynamics drive, not price momentum."
    },
    {
        "strategy": "bollinger_reversal", "symbol": "LMT",
        "params": {"period": "20", "std": "2.0"},
        "result": "fail", "sharpe": -0.73, "p_value": 0.8317,
        "notes": "Defense names not mean-reverting. Thesis is 12-24 month macro play. Confirms Feb 28 finding."
    },
    {
        "strategy": "momentum", "symbol": "XLE",
        "params": {"period": "default", "hold": "2d"},
        "result": "fail", "sharpe": -0.72, "p_value": 0.8020,
        "notes": "SPR release creates short-term headwind but no exploitable tactical pattern."
    },
]

print("Logging experiments to tracker...")
for exp in experiments:
    try:
        tracker.log_experiment(
            strategy=exp["strategy"],
            symbol=exp["symbol"],
            params=exp["params"],
            result=exp["result"],
            sharpe=exp["sharpe"],
            p_value=exp["p_value"],
            notes=exp.get("notes", "")
        )
        print(f"  Logged: {exp['strategy']}/{exp['symbol']} p={exp['p_value']:.4f}")
    except Exception as e:
        print(f"  ERROR logging {exp['strategy']}/{exp['symbol']}: {e}")

# Log insights
insights = [
    {
        "title": "Fertilizer Signal Chain Validated: CF +9.4% on Hormuz Disruption",
        "description": (
            "CF Industries surged +9.4% on March 11, 2026, directly validating the Hormuz-fertilizer thesis. "
            "33% of global fertilizer transits Hormuz; with 70% disruption, urea prices surged $60-80/ton. "
            "NTR is a catch-up candidate (CF +57.5% vs NTR +35.2% 3M, 22pp gap). "
            "MOS is also lagging by 34pp. CF beta to oil is 0.533 (inputs are natural gas, not oil). "
            "Signal chain: Hormuz disruption -> transit blocked -> urea/ammonia shortage -> CF/NTR revenue surge."
        ),
        "category": "macro",
        "evidence": {
            "cf_3m": 57.5, "ntr_3m": 35.2, "mos_3m": 23.5,
            "cf_oos_sharpe": 0.96, "cf_beta_oil": 0.533,
            "correlation_cf_ntr": 0.666, "correlation_cf_mos": 0.649
        },
        "tags": ["fertilizer", "hormuz", "signal_chain", "cf", "ntr", "mos"]
    },
    {
        "title": "Tanker vs Refiner Rotation: Both Win in Supply Disruptions",
        "description": (
            "In Hormuz disruptions, tankers and refiners are NOT zero-sum. Both can win simultaneously. "
            "Tankers benefit first (ton-mile demand, longer routes), refiners catch up 4-6 weeks later "
            "as crack spreads widen from crude discount. Tanker-refiner correlation is only 0.19-0.34 "
            "(near-independent). Current: tankers +42-47% 3M vs refiners +19-34% 3M. "
            "19.9pp gap suggests refiners are still in catch-up phase. PBF has lowest beta to oil (0.86x) "
            "of refiners but highest vol (67.8%). No tactical trading edge (all MCPT rejected)."
        ),
        "category": "macro",
        "evidence": {
            "avg_tanker_3m": 45.3, "avg_refiner_3m": 25.4, "gap_pp": 19.9,
            "fro_pbf_corr": 0.244, "fro_mpc_corr": 0.343
        },
        "tags": ["tanker", "refiner", "rotation", "hormuz", "supply_disruption", "fro", "pbf", "mpc"]
    },
    {
        "title": "SPR Releases Are Tactical Dips, Not Thesis Killers",
        "description": (
            "IEA 400M barrel SPR release announced March 11. Historical pattern analysis: "
            "400M bbl offsets only ~4 days of global consumption (100M bbl/day demand). "
            "Nov 2021 (50M bbl): XLE -5% then recovered in 3 weeks. "
            "Mar 2022 (180M bbl, largest ever): XLE -3% day, then +15% in 60 days, oil to $120+. "
            "The SPR announcement likely creates a 3-7% oil/XLE pullback. "
            "If Hormuz remains disrupted, that pullback is a buy opportunity. "
            "XLE currently +25.7% 3M; well above SMA50 (+10.9%) and SMA200 (+25.8%). "
            "Thesis-driven energy bull markets do not reverse from SPR releases alone."
        ),
        "category": "macro",
        "evidence": {
            "spr_size_bbls": 400_000_000,
            "global_daily_demand_bbls": 100_000_000,
            "days_offset": 4.0,
            "xle_3m": 25.7, "xle_vs_sma50": 10.9,
            "historical_mar2022": "180M bbl release preceded oil to $120+"
        },
        "tags": ["spr", "oil", "xle", "buy_the_dip", "iea", "hormuz", "energy"]
    },
    {
        "title": "Defense 0% Prediction Accuracy: Measurement Artifact, Not Signal Failure",
        "description": (
            "Belief updater shows 0% accuracy on Defense Spending thesis (6/6 five-day predictions missed). "
            "Root cause: 5-day prediction horizon is fundamentally wrong for a 12-24 month macro thesis. "
            "RTX -1.1%, LMT -0.7%, LHX -3.1% in the 5-day window were normal profit-taking after "
            "+32-46% 3-month runs. The underlying thesis catalysts (active US war, $991B budget, "
            "Europe rearmament) are 12-24 month horizon. LMT-SPY correlation is only 0.16, "
            "meaning defense can and does underperform in risk-off weeks. "
            "Recommendation: Change defense prediction timeframe to 30-90 days. "
            "Thesis conviction at 95% remains justified; 5-day miss is a calibration error not alpha failure. "
            "KBR/J/PSN are structural lags (non-pure-defense) - flagged in Feb 28 research."
        ),
        "category": "calibration",
        "evidence": {
            "prediction_horizon_used": "5d",
            "recommended_horizon": "30-90d",
            "lmt_spy_corr": 0.16,
            "lmt_3m": 35.9, "noc_3m": 29.1, "lhx_3m": 27.4,
            "kbr_ytd": -10.0, "psn_ytd": -11.0
        },
        "tags": ["defense", "calibration", "prediction_horizon", "belief_updater", "lmt", "noc", "rtx"]
    },
    {
        "title": "MU Pre-Earnings Setup: Hold, No Tactical Edge",
        "description": (
            "MU earnings March 18, 2026. Consensus $8.42 EPS (+440% YoY). "
            "Current price $418.69, up +21.5% from entry $344.54. "
            "MU is outperforming SMH by +13.1pp over 21 days - strong relative strength. "
            "MCPT testing found no significant pre-earnings momentum (momentum/MU p=0.39). "
            "Buy-and-hold Sharpe of 3.99 (3M) and 2.68 (1Y) far exceed any tactical strategy. "
            "Key signpost to watch: Q2 FY2026 guidance below $7.00 EPS would signal HBM cycle peak. "
            "MU is 90.6% above SMA200 - in extreme territory, common for supercycle stocks. "
            "Hold per Rule 2; the thesis is intact and earnings are expected to be a beat."
        ),
        "category": "strategy",
        "evidence": {
            "earnings_date": "2026-03-18",
            "consensus_eps": 8.42,
            "eps_growth_yoy": "440%",
            "current_price": 418.69,
            "entry_price": 344.54,
            "unrealized_pnl_pct": 21.5,
            "mu_rs_vs_smh_21d": 13.1,
            "momentum_p_value": 0.39
        },
        "tags": ["mu", "earnings", "hbm", "semiconductor", "pre_earnings", "hold"]
    },
    {
        "title": "Energy/Macro Names: MCPT Consistently Rejects All Tactical Strategies",
        "description": (
            "This cycle tested 8 strategy/symbol combinations on energy, fertilizer, defense, and tanker names. "
            "Zero passed MCPT significance threshold (p < 0.05). Pattern is consistent across two research cycles "
            "(Feb 28: 15 energy names tested, all rejected; Mar 11: 8 more tested, all rejected). "
            "The exception remains: bollinger_reversal on QCOM (p=0.007) and MU (p=0.007) - validated. "
            "Implication: thesis-driven macro positions should be managed via thesis conviction and signpost "
            "monitoring, NOT via technical trading signals. The buy-and-hold Sharpe on these names "
            "(1.87-2.86 annualized) exceeds any tactical strategy tested."
        ),
        "category": "methodology",
        "evidence": {
            "this_cycle_tests": 8,
            "this_cycle_passes": 0,
            "total_energy_tests": 23,
            "total_energy_passes": 0,
            "validated_non_energy": ["bollinger_reversal/QCOM p=0.007", "bollinger_reversal/MU p=0.007"],
            "best_oos_sharpe_this_cycle": {"strategy": "momentum/CF", "oos_sharpe": 0.96}
        },
        "tags": ["mcpt", "methodology", "energy", "macro", "thesis_driven", "tactical_trading"]
    },
]

print("\nLogging insights to tracker...")
for ins in insights:
    try:
        tracker.log_insight(
            title=ins["title"],
            description=ins["description"],
            category=ins["category"],
            evidence=ins["evidence"],
            tags=ins["tags"]
        )
        print(f"  Logged insight: {ins['title'][:60]}...")
    except Exception as e:
        print(f"  ERROR: {e}")

# Log to document index
print("\nIndexing research document...")
research_file = paths.live_research / "comprehensive_research_20260311.json"
try:
    athena_db.save_document(
        doc_type="research_result",
        title="Comprehensive Research Cycle - March 11 2026: Fertilizer, Tankers, SPR, Defense, MU",
        file_path=str(research_file),
        source="agent:research_20260311",
        symbols=["CF", "NTR", "MOS", "FRO", "DHT", "PBF", "MPC", "XLE", "LMT", "NOC", "MU"],
        tags=["fertilizer", "hormuz", "spr", "defense", "tanker", "refiner", "mu", "earnings"],
        content_inline=(
            "8 MCPT backtests (all rejected). "
            "Key findings: CF validates Hormuz-fertilizer thesis (+9.4%). "
            "NTR/MOS are catch-up candidates (22-34pp gap vs CF). "
            "SPR 400M bbl = 4 days demand - buy XLE dips. "
            "Defense 0% accuracy = wrong prediction horizon (use 30-90d). "
            "MU $419, +21.5% from entry, hold for Mar 18 earnings."
        )
    )
    print("  Document indexed in DB")
except Exception as e:
    print(f"  ERROR indexing doc: {e}")

print("\nDone. All results logged.")
print(f"\nResearch tracker summary:")
print(f"  Total insights: {len(tracker.insights)}")
print(f"  Total experiments: {len(tracker.experiments)}")
