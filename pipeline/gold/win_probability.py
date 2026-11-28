"""Win probability for pre-1999 play-by-play (fact_historical_plays).

PFR's play-by-play has no win probability, so we estimate it with a small
logistic model fit on 1999+ nflverse plays (scripts/fit_wp_model.py writes the
coefficients to pipeline/mappings/wp_model.json). It uses only what both eras
have:

  margin = score differential + expected points (team with the ball)
  t      = share of the game left (seconds remaining / 3600)

  logit(wp) = b0 + b1 margin/sqrt(t) + b2 diff/sqrt(t) + b3 spread*sqrt(t)
              + b4 home*sqrt(t) + b5 margin

the shape of PFR's own win probability formula (the lead plus the field
position's worth, against a margin spread that shrinks with the time left,
with the pregame spread fading out). No timeouts: PFR doesn't record them.

Like nflverse, there are two versions:
- wp: no pregame spread (b3 = 0), comparable to nflverse's wp;
- vegas_wp: with the pregame spread. That is dim_games.spread_line (PFR's
  Vegas line) where we have it, otherwise a spread estimated from
  FiveThirtyEight's QB-adjusted Elo (ref_team_elo), using a separate fit.

PFR's clock is only on the first play of each drive and quarter, so the time
left on other plays is spaced evenly between those. The fit uses nflverse
plays with their clocks thinned out the same way. PFR's expected points are
missing for 1993 and a few other plays; those are filled with PFR's average
expected points for the down, distance and field position in other seasons.
"""
import json
from pathlib import Path

import duckdb

MODEL_PATH = Path(__file__).resolve().parent.parent / "mappings" / "wp_model.json"

FEATURES = ["const", "margin_t", "diff_t", "spread_t", "home_t", "margin"]


def elo_code(team: str, season: str) -> str:
    """SQL: one of our team codes -> the current franchise code ref_team_elo uses."""
    return f"""CASE {team} WHEN 'OAK' THEN 'LV' WHEN 'RAI' THEN 'LV' WHEN 'SD' THEN 'LAC'
        WHEN 'SLC' THEN 'ARI' WHEN 'PHX' THEN 'ARI' WHEN 'STL' THEN 'LA'
        WHEN 'HOU' THEN CASE WHEN {season} < 1999 THEN 'TEN' ELSE 'HOU' END
        WHEN 'BAL' THEN CASE WHEN {season} <= 1983 THEN 'IND' ELSE 'BAL' END
        ELSE {team} END"""


def game_spreads_sql(model: dict | None) -> str:
    """SQL relation: per game, the Vegas line and the Elo-estimated line (home's view)."""
    home, away = elo_code("g.home_team", "g.season"), elo_code("g.away_team", "g.season")
    if model:
        e = model["elo_spread"]
        elo_spread = (f"{e['const']} + {e['qbelo_diff']} * qh"
                      f" + {e['home']} * (CASE WHEN neutral THEN 0 ELSE 1 END)")
    else:  # fitting: the script fits this itself
        elo_spread = "NULL::DOUBLE"
    return f"""(
        SELECT game_id, season, spread_line, qh, neutral, result, {elo_spread} AS elo_spread
        FROM (
            SELECT g.game_id, g.season, g.spread_line::DOUBLE AS spread_line, g.result,
                   (g.location = 'Neutral' OR (g.season < 1999 AND g.game_type = 'SB')) AS neutral,
                   any_value(CASE WHEN e.team1_norm = {home}
                        THEN e.qbelo1_pre - e.qbelo2_pre + coalesce(e.qb1_adj, 0) - coalesce(e.qb2_adj, 0)
                        ELSE e.qbelo2_pre - e.qbelo1_pre + coalesce(e.qb2_adj, 0) - coalesce(e.qb1_adj, 0)
                   END)::DOUBLE AS qh
            FROM dim_games g
            LEFT JOIN ref_team_elo e ON e.date = g.gameday
                AND {home} IN (e.team1_norm, e.team2_norm) AND {away} IN (e.team1_norm, e.team2_norm)
            GROUP BY ALL
        )
    )"""


