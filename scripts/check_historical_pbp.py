"""Sanity checks for fact_historical_plays, one line per season.

Run after a scraped season has been imported and loaded:

    uv run nfl ingest-historical
    uv run nfl clean historical_pbp
    uv run nfl load fact_historical_plays
    uv run python scripts/check_historical_pbp.py

Checks, per season:
  - games: every dim_games game for the season has play-by-play
    (games PFR has no play-by-play for are marked .none by the scraper)
  - orphans: plays whose game_id isn't in dim_games
  - final: games whose last running score differs from dim_games
  - tds: touchdowns parsed vs touchdowns in fact_game_scoring
  - other: share of plays the description parser couldn't classify
  - bad_side: yardline_side codes that no team uses that season (a missing
    code mapping in the cleaner)
  - typo_side: yardline_side is a real team but not one in the game (PFR typos,
    e.g. 'CAR 30' in a DET-CHI game); reported, not a failure
  - poss: share of plays with an inferred posteam
  - pen: team-named penalties (false start, offside, ...) credited to the right side,
    an independent check on posteam
Exits non-zero if any season has orphans, final-score mismatches or bad sides.
"""

import sys
from pathlib import Path

import duckdb

DB = Path(__file__).resolve().parent.parent / "data" / "nfl.duckdb"


def main() -> int:
    con = duckdb.connect(str(DB), read_only=True)
    rows = con.execute("""
        WITH p AS (SELECT * FROM fact_historical_plays),
        season_teams AS (
            SELECT DISTINCT season, home_team AS team FROM fact_historical_plays
            UNION SELECT DISTINCT season, away_team FROM fact_historical_plays
        ),
        last AS (
            SELECT game_id, arg_max(home_score, play_seq) FILTER (WHERE home_score IS NOT NULL) AS h,
                            arg_max(away_score, play_seq) FILTER (WHERE away_score IS NOT NULL) AS a
            FROM p GROUP BY 1
        ),
        per_season AS (
            SELECT season,
                   count(*) AS plays,
                   count(DISTINCT game_id) AS games,
                   count(*) FILTER (WHERE touchdown) AS tds,
                   count(*) FILTER (WHERE play_type = 'other') AS other,
                   count(*) FILTER (WHERE yardline_side IS NOT NULL
                                      AND yardline_side NOT IN (home_team, away_team)) AS off_side,
                   avg((posteam IS NOT NULL)::INT) FILTER (WHERE play_type IS NOT NULL) AS poss
            FROM p GROUP BY 1
        ),
        pen AS (
            SELECT season, kind,
                   CASE WHEN kind = 'off' THEN pt = posteam ELSE pt = defteam END AS ok
            FROM (
                SELECT season, posteam, defteam,
                       coalesce(map_extract(MAP {'GNB':'GB','KAN':'KC','NOR':'NO','NWE':'NE','SDG':'SD','SFO':'SF',
                                                 'TAM':'TB','WAS':'WSH','RAM':'LA','PHO':'PHX'},
                                            regexp_extract(description, '^Penalty on ([A-Z]{2,3}):', 1))[1],
                                regexp_extract(description, '^Penalty on ([A-Z]{2,3}):', 1)) AS pt,
                       CASE WHEN regexp_matches(description, '^Penalty on [A-Z]{2,3}: (False Start|Offensive Holding|Illegal Formation|Illegal Shift|Offensive Offside|Illegal Motion)')
                            THEN 'off'
                            WHEN regexp_matches(description, '^Penalty on [A-Z]{2,3}: (Defensive Offside|Defensive 12 Men|Defensive Holding|Encroachment|Neutral Zone Infraction)')
                            THEN 'def' END AS kind
                FROM p WHERE down IS NOT NULL AND posteam IS NOT NULL
            ) WHERE kind IS NOT NULL
        )
        SELECT s.season, s.plays, s.games,
               (SELECT count(*) FROM dim_games g WHERE g.season = s.season) AS sched_games,
               (SELECT count(*) FROM p WHERE p.season = s.season
                  AND p.game_id NOT IN (SELECT game_id FROM dim_games)) AS orphans,
               (SELECT count(*) FROM last l JOIN dim_games g USING (game_id)
                  WHERE g.season = s.season AND (l.h <> g.home_score OR l.a <> g.away_score)) AS final_bad,
               s.tds,
               (SELECT count(*) FROM fact_game_scoring f WHERE f.season = s.season
                  AND f.scoring_type = 'touchdown') AS scoring_tds,
               s.other,
               (SELECT count(*) FROM p WHERE p.season = s.season AND p.yardline_side IS NOT NULL
                  AND p.yardline_side NOT IN (SELECT team FROM season_teams t WHERE t.season = s.season)) AS bad_side,
               s.off_side, s.poss,
               (SELECT count(*) FILTER (WHERE ok) FROM pen WHERE pen.season = s.season) AS pen_ok,
               (SELECT count(*) FROM pen WHERE pen.season = s.season) AS pen_n
        FROM per_season s ORDER BY s.season DESC
    """).fetchall()

    failed = False
    print(f"{'season':>6} {'plays':>7} {'games':>9} {'orphans':>7} {'final':>5} {'tds':>11} {'other':>6} {'bad_side':>8} {'typo_side':>9} {'poss':>6} {'pen':>8}")
    for season, plays, games, sched, orphans, final_bad, tds, scoring_tds, other, bad_side, off_side, poss, pen_ok, pen_n in rows:
        bad = orphans or final_bad or bad_side
        failed |= bool(bad)
        print(f"{season:>6} {plays:>7,} {f'{games}/{sched}':>9} {orphans:>7} {final_bad:>5} "
              f"{f'{tds}/{scoring_tds}':>11} {other / plays:>6.1%} {bad_side:>8} {off_side - bad_side:>9} {(poss or 0):>6.1%} "
              f"{f'{pen_ok}/{pen_n}':>8}{'  <-- check' if bad else ''}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
