"""MCP server exposing the gold DuckDB database to AI clients.

Mounted into the FastAPI app (see api/main.py) and served over Streamable HTTP at
/mcp. It runs stateless so it works across uvicorn workers and Fly auto-stop.

Safety model for query_sql: the shared DuckDB connection is opened read-only with
external access disabled and its configuration locked (api/deps.py), so the
engine refuses writes, file/network reads and settings changes. On top of that we
accept exactly one SELECT statement, cap the rows returned, and interrupt queries
that run too long.
"""

from __future__ import annotations

import datetime as dt
import decimal
import threading
import uuid
from collections.abc import Callable
from typing import Any

import duckdb
from limits import parse as parse_limit
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from api.mcp_catalog import SCHEMA_GUIDE, TABLES

MAX_SQL_CHARS = 10_000
DEFAULT_ROWS = 100
MAX_ROWS = 500
MAX_CELL_CHARS = 2_000
QUERY_TIMEOUT_SECONDS = 15.0

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)

# Set by api.main so tools always see the current connection, including after
# /v1/admin/refresh swaps in a new database file.
_connection_getter: Callable[[], duckdb.DuckDBPyConnection | None] = lambda: None


def set_connection_getter(getter: Callable[[], duckdb.DuckDBPyConnection | None]) -> None:
    global _connection_getter
    _connection_getter = getter


def _cursor() -> duckdb.DuckDBPyConnection:
    conn = _connection_getter()
    if conn is None:
        raise ToolError("Database not yet available; a data refresh is in progress. Try again shortly.")
    # A cursor is a separate connection to the same database, safe to use from this worker thread.
    return conn.cursor()


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        if isinstance(value, str) and len(value) > MAX_CELL_CHARS:
            return value[:MAX_CELL_CHARS] + "…"
        return value
    if isinstance(value, float):
        return value if value == value and value not in (float("inf"), float("-inf")) else None
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (dt.date, dt.datetime, dt.time)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, uuid.UUID):
        return str(value)
    return str(value)


def validate_select(sql: str) -> str:
    """Return the single SELECT statement in `sql`, or raise ToolError."""
    if len(sql) > MAX_SQL_CHARS:
        raise ToolError(f"SQL is too long (max {MAX_SQL_CHARS} characters).")
    try:
        statements = duckdb.extract_statements(sql)
    except duckdb.Error as e:
        raise ToolError(f"SQL parse error: {e}") from None
    if len(statements) != 1:
        raise ToolError("Send exactly one SQL statement.")
    stmt = statements[0]
    if stmt.type != duckdb.StatementType.SELECT:
        raise ToolError(f"Only SELECT queries are allowed (got {stmt.type.name}).")
    return stmt.query


def run_query(sql: str, max_rows: int, params: list[Any] | None = None) -> dict[str, Any]:
    cur = _cursor()
    timer = threading.Timer(QUERY_TIMEOUT_SECONDS, cur.interrupt)
    timer.start()
    try:
        cur.execute(sql, params or [])
        columns = [d[0] for d in cur.description]
        rows = cur.fetchmany(max_rows + 1)
    except duckdb.InterruptException:
        raise ToolError(
            f"Query exceeded {QUERY_TIMEOUT_SECONDS:.0f}s and was cancelled. Add filters (season, team, player) or aggregate."
        ) from None
    except duckdb.OutOfMemoryException:
        raise ToolError(
            "Query ran out of memory on this small server. Select fewer columns, filter by season/team/player, or aggregate."
        ) from None
    except duckdb.Error as e:
        raise ToolError(f"{type(e).__name__}: {e}") from None
    finally:
        timer.cancel()
        cur.close()
    truncated = len(rows) > max_rows
    rows = rows[:max_rows]
    return {
        "columns": columns,
        "rows": [[_jsonable(v) for v in row] for row in rows],
        "row_count": len(rows),
        "truncated": truncated,
    }


server = MCPServer(
    name="nfldata",
    title="NFL Data",
    description="Query NFL games, play-by-play, player and team stats, rosters, draft, combine, contracts, and trades.",
    website_url="https://nfldata.br0wn.net",
    version="1.0.0",
    instructions=(
        "Read-only NFL database. Typical flow: list_tables to find data, describe_table for columns "
        "and sample rows, search_players to turn names into gsis_id values, then query_sql.\n\n" + SCHEMA_GUIDE
    ),
)


@server.tool(annotations=READ_ONLY)
def list_tables() -> dict[str, Any]:
    """List every table with a description, season coverage, and approximate row count. Start here."""
    cur = _cursor()
    try:
        sizes = dict(cur.execute("SELECT table_name, estimated_size FROM duckdb_tables()").fetchall())
    finally:
        cur.close()
    tables = []
    for name in sorted(sizes):
        info = TABLES.get(name, {})
        tables.append({
            "table": name,
            "description": info.get("description", ""),
            "coverage": info.get("coverage", ""),
            "approx_rows": sizes[name],
        })
    return {"tables": tables, "guide": SCHEMA_GUIDE}


