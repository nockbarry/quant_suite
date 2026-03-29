"""Opinion universe manager — builds the 50-80 symbol list for opinion capture."""

import json
import logging
import os
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Commodity proxies always included
COMMODITY_PROXIES = ["USO", "GLD", "UNG", "BDRY", "BNO"]


class OpinionUniverse:
    """Manages the 50-80 symbol universe for opinion capture.

    Sources:
    1. Thesis vehicles from active theses (~30-40)
    2. Core watchlist from config/watchlist.yaml (~33)
    3. Today's top movers (~5-10)
    4. Commodity proxies (~5)

    Deduplicates by symbol, preferring thesis-linked entries.
    """

    def __init__(self, results_dir: Path | None = None, project_dir: Path | None = None):
        self.results_dir = results_dir or Path(
            os.environ.get("QUANT_RESULTS_DIR", str(Path.home() / "quant_results"))
        )
        self.project_dir = project_dir or Path(__file__).parent.parent.parent

    def get_universe(self) -> list[dict]:
        """Return the full universe with category tags.

        Returns list of dicts with keys:
            symbol, category, thesis_id, thesis_name, conviction, extra
        """
        # Gather from all sources
        thesis_vehicles = self._get_thesis_vehicles()
        held_positions = self._get_held_positions()
        watchlist = self._get_watchlist_core()
        movers = self._get_movers()
        commodities = self._get_commodity_proxies()

        # Merge with thesis vehicles taking priority, then held positions
        return self._deduplicate(
            thesis_vehicles + held_positions + watchlist + movers + commodities
        )

    def _get_thesis_vehicles(self) -> list[dict]:
        """Read active thesis vehicles from theses/*.yaml."""
        theses_dir = self.results_dir / "theses"
        results = []
        if not theses_dir.exists():
            return results

        for f in sorted(theses_dir.glob("*.yaml")):
            try:
                t = yaml.safe_load(f.read_text())
                if not t or t.get("status") != "active":
                    continue
                conviction = t.get("conviction", 0)
                if isinstance(conviction, float):
                    conviction = int(conviction)
                thesis_name = t.get("name", "")
                thesis_id = t.get("id", "")
                for sym in t.get("positions", []):
                    results.append({
                        "symbol": sym,
                        "category": "thesis",
                        "thesis_id": thesis_id,
                        "thesis_name": thesis_name,
                        "conviction": conviction,
                        "extra": "",
                    })
            except Exception as e:
                logger.debug(f"Error reading thesis {f}: {e}")

        return results

    def _get_held_positions(self) -> list[dict]:
        """Read currently held positions from state.json.

        Ensures every held symbol is in the universe even if not
        in a thesis or watchlist (e.g., recently bought movers).
        """
        results = []
        state_path = self.results_dir / "live" / "state.json"
        if not state_path.exists():
            return results

        try:
            data = json.loads(state_path.read_text())
            for pos in data.get("positions", []):
                sym = pos.get("symbol", "")
                if not sym or len(sym) > 6:  # Skip options symbols
                    continue
                thesis_id = pos.get("thesis_id", "")
                results.append({
                    "symbol": sym,
                    "category": "held",
                    "thesis_id": thesis_id,
                    "thesis_name": "",
                    "conviction": 0,
                    "extra": f"held={pos.get('unrealized_pnl_pct', 0):+.1f}%",
                })
        except Exception as e:
            logger.debug(f"Error reading positions: {e}")

        return results

    def _get_watchlist_core(self) -> list[dict]:
        """Read config/watchlist.yaml for ETFs, benchmarks, mega caps."""
        watchlist_path = self.project_dir / "config" / "watchlist.yaml"
        results = []
        if not watchlist_path.exists():
            return results

        try:
            data = yaml.safe_load(watchlist_path.read_text())
            for sym in data.get("symbols", []):
                sym = sym.strip()
                if sym and not sym.startswith("#"):
                    results.append({
                        "symbol": sym,
                        "category": "watchlist",
                        "thesis_id": "",
                        "thesis_name": "",
                        "conviction": 0,
                        "extra": "",
                    })
        except Exception as e:
            logger.debug(f"Error reading watchlist: {e}")

        return results

    def _get_movers(self) -> list[dict]:
        """Read market_movers_latest.json for today's top movers."""
        movers_path = self.results_dir / "live" / "market_movers_latest.json"
        results = []
        if not movers_path.exists():
            return results

        try:
            data = json.loads(movers_path.read_text())
            movers = data.get("movers", data.get("top_movers", []))
            if isinstance(movers, list):
                for m in movers[:10]:
                    sym = m.get("symbol", m.get("ticker", ""))
                    change = m.get("change_pct", m.get("pct_change", 0))
                    if sym:
                        results.append({
                            "symbol": sym,
                            "category": "mover",
                            "thesis_id": "",
                            "thesis_name": "",
                            "conviction": 0,
                            "extra": f"mover={change:+.1f}%",
                        })
        except Exception as e:
            logger.debug(f"Error reading movers: {e}")

        return results

    def _get_commodity_proxies(self) -> list[dict]:
        """Static commodity proxy ETFs."""
        return [
            {
                "symbol": sym,
                "category": "commodity",
                "thesis_id": "",
                "thesis_name": "",
                "conviction": 0,
                "extra": "",
            }
            for sym in COMMODITY_PROXIES
        ]

    def _deduplicate(self, symbols: list[dict]) -> list[dict]:
        """Deduplicate by symbol, preferring thesis-linked entries."""
        seen: dict[str, dict] = {}
        for s in symbols:
            sym = s["symbol"]
            if sym not in seen:
                seen[sym] = s
            elif s["category"] == "thesis" and seen[sym]["category"] != "thesis":
                # Thesis entries take priority
                seen[sym] = s
            elif s["category"] == "thesis" and seen[sym]["category"] == "thesis":
                # Multiple theses — keep higher conviction
                if s["conviction"] > seen[sym]["conviction"]:
                    seen[sym] = s

        return sorted(seen.values(), key=lambda x: (-x["conviction"], x["symbol"]))
