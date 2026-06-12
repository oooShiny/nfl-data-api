from typing import Any

import duckdb
from fastapi import APIRouter, Depends, Query, Request

from api.deps import _build_filter, get_db
from api.models.responses import CombineResult, Contract, DraftPick, PaginatedResponse

router = APIRouter(tags=["reference"])


@router.get("/combine", response_model=PaginatedResponse[CombineResult])
def list_combine(
    request: Request,
    season: int | None = None,
    position: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    filters = [
        ("season = ?", season),
        ("pos = ?", position),
    ]
    where, params = _build_filter(filters)
    total = db.execute(f"SELECT COUNT(*) FROM ref_combine {where}", params).fetchone()[0]
    rows = db.execute(
        f"SELECT * FROM ref_combine {where} ORDER BY season DESC, player_name LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    cols = [d[0] for d in db.description]
    data = [CombineResult.model_validate(dict(zip(cols, row))) for row in rows]
    return PaginatedResponse(data=data, total=total, limit=limit, offset=offset)


@router.get("/draft/top-by-pick", response_model=PaginatedResponse[dict[str, Any]])
def list_draft_top_by_pick(
    request: Request,
    round: int = Query(default=1, ge=1, le=20),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    """For each pick number in a round, the player with the best career fantasy production."""
    total = db.execute(
        "SELECT COUNT(DISTINCT pick) FROM ref_draft_picks WHERE round = ?", [round]
    ).fetchone()[0]
    rows = db.execute(
        """
        WITH career AS (
            SELECT player_id,
                   SUM(games) AS games,
                   SUM(fantasy_points_ppr) AS fantasy_points_ppr
            FROM fact_player_season_stats
            WHERE season_type IN ('REG', 'REG+POST')
            GROUP BY player_id
        ),
        ranked AS (
            SELECT
                d.pick,
                d.season,
                d.team,
                d.player_name,
                d.position,
                d.college,
                d.gsis_id,
                COALESCE(c.games, 0) AS career_games,
                COALESCE(c.fantasy_points_ppr, 0) AS career_fantasy_points_ppr,
                ROW_NUMBER() OVER (
                    PARTITION BY d.pick ORDER BY COALESCE(c.fantasy_points_ppr, 0) DESC
                ) AS rn
            FROM ref_draft_picks d
            LEFT JOIN career c ON c.player_id = d.gsis_id
            WHERE d.round = ?
        )
        SELECT pick, season, team, player_name, position, college, gsis_id, career_games, career_fantasy_points_ppr
        FROM ranked
        WHERE rn = 1
        ORDER BY pick
        LIMIT ? OFFSET ?
        """,
        [round, limit, offset],
    ).fetchall()
    cols = [d[0] for d in db.description]
    data = [dict(zip(cols, row)) for row in rows]
    return PaginatedResponse(data=data, total=total, limit=limit, offset=offset)


@router.get("/draft", response_model=PaginatedResponse[DraftPick])
def list_draft(
    request: Request,
    season: int | None = None,
    round: int | None = None,
    team: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    filters = [
        ("season = ?", season),
        ("round = ?", round),
        ("team = ?", team),
    ]
    where, params = _build_filter(filters)
    total = db.execute(f"SELECT COUNT(*) FROM ref_draft_picks {where}", params).fetchone()[0]
    rows = db.execute(
        f"SELECT * FROM ref_draft_picks {where} ORDER BY season DESC, round, pick LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    cols = [d[0] for d in db.description]
    data = [DraftPick.model_validate(dict(zip(cols, row))) for row in rows]
    return PaginatedResponse(data=data, total=total, limit=limit, offset=offset)


@router.get("/contracts", response_model=PaginatedResponse[Contract])
def list_contracts(
    request: Request,
    team: str | None = None,
    position: str | None = None,
    year_signed: int | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    filters = [
        ("team = ?", team),
        ("position = ?", position),
        ("year_signed = ?", year_signed),
    ]
    where, params = _build_filter(filters)
    total = db.execute(f"SELECT COUNT(*) FROM ref_contracts {where}", params).fetchone()[0]
    rows = db.execute(
        f"SELECT * FROM ref_contracts {where} ORDER BY year_signed DESC, apy DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    cols = [d[0] for d in db.description]
    data = [Contract.model_validate(dict(zip(cols, row))) for row in rows]
    return PaginatedResponse(data=data, total=total, limit=limit, offset=offset)


@router.get("/trades", response_model=PaginatedResponse[dict[str, Any]])
def list_trades(
    request: Request,
    season: int | None = None,
    team: str | None = None,
    team2: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    """Each trade spans multiple ref_trades rows (one per asset moved); paginate by trade_id."""
    clauses, params = [], []
    if season is not None:
        clauses.append("season = ?")
        params.append(season)
    if team is not None:
        clauses.append("(gave = ? OR received = ?)")
        params += [team, team]
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    if team2 is not None:
        # Trades involving both `team` and `team2`: find trade_ids where each
        # team appears in at least one asset row, then apply the other filters.
        having_params = [team, team, team2, team2]
        trade_id_query = f"""
            SELECT trade_id FROM ref_trades {where}
            GROUP BY trade_id
            HAVING SUM(CASE WHEN gave = ? OR received = ? THEN 1 ELSE 0 END) > 0
               AND SUM(CASE WHEN gave = ? OR received = ? THEN 1 ELSE 0 END) > 0
        """
        total = db.execute(
            f"SELECT COUNT(*) FROM ({trade_id_query})", params + having_params
        ).fetchone()[0]
        trade_ids = [
            r[0] for r in db.execute(
                f"SELECT trade_id FROM ({trade_id_query}) ORDER BY trade_id DESC LIMIT ? OFFSET ?",
                params + having_params + [limit, offset],
            ).fetchall()
        ]
        if not trade_ids:
            return PaginatedResponse(data=[], total=total, limit=limit, offset=offset)

        rows = db.execute(
            f"SELECT * FROM ref_trades WHERE trade_id IN ({','.join('?' * len(trade_ids))}) ORDER BY trade_id DESC, gave",
            trade_ids,
        ).fetchall()
        cols = [d[0] for d in db.description]
        data = [dict(zip(cols, row)) for row in rows]
        return PaginatedResponse(data=data, total=total, limit=limit, offset=offset)

    total = db.execute(f"SELECT COUNT(DISTINCT trade_id) FROM ref_trades {where}", params).fetchone()[0]
    trade_ids = [
        r[0] for r in db.execute(
            f"SELECT DISTINCT trade_id FROM ref_trades {where} ORDER BY trade_id DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    ]
    if not trade_ids:
        return PaginatedResponse(data=[], total=total, limit=limit, offset=offset)

    rows = db.execute(
        f"SELECT * FROM ref_trades WHERE trade_id IN ({','.join('?' * len(trade_ids))}) ORDER BY trade_id DESC, gave",
        trade_ids,
    ).fetchall()
    cols = [d[0] for d in db.description]
    data = [dict(zip(cols, row)) for row in rows]
    return PaginatedResponse(data=data, total=total, limit=limit, offset=offset)
