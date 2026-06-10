from typing import Any

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.deps import _build_filter, get_db, list_table
from api.models.responses import Game, PaginatedResponse

router = APIRouter(tags=["games"])


@router.get("/games", response_model=PaginatedResponse[Game])
def list_games(
    request: Request,
    season: int | None = None,
    week: int | None = None,
    team: str | None = None,
    game_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    filters = [
        ("season = ?", season),
        ("week = ?", week),
        ("game_type = ?", game_type),
    ]
    where, params = _build_filter(filters)

    if team is not None:
        connector = "AND" if where else "WHERE"
        where += f" {connector} (home_team = ? OR away_team = ?)"
        params += [team, team]

    total = db.execute(f"SELECT COUNT(*) FROM dim_games {where}", params).fetchone()[0]
    rows = db.execute(
        f"SELECT * FROM dim_games {where} ORDER BY gameday DESC, game_id LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    cols = [d[0] for d in db.description]
    data = [Game.model_validate(dict(zip(cols, row))) for row in rows]
    return PaginatedResponse(data=data, total=total, limit=limit, offset=offset)


@router.get("/games/historical", response_model=PaginatedResponse[dict[str, Any]])
def list_historical_games(
    request: Request,
    season: int | None = None,
    week: int | None = None,
    team: str | None = None,
    game_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    """Pre-1999 game results from Pro-Football-Reference (1970-2022, 2000 missing)."""
    filters = [
        ("season = ?", season),
        ("week = ?", week),
        ("game_type = ?", game_type),
    ]
    where, params = _build_filter(filters)

    if team is not None:
        connector = "AND" if where else "WHERE"
        where += f" {connector} (home_team = ? OR away_team = ?)"
        params += [team, team]

    total = db.execute(f"SELECT COUNT(*) FROM fact_historical_games {where}", params).fetchone()[0]
    rows = db.execute(
        f"SELECT * FROM fact_historical_games {where} ORDER BY gameday DESC, game_id LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    cols = [d[0] for d in db.description]
    data = [dict(zip(cols, row)) for row in rows]
    return PaginatedResponse(data=data, total=total, limit=limit, offset=offset)


@router.get("/games/scoring", response_model=PaginatedResponse[dict[str, Any]])
def list_game_scoring(
    request: Request,
    game_id: str | None = None,
    season: int | None = None,
    team: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    """Scoring-play summaries for historical games (1970-1997)."""
    filters = [
        ("game_id = ?", game_id),
        ("season = ?", season),
        ("scoring_team = ?", team),
    ]
    return list_table(db, "fact_game_scoring", filters, "game_id, play_seq", limit, offset)


@router.get("/games/{game_id}", response_model=Game)
def get_game(
    game_id: str,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    row = db.execute("SELECT * FROM dim_games WHERE game_id = ?", [game_id]).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Game not found")
    cols = [d[0] for d in db.description]
    return Game.model_validate(dict(zip(cols, row)))
