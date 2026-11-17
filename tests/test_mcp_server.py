import json

import duckdb
import pytest
from fastapi.testclient import TestClient
from mcp.server.mcpserver.exceptions import ToolError

import api.deps
from api import mcp_server


@pytest.fixture(scope="module")
def gold_db(tmp_path_factory):
    path = tmp_path_factory.mktemp("gold") / "nfl.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE dim_teams (team_abbr VARCHAR, team_name VARCHAR, team_conf VARCHAR, team_division VARCHAR)")
    con.execute("INSERT INTO dim_teams VALUES ('KC','Kansas City Chiefs','AFC','AFC West'), ('SF','San Francisco 49ers','NFC','NFC West')")
    con.execute("CREATE TABLE dim_games (game_id VARCHAR, season INTEGER, gameday DATE)")
    con.execute("INSERT INTO dim_games VALUES ('2023_22_SF_KC', 2023, DATE '2024-02-11')")
    con.execute("""CREATE TABLE dim_players (gsis_id VARCHAR, display_name VARCHAR, position VARCHAR, birth_date DATE,
        college VARCHAR, draft_year INTEGER, draft_round INTEGER, draft_pick INTEGER, draft_club VARCHAR,
        rookie_year INTEGER, status VARCHAR, pfr_id VARCHAR)""")
    con.execute("INSERT INTO dim_players VALUES ('00-0033873','Patrick Mahomes','QB',DATE '1995-09-17','Texas Tech',2017,1,10,'KC',2017,'ACT','MahoPa00')")
    con.close()
    return path


@pytest.fixture(scope="module")
def conn(gold_db):
    # Open exactly as production does: DuckDB refuses a second connection to the
    # same file in one process if the config differs.
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(api.deps, "GOLD_DB", gold_db)
        c = api.deps.get_read_only_connection()
    assert c is not None
    mcp_server.set_connection_getter(lambda: c)
    yield c
    c.close()


def test_validate_select_accepts_select_and_cte():
    assert mcp_server.validate_select("SELECT 1")
    assert mcp_server.validate_select("WITH x AS (SELECT 1 AS a) SELECT a FROM x;")


@pytest.mark.parametrize("sql", [
    "CREATE TABLE t (x INT)",
    "INSERT INTO dim_teams VALUES ('X','X','X','X')",
    "COPY dim_teams TO 'out.csv'",
    "ATTACH 'other.db'",
    "INSTALL httpfs",
    "SET memory_limit = '4GB'",
    "SELECT 1; SELECT 2",
    "EXPLAIN SELECT 1",
    "not sql at all",
])
def test_validate_select_rejects(sql):
    with pytest.raises(ToolError):
        mcp_server.validate_select(sql)


@pytest.mark.parametrize("sql", [
    "SELECT * FROM read_csv('/etc/hosts')",
    "SELECT * FROM read_text('/etc/passwd')",
    "SELECT * FROM 'https://example.com/x.parquet'",
])
def test_engine_blocks_external_access(conn, sql):
    # These parse as SELECTs, so the engine-level lockdown is what stops them.
    query = mcp_server.validate_select(sql)
    with pytest.raises(ToolError):
        mcp_server.run_query(query, 10)


def test_query_sql_caps_rows_and_serializes(conn):
    out = mcp_server.query_sql("SELECT range AS n, DATE '2024-01-01' AS d FROM range(1000)", max_rows=5)
    assert out["row_count"] == 5 and out["truncated"] is True
    assert out["rows"][0] == [0, "2024-01-01"]
    assert mcp_server.query_sql("SELECT 1", max_rows=10_000)["truncated"] is False


def test_query_timeout(conn, monkeypatch):
    monkeypatch.setattr(mcp_server, "QUERY_TIMEOUT_SECONDS", 0.2)
    with pytest.raises(ToolError, match="cancelled"):
        mcp_server.query_sql("SELECT count(*) FROM range(10000000000) a")


def test_catalog_tools(conn):
    tables = {t["table"] for t in mcp_server.list_tables()["tables"]}
    assert {"dim_players", "dim_teams", "dim_games"} <= tables
    desc = mcp_server.describe_table("dim_players", sample_rows=1)
    assert "gsis_id" in [c["name"] for c in desc["columns"]]
    assert desc["sample"]["row_count"] == 1
    with pytest.raises(ToolError):
        mcp_server.describe_table('dim_players"; DROP TABLE x; --')


def test_search_players(conn):
    out = mcp_server.search_players("mahomes", position="qb")
    assert out["rows"][0][0] == "00-0033873"
    assert mcp_server.search_players("nobody")["row_count"] == 0


def _rpc(client, method, params=None, id_=1):
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}},
        headers={"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"},
    )
    return resp


def test_http_endpoint_end_to_end(gold_db, monkeypatch):
    monkeypatch.setattr(api.deps, "GOLD_DB", gold_db)
    from api.main import app

    with TestClient(app) as client:
        init = _rpc(client, "initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"},
        })
        assert init.status_code == 200, init.text
        assert init.json()["result"]["serverInfo"]["name"] == "nfldata"

        tools = _rpc(client, "tools/list", id_=2).json()["result"]["tools"]
        assert {t["name"] for t in tools} >= {"list_tables", "describe_table", "query_sql", "search_players"}

        call = _rpc(client, "tools/call", {"name": "query_sql", "arguments": {"sql": "SELECT count(*) AS n FROM dim_teams"}}, id_=3)
        result = call.json()["result"]
        assert not result.get("isError"), result
        payload = result.get("structuredContent") or json.loads(result["content"][0]["text"])
        assert payload["rows"] == [[2]]

        bad = _rpc(client, "tools/call", {"name": "query_sql", "arguments": {"sql": "DROP TABLE dim_teams"}}, id_=4).json()
        assert bad["result"]["isError"] is True

        # REST API still works alongside the mount.
        assert client.get("/v1/meta").status_code == 200
