from typing import Any

import duckdb
from fastapi import Request

from api.models.responses import PaginatedResponse
from pipeline.config import GOLD_DB


def get_read_only_connection() -> duckdb.DuckDBPyConnection | None:
    if not GOLD_DB.exists():
        return None
    try:
        return duckdb.connect(str(GOLD_DB), read_only=True)
    except Exception:
        return None


def get_db(request: Request) -> duckdb.DuckDBPyConnection:
    from fastapi import HTTPException
    if request.app.state.db is None:
        raise HTTPException(status_code=503, detail="Database not yet available — refresh in progress.")
    return request.app.state.db


def _build_filter(filters: list[tuple[str, object]]) -> tuple[str, list]:
    clauses, params = [], []
    for condition, value in filters:
        if value is not None:
            clauses.append(condition)
            params.append(value)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def list_table(
    db: duckdb.DuckDBPyConnection,
    table: str,
    filters: list[tuple[str, object]],
    order_by: str,
    limit: int,
    offset: int,
) -> PaginatedResponse[dict[str, Any]]:
    """Generic paginated SELECT * over a gold table, returned as plain dicts."""
    where, params = _build_filter(filters)
    total = db.execute(f"SELECT COUNT(*) FROM {table} {where}", params).fetchone()[0]
    rows = db.execute(
        f"SELECT * FROM {table} {where} ORDER BY {order_by} LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    cols = [d[0] for d in db.description]
    data = [dict(zip(cols, row)) for row in rows]
    return PaginatedResponse(data=data, total=total, limit=limit, offset=offset)
