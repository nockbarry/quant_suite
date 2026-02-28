"""Knowledge service -- CRUD for Company and Sector tables."""

import json
from datetime import datetime

from src.db.database import get_db
from src.db.models import Company, Sector
from src.db.sync import sync_company_to_file, sync_sector_to_file


# ---------------------------------------------------------------------------
# Company CRUD
# ---------------------------------------------------------------------------


def list_companies() -> list[dict]:
    """Return all companies ordered by symbol."""
    with get_db() as session:
        rows = session.query(Company).order_by(Company.symbol).all()
        return [r.to_dict() for r in rows]


def get_company(symbol: str) -> dict | None:
    """Return a single company by symbol, or None."""
    with get_db() as session:
        row = session.query(Company).filter(Company.symbol == symbol.upper()).first()
        return row.to_dict() if row else None


def create_company(data: dict) -> dict:
    """Insert a new company record. Dual-writes to YAML file."""
    data.setdefault("updated", datetime.utcnow().isoformat())
    row = Company.from_dict(data)
    with get_db() as session:
        session.add(row)
        session.flush()
        result = row.to_dict()
    sync_company_to_file(result)
    return result


def update_company(symbol: str, data: dict) -> dict | None:
    """Update an existing company. Returns updated dict or None if not found."""
    with get_db() as session:
        row = session.query(Company).filter(Company.symbol == symbol.upper()).first()
        if row is None:
            return None
        # Apply updates
        for key, value in data.items():
            if key == "symbol":
                continue  # don't change PK
            if key in ("key_risks", "key_catalysts") and isinstance(value, list):
                value = json.dumps(value)
            if hasattr(row, key):
                setattr(row, key, value)
        row.updated = datetime.utcnow()
        session.flush()
        result = row.to_dict()
    sync_company_to_file(result)
    return result


def delete_company(symbol: str) -> bool:
    """Delete a company. Returns True if deleted, False if not found."""
    with get_db() as session:
        row = session.query(Company).filter(Company.symbol == symbol.upper()).first()
        if row is None:
            return False
        session.delete(row)
    return True


# ---------------------------------------------------------------------------
# Sector CRUD
# ---------------------------------------------------------------------------


def list_sectors() -> list[dict]:
    """Return all sectors ordered by name."""
    with get_db() as session:
        rows = session.query(Sector).order_by(Sector.sector).all()
        return [r.to_dict() for r in rows]


def get_sector(name: str) -> dict | None:
    """Return a single sector by name, or None."""
    with get_db() as session:
        row = session.query(Sector).filter(Sector.sector == name).first()
        return row.to_dict() if row else None


def create_sector(data: dict) -> dict:
    """Insert a new sector record. Dual-writes to YAML file."""
    data.setdefault("updated", datetime.utcnow().isoformat())
    row = Sector.from_dict(data)
    with get_db() as session:
        session.add(row)
        session.flush()
        result = row.to_dict()
    sync_sector_to_file(result)
    return result


def update_sector(name: str, data: dict) -> dict | None:
    """Update an existing sector. Returns updated dict or None if not found."""
    with get_db() as session:
        row = session.query(Sector).filter(Sector.sector == name).first()
        if row is None:
            return None
        for key, value in data.items():
            if key == "sector":
                continue  # don't change PK
            if key in ("key_drivers", "leading_indicators", "leaders", "laggards") and isinstance(value, list):
                value = json.dumps(value)
            if key == "correlations" and isinstance(value, dict):
                value = json.dumps(value)
            if hasattr(row, key):
                setattr(row, key, value)
        row.updated = datetime.utcnow()
        session.flush()
        result = row.to_dict()
    sync_sector_to_file(result)
    return result
