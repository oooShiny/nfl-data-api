import json

import duckdb
from fastapi import APIRouter, Depends, Request

from api.deps import get_db
from pipeline.config import LAST_RUN_COUNTS_FILE

router = APIRouter(tags=["meta"])

GOLD_TABLES = [
    "dim_players", "dim_teams", "dim_games",
    "fact_historical_games", "fact_game_scoring",
    "fact_plays", "fact_pass_plays", "fact_rush_plays", "fact_kick_plays",
    "fact_pbp_participation", "fact_ftn_charting",
    "fact_player_game_stats", "fact_player_season_stats", "fact_weekly_rosters", "fact_rosters",
    "fact_snap_counts", "fact_depth_charts", "fact_injuries",
    "fact_ngs_passing", "fact_ngs_receiving", "fact_ngs_rushing",
    "ref_combine", "ref_contracts", "ref_draft_picks", "ref_trades", "ref_pfr_rosters",
    "ref_team_stats", "ref_qbr_season", "ref_qbr_week",
    "ref_pfr_adv_pass", "ref_pfr_adv_rush", "ref_pfr_adv_rec", "ref_pfr_adv_def",
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
