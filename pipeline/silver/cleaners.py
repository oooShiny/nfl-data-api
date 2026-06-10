"""Silver layer: clean and normalize raw bronze parquet files."""

import json
from pathlib import Path

import polars as pl

from pipeline.config import BRONZE_DIR, SILVER_DIR

_TEAM_MAP: dict[str, str] | None = None
_MAPPINGS_DIR = Path(__file__).parent.parent / "mappings"


def _team_map() -> dict[str, str]:
    global _TEAM_MAP
    if _TEAM_MAP is None:
        raw = json.loads((_MAPPINGS_DIR / "team_abbr.json").read_text())
        _TEAM_MAP = {k: v for k, v in raw.items() if not k.startswith("_")}
    return _TEAM_MAP


# ── Common transformations ──────────────────────────────────────────────────

def normalize_team_abbrs(df: pl.DataFrame, cols: list[str]) -> pl.DataFrame:
    mapping = _team_map()
    for col in cols:
        if col in df.columns:
            df = df.with_columns(
                pl.col(col).replace(mapping, default=pl.col(col)).alias(col)
            )
    return df


def cast_bool_cols(df: pl.DataFrame) -> pl.DataFrame:
    """Convert 0/1 integer columns that are semantically boolean."""
    bool_col_names = {c for c in df.columns if c.startswith("is_") or c.startswith("has_")}
    for col in bool_col_names:
        if df[col].dtype in (pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.UInt8):
            df = df.with_columns(pl.col(col).cast(pl.Boolean))
    return df


def drop_all_null_cols(df: pl.DataFrame) -> pl.DataFrame:
    """Drop columns where every single value is null."""
    null_counts = df.null_count()
    all_null = [c for c in df.columns if null_counts[c][0] == len(df)]
    if all_null:
        df = df.drop(all_null)
    return df


def normalize_nulls(df: pl.DataFrame) -> pl.DataFrame:
    """Replace empty-string sentinel nulls with actual nulls in string columns."""
    str_cols = [c for c, t in zip(df.columns, df.dtypes) if t == pl.Utf8 or t == pl.String]
    if str_cols:
        df = df.with_columns([
            pl.when(pl.col(c).str.strip_chars() == "").then(None).otherwise(pl.col(c)).alias(c)
            for c in str_cols
        ])
    return df


def base_clean(df: pl.DataFrame, team_cols: list[str] | None = None) -> pl.DataFrame:
    df = normalize_nulls(df)
    df = drop_all_null_cols(df)
    df = cast_bool_cols(df)
    if team_cols:
        df = normalize_team_abbrs(df, team_cols)
    return df


# ── Per-dataset cleaners ────────────────────────────────────────────────────

TEAM_COLS_BY_DATASET = {
    "schedules": ["home_team", "away_team"],
    "rosters": ["team"],
    "weekly_rosters": ["team"],
    "depth_charts": ["club_code"],
    "snap_counts": ["team"],
    "injuries": ["team"],
    "player_stats": ["recent_team", "opponent_team"],
    "pbp_participation": ["offense_team", "defense_team"],
    "stats_player": ["team"],
    "stats_team": ["team"],
    "ftn_charting": ["nflverse_game_id"],  # no direct team col in charting
    "pbp": [
        "home_team", "away_team", "posteam", "defteam",
        "side_of_field", "penalty_team", "td_team",
        "forced_fumble_player_1_team", "forced_fumble_player_2_team",
        "fumbled_1_team", "fumbled_2_team",
        "blocked_player_team", "field_goal_attempt_team",
    ],
    "historical_gamelogs": ["tm_alias", "opp_alias"],
}


def clean_dataset(tag: str, source: Path) -> pl.DataFrame:
    df = pl.read_parquet(source)
    team_cols = TEAM_COLS_BY_DATASET.get(tag)
    df = base_clean(df, team_cols=team_cols)
    cleaner = _SPECIFIC_CLEANERS.get(tag)
    if cleaner:
        df = cleaner(df)
    return df


def _clean_schedules(df: pl.DataFrame) -> pl.DataFrame:
    for col in ("gameday", "gametime"):
        if col in df.columns and df[col].dtype == pl.Utf8:
            df = df.with_columns(pl.col(col).str.to_date(format="%Y-%m-%d", strict=False).alias(col))
    return df


