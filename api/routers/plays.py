from typing import Any

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.deps import _build_filter, get_db
from api.models.responses import PaginatedResponse

router = APIRouter(tags=["plays"])

# Player roles on every play, in both eras: <role>_player_id / <role>_player_name.
PLAY_ROLES = [
    "passer", "rusher", "receiver", "interception", "sack", "kicker", "punter", "returner",
    "tackler_1", "tackler_2", "forced_fumble", "fumble_recovery", "penalty",
]


@router.get("/plays", response_model=PaginatedResponse[dict[str, Any]])
def list_plays(
    request: Request,
    game_id: str | None = None,
    season: int | None = None,
    week: int | None = None,
    season_type: str | None = Query(default=None, description="REG or POST"),
    team: str | None = Query(default=None, description="Either team in the game"),
    posteam: str | None = Query(default=None, description="Team with the ball"),
    play_type: str | None = None,
    player_id: str | None = Query(default=None, description="gsis_id in any player role (passer, rusher, tackler, ...)"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    """Play-by-play for every season with it: 1999 on from nflverse, before 1999
    from Pro-Football-Reference (being back-filled season by season).

    Every row has the same columns: down, distance, field position, clock, score
    before and after, play type, yards, the description, and each player role
    as <role>_player_id / <role>_player_name. `source` says where the play came
    from. Before 1999 there is no win probability, air yards or series data,
    ep/epa are PFR's expected points (not nflfastR's), the team with the ball
    is inferred, and the clock is often missing. Team codes are today's from
    1999 and those of the time before (as in /v1/games).
    """
    if game_id is None and season is None and team is None and player_id is None:
        raise HTTPException(status_code=422, detail="One of 'game_id', 'season', 'team' or 'player_id' is required.")
    filters = [
        ("game_id = ?", game_id),
        ("season = ?", season),
        ("week = ?", week),
        ("season_type = ?", season_type),
        ("posteam = ?", posteam),
        ("play_type = ?", play_type),
    ]
    where, params = _build_filter(filters)
    if team is not None:
        where += f" {'AND' if where else 'WHERE'} (home_team = ? OR away_team = ?)"
        params += [team, team]
    if player_id is not None:
        id_cols = ", ".join(f"{r}_player_id" for r in PLAY_ROLES)
        where += f" {'AND' if where else 'WHERE'} ? IN ({id_cols})"
        params.append(player_id)

    total = db.execute(f"SELECT COUNT(*) FROM v_plays {where}", params).fetchone()[0]
    rows = db.execute(
        f"SELECT * FROM v_plays {where} ORDER BY season, game_id, play_id LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    cols = [d[0] for d in db.description]
    return PaginatedResponse(data=[dict(zip(cols, r)) for r in rows], total=total, limit=limit, offset=offset)
