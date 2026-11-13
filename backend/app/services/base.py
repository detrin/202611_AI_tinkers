"""Small shared helpers for services."""
from ..errors import NotFound
from ..ports import Database, Row


def get_one(db: Database, table: str, **where) -> Row:
    rows = db.select(table, where, limit=1)
    if not rows:
        raise NotFound(f"{table} not found")
    return rows[0]


def latest(db: Database, table: str, **where) -> Row | None:
    rows = db.select(table, where, order_by="created_at", desc=True, limit=1)
    return rows[0] if rows else None
