"""Game and season stats derived from pre-1999 play-by-play (fact_historical_plays).

Columns follow fact_player_game_stats / fact_player_season_stats /
ref_team_stats where they overlap, with source = 'pfr_pbp'; team codes are
dim_games' historical codes.

PFR's play-by-play only has descriptions, so these are sums over the parsed
plays rather than official totals; scripts/check_historical_stats.py compares
the season totals with PFR's official season tables.

Every stat is first written as one row per (play, player, stat) in
_hist_events; player game lines pivot those rows and season lines sum the
game lines, so both use the same counting rules.

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
    on the play or its conversion (from the running score, when it shows
    anyone scoring), so pick-sixes and fumble-return
    TDs don't count for the offense, nor does a fumble recovered in the end
    zone
  - a split sack ("sacked by A and B") is half a sack and half the yards
    for each
  - no tackles: PFR's "(tackle by ...)" text doesn't reproduce the official
    tackle counts (checked against PFR's 1994-98 tables), so it isn't summed
  - each "X fumbles" is a fumble by X; it's lost when the player who
    recovers it is on the other team (when PFR doesn't say who, when the
    other team has the ball next). Recoveries count only on plays with a
    fumble (not blocked kicks)
  - a blocked punt is a punt of 0 yards; a muffed catch is a return of 0
    yards (as in PFR's tables)
"""

import duckdb
import polars as pl

from pipeline.historical_players import match_player_ids
from pipeline.silver.pfr_pbp_parser import NAME

# Player game/season stat columns after the identifying ones, in table order:
# (column, SQL type, how to combine plays: sum or max).
STAT_COLUMNS = [
    ("completions", "INTEGER", "sum"), ("attempts", "INTEGER", "sum"), ("passing_yards", "INTEGER", "sum"),
    ("passing_tds", "INTEGER", "sum"), ("passing_interceptions", "INTEGER", "sum"),
    ("sacks_suffered", "INTEGER", "sum"), ("sack_yards_lost", "INTEGER", "sum"),
    ("carries", "INTEGER", "sum"), ("rushing_yards", "INTEGER", "sum"), ("rushing_tds", "INTEGER", "sum"),
    ("targets", "INTEGER", "sum"), ("receptions", "INTEGER", "sum"), ("receiving_yards", "INTEGER", "sum"),
    ("receiving_tds", "INTEGER", "sum"),
    ("fumbles", "INTEGER", "sum"), ("fumbles_lost", "INTEGER", "sum"),
    ("def_sacks", "DOUBLE", "sum"), ("def_sack_yards", "DOUBLE", "sum"),
    ("def_interceptions", "INTEGER", "sum"), ("def_interception_yards", "INTEGER", "sum"),
    ("def_interception_tds", "INTEGER", "sum"), ("def_fumbles_forced", "INTEGER", "sum"),
    ("fumble_recovery_own", "INTEGER", "sum"), ("fumble_recovery_opp", "INTEGER", "sum"),
    ("fumble_recovery_tds", "INTEGER", "sum"),
    ("fg_made", "INTEGER", "sum"), ("fg_att", "INTEGER", "sum"), ("fg_blocked", "INTEGER", "sum"),
    ("fg_long", "INTEGER", "max"),
    *[(f"fg_{r}_{b}", "INTEGER", "sum") for r in ("made", "missed")
      for b in ("0_19", "20_29", "30_39", "40_49", "50_59", "60_")],
    ("pat_made", "INTEGER", "sum"), ("pat_att", "INTEGER", "sum"),
    ("punts", "INTEGER", "sum"), ("punt_yards", "INTEGER", "sum"), ("punt_long", "INTEGER", "max"),
    ("punts_blocked", "INTEGER", "sum"),
    ("kickoff_returns", "INTEGER", "sum"), ("kickoff_return_yards", "INTEGER", "sum"),
    ("kickoff_return_tds", "INTEGER", "sum"),
    ("punt_returns", "INTEGER", "sum"), ("punt_return_yards", "INTEGER", "sum"),
    ("punt_return_tds", "INTEGER", "sum"),
]

N = NAME.replace("'", "''")  # player-name regex, quoted for SQL


