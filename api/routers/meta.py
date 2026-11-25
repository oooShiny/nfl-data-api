import json

import duckdb
from fastapi import APIRouter, Depends, Request

from api.deps import get_db
from pipeline.config import LAST_RUN_COUNTS_FILE

router = APIRouter(tags=["meta"])

GOLD_TABLES = [
    "dim_players", "dim_teams", "dim_games",
    "fact_game_scoring", "fact_historical_plays",
    "fact_historical_player_season_stats", "fact_historical_team_season_stats",
    "fact_plays", "fact_pass_plays", "fact_rush_plays", "fact_kick_plays",
    "fact_pbp_participation", "fact_ftn_charting",
    "fact_player_game_stats", "fact_player_season_stats", "fact_weekly_rosters", "fact_rosters",
    "fact_snap_counts", "fact_depth_charts", "fact_injuries",
    "fact_ngs_passing", "fact_ngs_receiving", "fact_ngs_rushing",
    "ref_combine", "ref_contracts", "ref_draft_picks", "ref_trades", "ref_pfr_rosters",
    "ref_team_stats", "ref_qbr_season", "ref_qbr_week",
    "ref_pfr_adv_pass", "ref_pfr_adv_rush", "ref_pfr_adv_rec", "ref_pfr_adv_def",
    "ref_team_elo", "ref_officials",
    "name_resolution",
]


@router.get("/meta")
def meta(db: duckdb.DuckDBPyConnection = Depends(get_db)):
    seasons = [r[0] for r in db.execute(
        "SELECT DISTINCT season FROM dim_games WHERE season IS NOT NULL ORDER BY season"
    ).fetchall()]
    teams = [
        {"abbr": r[0], "name": r[1], "conf": r[2], "division": r[3]}
        for r in db.execute(
            "SELECT team_abbr, team_name, team_conf, team_division FROM dim_teams ORDER BY team_abbr"
        ).fetchall()
    ]
    return {"seasons": seasons, "teams": teams}


@router.get("/health")
def health(db: duckdb.DuckDBPyConnection = Depends(get_db)):
    row_counts: dict[str, int | None] = {}
    for t in GOLD_TABLES:
        try:
            row_counts[t] = db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except Exception:
            row_counts[t] = None

    last_refresh = None
    if LAST_RUN_COUNTS_FILE.exists():
        try:
            last_refresh = json.loads(LAST_RUN_COUNTS_FILE.read_text()).get("run_at")
        except Exception:
            pass

    return {"status": "ok", "row_counts": row_counts, "last_refresh": last_refresh}


