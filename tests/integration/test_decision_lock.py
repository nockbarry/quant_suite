"""Concurrency test: DecisionLogger.log_decision() must serialize writes
across concurrent threads/processes.

Independent reliability fix B (per plan). Without the flock, two writers
that read the same daily JSON simultaneously each append one decision
and overwrite each other — N writers can lose up to N-1 decisions.
"""

import json
import threading
from pathlib import Path

import pytest


@pytest.fixture
def tmp_decisions_dir(tmp_path) -> Path:
    d = tmp_path / "decisions"
    d.mkdir()
    return d


def _make_decision(symbol: str, idx: int):
    """Build a minimal valid TradingDecision."""
    from src.decision.decision_logger import TradingDecision, Action
    from datetime import datetime
    return TradingDecision(
        id=f"test_{symbol}_{idx}",
        timestamp=datetime.now(),
        symbol=symbol,
        action=Action.BUY,
        confidence=0.7,
        size_pct=2.0,
        limit_price=None,
        stop_loss_pct=5.0,
        take_profit_pct=15.0,
        expected_hold_days=5,
        reasoning=f"test {idx}",
        key_factors=["t"],
        risks=["r"],
        context={},
    )


def test_log_decision_serializes_concurrent_writers(tmp_decisions_dir, monkeypatch):
    """20 threads each writing 5 decisions = 100 decisions in the file.
    With a working lock, all 100 land. Without it, many are lost."""
    # Patch DB sync and document indexing to no-ops so the test is hermetic
    monkeypatch.setattr(
        "src.db.write_api.athena_db.upsert_decision",
        lambda *a, **kw: None,
        raising=False,
    )
    monkeypatch.setattr(
        "src.db.write_api.athena_db.save_document",
        lambda *a, **kw: None,
        raising=False,
    )
    # Also no-op the events emit so we don't drag external state in
    import src.core.events as events_mod
    monkeypatch.setattr(events_mod, "emit", lambda *a, **kw: None)

    from src.decision.decision_logger import DecisionLogger
    logger = DecisionLogger(decisions_dir=tmp_decisions_dir)

    n_threads = 20
    writes_per_thread = 5
    errors = []

    def worker(tid: int):
        try:
            for i in range(writes_per_thread):
                d = _make_decision(f"T{tid}", i)
                logger.log_decision(d)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"Errors during concurrent writes: {errors}"

    # Verify all decisions landed
    daily_files = list(tmp_decisions_dir.glob("decisions_*.json"))
    assert len(daily_files) == 1
    data = json.loads(daily_files[0].read_text())
    decisions = data["decisions"]
    n_expected = n_threads * writes_per_thread
    assert len(decisions) == n_expected, (
        f"Lost writes: got {len(decisions)} of {n_expected}. "
        f"Lock is not preventing the read-modify-write race."
    )

    # All decision IDs unique (no duplicate writes)
    ids = [d["id"] for d in decisions]
    assert len(set(ids)) == n_expected
