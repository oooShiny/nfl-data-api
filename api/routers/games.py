from typing import Any

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.deps import _build_filter, get_db, list_table
from api.models.responses import Game, PaginatedResponse
from pipeline.historical_players import NAME_COLUMNS as HISTORICAL_NAME_COLUMNS

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


@router.get("/games/scoring", response_model=PaginatedResponse[dict[str, Any]])
def list_game_scoring(
    request: Request,
    game_id: str | None = None,
    season: int | None = None,
    team: str | None = None,
    scoring_type: str | None = Query(default=None, description="touchdown, field_goal, safety, defensive_two_point"),
    scoring_method: str | None = Query(default=None, description="e.g. pass, rush, interception_return, punt_return"),
    scorer_id: str | None = Query(default=None, description="gsis_id (2007+ rows derived from nflverse only)"),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    """Scoring-play summaries, 1970-present (PFR through part of 2007, then derived from nflverse play-by-play).

    Every row has a PFR-style description plus structured fields (scoring type
    and method, yards, scorer, passer, and the try after a touchdown).
    """
    filters = [
        ("game_id = ?", game_id),
        ("season = ?", season),
        ("scoring_team = ?", team),
        ("scoring_type = ?", scoring_type),
        ("scoring_method = ?", scoring_method),
        ("scorer_id = ?", scorer_id),
    ]
    return list_table(db, "fact_game_scoring", filters, "game_id, play_seq", limit, offset)


@router.get("/games/historical-plays", response_model=PaginatedResponse[dict[str, Any]])
def list_historical_plays(
    request: Request,
    game_id: str | None = None,
    season: int | None = None,
    week: int | None = None,
    team: str | None = None,
    play_type: str | None = None,
    posteam: str | None = Query(default=None, description="Team with the ball (inferred)"),
    player_id: str | None = Query(default=None, description="gsis_id in any player role (passer, rusher, tackler, ...)"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    """Full play-by-play for pre-1999 games, scraped from Pro-Football-Reference.

    Descriptions plus parsed play_type, yards, touchdowns and player names
    with gsis_ids (*_id, matched through rosters), the team with the ball
    (posteam, inferred from PFR's expected points, scores and field position)
    and drive numbers. No nflfastR EPA; see /v1/plays for 1999+.
    """
    if game_id is None and season is None:
        raise HTTPException(status_code=422, detail="Either 'game_id' or 'season' is required.")
    filters = [
        ("game_id = ?", game_id),
        ("season = ?", season),
        ("week = ?", week),
        ("play_type = ?", play_type),
        ("posteam = ?", posteam),
    ]
    where, params = _build_filter(filters)
    if team is not None:
        where += f" {'AND' if where else 'WHERE'} (home_team = ? OR away_team = ?)"
        params += [team, team]
    if player_id is not None:
        id_cols = ", ".join(f"{c}_id" for c in HISTORICAL_NAME_COLUMNS)
        where += f" {'AND' if where else 'WHERE'} ? IN ({id_cols})"
        params.append(player_id)

    total = db.execute(f"SELECT COUNT(*) FROM fact_historical_plays {where}", params).fetchone()[0]
    rows = db.execute(
        f"SELECT * FROM fact_historical_plays {where} ORDER BY game_id, play_seq LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    cols = [d[0] for d in db.description]
    return PaginatedResponse(data=[dict(zip(cols, r)) for r in rows], total=total, limit=limit, offset=offset)


@router.get("/games/head-to-head", response_model=dict[str, Any])
def head_to_head(
    request: Request,
    team1: str,
    team2: str,
    season: int | None = None,
    game_type: str | None = None,
    top_n: int = Query(default=5, ge=1, le=20),
    db: duckdb.DuckDBPyConnection = Depends(get_db),
):
    """Matchup history between two teams: results, biggest wins, and top player performances."""
    if team1 == team2:
        raise HTTPException(status_code=400, detail="team1 and team2 must be different")

    filters = [
        ("season = ?", season),
        ("game_type = ?", game_type),
    ]
    extra_where, extra_params = _build_filter(filters)
    connector = "AND" if extra_where else "WHERE"

    games = db.execute(
        f"""
        SELECT game_id, season, week, game_type, gameday, home_team, away_team, home_score, away_score
        FROM dim_games
        {extra_where}
        {connector} ((home_team = ? AND away_team = ?) OR (home_team = ? AND away_team = ?))
        ORDER BY gameday DESC
        """,
        extra_params + [team1, team2, team2, team1],
    ).fetchall()
    cols = [d[0] for d in db.description]
    games = [dict(zip(cols, row)) for row in games]

    record = {team1: {"wins": 0, "losses": 0, "ties": 0}, team2: {"wins": 0, "losses": 0, "ties": 0}}
    home_record = {team1: {"wins": 0, "losses": 0, "ties": 0}, team2: {"wins": 0, "losses": 0, "ties": 0}}
    biggest_win = {team1: None, team2: None}

    for g in games:
        home, away = g["home_team"], g["away_team"]
        hs, as_ = g["home_score"], g["away_score"]
        if hs is None or as_ is None:
            continue
        if hs == as_:
            record[team1]["ties"] += 1
            record[team2]["ties"] += 1
            home_record[home]["ties"] += 1
            continue

        winner, loser, margin = (home, away, hs - as_) if hs > as_ else (away, home, as_ - hs)
        record[winner]["wins"] += 1
        record[loser]["losses"] += 1
        if home == winner:
            home_record[home]["wins"] += 1
        else:
            home_record[home]["losses"] += 1

        current = biggest_win[winner]
        if current is None or margin > current["margin"]:
            biggest_win[winner] = {
                "game_id": g["game_id"],
                "season": g["season"],
                "week": g["week"],
                "gameday": g["gameday"],
                "margin": margin,
                "score": f"{hs}-{as_}" if home == winner else f"{as_}-{hs}",
                "opponent": loser,
            }

    game_ids = [g["game_id"] for g in games]
    top_performances: dict[str, list] = {"passing": [], "rushing": [], "receiving": []}
    career_totals: dict[str, list] = {"passing": [], "rushing": [], "receiving": []}

    if game_ids:
        placeholders = ",".join("?" * len(game_ids))
        stat_cols = {
            "passing": ("passing_yards", "passing_tds"),
            "rushing": ("rushing_yards", "rushing_tds"),
            "receiving": ("receiving_yards", "receiving_tds"),
        }
        for kind, (yards_col, tds_col) in stat_cols.items():
            rows = db.execute(
                f"""
                SELECT player_id, player_name, recent_team, game_id, season, week, {yards_col}, {tds_col}
                FROM fact_player_game_stats
                WHERE game_id IN ({placeholders}) AND recent_team IN (?, ?)
                ORDER BY {yards_col} DESC NULLS LAST
                LIMIT ?
                """,
                game_ids + [team1, team2, top_n],
            ).fetchall()
            stat_cols_names = [d[0] for d in db.description]
            top_performances[kind] = [dict(zip(stat_cols_names, row)) for row in rows]

            rows = db.execute(
                f"""
                SELECT player_id, player_name, recent_team,
                       SUM({yards_col}) AS {yards_col}, SUM({tds_col}) AS {tds_col},
                       COUNT(*) AS games
                FROM fact_player_game_stats
                WHERE game_id IN ({placeholders}) AND recent_team IN (?, ?)
                GROUP BY player_id, player_name, recent_team
                ORDER BY {yards_col} DESC NULLS LAST
                LIMIT ?
                """,
                game_ids + [team1, team2, top_n],
            ).fetchall()
            career_cols_names = [d[0] for d in db.description]
            career_totals[kind] = [dict(zip(career_cols_names, row)) for row in rows]

    return {
        "team1": team1,
        "team2": team2,
        "total_games": len(games),
        "record": record,
        "home_record": home_record,
        "biggest_win": biggest_win,
        "games": games,
        "top_performances": top_performances,
        "career_totals": career_totals,
    }


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
