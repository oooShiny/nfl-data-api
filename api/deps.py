import duckdb
from fastapi import Request

from pipeline.config import GOLD_DB


def get_read_only_connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(GOLD_DB), read_only=True)


def get_db(request: Request) -> duckdb.DuckDBPyConnection:
    return request.app.state.db


def _build_filter(filters: list[tuple[str, object]]) -> tuple[str, list]:
    clauses, params = [], []
    for condition, value in filters:
        if value is not None:
            clauses.append(condition)
            params.append(value)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params