def _clean_players(df: pl.DataFrame) -> pl.DataFrame:
    for col in ("birth_date", "rookie_year"):
        if col in df.columns and df[col].dtype == pl.Utf8:
            df = df.with_columns(pl.col(col).str.to_date(strict=False).alias(col))
    return df


def _clean_rosters(df: pl.DataFrame) -> pl.DataFrame:
    if "season" in df.columns:
        df = df.with_columns(pl.col("season").cast(pl.Int16))
    return df


def _clean_pbp(df: pl.DataFrame) -> pl.DataFrame:
    if "game_date" in df.columns and df["game_date"].dtype == pl.Utf8:
        df = df.with_columns(pl.col("game_date").str.to_date(strict=False).alias("game_date"))
    return df


# Number of regular-season weeks, used to split REG from playoff weeks in the
# historical (1970+) gamelogs, which only carry a single "week" number. The
# playoffs always run 3 rounds (DIV/CON/SB) through 1977 and 4 rounds
# (WC/DIV/CON/SB) from 1978 on, so reg-season length = max_week - num_rounds.
def _regular_season_weeks(season: int, max_week: int) -> int:
    return max_week - (3 if season <= 1977 else 4)


def _clean_historical_gamelogs(df: pl.DataFrame) -> pl.DataFrame:
    df = df.with_columns(pl.col("event_date").str.to_date(strict=False).alias("gameday"))

    df = df.with_columns([
        pl.when(pl.col("tm_location") == "H").then(pl.col("tm_alias")).otherwise(pl.col("opp_alias")).alias("home_team"),
        pl.when(pl.col("tm_location") == "H").then(pl.col("opp_alias")).otherwise(pl.col("tm_alias")).alias("away_team"),
        pl.when(pl.col("tm_location") == "H").then(pl.col("tm_score")).otherwise(pl.col("opp_score")).alias("home_score"),
        pl.when(pl.col("tm_location") == "H").then(pl.col("opp_score")).otherwise(pl.col("tm_score")).alias("away_score"),
    ])

    season = int(df["season"][0])

    # The 1993 source data mislabels the Wild Card round as week 18 (shared
    # with the regular-season finale) and shifts the remaining playoff rounds
    # down by one. Remap so 1993 matches every other 1990-2020 season.
    if season == 1993:
        df = df.with_columns(
            pl.when((pl.col("week") == 18) & (pl.col("event_date") >= "1994-01-08"))
            .then(pl.lit(19))
            .when(pl.col("week") >= 19)
            .then(pl.col("week") + 1)
            .otherwise(pl.col("week"))
            .alias("week")
        )

    max_week = int(df["week"].max())
    reg_weeks = _regular_season_weeks(season, max_week)
    playoff_labels = {offset: label for offset, label in enumerate(["SB", "CON", "DIV", "WC"])}

    df = df.with_columns(
        pl.when(pl.col("week") <= reg_weeks)
        .then(pl.lit("REG"))
        .otherwise((pl.lit(max_week) - pl.col("week")).replace(playoff_labels, default=pl.lit("POST")))
        .alias("game_type")
    )

    df = df.with_columns(
        (
            pl.col("season").cast(pl.Utf8) + "_"
            + pl.col("week").cast(pl.Utf8).str.zfill(2) + "_"
            + pl.col("away_team") + "_" + pl.col("home_team")
        ).alias("game_id")
    )

    df = df.with_columns([
        (pl.col("home_score") - pl.col("away_score")).cast(pl.Int16).alias("result"),
        (pl.col("home_score") + pl.col("away_score")).cast(pl.Int16).alias("total"),
    ])

    return df.select([
        "game_id", "season", "week", "game_type", "gameday",
        "home_team", "away_team", "home_score", "away_score", "result", "total",
        pl.col("boxscore_stats_link").alias("boxscore_url"),
    ])


