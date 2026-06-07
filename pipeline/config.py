from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"
BRONZE_DIR = DATA_DIR / "bronze"
SILVER_DIR = DATA_DIR / "silver"
GOLD_DB = DATA_DIR / "nfl.duckdb"

NFLVERSE_REPO = "nflverse/nflverse-data"
NFLVERSE_RELEASES_URL = "https://github.com/nflverse/nflverse-data/releases/download"

# All release tags in nflverse-data, ordered from smallest to largest
RELEASE_TAGS = [
    "teams",
    "players",
    "players_components",
    "combine",
    "draft_picks",
    "contracts",
    "officials",
    "trades",
    "schedules",
    "rosters",
    "weekly_rosters",
    "depth_charts",
    "snap_counts",
    "injuries",
    "player_stats",
    "pbp_participation",
    "nextgen_stats",
    "espn_data",
    "pfr_advstats",
    "ftn_charting",
    "stats_player",
    "stats_team",
    "misc",
    "pbp",
]

# Tags that are expensive (large per-season files) — download last
LARGE_TAGS = {"pbp", "stats_player", "stats_team"}