def _interpolated_seconds(src: str) -> str:
    """SQL: add `secs` to a relation with game_id, seq, quarter, known_secs
    (game seconds left, only on some plays): known where given, else spaced
    evenly by play between the nearest known plays in the quarter (the quarter's
    start and end when there is none)."""
    return f"""(
        SELECT * EXCLUDE (i, n, a_i, a_s, b_i, b_s),
            CASE WHEN known_secs IS NOT NULL THEN known_secs::DOUBLE ELSE
                coalesce(a_s, q_start) + (coalesce(b_s, q_end) - coalesce(a_s, q_start))
                * (i - coalesce(a_i, -1)) / (coalesce(b_i, n) - coalesce(a_i, -1)) END AS secs
        FROM (
            SELECT *,
                last_value(CASE WHEN known_secs IS NOT NULL THEN i END IGNORE NULLS) OVER before AS a_i,
                last_value(known_secs IGNORE NULLS) OVER before AS a_s,
                first_value(CASE WHEN known_secs IS NOT NULL THEN i END IGNORE NULLS) OVER after AS b_i,
                first_value(known_secs IGNORE NULLS) OVER after AS b_s
            FROM (
                SELECT *,
                    row_number() OVER (PARTITION BY game_id, quarter ORDER BY seq) - 1 AS i,
                    count(*) OVER (PARTITION BY game_id, quarter) AS n,
                    CASE WHEN quarter <= 4 THEN (5 - quarter) * 900 ELSE 900 END::DOUBLE AS q_start,
                    CASE WHEN quarter <= 4 THEN (4 - quarter) * 900 ELSE 0 END::DOUBLE AS q_end
                FROM {src}
            )
            WINDOW before AS (PARTITION BY game_id, quarter ORDER BY seq
                              ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),
                   after AS (PARTITION BY game_id, quarter ORDER BY seq
                             ROWS BETWEEN 1 FOLLOWING AND UNBOUNDED FOLLOWING)
        )
    )"""


def nflverse_inputs_sql() -> str:
    """SQL: model inputs for 1999+ nflverse plays (for fitting), with clocks
    thinned to the first play of each drive and quarter, as PFR has them."""
    src = """(
        SELECT p.game_id, p.play_id AS seq, p.season, p.quarter, p.posteam, p.home_team, p.play_type,
               p.score_differential::DOUBLE AS diff, p.ep::DOUBLE AS ep,
               p.game_seconds_remaining::DOUBLE AS true_secs,
               CASE WHEN p.drive IS DISTINCT FROM lag(p.drive) OVER w
                      OR p.quarter IS DISTINCT FROM lag(p.quarter) OVER w
                    THEN p.game_seconds_remaining END AS known_secs
        FROM fact_plays p
        WHERE p.posteam IS NOT NULL AND p.play_type IS NOT NULL AND p.ep IS NOT NULL
          AND p.score_differential IS NOT NULL AND p.game_seconds_remaining IS NOT NULL
        WINDOW w AS (PARTITION BY p.game_id ORDER BY p.play_id)
    )"""
    return _interpolated_seconds(src)


def pfr_inputs_sql() -> str:
    """SQL: model inputs for fact_historical_plays."""
    ep_table = """(
        SELECT down, least(ydstogo, 21) AS togo, yardline_100, avg(exp_pts_before) AS ep_avg
        FROM fact_historical_plays
        WHERE exp_pts_before IS NOT NULL AND down IS NOT NULL AND play_type IN ('pass', 'run', 'punt', 'field_goal')
        GROUP BY ALL
    )"""
    src = f"""(
        SELECT p.game_id, p.play_seq AS seq, p.season, p.quarter, p.posteam, p.home_team, p.play_type,
               (p.posteam_score - p.defteam_score)::DOUBLE AS diff,
               coalesce(p.exp_pts_before, t.ep_avg)::DOUBLE AS ep,
               p.game_seconds_remaining::DOUBLE AS known_secs
        FROM fact_historical_plays p
        LEFT JOIN {ep_table} t ON t.down = p.down AND t.togo = least(p.ydstogo, 21) AND t.yardline_100 = p.yardline_100
        WHERE p.posteam IS NOT NULL AND p.posteam_score IS NOT NULL AND p.quarter IS NOT NULL
    )"""
    return _interpolated_seconds(src)


def feature_sql(model: dict, spread: str) -> dict[str, str]:
    """SQL for each model feature, from an inputs row (m) joined to game
    spreads (s). Kickoffs and tries use fixed expected points (the two eras
    value them differently); other plays with no expected points count as 0."""
    ep = (f"CASE WHEN m.play_type = 'kickoff' THEN {model['kickoff_ep']} "
          f"WHEN m.play_type = 'extra_point' THEN {model['extra_point_ep']} ELSE coalesce(m.ep, 0) END")
    rt = "sqrt(greatest(m.secs, 1) / 3600.0)"
    home = "CASE WHEN s.neutral THEN 0 WHEN m.posteam = m.home_team THEN 1 ELSE -1 END"
    return {
        "const": "1.0",
        "margin_t": f"(m.diff + {ep}) / {rt}",
        "diff_t": f"m.diff / {rt}",
        "spread_t": f"({spread}) * {rt}",
        "home_t": f"({home}) * {rt}",
        "margin": f"(m.diff + {ep})",
    }


