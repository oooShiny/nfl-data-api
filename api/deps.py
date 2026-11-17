from typing import Any

import duckdb
from fastapi import Request

from api.models.responses import PaginatedResponse
from pipeline.config import GOLD_DB


# Hardening for the shared connection. The MCP `query_sql` tool runs arbitrary
# SELECTs from the public internet on this connection, so the engine itself must
# refuse file/network access (read_csv, COPY TO, INSTALL, ...) and the settings
# must be immutable from SQL. DuckDB only allows one configuration per database
# file per process, so the REST API shares these settings (it needs none of the
# blocked features). memory_limit/threads are sized for 2 uvicorn workers on a
# 512MB Fly machine.
DB_CONFIG = {
    "enable_external_access": False,
    "autoinstall_known_extensions": False,
    "autoload_known_extensions": False,
    "memory_limit": "128MB",
    "threads": 2,
    # Big sorts/joins spill here instead of failing; capped so they can't fill the volume.
    "max_temp_directory_size": "512MB",
    "lock_configuration": True,
}
TEMP_DIR_NAME = "duckdb_tmp"


def get_read_only_connection() -> duckdb.DuckDBPyConnection | None:
    if not GOLD_DB.exists():
        return None
    temp_dir = GOLD_DB.parent / TEMP_DIR_NAME
    try:
        temp_dir.mkdir(exist_ok=True)
        return duckdb.connect(
            str(GOLD_DB), read_only=True, config={**DB_CONFIG, "temp_directory": str(temp_dir)}
        )
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