def _name(sql: str) -> str:
    """A name matched with N, cut where it runs on into the next sentence
    (as pfr_pbp_parser.clean_name does)."""
    return f"nullif(regexp_replace({sql}, '([a-z]{{2}})\\. [A-Z].*$', '\\1'), '')"

# One row per offensive play, with the flags the offense sums need.
# Points each team scored on a play, counting its conversion: in 1989-90
# PFR puts a touchdown's 6 on the conversion row, after any penalty rows, so
# the score after the play is the later of its own and the next non-penalty
# row's.
_SCORES_SQL = """
CREATE OR REPLACE TEMP TABLE _hist_scores AS
SELECT game_id, play_seq,
       greatest(home_score, first_value(CASE WHEN play_type IS DISTINCT FROM 'no_play' THEN home_score END
                                        IGNORE NULLS) OVER after)
           - coalesce(lag(home_score IGNORE NULLS) OVER w, 0) AS home_gain,
       greatest(away_score, first_value(CASE WHEN play_type IS DISTINCT FROM 'no_play' THEN away_score END
                                        IGNORE NULLS) OVER after)
           - coalesce(lag(away_score IGNORE NULLS) OVER w, 0) AS away_gain,
       -- who has the ball next, in the same half (for fumbles PFR doesn't
       -- say who recovered)
       CASE WHEN first_value(CASE WHEN posteam IS NOT NULL THEN (quarter >= 3)::INT + (quarter >= 5)::INT END
                             IGNORE NULLS) OVER after = (quarter >= 3)::INT + (quarter >= 5)::INT
            THEN first_value(posteam IGNORE NULLS) OVER after END AS next_posteam
FROM fact_historical_plays
WINDOW w AS (PARTITION BY game_id ORDER BY play_seq),
       after AS (w ROWS BETWEEN 1 FOLLOWING AND UNBOUNDED FOLLOWING)
"""

_PLAYS_SQL = r"""
CREATE OR REPLACE TEMP TABLE _hist_off AS
WITH scores AS (
    SELECT *,
        coalesce(lag(home_score IGNORE NULLS) OVER w, 0) AS prev_home,
        coalesce(lag(away_score IGNORE NULLS) OVER w, 0) AS prev_away,
        -- 1989-90: PFR puts a touchdown's 6 on the conversion row, after any
        -- penalty rows, so the score after the play is the later of its own
        -- and the next non-penalty row's.
        greatest(home_score, first_value(CASE WHEN play_type IS DISTINCT FROM 'no_play' THEN home_score END
                                         IGNORE NULLS) OVER after) AS after_home,
        greatest(away_score, first_value(CASE WHEN play_type IS DISTINCT FROM 'no_play' THEN away_score END
                                         IGNORE NULLS) OVER after) AS after_away,
        -- Accepted intentional grounding is an incomplete pass by the
        -- penalized passer; PFR's text often has only the penalty.
        play_type IN ('no_play', 'other') AND penalized_player IS NOT NULL
            AND regexp_matches(description, 'Penalty on [^:]+: Intentional Grounding')
            AND NOT regexp_matches(description, 'Intentional Grounding[^.]*\((declined|offset)\)') AS grounding
    FROM fact_historical_plays
    WINDOW w AS (PARTITION BY game_id ORDER BY play_seq),
           after AS (w ROWS BETWEEN 1 FOLLOWING AND UNBOUNDED FOLLOWING)
)
SELECT season,
       CASE WHEN game_type = 'REG' THEN 'REG' ELSE 'POST' END AS season_type,
       game_id, play_seq, home_team, away_team, posteam AS team,
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
       touchdown AND ((CASE WHEN posteam = home_team THEN after_home - prev_home
                            ELSE after_away - prev_away END) >= 6
                      -- PFR's running score sometimes misses a touchdown
                      -- altogether; with no score for either side, the
                      -- description is all there is
                      OR (after_home - prev_home < 6 AND after_away - prev_away < 6))
           -- a fumble recovered for a touchdown is the recoverer's, not a
           -- rushing/receiving touchdown (only when the text says so: a
           -- wider rule loses touchdowns PFR's tables do credit)
           AND NOT regexp_matches(description, 'recovered by [^.]*touchdown') AS off_td
FROM scores
WHERE (play_type IN ('pass', 'run', 'qb_kneel', 'qb_spike') OR grounding)
  AND NOT coalesce(two_point_attempt, false)
"""

