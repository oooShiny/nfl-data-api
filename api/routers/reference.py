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
