"""Season stats derived from pre-1999 play-by-play (fact_historical_plays).

Columns follow fact_player_season_stats / ref_team_stats where they overlap,
with source = 'pfr_pbp'; team codes are dim_games' historical codes.

PFR's play-by-play only has descriptions, so these are sums over the parsed
plays rather than official totals; scripts/check_historical_stats.py compares
them with PFR's official season tables.

Counting rules (as in the official stats):
  - plays nullified by penalty are play_type 'no_play' and don't count;
    two-point tries don't count
  - pass attempts include spikes and accepted intentional grounding and
    exclude sacks; passing yards are
    completion yards (gross); sacks and sack yards are counted separately
    and team net passing yards = gross - sack yards
  - kneels are rushes
  - plays with no inferred posteam count for the players (team NULL) but
    not for either team
  - a passing/rushing/receiving TD needs the team with the ball to score
    on the play (from the running score), so pick-sixes and fumble-return
    TDs don't count for the offense
"""

import duckdb

# One row per offensive play, with the flags the season sums need.
_PLAYS_SQL = """
CREATE OR REPLACE TEMP TABLE _hist_off AS
WITH scores AS (
    SELECT *,
        coalesce(lag(home_score IGNORE NULLS) OVER w, 0) AS prev_home,
        coalesce(lag(away_score IGNORE NULLS) OVER w, 0) AS prev_away,
        -- Accepted intentional grounding is an incomplete pass by the
        -- penalized passer; PFR's text often has only the penalty.
        play_type IN ('no_play', 'other') AND penalized_player IS NOT NULL
            AND regexp_matches(description, 'Penalty on [^:]+: Intentional Grounding')
            AND NOT regexp_matches(description, 'Intentional Grounding[^.]*\((declined|offset)\)') AS grounding
    FROM fact_historical_plays
    WINDOW w AS (PARTITION BY game_id ORDER BY play_seq)
)
SELECT season,
       CASE WHEN game_type = 'REG' THEN 'REG' ELSE 'POST' END AS season_type,
       game_id, home_team, away_team, posteam AS team,
       CASE WHEN grounding THEN 'pass' ELSE play_type END AS play_type,
       CASE WHEN grounding THEN penalized_player ELSE passer END AS passer,
       CASE WHEN grounding THEN penalized_player_id ELSE passer_id END AS passer_id,
       rusher, rusher_id,
       CASE WHEN grounding THEN NULL ELSE receiver END AS receiver,
       CASE WHEN grounding THEN NULL ELSE receiver_id END AS receiver_id,
       yards_gained,
       (sacker IS NOT NULL OR regexp_matches(description, ' sacked( |$)')) AS sack,
       (play_type = 'pass' AND regexp_matches(description, ' pass complete')) AS complete,
       (interceptor IS NOT NULL OR regexp_matches(description, ' intercepted ')) AS interception,
       touchdown AND (CASE WHEN posteam = home_team THEN home_score - prev_home
                           ELSE away_score - prev_away END) >= 6 AS off_td
FROM scores
WHERE (play_type IN ('pass', 'run', 'qb_kneel', 'qb_spike') OR grounding)
  AND NOT coalesce(two_point_attempt, false)
"""

# A player's team in a game: his roster team when exactly one of the two
# teams lists him, else the inferred posteam. Keeps a rare misread play (e.g.
# a botched snap PFR scores as a turnover) from giving him a row for the
# other team.
def _player_team(role: str) -> str:
    return f"""coalesce((SELECT any_value(r.team) FROM fact_rosters r
                        WHERE r.season = _hist_off.season AND r.player_id = _hist_off.{role}_id
                          AND r.team IN (_hist_off.home_team, _hist_off.away_team)
                        HAVING count(DISTINCT r.team) = 1), _hist_off.team)"""