# Stat rows before player ids and teams are settled: the name as written,
# its id when the play-by-play matched one, and the team the player is on
# given his role (side; NULL when the role can be either team).
_RAW_EVENTS_SQL = f"""
CREATE OR REPLACE TEMP TABLE _hist_raw AS
WITH p AS (
    SELECT *, CASE WHEN game_type = 'REG' THEN 'REG' ELSE 'POST' END AS season_type
    FROM fact_historical_plays
    WHERE play_type IS DISTINCT FROM 'no_play' AND NOT coalesce(two_point_attempt, false)
),
off AS (
    SELECT * FROM _hist_off
),
-- The team that didn't have the ball at the end of the play: whoever forces
-- a fumble is on it.
tackling AS (
    SELECT *, CASE WHEN play_type = 'punt' THEN posteam
                   WHEN interceptor IS NOT NULL THEN posteam
                   ELSE defteam END AS tackling_team
    FROM p
),
sack AS (
    SELECT *, {_name(f"regexp_extract(description, 'sacked by ({N})(?: and ({N}))?', 1)")} AS s1,
              {_name(f"regexp_extract(description, 'sacked by ({N})(?: and ({N}))?', 2)")} AS s2
    FROM p WHERE play_type = 'pass' AND sacker IS NOT NULL
),
fumble AS (
    -- Each fumble on the play, paired in order with the recovery after it.
    -- A recovery is a touchdown when its text says so, or when it's the
    -- play's last recovery on a touchdown play and the recoverer's team
    -- scored (PFR's text is often cut short; settled once teams are known).
    SELECT p.*, f.i, {_name("f.fumbler")} AS fumbler,
           {_name(f"regexp_extract(r.seg, '^({N})', 1)")} AS recoverer,
           r.seg LIKE '%touchdown%' AS rec_td,
           CASE WHEN p.touchdown
                     AND f.i = len(regexp_extract_all(p.description, 'recovered by ({N}[^.]*)', 1))
                THEN CASE WHEN sc.home_gain >= 6 THEN p.home_team WHEN sc.away_gain >= 6 THEN p.away_team END
           END AS scoring_team,
           CASE WHEN f.i = len(regexp_extract_all(p.description, '(?:^|\\. )({N}) fumbles', 1))
                THEN sc.next_posteam END AS next_posteam
    FROM p JOIN _hist_scores sc USING (game_id, play_seq),
         LATERAL (SELECT unnest(regexp_extract_all(p.description, '(?:^|\\. )({N}) fumbles', 1)) AS fumbler,
                         generate_subscripts(regexp_extract_all(p.description, '(?:^|\\. )({N}) fumbles', 1), 1) AS i) f
    LEFT JOIN LATERAL (SELECT unnest(regexp_extract_all(p.description, 'recovered by ({N}[^.]*)', 1)) AS seg,
                              generate_subscripts(regexp_extract_all(p.description, 'recovered by ({N}[^.]*)', 1), 1) AS i) r
           ON r.i = f.i
),
kick AS (
    SELECT *, try_cast(regexp_extract(description, '(\\d+) yard field goal', 1) AS INTEGER) AS dist,
              regexp_matches(description, 'field goal good') AS made
    FROM p WHERE play_type = 'field_goal' AND kicker IS NOT NULL
),
-- Blocked punts: "X punts blocked by Y" to 1995, "X punts, recovered by Y"
-- from 1996. A bare "X punts" is neither a punt nor a block in PFR's tables.
blocked_punt AS (
    SELECT *, {_name(f"regexp_extract(description, '^({N}) punts', 1)")} AS who
    FROM p WHERE play_type IS DISTINCT FROM 'punt' AND regexp_matches(description, '^{N} punts( blocked by|,)')
),
-- Returns, and muffed catches, which PFR counts as returns of 0 yards.
ret AS (
    SELECT *, coalesce(try_cast(regexp_extract(description, 'returned by {N} for (-?\\d+) yard', 1) AS INTEGER), 0) AS ret_yds,
              -- "returned by X for 11 yards, touchdown. X fumbles, recovered
              -- by Y ...": the touchdown is the recoverer's
              regexp_matches(description, 'returned by {N} for [^,.]*, touchdown')
                  AND NOT regexp_matches(description, ' fumbles[^.]*recovered by ') AS ret_td,
              CASE WHEN returner IS NOT NULL AND regexp_matches(description, 'returned by ') THEN returner
                   ELSE muffer END AS ret_player,
              CASE WHEN returner IS NOT NULL AND regexp_matches(description, 'returned by ') THEN returner_id
                   END AS ret_player_id
    FROM (SELECT *, {_name(f"regexp_extract(description, 'muffed catch by ({N})', 1)")} AS muffer
          FROM p WHERE play_type IN ('kickoff', 'punt'))
    WHERE (returner IS NOT NULL AND regexp_matches(description, 'returned by ')) OR muffer IS NOT NULL
)
SELECT season, season_type, game_id, play_seq, home_team, away_team, player, player_id, side, stat,
       value::DOUBLE AS value, scoring_team, next_posteam
FROM (
    -- offense
    SELECT *, passer AS player, passer_id AS player_id, team AS side FROM (
        SELECT season, season_type, game_id, play_seq, home_team, away_team, team, passer, passer_id,
               (NOT sack)::INT AS attempts, complete::INT AS completions,
               CASE WHEN complete THEN yards_gained END AS passing_yards,
               (complete AND off_td)::INT AS passing_tds, interception::INT AS passing_interceptions,
               sack::INT AS sacks_suffered, CASE WHEN sack THEN -yards_gained END AS sack_yards_lost
        FROM off WHERE play_type IN ('pass', 'qb_spike') AND passer IS NOT NULL
    ) UNPIVOT (value FOR stat IN (attempts, completions, passing_yards, passing_tds, passing_interceptions,
                                  sacks_suffered, sack_yards_lost))
    UNION ALL BY NAME
    SELECT *, rusher AS player, rusher_id AS player_id, team AS side FROM (
        SELECT season, season_type, game_id, play_seq, home_team, away_team, team, rusher, rusher_id,
               1 AS carries, yards_gained AS rushing_yards, off_td::INT AS rushing_tds
        FROM off WHERE play_type IN ('run', 'qb_kneel') AND rusher IS NOT NULL
    ) UNPIVOT (value FOR stat IN (carries, rushing_yards, rushing_tds))
    UNION ALL BY NAME
    SELECT *, receiver AS player, receiver_id AS player_id, team AS side FROM (
        SELECT season, season_type, game_id, play_seq, home_team, away_team, team, receiver, receiver_id,
               (NOT sack)::INT AS targets, complete::INT AS receptions,
               CASE WHEN complete THEN yards_gained END AS receiving_yards,
               (complete AND off_td)::INT AS receiving_tds
        FROM off WHERE play_type = 'pass' AND receiver IS NOT NULL
    ) UNPIVOT (value FOR stat IN (targets, receptions, receiving_yards, receiving_tds))
    -- defense
    UNION ALL BY NAME
    SELECT season, season_type, game_id, play_seq, home_team, away_team,
           s1 AS player,
           CASE WHEN s1 = sacker THEN sacker_id END AS player_id,
           defteam AS side,
           unnest(['def_sacks', 'def_sack_yards']) AS stat,
           unnest([1.0, -yards_gained]) * CASE WHEN s2 IS NULL THEN 1 ELSE 0.5 END AS value
    FROM sack
    UNION ALL BY NAME
    SELECT season, season_type, game_id, play_seq, home_team, away_team,
           s2 AS player,
           NULL AS player_id,
           defteam AS side,
           unnest(['def_sacks', 'def_sack_yards']) AS stat,
           unnest([0.5, -yards_gained * 0.5]) AS value
    FROM sack WHERE s2 IS NOT NULL
    UNION ALL BY NAME
    SELECT season, season_type, game_id, play_seq, home_team, away_team,
           interceptor AS player,
           interceptor_id AS player_id,
           defteam AS side,
           unnest(['def_interceptions', 'def_interception_yards', 'def_interception_tds']) AS stat,
           unnest([1, coalesce(try_cast(regexp_extract(description, 'intercepted by {N}(?: at\\s*\\S*)? and returned for (-?\\d+) yard',
                                              1) AS INTEGER), 0),
                   (touchdown AND regexp_matches(description, 'intercepted by [^.]*touchdown'))::INT]) AS value
    FROM p WHERE play_type = 'pass' AND interceptor IS NOT NULL
    UNION ALL BY NAME
    SELECT season, season_type, game_id, play_seq, home_team, away_team,
           forcer AS player,
           CASE WHEN forcer = forced_fumble_player THEN forced_fumble_player_id END AS player_id,
           tackling_team AS side,
           'def_fumbles_forced' AS stat,
           1 AS value
    FROM (SELECT *, {_name("unnest(regexp_extract_all(description, 'forced by (" + N + ")', 1))")} AS forcer
          FROM tackling)
    -- fumbles: the fumbler's and recoverer's teams are settled later
    UNION ALL BY NAME
    SELECT season, season_type, game_id, play_seq, home_team, away_team,
           fumbler AS player,
           CASE WHEN fumbler = rusher THEN rusher_id WHEN fumbler = receiver THEN receiver_id
                WHEN fumbler = passer THEN passer_id WHEN fumbler = returner THEN returner_id
                WHEN fumbler = interceptor THEN interceptor_id END AS player_id,
           CASE WHEN fumbler IN (rusher, receiver, passer) THEN posteam
                WHEN fumbler = returner AND play_type = 'kickoff' THEN posteam
                WHEN fumbler = returner AND play_type = 'punt' THEN defteam
                WHEN fumbler = interceptor THEN defteam END AS side,
           'fumble#' || i || '#' || coalesce(recoverer, '') AS stat,
           1 AS value, next_posteam
    FROM fumble
    UNION ALL BY NAME
    SELECT season, season_type, game_id, play_seq, home_team, away_team,
           recoverer AS player,
           CASE WHEN recoverer = fumble_recovery_player THEN fumble_recovery_player_id END AS player_id,
           NULL AS side,
           'recovery#' || i || '#' || fumbler || '#' || rec_td::INT AS stat,
           1 AS value, scoring_team
    FROM fumble WHERE recoverer IS NOT NULL
    -- kicking and punting
    UNION ALL BY NAME
    SELECT season, season_type, game_id, play_seq, home_team, away_team,
           kicker AS player,
           kicker_id AS player_id,
           posteam AS side,
           unnest(['fg_att', 'fg_made', 'fg_blocked', 'fg_long',
                   'fg_' || CASE WHEN made THEN 'made' ELSE 'missed' END || '_'
                   || CASE WHEN dist < 20 THEN '0_19' WHEN dist < 30 THEN '20_29' WHEN dist < 40 THEN '30_39'
                           WHEN dist < 50 THEN '40_49' WHEN dist < 60 THEN '50_59' ELSE '60_' END]) AS stat,
           unnest([1, made::INT, regexp_matches(description, 'blocked')::INT, CASE WHEN made THEN dist END, 1]) AS value
    FROM kick
    UNION ALL BY NAME
    SELECT season, season_type, game_id, play_seq, home_team, away_team,
           kicker AS player,
           kicker_id AS player_id,
           posteam AS side,
           unnest(['pat_att', 'pat_made']) AS stat,
           unnest([1, regexp_matches(description, 'extra point good')::INT]) AS value
    FROM p WHERE play_type = 'extra_point' AND kicker IS NOT NULL
    UNION ALL BY NAME
    SELECT season, season_type, game_id, play_seq, home_team, away_team,
           punter AS player,
           punter_id AS player_id,
           posteam AS side,
           unnest(['punts', 'punt_yards', 'punt_long']) AS stat,
           unnest([1, try_cast(regexp_extract(description, ' punts (\\d+) yard', 1) AS INTEGER),
                   try_cast(regexp_extract(description, ' punts (\\d+) yard', 1) AS INTEGER)]) AS value
    FROM p WHERE play_type = 'punt' AND punter IS NOT NULL
    UNION ALL BY NAME
    SELECT season, season_type, game_id, play_seq, home_team, away_team,
           who AS player,
           NULL AS player_id,
           posteam AS side,
           unnest(['punts', 'punts_blocked']) AS stat,
           -- PFR doesn't count a blocked punt as a punt (0 keeps the game
           -- row for a punter whose only kick was blocked).
           unnest([0, 1]) AS value
    FROM blocked_punt
    -- returns
    UNION ALL BY NAME
    SELECT season, season_type, game_id, play_seq, home_team, away_team,
           ret_player AS player,
           ret_player_id AS player_id,
           CASE WHEN play_type = 'kickoff' THEN posteam ELSE defteam END AS side,
           unnest(CASE WHEN play_type = 'kickoff' THEN ['kickoff_returns', 'kickoff_return_yards', 'kickoff_return_tds']
                       ELSE ['punt_returns', 'punt_return_yards', 'punt_return_tds'] END) AS stat,
           unnest([1, ret_yds, ret_td::INT]) AS value
    FROM ret
)
WHERE value IS NOT NULL AND player IS NOT NULL AND player <> ''
"""