# Datasets shown on the coverage map, grouped like the Data Coverage page.
# Each query returns (season, rows) pairs.
COVERAGE_ROWS: list[tuple[str, str, str]] = [
    ("Games & Schedules", "Game results",
     "SELECT season, count(*) FROM dim_games WHERE result IS NOT NULL GROUP BY 1"),
    ("Games & Schedules", "Weather & betting lines",
     "SELECT season, count(*) FROM dim_games WHERE result IS NOT NULL AND spread_line IS NOT NULL GROUP BY 1"),
    ("Games & Schedules", "Scoring plays",
     "SELECT season, count(*) FROM fact_game_scoring GROUP BY 1"),
    ("Games & Schedules", "Officiating crews",
     "SELECT season, count(*) FROM ref_officials GROUP BY 1"),
    ("Play-by-Play", "Play-by-play (EPA/WPA)",
     "SELECT season, count(*) FROM fact_plays GROUP BY 1"),
    ("Play-by-Play", "Historical play-by-play",
     "SELECT season, count(*) FROM fact_historical_plays GROUP BY 1"),
    ("Play-by-Play", "Personnel & formations",
     "SELECT TRY_CAST(split_part(game_id, '_', 1) AS INTEGER), count(*) FROM fact_pbp_participation GROUP BY 1"),
    ("Play-by-Play", "FTN charting",
     "SELECT season, count(*) FROM fact_ftn_charting GROUP BY 1"),
    ("Players & Stats", "Game stat lines",
     "SELECT season, count(*) FROM fact_player_game_stats GROUP BY 1"),
    # Before 1999: derived from the PFR play-by-play (fact_historical_*_season_stats).
    ("Players & Stats", "Season stat totals",
     """SELECT season, count(*) FROM (
            SELECT season FROM fact_player_season_stats WHERE season_type = 'REG' UNION ALL
            SELECT season FROM fact_historical_player_season_stats WHERE season_type = 'REG') GROUP BY 1"""),
    ("Players & Stats", "Team season totals",
     """SELECT season, count(*) FROM (
            SELECT season FROM ref_team_stats WHERE season_type = 'REG' UNION ALL
            SELECT season FROM fact_historical_team_season_stats WHERE season_type = 'REG') GROUP BY 1"""),
    ("Players & Stats", "Next Gen Stats",
     """SELECT season, count(*) FROM (SELECT season FROM fact_ngs_passing UNION ALL
        SELECT season FROM fact_ngs_receiving UNION ALL SELECT season FROM fact_ngs_rushing) GROUP BY 1"""),
    ("Players & Stats", "PFR advanced stats",
     """SELECT season, count(*) FROM (SELECT season FROM ref_pfr_adv_pass UNION ALL SELECT season FROM ref_pfr_adv_rush
        UNION ALL SELECT season FROM ref_pfr_adv_rec UNION ALL SELECT season FROM ref_pfr_adv_def) GROUP BY 1"""),
    ("Players & Stats", "ESPN QBR",
     "SELECT season, count(*) FROM ref_qbr_week GROUP BY 1"),
    ("Rosters & Personnel", "Season rosters",
     "SELECT season, count(*) FROM fact_rosters GROUP BY 1"),
    ("Rosters & Personnel", "Weekly rosters",
     "SELECT season, count(*) FROM fact_weekly_rosters GROUP BY 1"),
    ("Rosters & Personnel", "Depth charts",
     "SELECT season, count(*) FROM fact_depth_charts GROUP BY 1"),
    ("Rosters & Personnel", "Snap counts",
     "SELECT season, count(*) FROM fact_snap_counts GROUP BY 1"),
    ("Rosters & Personnel", "Injury reports",
     "SELECT season, count(*) FROM fact_injuries GROUP BY 1"),
    ("Draft, Combine, Contracts & Trades", "Draft picks",
     "SELECT season, count(*) FROM ref_draft_picks GROUP BY 1"),
    ("Draft, Combine, Contracts & Trades", "Combine results",
     "SELECT season, count(*) FROM ref_combine GROUP BY 1"),
    ("Draft, Combine, Contracts & Trades", "Contracts",
     "SELECT year_signed, count(*) FROM ref_contracts WHERE year_signed > 0 GROUP BY 1"),
    ("Draft, Combine, Contracts & Trades", "Trades",
     "SELECT season, count(*) FROM ref_trades GROUP BY 1"),
    ("Teams & Ratings", "Elo ratings (538)",
     "SELECT season, count(*) FROM ref_team_elo GROUP BY 1"),
]

# Computed once per database connection; /v1/admin/refresh swaps the connection.
_coverage_cache: dict[int, dict] = {}


@router.get("/coverage")
def coverage(db: duckdb.DuckDBPyConnection = Depends(get_db)):
    """Rows per season for each dataset, for the coverage map on the website."""
    cached = _coverage_cache.get(id(db))
    if cached is not None:
        return cached

    cur = db.cursor()
    try:
        current_season, in_progress = cur.execute("""
            SELECT season, bool_or(result IS NULL)
            FROM dim_games WHERE season = (SELECT max(season) FROM dim_games WHERE result IS NOT NULL)
            GROUP BY season""").fetchone()
        games = {int(s): int(n) for s, n in cur.execute(
            "SELECT season, count(*) FROM dim_games WHERE result IS NOT NULL GROUP BY 1").fetchall()}
        groups: dict[str, list[dict]] = {}
        for group, label, sql in COVERAGE_ROWS:
            try:
                seasons = {int(s): int(n) for s, n in cur.execute(sql).fetchall() if s is not None and s > 0}
            except duckdb.Error:
                seasons = {}
            groups.setdefault(group, []).append({"label": label, "seasons": seasons})
    finally:
        cur.close()

    all_seasons = [s for rows in groups.values() for r in rows for s in r["seasons"]]
    result = {
        "season_min": min(all_seasons, default=None),
        "season_max": max(all_seasons, default=None),
        "current_season": current_season,
        "current_season_in_progress": bool(in_progress),
        "games_per_season": games,
        "groups": [{"name": name, "rows": rows} for name, rows in groups.items()],
    }
    _coverage_cache.clear()
    _coverage_cache[id(db)] = result
    return result
