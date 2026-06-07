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


_SPECIFIC_CLEANERS = {
    "schedules": _clean_schedules,
    "players": _clean_players,
    "rosters": _clean_rosters,
    "weekly_rosters": _clean_rosters,
    "pbp": _clean_pbp,
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
    from pipeline.config import RELEASE_TAGS
    tags = tags or RELEASE_TAGS
    results = {}
    for tag in tags:
        results[tag] = clean_release(tag, force=force)
    return results