# Settle each stat row's team: the player's roster team when exactly one of
# the two teams lists him, else his side on the play. Then turn the fumble
# placeholders into fumbles / fumbles_lost / recoveries.
_EVENTS_SQL = """
CREATE OR REPLACE TEMP TABLE _hist_events AS
WITH roster_team AS (
    SELECT r.player_id, g.game_id, any_value(r.team) AS team
    FROM fact_rosters r
    JOIN (SELECT DISTINCT game_id, season, home_team, away_team FROM _hist_raw) g
      ON r.season = g.season AND r.team IN (g.home_team, g.away_team)
    WHERE r.player_id IN (SELECT player_id FROM _hist_raw)
    GROUP BY ALL HAVING count(DISTINCT r.team) = 1
),
e AS (
    SELECT x.*, coalesce(x.player_id, m.player_id) AS pid
    FROM _hist_raw x
    LEFT JOIN _hist_name_ids m
      ON m.game_id = x.game_id AND m.name = x.player AND m.side IS NOT DISTINCT FROM x.side
),
t AS (
    SELECT e.*, coalesce(rt.team, e.side) AS team
    FROM e LEFT JOIN roster_team rt ON rt.player_id = e.pid AND rt.game_id = e.game_id
),
fum AS (
    SELECT f.*, split_part(f.stat, '#', 2) AS i, nullif(split_part(f.stat, '#', 3), '') AS recoverer
    FROM t f WHERE f.stat LIKE 'fumble#%'
),
rec AS (
    SELECT r.*, split_part(r.stat, '#', 2) AS i,
           split_part(r.stat, '#', 4) = '1' OR r.team = r.scoring_team AS td
    FROM t r WHERE r.stat LIKE 'recovery#%'
)
SELECT season, season_type, game_id, play_seq, player, pid AS player_id, team, stat, value
FROM t WHERE stat NOT LIKE 'fumble#%' AND stat NOT LIKE 'recovery#%'
UNION ALL
SELECT fum.season, fum.season_type, fum.game_id, fum.play_seq, fum.player, fum.pid, fum.team,
       unnest(['fumbles', 'fumbles_lost']),
       -- lost: recovered by the other team; with no recoverer (or his team
       -- unknown), the other team has the ball next
       unnest([1, coalesce(CASE WHEN rec.team IS NOT NULL THEN rec.team <> fum.team END,
                           fum.next_posteam <> fum.team, false)::INT])
FROM fum LEFT JOIN rec ON rec.game_id = fum.game_id AND rec.play_seq = fum.play_seq AND rec.i = fum.i
UNION ALL
SELECT rec.season, rec.season_type, rec.game_id, rec.play_seq, rec.player, rec.pid, rec.team,
       unnest([CASE WHEN rec.team IS NOT DISTINCT FROM fum.team THEN 'fumble_recovery_own'
                    ELSE 'fumble_recovery_opp' END, 'fumble_recovery_tds']),
       unnest([1, rec.td::INT])
FROM rec LEFT JOIN fum ON fum.game_id = rec.game_id AND fum.play_seq = rec.play_seq AND fum.i = rec.i
"""


