from typing import Any

import duckdb
from fastapi import APIRouter, Depends, Query, Request

from api.deps import get_db, list_table
from api.models.responses import PaginatedResponse

router = APIRouter(tags=["advanced"])

# Pre-1999 season stats are derived from PFR play-by-play
# (fact_historical_*_season_stats, source = 'pfr_pbp'); 1999+ come from nflverse.
HISTORICAL_LAST_SEASON = 1998


def _season_source(nflverse: str, historical: str, season: int | None) -> str:
    """Table (or union of both) to read for a season filter."""
    if season is None:
        return f"(SELECT * FROM {nflverse} UNION ALL BY NAME SELECT * FROM {historical})"
    return historical if season <= HISTORICAL_LAST_SEASON else nflverse


@router.get("/stats/team", response_model=PaginatedResponse[dict[str, Any]])
def team_stats(
    request: Request,
    season: int | None = None,
    team: str | None = None,
    season_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    """Team season totals. 1999+ from nflverse; 1970-1998 derived from PFR
    play-by-play (source = 'pfr_pbp': passing, rushing and sack totals only,
    historical team codes)."""
    filters = [
        ("season = ?", season),
        ("team = ?", team),
        ("season_type = ?", season_type),
    ]
    table = _season_source("ref_team_stats", "fact_historical_team_season_stats", season)
    return list_table(db, table, filters, "season DESC, team", limit, offset)


@router.get("/stats/season", response_model=PaginatedResponse[dict[str, Any]])
def player_season_stats(
    request: Request,
    player_id: str | None = None,
    season: int | None = None,
    season_type: str | None = None,
    position: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    """Player season stats. 1999+ from nflverse; 1970-1998 derived from PFR
    play-by-play (source = 'pfr_pbp': passing, rushing and receiving totals,
    REG and POST, one row per player and team)."""
    filters = [
        ("player_id = ?", player_id),
        ("season = ?", season),
        ("season_type = ?", season_type),
        ("position = ?", position),
    ]
    table = _season_source("fact_player_season_stats", "fact_historical_player_season_stats", season)
    order = ("season DESC, fantasy_points_ppr DESC NULLS LAST, "
             "passing_yards + rushing_yards + receiving_yards DESC")
    if season is not None and season <= HISTORICAL_LAST_SEASON:
        order = "passing_yards + rushing_yards + receiving_yards DESC"
    return list_table(db, table, filters, order, limit, offset)


@router.get("/stats/ngs/passing", response_model=PaginatedResponse[dict[str, Any]])
def ngs_passing(
    request: Request,
    season: int | None = None,
    week: int | None = None,
    season_type: str | None = None,
    player_gsis_id: str | None = None,
    team_abbr: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    filters = [
        ("season = ?", season),
        ("week = ?", week),
        ("season_type = ?", season_type),
        ("player_gsis_id = ?", player_gsis_id),
        ("team_abbr = ?", team_abbr),
    ]
    return list_table(db, "fact_ngs_passing", filters, "season DESC, week DESC", limit, offset)


@router.get("/stats/ngs/rushing", response_model=PaginatedResponse[dict[str, Any]])
def ngs_rushing(
    request: Request,
    season: int | None = None,
    week: int | None = None,
    season_type: str | None = None,
    player_gsis_id: str | None = None,
    team_abbr: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    filters = [
        ("season = ?", season),
        ("week = ?", week),
        ("season_type = ?", season_type),
        ("player_gsis_id = ?", player_gsis_id),
        ("team_abbr = ?", team_abbr),
    ]
    return list_table(db, "fact_ngs_rushing", filters, "season DESC, week DESC", limit, offset)


@router.get("/stats/ngs/receiving", response_model=PaginatedResponse[dict[str, Any]])
def ngs_receiving(
    request: Request,
    season: int | None = None,
    week: int | None = None,
    season_type: str | None = None,
    player_gsis_id: str | None = None,
    team_abbr: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    filters = [
        ("season = ?", season),
        ("week = ?", week),
        ("season_type = ?", season_type),
        ("player_gsis_id = ?", player_gsis_id),
        ("team_abbr = ?", team_abbr),
    ]
    return list_table(db, "fact_ngs_receiving", filters, "season DESC, week DESC", limit, offset)


@router.get("/stats/advanced/passing", response_model=PaginatedResponse[dict[str, Any]])
def pfr_advanced_passing(
    request: Request,
    season: int | None = None,
    pfr_id: str | None = None,
    team: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    filters = [
        ("season = ?", season),
        ("pfr_id = ?", pfr_id),
        ("team = ?", team),
    ]
    return list_table(db, "ref_pfr_adv_pass", filters, "season DESC, pass_attempts DESC NULLS LAST", limit, offset)


@router.get("/stats/advanced/rushing", response_model=PaginatedResponse[dict[str, Any]])
def pfr_advanced_rushing(
    request: Request,
    season: int | None = None,
    pfr_id: str | None = None,
    team: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    filters = [
        ("season = ?", season),
        ("pfr_id = ?", pfr_id),
        ("team = ?", team),
    ]
    return list_table(db, "ref_pfr_adv_rush", filters, "season DESC, yards DESC NULLS LAST", limit, offset)


@router.get("/stats/advanced/receiving", response_model=PaginatedResponse[dict[str, Any]])
def pfr_advanced_receiving(
    request: Request,
    season: int | None = None,
    pfr_id: str | None = None,
    team: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    filters = [
        ("season = ?", season),
        ("pfr_id = ?", pfr_id),
        ("team = ?", team),
    ]
    return list_table(db, "ref_pfr_adv_rec", filters, "season DESC, yards DESC NULLS LAST", limit, offset)


@router.get("/stats/advanced/defense", response_model=PaginatedResponse[dict[str, Any]])
def pfr_advanced_defense(
    request: Request,
    season: int | None = None,
    pfr_id: str | None = None,
    team: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    filters = [
        ("season = ?", season),
        ("pfr_id = ?", pfr_id),
        ("team = ?", team),
    ]
    return list_table(db, "ref_pfr_adv_def", filters, "season DESC, combined_tackles DESC NULLS LAST", limit, offset)


@router.get("/qbr/season", response_model=PaginatedResponse[dict[str, Any]])
def qbr_season(
    request: Request,
    season: int | None = None,
    season_type: str | None = None,
    player_id: str | None = None,
    team: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    filters = [
        ("season = ?", season),
        ("season_type = ?", season_type),
        ("player_id = ?", player_id),
        ("team = ?", team),
    ]
    return list_table(db, "ref_qbr_season", filters, "season DESC, qbr_total DESC NULLS LAST", limit, offset)


@router.get("/qbr/week", response_model=PaginatedResponse[dict[str, Any]])
def qbr_week(
    request: Request,
    season: int | None = None,
    season_type: str | None = None,
    week: int | None = None,
    player_id: str | None = None,
    team: str | None = None,
    game_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    filters = [
        ("season = ?", season),
        ("season_type = ?", season_type),
        ("week_num = ?", week),
        ("player_id = ?", player_id),
        ("team = ?", team),
        ("game_id = ?", game_id),
    ]
    return list_table(db, "ref_qbr_week", filters, "season DESC, week_num DESC", limit, offset)


@router.get("/rosters/pfr", response_model=PaginatedResponse[dict[str, Any]])
def pfr_rosters(
    request: Request,
    season: int | None = None,
    team: str | None = None,
    position: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    filters = [
        ("season = ?", season),
        ("nfl_team = ?", team),
        ("position = ?", position),
    ]
    return list_table(db, "ref_pfr_rosters", filters, "season DESC, player", limit, offset)


@router.get("/charting", response_model=PaginatedResponse[dict[str, Any]])
def ftn_charting(
    request: Request,
    game_id: str | None = None,
    season: int | None = None,
    week: int | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    filters = [
        ("game_id = ?", game_id),
        ("season = ?", season),
        ("week = ?", week),
    ]
    return list_table(db, "fact_ftn_charting", filters, "game_id, play_id", limit, offset)


@router.get("/participation", response_model=PaginatedResponse[dict[str, Any]])
def pbp_participation(
    request: Request,
    game_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    filters = [
        ("game_id = ?", game_id),
    ]
    return list_table(db, "fact_pbp_participation", filters, "game_id, play_id", limit, offset)