PLAYER_SEASON_SQL = """
INSERT INTO fact_historical_player_season_stats BY NAME
WITH pass AS (
    SELECT season, season_type, passer_id AS player_id, passer AS player_name, {team_passer} AS team,
           count(DISTINCT game_id) AS games,
           count(*) FILTER (WHERE NOT sack) AS attempts,
           count(*) FILTER (WHERE complete) AS completions,
           sum(yards_gained) FILTER (WHERE complete) AS passing_yards,
           count(*) FILTER (WHERE complete AND off_td) AS passing_tds,
           count(*) FILTER (WHERE interception) AS passing_interceptions,
           count(*) FILTER (WHERE sack) AS sacks_suffered,
           -sum(yards_gained) FILTER (WHERE sack) AS sack_yards_lost
    FROM _hist_off WHERE play_type IN ('pass', 'qb_spike') AND passer IS NOT NULL
    GROUP BY ALL
),
rush AS (
    SELECT season, season_type, rusher_id AS player_id, rusher AS player_name, {team_rusher} AS team,
           count(DISTINCT game_id) AS games,
           count(*) AS carries,
           sum(yards_gained) AS rushing_yards,
           count(*) FILTER (WHERE off_td) AS rushing_tds
    FROM _hist_off WHERE play_type IN ('run', 'qb_kneel') AND rusher IS NOT NULL
    GROUP BY ALL
),
rec AS (
    SELECT season, season_type, receiver_id AS player_id, receiver AS player_name, {team_receiver} AS team,
           count(DISTINCT game_id) AS games,
           count(*) FILTER (WHERE NOT sack) AS targets,
           count(*) FILTER (WHERE complete) AS receptions,
           sum(yards_gained) FILTER (WHERE complete) AS receiving_yards,
           count(*) FILTER (WHERE complete AND off_td) AS receiving_tds
    FROM _hist_off WHERE play_type = 'pass' AND receiver IS NOT NULL
    GROUP BY ALL
),
games AS (
    SELECT season, season_type, player_id, player_name, team, count(DISTINCT game_id) AS games
    FROM (
        SELECT season, season_type, passer_id AS player_id, passer AS player_name, {team_passer} AS team, game_id
            FROM _hist_off WHERE passer IS NOT NULL
        UNION ALL SELECT season, season_type, rusher_id, rusher, {team_rusher}, game_id
            FROM _hist_off WHERE rusher IS NOT NULL
        UNION ALL SELECT season, season_type, receiver_id, receiver, {team_receiver}, game_id
            FROM _hist_off WHERE receiver IS NOT NULL
    ) GROUP BY ALL
)
SELECT g.season::SMALLINT AS season, g.season_type, g.player_id, g.player_name,
       (SELECT r.position FROM fact_rosters r WHERE r.season = g.season AND r.player_id = g.player_id
        ORDER BY r.team = g.team DESC LIMIT 1) AS position,
       g.team,
       g.games::SMALLINT AS games,
       coalesce(pass.completions, 0)::INTEGER AS completions,
       coalesce(pass.attempts, 0)::INTEGER AS attempts,
       coalesce(pass.passing_yards, 0)::INTEGER AS passing_yards,
       coalesce(pass.passing_tds, 0)::INTEGER AS passing_tds,
       coalesce(pass.passing_interceptions, 0)::INTEGER AS passing_interceptions,
       coalesce(pass.sacks_suffered, 0)::INTEGER AS sacks_suffered,
       coalesce(pass.sack_yards_lost, 0)::INTEGER AS sack_yards_lost,
       coalesce(rush.carries, 0)::INTEGER AS carries,
       coalesce(rush.rushing_yards, 0)::INTEGER AS rushing_yards,
       coalesce(rush.rushing_tds, 0)::INTEGER AS rushing_tds,
       coalesce(rec.targets, 0)::INTEGER AS targets,
       coalesce(rec.receptions, 0)::INTEGER AS receptions,
       coalesce(rec.receiving_yards, 0)::INTEGER AS receiving_yards,
       coalesce(rec.receiving_tds, 0)::INTEGER AS receiving_tds,
       'pfr_pbp' AS source
FROM games g
LEFT JOIN pass USING (season, season_type, player_id, player_name, team)
LEFT JOIN rush USING (season, season_type, player_id, player_name, team)
LEFT JOIN rec  USING (season, season_type, player_id, player_name, team)
ORDER BY season, season_type, team, player_name
""".format(team_passer=_player_team("passer"), team_rusher=_player_team("rusher"),
           team_receiver=_player_team("receiver"))

TEAM_SEASON_SQL = """
INSERT INTO fact_historical_team_season_stats BY NAME
SELECT season::SMALLINT AS season, season_type, team,
       count(DISTINCT game_id)::SMALLINT AS games,
       count(*) FILTER (WHERE play_type IN ('pass', 'run'))::INTEGER AS plays,
       count(*) FILTER (WHERE play_type IN ('pass', 'qb_spike') AND NOT sack)::INTEGER AS attempts,
       count(*) FILTER (WHERE complete)::INTEGER AS completions,
       coalesce(sum(yards_gained) FILTER (WHERE complete), 0)::INTEGER AS passing_yards,
       coalesce(-sum(yards_gained) FILTER (WHERE play_type = 'pass' AND sack), 0)::INTEGER AS sack_yards_lost,
       count(*) FILTER (WHERE play_type = 'pass' AND sack)::INTEGER AS sacks_suffered,
       (coalesce(sum(yards_gained) FILTER (WHERE complete), 0)
        + coalesce(sum(yards_gained) FILTER (WHERE play_type = 'pass' AND sack), 0))::INTEGER AS net_passing_yards,
       count(*) FILTER (WHERE complete AND off_td)::INTEGER AS passing_tds,
       count(*) FILTER (WHERE interception)::INTEGER AS passing_interceptions,
       count(*) FILTER (WHERE play_type IN ('run', 'qb_kneel'))::INTEGER AS carries,
       coalesce(sum(yards_gained) FILTER (WHERE play_type IN ('run', 'qb_kneel')), 0)::INTEGER AS rushing_yards,
       count(*) FILTER (WHERE play_type IN ('run', 'qb_kneel') AND off_td)::INTEGER AS rushing_tds,
       'pfr_pbp' AS source
FROM _hist_off
WHERE team IS NOT NULL
GROUP BY ALL
ORDER BY season, season_type, team
"""


def build_historical_season_stats(con: duckdb.DuckDBPyConnection) -> tuple[int, int]:
    con.execute(_PLAYS_SQL)
    con.execute("DELETE FROM fact_historical_player_season_stats")
    con.execute("DELETE FROM fact_historical_team_season_stats")
    con.execute(PLAYER_SEASON_SQL)
    con.execute(TEAM_SEASON_SQL)
    con.execute("DROP TABLE _hist_off")
    players = con.execute("SELECT count(*) FROM fact_historical_player_season_stats").fetchone()[0]
    teams = con.execute("SELECT count(*) FROM fact_historical_team_season_stats").fetchone()[0]
    return players, teams
