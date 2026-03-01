#!/usr/bin/env python3
"""Convenience script to get full context for a symbol.

Usage:
    PYTHONPATH=. python3 scripts/context_for_symbol.py SLB
    PYTHONPATH=. python3 scripts/context_for_symbol.py SLB HAL GLD
    PYTHONPATH=. python3 scripts/context_for_symbol.py SLB --json
"""

import argparse
import json
import sys


def get_context(symbol: str, as_json: bool = False) -> dict:
    """Get full context for a symbol: documents, insights, decisions, theses."""
    from src.db.write_api import athena_db
    from src.db.database import get_db
    from src.db.models import ThesisRecord, DecisionRecord

    context = {"symbol": symbol, "documents": [], "insights": [], "theses": [], "decisions": []}

    # Documents mentioning this symbol
    docs = athena_db.get_documents_for_symbol(symbol, limit=15)
    context["documents"] = [
        {
            "id": d.id if hasattr(d, "id") else d.get("id"),
            "type": d.doc_type if hasattr(d, "doc_type") else d.get("doc_type"),
            "title": d.title if hasattr(d, "title") else d.get("title"),
            "created": str(d.created if hasattr(d, "created") else d.get("created", ""))[:10],
            "source": d.source if hasattr(d, "source") else d.get("source"),
        }
        for d in docs
    ]

    # Research insights mentioning this symbol
    insights = athena_db.search_insights(symbol)
    context["insights"] = [
        {
            "title": i.title if hasattr(i, "title") else i.get("title"),
            "category": i.category if hasattr(i, "category") else i.get("category"),
            "confidence": i.confidence if hasattr(i, "confidence") else i.get("confidence"),
            "validated": i.validated if hasattr(i, "validated") else i.get("validated"),
        }
        for i in insights[:10]
    ]

    # Linked theses
    with get_db() as session:
        theses = session.query(ThesisRecord).all()
        for t in theses:
            positions = json.loads(t.positions) if t.positions else []
            if symbol in positions:
                context["theses"].append({
                    "id": t.id,
                    "name": t.name,
                    "conviction": t.conviction,
                    "status": t.status,
                })

    # Recent decisions for this symbol
    with get_db() as session:
        decisions = (
            session.query(DecisionRecord)
            .filter(DecisionRecord.symbol == symbol)
            .order_by(DecisionRecord.timestamp.desc())
            .limit(10)
            .all()
        )
        context["decisions"] = [
            {
                "id": d.id,
                "action": d.action,
                "confidence": d.confidence,
                "status": d.status,
                "date": str(d.timestamp)[:10] if d.timestamp else "",
                "pnl_pct": d.realized_pnl_pct,
            }
            for d in decisions
        ]

    if as_json:
        return context

    # Pretty print
    print(f"\n{'='*60}")
    print(f"  CONTEXT: {symbol}")
    print(f"{'='*60}")

    if context["theses"]:
        print(f"\n  THESES ({len(context['theses'])})")
        print(f"  {'─'*40}")
        for t in context["theses"]:
            print(f"  [{t['status']}] {t['name']} — {t['conviction']}% conviction")

    if context["decisions"]:
        print(f"\n  DECISIONS ({len(context['decisions'])})")
        print(f"  {'─'*40}")
        for d in context["decisions"]:
            pnl = f" → {d['pnl_pct']:+.1f}%" if d["pnl_pct"] is not None else ""
            print(f"  {d['date']}  {d['action']:5s}  {d['confidence']:.0%} conf  [{d['status']}]{pnl}")

    if context["documents"]:
        print(f"\n  DOCUMENTS ({len(context['documents'])})")
        print(f"  {'─'*40}")
        for d in context["documents"]:
            print(f"  {d['created']}  [{d['type']}]  {d['title'][:50]}")

    if context["insights"]:
        print(f"\n  INSIGHTS ({len(context['insights'])})")
        print(f"  {'─'*40}")
        for i in context["insights"]:
            v = " [validated]" if i.get("validated") else ""
            c = f" ({i['confidence']:.0%})" if i.get("confidence") else ""
            print(f"  [{i.get('category', '?')}] {i['title'][:50]}{c}{v}")

    if not any(context[k] for k in ("theses", "decisions", "documents", "insights")):
        print(f"\n  No context found for {symbol}")

    print()
    return context


def main():
    parser = argparse.ArgumentParser(description="Get full context for a symbol")
    parser.add_argument("symbols", nargs="+", help="Symbol(s) to look up")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    results = {}
    for symbol in args.symbols:
        symbol = symbol.upper()
        ctx = get_context(symbol, as_json=args.json)
        results[symbol] = ctx

    if args.json:
        print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
