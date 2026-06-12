import duckdb
from fastapi import APIRouter, Depends, Query, Request

from api.deps import _build_filter, get_db
from api.models.responses import PaginatedResponse, PlayerGameStats

router = APIRouter(tags=["stats"])


def _default_season(db: duckdb.DuckDBPyConnection) -> int:
    return db.execute(
        "SELECT MAX(season) FROM fact_player_game_stats"
    ).fetchone()[0]


def _stats_query(
    db: duckdb.DuckDBPyConnection,
    order_col: str,
    season: int | None,
    week: int | None,
    season_type: str | None,
    team: str | None,
    limit: int,
    offset: int,
) -> PaginatedResponse[PlayerGameStats]:
    resolved_season = season if season is not None else _default_season(db)
    filters = [
        ("season = ?", resolved_season),
        ("week = ?", week),
        ("season_type = ?", season_type),
        ("recent_team = ?", team),
    ]
    where, params = _build_filter(filters)
    total = db.execute(
        f"SELECT COUNT(*) FROM fact_player_game_stats {where}", params
    ).fetchone()[0]
    rows = db.execute(
        f"SELECT * FROM fact_player_game_stats {where} ORDER BY {order_col} DESC NULLS LAST LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    cols = [d[0] for d in db.description]
    data = [PlayerGameStats.model_validate(dict(zip(cols, row))) for row in rows]
    return PaginatedResponse(data=data, total=total, limit=limit, offset=offset)


@router.get("/stats/passing", response_model=PaginatedResponse[PlayerGameStats])
def passing_stats(
    request: Request,
    season: int | None = None,
    week: int | None = None,
    season_type: str | None = None,
    team: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    return _stats_query(db, "passing_yards", season, week, season_type, team, limit, offset)


@router.get("/stats/rushing", response_model=PaginatedResponse[PlayerGameStats])
def rushing_stats(
    request: Request,
    season: int | None = None,
    week: int | None = None,
    season_type: str | None = None,
    team: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    return _stats_query(db, "rushing_yards", season, week, season_type, team, limit, offset)


@router.get("/stats/receiving", response_model=PaginatedResponse[PlayerGameStats])
def receiving_stats(
    request: Request,
    season: int | None = None,
    week: int | None = None,
    season_type: str | None = None,
    team: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    return _stats_query(db, "receiving_yards", season, week, season_type, team, limit, offset)