@server.tool(annotations=READ_ONLY)
def describe_table(table: str, sample_rows: int = 3) -> dict[str, Any]:
    """Show a table's columns and types, notes on keys and joins, and a few sample rows.

    Args:
        table: Table name from list_tables, e.g. "fact_plays".
        sample_rows: Number of example rows to include (0-10).
    """
    cur = _cursor()
    try:
        known = {r[0] for r in cur.execute("SELECT table_name FROM duckdb_tables()").fetchall()}
        if table not in known:
            raise ToolError(f"Unknown table {table!r}. Call list_tables for valid names.")
        columns = [
            {"name": name, "type": col_type}
            for name, col_type, *_ in cur.execute(f'DESCRIBE "{table}"').fetchall()
        ]
    finally:
        cur.close()
    n = max(0, min(sample_rows, 10))
    sample = run_query(f'SELECT * FROM "{table}" LIMIT {n}', n) if n else None
    info = TABLES.get(table, {})
    return {
        "table": table,
        "description": info.get("description", ""),
        "coverage": info.get("coverage", ""),
        "notes": info.get("notes", ""),
        "columns": columns,
        "sample": sample,
    }


@server.tool(annotations=READ_ONLY)
def query_sql(sql: str, max_rows: int = DEFAULT_ROWS) -> dict[str, Any]:
    """Run one read-only DuckDB SELECT (CTEs allowed) and return the rows.

    Use aggregates and filters rather than pulling raw play-by-play: results are capped
    and queries over 15 seconds are cancelled. DuckDB SQL dialect (e.g. ILIKE, QUALIFY,
    FILTER, list functions). Check `truncated` in the result.

    Args:
        sql: A single SELECT or WITH ... SELECT statement.
        max_rows: Rows to return, 1-500 (default 100).
    """
    query = validate_select(sql)
    return run_query(query, max(1, min(max_rows, MAX_ROWS)))


@server.tool(annotations=READ_ONLY)
def search_players(name: str, position: str | None = None, limit: int = 10) -> dict[str, Any]:
    """Find players by (partial) name and get their gsis_id and other IDs for use in queries.

    Args:
        name: Full or partial name, case-insensitive, e.g. "mahomes".
        position: Optional position filter, e.g. "QB", "WR".
        limit: Maximum matches, 1-50.
    """
    sql = """
        SELECT gsis_id, display_name, position, birth_date, college,
               draft_year, draft_round, draft_pick, draft_club, rookie_year, status, pfr_id
        FROM dim_players
        WHERE display_name ILIKE ? {pos}
        ORDER BY rookie_year DESC NULLS LAST, display_name
        LIMIT ?
    """.format(pos="AND position = ?" if position else "")
    n = max(1, min(limit, 50))
    params: list[Any] = [f"%{name}%"] + ([position.upper()] if position else []) + [n]
    return run_query(sql, n, params)


@server.tool(annotations=READ_ONLY)
def list_teams_and_seasons() -> dict[str, Any]:
    """List team abbreviations with names, conference and division, plus the seasons that have games."""
    teams = run_query(
        "SELECT team_abbr, team_name, team_conf, team_division FROM dim_teams ORDER BY team_abbr", 100
    )
    seasons = run_query(
        "SELECT DISTINCT season FROM dim_games WHERE season IS NOT NULL ORDER BY season", 200
    )
    return {"teams": teams["rows"], "team_columns": teams["columns"], "seasons": [r[0] for r in seasons["rows"]]}


@server.resource("nfldata://schema-guide", name="schema-guide", mime_type="text/markdown",
                 description="Identifiers, conventions, and coverage notes for the NFL database.")
def schema_guide() -> str:
    lines = [SCHEMA_GUIDE, "\nTables\n"]
    for name, info in sorted(TABLES.items()):
        lines.append(f"- {name}: {info['description']} Coverage: {info['coverage']} {info.get('notes', '')}".rstrip())
    return "\n".join(lines)


class RateLimitMiddleware:
    """Per-client-IP moving-window limit for the MCP endpoint.

    Fly's proxy puts the real client address in Fly-Client-IP; request.client is
    the proxy. Counts are in-memory per process (the Dockerfile runs one worker)
    and reset when the machine restarts.
    """

    def __init__(self, app: ASGIApp, rate: str = "60/minute") -> None:
        self.app = app
        self.limit = parse_limit(rate)
        self.limiter = MovingWindowRateLimiter(MemoryStorage())

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("method") == "POST":
            headers = dict(scope.get("headers") or [])
            ip = headers.get(b"fly-client-ip", b"").decode() or (scope.get("client") or ("unknown",))[0]
            if not self.limiter.hit(self.limit, "mcp", ip):
                response = JSONResponse(
                    {"jsonrpc": "2.0", "id": None,
                     "error": {"code": -32000, "message": "Rate limit exceeded; slow down and retry in a minute."}},
                    status_code=429,
                    headers={"Retry-After": "60"},
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def build_asgi_app() -> ASGIApp:
    """Starlette app serving MCP at /mcp. Its session manager must be run in the host app's lifespan."""
    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        host="0.0.0.0",  # public server: skip the localhost-only DNS-rebinding defaults
    )
    return RateLimitMiddleware(app)
