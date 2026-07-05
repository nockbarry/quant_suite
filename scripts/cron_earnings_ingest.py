"""
Cron entry point: fetch new earnings press releases from SEC EDGAR
and store them in the text corpus.

Milestone v0 — plumbing only, no LLM extraction.

Schedule: 6:05 AM ET daily (event-driven internally — only fetches if
new accession numbers appear in EDGAR submissions index).

Usage:
    PYTHONPATH=. python3 scripts/cron_earnings_ingest.py --once
    PYTHONPATH=. python3 scripts/cron_earnings_ingest.py --dry-run
    PYTHONPATH=. python3 scripts/cron_earnings_ingest.py --symbol MU
"""

import argparse
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.paths import paths
from src.data.sources.alternative.document_signal_extractor import (
    DocumentSignalExtractor,
)
from src.data.sources.alternative.earnings_transcripts import (
    EarningsContent,
    EarningsTranscriptCollector,
)
from src.knowledge.signal_provenance import (
    SignalSource,
    get_provenance_tracker,
)
from src.text_research.corpus import TextCorpus

logger = logging.getLogger(__name__)

# Default universe — AI / semiconductor cohort.
# TSM excluded (foreign 6-K filer; covered by cron_monthly_revenue_signals.py).
# ARM excluded by default (recent IPO 2023, limited 8-K history).
DEFAULT_UNIVERSE = [
    # Hyperscalers (AI capex announcers)
    "MSFT", "GOOGL", "META", "AMZN", "ORCL",
    # AI compute
    "NVDA", "AMD", "AVGO", "MRVL",
    # Memory / storage
    "MU", "WDC",
    # Foundry / semicap
    "INTC", "AMAT", "LRCX", "KLAC", "ASML",
    # Mobile / IP
    "QCOM",
]
# Backwards compat alias
V0_UNIVERSE = DEFAULT_UNIVERSE

# Per-symbol fetch budget per run
QUARTERS_PER_SYMBOL = 4


def _cache_path() -> Path:
    return paths.scheduler / "processed_earnings.json"


def _load_processed_cache() -> dict:
    """Returns {accession_number: {symbol, filed_date, ingested_at}}."""
    p = _cache_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        logger.warning(f"Corrupt cache at {p}, starting fresh")
        return {}


def _save_processed_cache(cache: dict) -> None:
    p = _cache_path()
    p.write_text(json.dumps(cache, indent=2, sort_keys=True))


def _content_to_metadata(content: EarningsContent) -> dict:
    return {
        "accession_number": content.accession_number,
        "filed_date": content.filed_date,
        "period": content.period,
        "exhibit_filename": content.exhibit_filename,
        "items": content.items,
        "has_qa": bool(content.qa_section),
        "prepared_chars": len(content.prepared_remarks),
        "qa_chars": len(content.qa_section),
        "source_url": (
            f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
            f"&filenum=&type=8-K&dateb=&owner=include&count=10"
        ),
    }


async def _ingest_symbol(
    collector: EarningsTranscriptCollector,
    corpus: TextCorpus,
    extractor: Optional[DocumentSignalExtractor],
    symbol: str,
    cache: dict,
    dry_run: bool,
) -> tuple[int, int, int]:
    """Returns (new_count, skipped_count, signal_count)."""
    items = await collector.get_recent_earnings(symbol, quarters=QUARTERS_PER_SYMBOL)
    new_count = 0
    skipped = 0
    signal_count = 0
    for content in items:
        if content.accession_number in cache:
            skipped += 1
            continue
        if dry_run:
            logger.info(
                f"[DRY] would ingest {symbol} {content.period} "
                f"({content.accession_number}, {len(content.full_text)} chars)"
            )
            new_count += 1
            continue

        try:
            call_dt = datetime.strptime(content.filed_date, "%Y-%m-%d")
        except ValueError:
            logger.warning(f"Bad filed_date '{content.filed_date}' for {symbol}")
            continue

        doc_id = corpus.add_earnings_call(
            symbol=symbol,
            transcript=content.full_text,
            call_date=call_dt,
            metadata=_content_to_metadata(content),
        )
        if doc_id is None:
            logger.warning(f"Corpus rejected {symbol} {content.accession_number}")
            continue

        cache_entry = {
            "symbol": symbol,
            "filed_date": content.filed_date,
            "period": content.period,
            "doc_id": doc_id,
            "ingested_at": datetime.now().isoformat(timespec="seconds"),
        }

        # v1: extract capex signal and record SignalProvenance.
        if extractor is not None:
            signal = _extract_and_record(extractor, symbol, content, doc_id)
            if signal is not None:
                signal_count += 1
                cache_entry["signal_id"] = signal["signal_id"]
                cache_entry["signal_direction"] = signal["direction"]

        cache[content.accession_number] = cache_entry
        new_count += 1
        logger.info(
            f"ingested {symbol} {content.period} "
            f"({content.accession_number}, doc_id={doc_id})"
        )

    return new_count, skipped, signal_count


