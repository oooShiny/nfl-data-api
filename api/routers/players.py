import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.deps import _build_filter, get_db
from api.models.responses import PaginatedResponse, Player, PlayerGameStats

router = APIRouter(tags=["players"])


@router.get("/players", response_model=PaginatedResponse[Player])
def list_players(
    request: Request,
    name: str | None = None,
    position: str | None = None,
    team: str | None = None,
    season: int | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    if team is not None:
        # Correlated EXISTS against fact_weekly_rosters
        season_clause = "AND r.season = ?" if season is not None else ""
        season_param = [season] if season is not None else []
        name_clause = "AND p.display_name ILIKE ?" if name is not None else ""
        name_param = [f"%{name}%"] if name is not None else []
        pos_clause = "AND p.position = ?" if position is not None else ""
        pos_param = [position] if position is not None else []

        base = f"""
            FROM dim_players p
            WHERE EXISTS (
                SELECT 1 FROM fact_weekly_rosters r
                WHERE r.gsis_id = p.gsis_id AND r.team = ? {season_clause}
            )
            {name_clause} {pos_clause}
        """
        params = [team] + season_param + name_param + pos_param
        total = db.execute(f"SELECT COUNT(*) {base}", params).fetchone()[0]
        rows = db.execute(
            f"SELECT p.* {base} ORDER BY p.display_name LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    else:
        filters = [
            ("display_name ILIKE ?", f"%{name}%" if name else None),
            ("position = ?", position),
        ]
        where, params = _build_filter(filters)
        total = db.execute(f"SELECT COUNT(*) FROM dim_players {where}", params).fetchone()[0]
        rows = db.execute(
            f"SELECT * FROM dim_players {where} ORDER BY display_name LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()

    cols = [d[0] for d in db.description]
    data = [Player.model_validate(dict(zip(cols, row))) for row in rows]
    return PaginatedResponse(data=data, total=total, limit=limit, offset=offset)


@router.get("/players/{gsis_id}", response_model=Player)
def get_player(
    gsis_id: str,
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    row = db.execute("SELECT * FROM dim_players WHERE gsis_id = ?", [gsis_id]).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Player not found")
    cols = [d[0] for d in db.description]
    return Player.model_validate(dict(zip(cols, row)))


@router.get("/players/{gsis_id}/stats", response_model=PaginatedResponse[PlayerGameStats])
def get_player_stats(
    gsis_id: str,
    season: int | None = None,
    week: int | None = None,
    season_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    filters = [
        ("player_id = ?", gsis_id),
        ("season = ?", season),
        ("week = ?", week),
        ("season_type = ?", season_type),
    ]
    where, params = _build_filter(filters)
    total = db.execute(
        f"SELECT COUNT(*) FROM fact_player_game_stats {where}", params
    ).fetchone()[0]
    rows = db.execute(
        f"SELECT * FROM fact_player_game_stats {where} ORDER BY season DESC, week DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    cols = [d[0] for d in db.description]
    data = [PlayerGameStats.model_validate(dict(zip(cols, row))) for row in rows]
    return PaginatedResponse(data=data, total=total, limit=limit, offset=offset)