def _clean_historical_scoring(df: pl.DataFrame) -> pl.DataFrame:
    season = int(df["season"][0])
    games_path = SILVER_DIR / "historical_gamelogs" / f"{season}.parquet"
    if not games_path.exists():
        return df.clear().select([
            pl.lit(None, dtype=pl.Utf8).alias("game_id"),
            pl.lit(None, dtype=pl.Int16).alias("season"),
            pl.lit(None, dtype=pl.Date).alias("gameday"),
            pl.lit(None, dtype=pl.Int32).alias("play_seq"),
            pl.lit(None, dtype=pl.Int16).alias("quarter"),
            pl.lit(None, dtype=pl.Utf8).alias("time"),
            pl.lit(None, dtype=pl.Utf8).alias("scoring_team"),
            pl.lit(None, dtype=pl.Int16).alias("home_score"),
            pl.lit(None, dtype=pl.Int16).alias("away_score"),
            pl.lit(None, dtype=pl.Utf8).alias("description"),
            pl.lit(None, dtype=pl.Utf8).alias("boxscore_url"),
        ])

    if "time" not in df.columns:
        df = df.with_columns(pl.lit(None, dtype=pl.Utf8).alias("time"))

    df = df.with_columns(pl.col("event_date").str.to_date(strict=False).alias("gameday"))

    games = pl.read_parquet(games_path).select([
        "game_id", "home_team", "away_team", "home_score", "away_score",
        pl.col("boxscore_url").alias("boxscore_stats_link"),
    ])
    df = df.join(games, on="boxscore_stats_link", how="inner")

    # The "tm"/"opp" labels in this dataset are not always reliable for
    # franchises that relocated/renamed (e.g. Houston Oilers -> Tennessee
    # Titans gets mislabeled as the unrelated Houston Texans in some files).
    # Determine whether "tm" is the home or away team by matching the final
    # running score against the authoritative game result from gamelogs.
    df = df.with_columns([
        pl.col("tm_score").last().over("boxscore_stats_link").alias("_final_tm"),
        pl.col("opp_score").last().over("boxscore_stats_link").alias("_final_opp"),
    ])
    df = df.with_columns(
        ((pl.col("_final_tm") == pl.col("home_score")) & (pl.col("_final_opp") == pl.col("away_score")))
        .alias("_tm_is_home")
    )
    df = df.with_columns((pl.col("scoring_team") == pl.col("tm_name")).alias("_scoring_is_tm"))

    df = df.with_columns(
        pl.when(pl.col("_scoring_is_tm") == pl.col("_tm_is_home"))
        .then(pl.col("home_team"))
        .otherwise(pl.col("away_team"))
        .alias("scoring_team_abbr")
    )

    df = df.with_columns([
        pl.when(pl.col("_tm_is_home")).then(pl.col("tm_score")).otherwise(pl.col("opp_score")).cast(pl.Int16).alias("home_score_after"),
        pl.when(pl.col("_tm_is_home")).then(pl.col("opp_score")).otherwise(pl.col("tm_score")).cast(pl.Int16).alias("away_score_after"),
    ])

    df = df.with_columns(pl.int_range(1, pl.len() + 1).over("game_id").cast(pl.Int32).alias("play_seq"))

    return df.select([
        "game_id",
        pl.col("season").cast(pl.Int16),
        "gameday",
        "play_seq",
        pl.col("quarter").cast(pl.Int16),
        pl.col("time").cast(pl.Utf8),
        pl.col("scoring_team_abbr").alias("scoring_team"),
        pl.col("home_score_after").alias("home_score"),
        pl.col("away_score_after").alias("away_score"),
        "description",
        pl.col("boxscore_stats_link").alias("boxscore_url"),
    ])


_SPECIFIC_CLEANERS = {
    "schedules": _clean_schedules,
    "players": _clean_players,
    "rosters": _clean_rosters,
    "weekly_rosters": _clean_rosters,
    "pbp": _clean_pbp,
    "historical_gamelogs": _clean_historical_gamelogs,
    "historical_scoring": _clean_historical_scoring,
}


# ── Orchestration ────────────────────────────────────────────────────────────

def clean_release(tag: str, force: bool = False) -> int:
    """Clean all parquet files for a release tag. Returns count of files written."""
    src_dir = BRONZE_DIR / tag
    dst_dir = SILVER_DIR / tag
    dst_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(src_dir.glob("*.parquet"))
    if not files:
        return 0

    written = 0
    for src in files:
        dst = dst_dir / src.name
        if not force and dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
            continue
        df = clean_dataset(tag, src)
        df.write_parquet(dst, compression="zstd")
        written += 1
    return written


def clean_all(tags: list[str] | None = None, force: bool = False) -> dict[str, int]:
    from pipeline.config import RELEASE_TAGS, LOCAL_TAGS
    tags = tags or RELEASE_TAGS + LOCAL_TAGS
    results = {}
    for tag in tags:
        results[tag] = clean_release(tag, force=force)
    return results
