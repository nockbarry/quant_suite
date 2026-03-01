#!/usr/bin/env python3
"""One-time idempotent migration: backfill DB from existing YAML/JSON files.

Reads all theses, companies, sectors, decisions, and learnings from their
file-based stores and upserts them into the Athena DB. Safe to run multiple
times — uses upsert semantics.

Usage:
    PYTHONPATH=. python scripts/migrate_to_db.py
"""

import json
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
from src.db.database import init_db
from src.db.write_api import athena_db


def _results_dir() -> Path:
    return Path(os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results")))


def migrate_theses() -> int:
    """Migrate all thesis YAML files to DB."""
    theses_dir = _results_dir() / "theses"
    if not theses_dir.exists():
        return 0

    count = 0
    for filepath in theses_dir.glob("*.yaml"):
        try:
            data = yaml.safe_load(filepath.read_text())
            if data and data.get("id"):
                athena_db.upsert_thesis(data)
                count += 1
        except Exception as e:
            print(f"  WARN: Failed to migrate thesis {filepath.name}: {e}")

    for filepath in theses_dir.glob("*.json"):
        try:
            data = json.loads(filepath.read_text())
            if data and data.get("id"):
                athena_db.upsert_thesis(data)
                count += 1
        except Exception as e:
            print(f"  WARN: Failed to migrate thesis {filepath.name}: {e}")

    return count


def migrate_companies() -> int:
    """Migrate all company YAML files to DB."""
    companies_dir = _results_dir() / "knowledge" / "companies"
    if not companies_dir.exists():
        return 0

    count = 0
    for filepath in companies_dir.glob("*.*"):
        if filepath.suffix not in (".yaml", ".json"):
            continue
        try:
            if filepath.suffix == ".yaml":
                data = yaml.safe_load(filepath.read_text())
            else:
                data = json.loads(filepath.read_text())
            if data and data.get("symbol"):
                athena_db.upsert_company(data)
                count += 1
        except Exception as e:
            print(f"  WARN: Failed to migrate company {filepath.name}: {e}")

    return count


def migrate_sectors() -> int:
    """Migrate all sector YAML files to DB."""
    sectors_dir = _results_dir() / "knowledge" / "sectors"
    if not sectors_dir.exists():
        return 0

    count = 0
    for filepath in sectors_dir.glob("*.*"):
        if filepath.suffix not in (".yaml", ".json"):
            continue
        try:
            if filepath.suffix == ".yaml":
                data = yaml.safe_load(filepath.read_text())
            else:
                data = json.loads(filepath.read_text())
            if data and data.get("sector"):
                athena_db.upsert_sector(data)
                count += 1
        except Exception as e:
            print(f"  WARN: Failed to migrate sector {filepath.name}: {e}")

    return count


def migrate_decisions() -> int:
    """Migrate all decision JSON files to DB."""
    decisions_dir = _results_dir() / "decisions"
    if not decisions_dir.exists():
        return 0

    count = 0
    for filepath in decisions_dir.glob("decisions_*.json"):
        try:
            content = json.loads(filepath.read_text())
            decisions = content if isinstance(content, list) else content.get("decisions", [])
            for d in decisions:
                if d.get("id"):
                    athena_db.upsert_decision(d)
                    count += 1
        except Exception as e:
            print(f"  WARN: Failed to migrate decisions {filepath.name}: {e}")

    return count


def migrate_learnings() -> int:
    """Migrate all learning JSON files to DB."""
    learnings_dir = _results_dir() / "learnings"
    if not learnings_dir.exists():
        return 0

    count = 0
    for filepath in learnings_dir.glob("*.json"):
        try:
            content = json.loads(filepath.read_text())
            items = content if isinstance(content, list) else content.get("learnings", [])
            for item in items:
                if item.get("id"):
                    athena_db.upsert_learning(item)
                    count += 1
        except Exception as e:
            print(f"  WARN: Failed to migrate learnings {filepath.name}: {e}")

    return count


def main():
    print("Athena DB Migration")
    print("=" * 50)

    # Ensure tables exist
    print("Initializing DB schema...")
    init_db()

    print("\nMigrating data...")

    theses = migrate_theses()
    print(f"  Theses:     {theses}")

    companies = migrate_companies()
    print(f"  Companies:  {companies}")

    sectors = migrate_sectors()
    print(f"  Sectors:    {sectors}")

    decisions = migrate_decisions()
    print(f"  Decisions:  {decisions}")

    learnings = migrate_learnings()
    print(f"  Learnings:  {learnings}")

    total = theses + companies + sectors + decisions + learnings
    print(f"\nTotal records upserted: {total}")
    print("Migration complete.")


if __name__ == "__main__":
    main()
