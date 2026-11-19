"""Data audit for the gold database: freshness, gaps, coverage, and regressions.

Run by `nfl audit` in the nightly refresh. Findings are either:
  error   - something broke in this build (table empty or shrank sharply versus the
            previous run). With --strict the command exits non-zero so the nightly
            job stops before publishing the database.
  warning - data is stale or has gaps (often upstream delays); reported, not blocking.

Expectations below encode what "complete" means for each table. When a source
changes coverage on purpose, update them here.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import duckdb

# Max seasons a table may trail the latest season with a played game.
# Tables not listed (frozen sources like Elo, pre-1998 scoring) are not checked.
SEASON_LAG = {
    "dim_games": 0,
    "fact_plays": 0, "fact_pass_plays": 0, "fact_rush_plays": 0, "fact_kick_plays": 0,
    "fact_player_game_stats": 0, "fact_player_season_stats": 0,
    "fact_weekly_rosters": 0, "fact_rosters": 0, "fact_depth_charts": 0,
    "fact_snap_counts": 0, "fact_injuries": 0,
    "fact_ngs_passing": 0, "fact_ngs_receiving": 0, "fact_ngs_rushing": 0,
    "fact_ftn_charting": 0, "ref_qbr_week": 0, "ref_qbr_season": 0, "ref_team_stats": 0,
    # Published after the season or irregularly upstream.
    "fact_pbp_participation": 1, "ref_officials": 1,
    "ref_pfr_adv_pass": 1, "ref_pfr_adv_rush": 1, "ref_pfr_adv_rec": 1, "ref_pfr_adv_def": 1,
    "ref_draft_picks": 1, "ref_combine": 1, "ref_trades": 1, "ref_contracts": 1,
}

# Weekly tables: (week column, weeks of lag allowed behind the latest played week).
WEEK_LAG = {
    "fact_plays": ("week", 0),
    "fact_player_game_stats": ("week", 1),
    "fact_snap_counts": ("week", 1),
    "fact_injuries": ("week", 1),
    "fact_weekly_rosters": ("week", 1),
    "fact_depth_charts": ("week", 1),
    "fact_ngs_passing": ("week", 1),
    "fact_ftn_charting": ("week", 2),
}

# Every played game from `since` should have rows in these game_id tables.
GAME_COVERAGE = {
    "fact_plays": 1999,
    "fact_player_game_stats": 1999,
    "fact_snap_counts": 2013,
    "fact_ftn_charting": 2022,
    "fact_pbp_participation": 2016,
}
# Played games known to be absent upstream; not reported.
_NO_PBP_GAMES = {"1999_01_BAL_STL", "2000_03_SD_KC", "2000_06_BUF_MIA"}
KNOWN_MISSING_GAMES = {"fact_plays": _NO_PBP_GAMES, "fact_player_game_stats": _NO_PBP_GAMES}

# Tables whose game_id uses another ID scheme: the dim_games column it matches.
GAME_ID_JOIN = {"ref_officials": "old_game_id", "ref_qbr_week": "espn"}
# Share of rows allowed to point at unknown games before it is reported.
ORPHAN_TOLERANCE = 0.01

# Seasons known to be absent upstream; not reported as gaps.
KNOWN_SEASON_GAPS = {"ref_contracts": {1984}}

# Row-count regression threshold versus the previous run.
MAX_DROP = 0.10


@dataclass
class Finding:
    severity: str  # "error" | "warning"
    table: str
    check: str
    message: str


def _season_col(cols: set[str]) -> str | None:
    if "season" in cols:
        return "season"
    if "year_signed" in cols:
        return "year_signed"
    return None


def run_audit(con: duckdb.DuckDBPyConnection, previous_counts: dict[str, int] | None = None) -> list[Finding]:
    findings: list[Finding] = []
    add = lambda sev, t, chk, msg: findings.append(Finding(sev, t, chk, msg))
    q = lambda sql, params=None: con.execute(sql, params or []).fetchall()

    tables = {r[0] for r in q("SELECT table_name FROM duckdb_tables()")}
    columns = {t: {r[0] for r in q(f'DESCRIBE "{t}"')} for t in tables}
    counts = {t: q(f'SELECT count(*) FROM "{t}"')[0][0] for t in tables}

    # 1. Empty tables and regressions versus the previous run.
    for t in sorted(tables):
        if counts[t] == 0:
            add("error", t, "empty", "table has no rows")
        prev = (previous_counts or {}).get(t)
        if prev and counts[t] < prev * (1 - MAX_DROP):
            add("error", t, "row_drop", f"{counts[t]:,} rows, down {1 - counts[t] / prev:.0%} from {prev:,} last run")
    for t in sorted(set(previous_counts or {}) - tables):
        if (previous_counts or {}).get(t):
            add("error", t, "missing_table", "table existed last run but is gone")

    if "dim_games" not in tables or counts.get("dim_games", 0) == 0:
        return findings

    latest_season, latest_week = q("""
        SELECT season, max(week) FILTER (WHERE game_type = 'REG')
        FROM dim_games WHERE result IS NOT NULL
        GROUP BY season ORDER BY season DESC LIMIT 1""")[0]

    # 2. Season freshness.
    for t, lag in SEASON_LAG.items():
        if t not in tables or counts[t] == 0:
            continue
        scol = _season_col(columns[t])
        if scol is None:
            continue
        max_season = q(f'SELECT max({scol}) FROM "{t}"')[0][0]
        if max_season is None or max_season < latest_season - lag:
            add("warning", t, "stale_season",
                f"latest season {max_season}, expected {latest_season - lag}+ (latest played season is {latest_season})")

    # 3. Week freshness for the latest season.
    if latest_week:
        for t, (wcol, lag) in WEEK_LAG.items():
            if t not in tables or counts[t] == 0 or wcol not in columns[t]:
                continue
            max_week = q(f'SELECT max({wcol}) FROM "{t}" WHERE season = ? AND {wcol} <= 18', [latest_season])[0][0]
            if max_week is None or max_week < latest_week - lag:
                add("warning", t, "stale_week",
                    f"{latest_season} loaded through week {max_week}, games played through week {latest_week}")

    # 4. Seasons missing inside each table's range.
    for t in sorted(tables):
        scol = _season_col(columns[t])
        if scol is None or counts[t] == 0:
            continue
        seasons = {r[0] for r in q(f'SELECT DISTINCT {scol} FROM "{t}" WHERE {scol} > 0')}
        if not seasons:
            continue
        gaps = sorted(set(range(min(seasons), max(seasons) + 1)) - seasons - KNOWN_SEASON_GAPS.get(t, set()))
        if gaps:
            add("warning", t, "season_gap", f"no rows for seasons {gaps}")

    # 5. Played games with no rows in game-level tables.
    for t, since in GAME_COVERAGE.items():
        if t not in tables or counts[t] == 0 or "game_id" not in columns[t]:
            continue
        # Allow a source's latest season to trail (e.g. participation is published after the season).
        until = latest_season - SEASON_LAG.get(t, 0)
        missing = [r[0] for r in q(f"""
            SELECT g.game_id FROM dim_games g
            WHERE g.season BETWEEN ? AND ? AND g.result IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM "{t}" x WHERE x.game_id = g.game_id)
            ORDER BY g.game_id""", [since, until])]
        missing = [g for g in missing if g not in KNOWN_MISSING_GAMES.get(t, set())]
        # The newest games may simply not be published yet.
        recent = {r[0] for r in q("""SELECT game_id FROM dim_games WHERE result IS NOT NULL
                                     AND gameday::DATE >= (SELECT max(gameday::DATE) FROM dim_games WHERE result IS NOT NULL) - 3""")}
        missing = [g for g in missing if g not in recent]
        if missing:
            shown = ", ".join(missing[:5]) + (f" (+{len(missing) - 5} more)" if len(missing) > 5 else "")
            add("warning", t, "missing_games", f"{len(missing)} played games have no rows: {shown}")

    # Depth charts have no game_id; check team-games from the snapshot era instead.
    if "fact_depth_charts" in tables and counts["fact_depth_charts"]:
        n = q("""
            SELECT count(*) FROM dim_games g, unnest([g.home_team, g.away_team]) AS t(team)
            WHERE g.season >= 2025 AND g.result IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM fact_depth_charts d
                              WHERE d.season = g.season AND d.week = g.week AND d.club_code = t.team)""")[0][0]
        if n:
            add("warning", "fact_depth_charts", "missing_games", f"{n} team-games since 2025 have no depth chart")

    # 6. Rows pointing at games that don't exist.
    for t in sorted(tables):
        if t == "dim_games" or "game_id" not in columns[t] or counts[t] == 0:
            continue
        key = GAME_ID_JOIN.get(t, "game_id")
        n, total = q(f"""SELECT count(DISTINCT x.game_id) FILTER (WHERE NOT EXISTS (
                             SELECT 1 FROM dim_games g WHERE g.{key}::VARCHAR = x.game_id::VARCHAR)),
                         count(DISTINCT x.game_id)
                  FROM "{t}" x WHERE x.game_id IS NOT NULL""")[0]
        if n and n > total * ORPHAN_TOLERANCE:
            add("warning", t, "orphan_games", f"{n:,} of {total:,} game_id values not in dim_games.{key}")

    return findings


def load_previous_counts(path: Path | None) -> dict[str, int]:
    if path is None or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.get("row_counts", {}).items() if isinstance(v, int)}


def findings_to_json(findings: list[Finding]) -> str:
    return json.dumps([asdict(f) for f in findings], indent=2)