def _pivot(agg_of: dict[str, str]) -> str:
    return ",\n       ".join(
        f"coalesce({agg}(value) FILTER (WHERE stat = '{c}'), 0)::{t} AS {c}" if agg == "sum"
        else f"{agg}(value) FILTER (WHERE stat = '{c}')::{t} AS {c}"
        for c, t, agg in STAT_COLUMNS if c in agg_of)


def _position(alias: str) -> str:
    return f"""(SELECT r.position FROM fact_rosters r WHERE r.season = {alias}.season AND r.player_id = {alias}.player_id
        ORDER BY r.team = {alias}.team DESC LIMIT 1)"""


PLAYER_GAME_SQL = f"""
INSERT INTO fact_historical_player_game_stats BY NAME
WITH g AS (
    SELECT e.game_id, e.season, e.season_type, e.player_id, e.player AS player_name, e.team,
           {_pivot({c for c, _, _ in STAT_COLUMNS})}
    FROM _hist_events e
    GROUP BY ALL
)
SELECT g.game_id, g.season::SMALLINT AS season, d.week::SMALLINT AS week, g.season_type,
       g.player_id, g.player_name, {_position('g')} AS position, g.team,
       CASE WHEN g.team = d.home_team THEN d.away_team WHEN g.team = d.away_team THEN d.home_team END AS opponent,
       g.* EXCLUDE (game_id, season, season_type, player_id, player_name, team),
       'pfr_pbp' AS source
FROM g JOIN (SELECT DISTINCT game_id, week, home_team, away_team FROM fact_historical_plays) d USING (game_id)
ORDER BY g.game_id, g.team, g.player_name
"""

