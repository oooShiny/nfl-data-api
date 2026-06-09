import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.deps import _build_filter, get_db
from api.models.responses import PaginatedResponse, Play

router = APIRouter(tags=["plays"])


@router.get("/plays", response_model=PaginatedResponse[Play])
def list_plays(
    request: Request,
    game_id: str | None = None,
    season: int | None = None,
    week: int | None = None,
    play_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    if game_id is None and season is None:
        raise HTTPException(
            status_code=422,
            detail="Either 'game_id' or 'season' is required.",
        )

    filters = [
        ("game_id = ?", game_id),
        ("season = ?", season),
        ("week = ?", week),
        ("play_type = ?", play_type),
    ]
    where, params = _build_filter(filters)

    total = db.execute(f"SELECT COUNT(*) FROM fact_plays {where}", params).fetchone()[0]
    rows = db.execute(
        f"SELECT * FROM fact_plays {where} ORDER BY game_id, quarter, game_seconds_remaining DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    cols = [d[0] for d in db.description]
    data = [Play.model_validate(dict(zip(cols, row))) for row in rows]
    return PaginatedResponse(data=data, total=total, limit=limit, offset=offset)