def logit_sql(model: dict, part: str, spread: str) -> str:
    """SQL: log-odds of the team with the ball winning, for model part
    'wp' (spread ignored), 'vegas_wp' or 'elo_wp'."""
    coef = model[part]["coef"]
    feats = feature_sql(model, spread)
    return "(" + " + ".join(f"{coef[k]} * {feats[k]}" for k in FEATURES if coef.get(k)) + ")"


def posteam_spread(column: str) -> str:
    """SQL: a home-view spread column of s, from the team with the ball's view."""
    return f"(CASE WHEN m.posteam = m.home_team THEN s.{column} ELSE -s.{column} END)"


def load_model() -> dict | None:
    return json.loads(MODEL_PATH.read_text()) if MODEL_PATH.exists() else None


def derive_historical_wp(con: duckdb.DuckDBPyConnection) -> int:
    """Fill fact_historical_plays.wp/wpa/vegas_wp/vegas_wpa. Returns rows filled."""
    model = load_model()
    if model is None:
        return 0
    has_elo = con.execute(
        "SELECT count(*) FROM duckdb_tables() WHERE table_name = 'ref_team_elo'").fetchone()[0]
    if not has_elo:  # e.g. a partial test database: Vegas lines only
        con.execute("CREATE TEMP TABLE ref_team_elo AS SELECT NULL::DATE date, NULL::VARCHAR team1_norm, "
                    "NULL::VARCHAR team2_norm, NULL::FLOAT qbelo1_pre, NULL::FLOAT qbelo2_pre, "
                    "NULL::FLOAT qb1_adj, NULL::FLOAT qb2_adj WHERE false")
    wp = f"1 / (1 + exp(-{logit_sql(model, 'wp', '0')}))"
    vegas = (f"CASE WHEN s.spread_line IS NOT NULL "
             f"THEN 1 / (1 + exp(-{logit_sql(model, 'vegas_wp', posteam_spread('spread_line'))})) "
             f"WHEN s.elo_spread IS NOT NULL "
             f"THEN 1 / (1 + exp(-{logit_sql(model, 'elo_wp', posteam_spread('elo_spread'))})) END")
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _hist_wp AS
        WITH probs AS (
            SELECT m.game_id, m.seq, m.posteam,
                   CASE WHEN s.result IS NULL THEN NULL WHEN s.result = 0 THEN 0.5
                        WHEN (s.result > 0) = (m.posteam = m.home_team) THEN 1.0 ELSE 0.0 END AS final,
                   {wp} AS wp, {vegas} AS vegas_wp
            FROM {pfr_inputs_sql()} m
            JOIN {game_spreads_sql(model)} s USING (game_id)
        ),
        nxt AS (
            SELECT *, lead(posteam) OVER w AS next_team, lead(wp) OVER w AS next_wp,
                      lead(vegas_wp) OVER w AS next_vegas_wp
            FROM probs WINDOW w AS (PARTITION BY game_id ORDER BY seq)
        )
        SELECT game_id, seq, wp, vegas_wp,
            -- Next play's probability from this team's view; after the last
            -- play, the result.
            CASE WHEN next_team IS NULL THEN final WHEN next_team = posteam THEN next_wp ELSE 1 - next_wp END
                - wp AS wpa,
            CASE WHEN next_team IS NULL THEN final
                 WHEN next_team = posteam THEN next_vegas_wp ELSE 1 - next_vegas_wp END - vegas_wp AS vegas_wpa
        FROM nxt
    """)
    con.execute("""
        UPDATE fact_historical_plays p
        SET wp = w.wp, wpa = w.wpa, vegas_wp = w.vegas_wp, vegas_wpa = w.vegas_wpa
        FROM _hist_wp w WHERE w.game_id = p.game_id AND w.seq = p.play_seq
    """)
    n = con.execute("SELECT count(*) FROM _hist_wp WHERE wp IS NOT NULL").fetchone()[0]
    con.execute("DROP TABLE _hist_wp")
    if not has_elo:
        con.execute("DROP TABLE ref_team_elo")
    return n