PLAYER_SEASON_SQL = """
INSERT INTO fact_historical_player_season_stats BY NAME
SELECT season, season_type, player_id, player_name, {position} AS position, team,
       count(*)::SMALLINT AS games,
       {sums},
       'pfr_pbp' AS source
FROM fact_historical_player_game_stats g
GROUP BY season, season_type, player_id, player_name, team
ORDER BY season, season_type, team, player_name
""".format(position=_position("g"), sums=",\n       ".join(
    f"{agg}({c})::{t} AS {c}" for c, t, agg in STAT_COLUMNS))

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


def _match_extra_names(con: duckdb.DuckDBPyConnection) -> None:
    """Ids for names the play-by-play's own matching didn't cover (a split
    sack's second player, fumblers and recoverers past the first, blocked
    punters), by the same name matching against fact_rosters."""
    names = con.execute("""
        SELECT DISTINCT season, game_id, home_team, away_team, player AS name, side AS team
        FROM _hist_raw WHERE player_id IS NULL""").pl()
    rosters = con.execute(
        "SELECT season, team, player_name, player_id FROM fact_rosters WHERE season <= 1998").pl()
    if names.is_empty() or rosters.is_empty():
        matched = names.with_columns(player_id=pl.lit(None, pl.Utf8))
    else:
        matched = match_player_ids(names, rosters)
    con.register("_hist_name_ids_df", matched.select("game_id", "name", pl.col("team").alias("side"), "player_id"))
    con.execute("CREATE OR REPLACE TEMP TABLE _hist_name_ids AS SELECT * FROM _hist_name_ids_df")
    con.unregister("_hist_name_ids_df")