def _extract_and_record(
    extractor: DocumentSignalExtractor,
    symbol: str,
    content: EarningsContent,
    doc_id: str,
) -> Optional[dict]:
    """Run extractor, write SignalProvenance if a valid signal returned.

    Returns a small dict {signal_id, direction} for the cache, or None.
    Failures are caught — extraction errors should not block ingest.
    """
    try:
        signal = extractor.extract_capex(
            symbol=symbol,
            text=content.full_text,
            filed_date=content.filed_date,
            doc_type="earnings_call",
            source_doc_id=doc_id,
        )
    except Exception as e:
        logger.exception(f"Extractor crashed for {symbol} {content.filed_date}: {e}")
        return None

    if signal is None:
        return None

    try:
        tracker = get_provenance_tracker()
        provenance = tracker.create_signal(
            source=SignalSource.EARNINGS_CALL,
            symbol=signal.symbol,
            confidence=signal.confidence,
            direction=signal.direction,
            description=signal.driver_text or signal.exact_quote[:200],
            detection_method=f"capex_extractor:{content.doc_type if hasattr(content, 'doc_type') else 'earnings_call'}",
            metadata={
                "signal_type": signal.signal_type,
                "magnitude": signal.magnitude,
                "exact_quote": signal.exact_quote,
                "yoy_change_pct": signal.yoy_change_pct,
                "filed_date": signal.filed_date,
                "period": content.period,
                "accession_number": content.accession_number,
                "source_doc_id": doc_id,
                "extraction": signal.extraction_metadata,
            },
        )
    except Exception as e:
        logger.exception(f"Provenance write failed for {symbol}: {e}")
        return None

    logger.info(
        f"  signal: {signal.symbol} {signal.direction}/{signal.magnitude} "
        f"conf={signal.confidence:.2f} (provenance_id={provenance.signal_id})"
    )
    return {"signal_id": provenance.signal_id, "direction": signal.direction}


async def run(
    symbols: list[str],
    dry_run: bool = False,
    extract_signals: bool = True,
) -> dict:
    """Returns summary stats dict.

    Args:
        symbols: Tickers to ingest.
        dry_run: If True, don't store anything.
        extract_signals: If True (default in v1+), run LLM capex extraction
            on each new transcript and write SignalProvenance. Pass False
            to skip API calls (e.g. v0 plumbing-only mode).
    """
    cache = _load_processed_cache()
    corpus = TextCorpus()
    collector = EarningsTranscriptCollector()

    extractor: Optional[DocumentSignalExtractor] = None
    if extract_signals and not dry_run:
        try:
            extractor = DocumentSignalExtractor()
        except Exception as e:
            logger.warning(
                f"Extractor not available ({e}); proceeding without signal extraction"
            )

    total_new = 0
    total_skipped = 0
    total_signals = 0
    per_symbol: dict[str, dict] = {}

    try:
        for symbol in symbols:
            try:
                new, skipped, signals = await _ingest_symbol(
                    collector, corpus, extractor, symbol, cache, dry_run
                )
            except Exception as e:
                logger.exception(f"Symbol {symbol} failed: {e}")
                per_symbol[symbol] = {"error": str(e)}
                continue
            per_symbol[symbol] = {"new": new, "skipped": skipped, "signals": signals}
            total_new += new
            total_skipped += skipped
            total_signals += signals
    finally:
        await collector.close()

    if not dry_run:
        _save_processed_cache(cache)

    summary = {
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "dry_run": dry_run,
        "extract_signals": extractor is not None,
        "symbols": symbols,
        "total_new": total_new,
        "total_skipped": total_skipped,
        "total_signals": total_signals,
        "per_symbol": per_symbol,
        "cache_size": len(cache),
    }

    log_path = paths.logs / "earnings_ingest.jsonl"
    with log_path.open("a") as f:
        f.write(json.dumps(summary) + "\n")

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="SEC earnings ingest (v0)")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--dry-run", action="store_true", help="Don't store anything")
    parser.add_argument(
        "--symbol",
        action="append",
        help="Override universe (repeatable, e.g. --symbol MU --symbol NVDA)",
    )
    parser.add_argument(
        "--no-extract",
        action="store_true",
        help="Skip LLM signal extraction (v0 plumbing-only mode, no API cost)",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    symbols = args.symbol or V0_UNIVERSE
    summary = asyncio.run(
        run(symbols, dry_run=args.dry_run, extract_signals=not args.no_extract)
    )

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
