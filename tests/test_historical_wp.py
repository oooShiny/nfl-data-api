"""Win probability for pre-1999 plays (pipeline/gold/win_probability.py)."""
import duckdb
import pytest

from pipeline.gold import win_probability as wpm
from pipeline.gold.loader import load_historical_win_probability
from pipeline.gold.schema import SCHEMA_SQL


def _db():
    con = duckdb.connect()
    con.execute(SCHEMA_SQL)
    con.execute("""INSERT INTO dim_games (game_id, season, game_type, gameday, home_team, away_team,
                                          home_score, away_score, result, spread_line) VALUES
        ('1985_01_DAL_NYG', 1985, 'REG', '1985-09-08', 'NYG', 'DAL', 10, 17, -7, -3.0),
        ('1975_01_DAL_NYG', 1975, 'REG', '1975-09-21', 'NYG', 'DAL', 21, 7, 14, NULL)""")
    plays = []
    for gid in ("1985_01_DAL_NYG", "1975_01_DAL_NYG"):
        plays += [
            (gid, 1, 1, "NYG", "kickoff", 0, 0, None, "15:00", 3600, None, None, None),
            (gid, 2, 1, "NYG", "run", 0, 0, 0.6, None, None, 1, 10, 75),
            (gid, 3, 1, "DAL", "pass", 0, 0, 1.2, "9:00", 3240, 1, 10, 60),
            (gid, 4, 4, "DAL", "pass", 7, 0, 3.9, "1:00", 60, 1, 10, 20),  # DAL up 7, 1 min left
        ]
    con.executemany("""INSERT INTO fact_historical_plays (game_id, play_seq, quarter, posteam, play_type,
            posteam_score, defteam_score, exp_pts_before, clock, game_seconds_remaining, down, ydstogo,
            yardline_100, season, home_team, away_team)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1985, 'NYG', 'DAL')""", plays)
    return con


def test_win_probability_for_pfr_plays():
    con = _db()
    load_historical_win_probability(con)
    rows = con.execute("""SELECT game_id, play_seq, wp, wpa, vegas_wp, vegas_wpa FROM fact_historical_plays
                          ORDER BY game_id DESC, play_seq""").fetchall()
    by = {(g, s): r for g, s, *r in rows}
    wp, wpa, vegas_wp, vegas_wpa = by[("1985_01_DAL_NYG", 4)]
    assert wp > 0.95  # a 7-point lead with a minute left, already in field goal range
    # Last play: the result (DAL won) minus the probability before it.
    assert wpa == pytest.approx(1 - wp, abs=1e-6)
    assert vegas_wpa == pytest.approx(1 - vegas_wp, abs=1e-6)
    # DAL was a 3-point road favorite, so the spread version likes them more at the start.
    nyg_start_wp, nyg_start_vegas = by[("1985_01_DAL_NYG", 1)][0], by[("1985_01_DAL_NYG", 1)][2]
    assert nyg_start_vegas < nyg_start_wp
    # WPA chains: NYG's play 1 -> NYG's play 2 -> DAL's play 3 (from NYG's view, 1 - DAL's wp).
    assert by[("1985_01_DAL_NYG", 2)][1] == pytest.approx(1 - by[("1985_01_DAL_NYG", 3)][0] - by[("1985_01_DAL_NYG", 2)][0], abs=1e-6)
    # No Vegas line and no Elo (not loaded in this database): no vegas_wp, but wp.
    assert by[("1975_01_DAL_NYG", 4)][0] is not None and by[("1975_01_DAL_NYG", 4)][2] is None
    # Shows up in the unified view.
    assert con.execute("SELECT count(wp), count(vegas_wp) FROM v_plays WHERE source = 'pfr'").fetchone() == (8, 4)
    con.close()


def test_missing_clocks_are_spaced_between_known_ones():
    con = duckdb.connect()
    con.execute("""CREATE TABLE src AS SELECT * FROM (VALUES
        ('g', 1, 1, 3600), ('g', 2, 1, NULL), ('g', 3, 1, NULL), ('g', 4, 1, 3000), ('g', 5, 1, NULL),
        ('g', 6, 2, NULL)) t(game_id, seq, quarter, known_secs)""")
    secs = con.execute(f"SELECT secs FROM {wpm._interpolated_seconds('src')} ORDER BY seq").fetchall()
    # 3600 -> 3000 over three plays; after the last known play, on to the quarter's end
    # (2700); a lone play in a quarter with no clock goes halfway through it (2700 -> 1800).
    assert [round(s[0]) for s in secs] == [3600, 3400, 3200, 3000, 2850, 2250]