# Seasons whose play-by-play text leaves out (nearly) every blocked punt:
# 1987 has 2 and 1988 none, where PFR's season tables list 29 and 23.
BLOCKED_PUNTS_UNRECORDED = (1987, 1988)


def build_historical_stats(con: duckdb.DuckDBPyConnection) -> tuple[int, int, int]:
    con.execute(_SCORES_SQL)
    con.execute(_PLAYS_SQL)
    con.execute(_RAW_EVENTS_SQL)
    _match_extra_names(con)
    con.execute(_EVENTS_SQL)
    for t in ("fact_historical_player_game_stats", "fact_historical_player_season_stats",
              "fact_historical_team_season_stats"):
        con.execute(f"DELETE FROM {t}")
    con.execute(PLAYER_GAME_SQL)
    # There 0 would be wrong, not known.
    con.execute("UPDATE fact_historical_player_game_stats SET punts_blocked = NULL "
                f"WHERE season IN {BLOCKED_PUNTS_UNRECORDED}")
    con.execute(PLAYER_SEASON_SQL)
    con.execute(TEAM_SEASON_SQL)
    for t in ("_hist_scores", "_hist_off", "_hist_raw", "_hist_name_ids", "_hist_events"):
        con.execute(f"DROP TABLE {t}")
    return tuple(con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in (
        "fact_historical_player_game_stats", "fact_historical_player_season_stats",
        "fact_historical_team_season_stats"))


# Kept for callers of the old name.
def build_historical_season_stats(con: duckdb.DuckDBPyConnection) -> tuple[int, int]:
    _, players, teams = build_historical_stats(con)
    return players, teams
