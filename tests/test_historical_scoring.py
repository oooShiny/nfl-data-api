import polars as pl

from pipeline.silver import cleaners

URL = "https://www.pro-football-reference.com/boxscores/200301040gnb.htm"


def _bronze_rows():
    # Shape of the PFR scoring CSVs: "tm" is GB (home), "opp" is ATL.
    base = dict(season=2002, event_date="2003-01-04", tm_market="Green Bay", tm_name="Packers", tm_alias="GB",
                opp_market="Atlanta", opp_name="Falcons", opp_alias="ATL", boxscore_stats_link=URL)
    return pl.DataFrame([
        {**base, "quarter": 1.0, "time": "557", "scoring_team": "Falcons", "tm_score": 0, "opp_score": 7,
         "description": "Shawn Jefferson 10 yard pass from Michael Vick (Jay Feely kick)"},
        {**base, "quarter": 2.0, "time": "120", "scoring_team": "Packers", "tm_score": 7, "opp_score": 7,
         "description": "Ahman Green 1 yard rush (Ryan Longwell kick)"},
    ])


def test_clean_scoring_1999_plus_matches_schedules_on_pfr_id(tmp_path, monkeypatch):
    (tmp_path / "schedules").mkdir()
    pl.DataFrame([
        {"game_id": "2002_18_ATL_GB", "season": 2002, "home_team": "GB", "away_team": "ATL",
         "home_score": 7, "away_score": 7, "pfr": "200301040gnb"},
        {"game_id": "2001_01_X_Y", "season": 2001, "home_team": "Y", "away_team": "X",
         "home_score": 0, "away_score": 0, "pfr": "200109090gnb"},
    ]).write_parquet(tmp_path / "schedules" / "games.parquet")
    monkeypatch.setattr(cleaners, "SILVER_DIR", tmp_path)

    src = tmp_path / "2002.parquet"
    _bronze_rows().write_parquet(src)
    df = cleaners.clean_dataset("historical_scoring", src)

    assert df["game_id"].to_list() == ["2002_18_ATL_GB"] * 2
    assert df["scoring_team"].to_list() == ["ATL", "GB"]
    assert df["home_score"].to_list() == [0, 7]
    assert df["away_score"].to_list() == [7, 7]
    assert df["play_seq"].to_list() == [1, 2]
    assert df["boxscore_url"].to_list() == [URL] * 2


def _pbp_row(game_id, play_id, qtr, secs, desc, home, away, h, a, **kw):
    from pipeline.gold.loader import _PBP_EVENT_COLUMNS
    row = {c: None for c in _PBP_EVENT_COLUMNS}
    row.update(game_id=game_id, play_id=float(play_id), season=int(game_id[:4]), qtr=float(qtr),
               quarter_seconds_remaining=float(secs), desc=desc, home_team=home, away_team=away,
               touchdown=0.0, safety=0.0, extra_point_attempt=0.0, two_point_attempt=0.0,
               total_home_score=float(h), total_away_score=float(a))
    row.update(kw)
    return row


def test_scoring_derived_from_nflverse_pbp(tmp_path, monkeypatch):
    import duckdb

    from pipeline.gold import loader
    from pipeline.gold.schema import SCHEMA_SQL

    silver = tmp_path / "silver"
    (silver / "historical_scoring").mkdir(parents=True)
    (silver / "pbp").mkdir()
    monkeypatch.setattr(loader, "SILVER_DIR", silver)
    con = duckdb.connect()
    con.execute(SCHEMA_SQL)
    con.execute("""INSERT INTO dim_games (game_id, season, week, game_type, gameday, home_team, away_team,
                                          home_score, away_score, pfr) VALUES
        ('2010_01_DAL_PHI', 2010, 1, 'REG', DATE '2010-09-12', 'PHI', 'DAL', 3, 22, '201009120phi'),
        ('2010_01_NYG_WAS', 2010, 1, 'REG', DATE '2010-09-12', 'WAS', 'NYG', 3, 0, NULL),
        ('2005_01_NYG_WAS', 2005, 1, 'REG', DATE '2005-09-11', 'WAS', 'NYG', 0, 7, NULL)""")
    con.execute("""INSERT INTO dim_players (gsis_id, display_name, pfr_id) VALUES
        ('00-R', 'Tony Romo', 'RomoTo00'), ('00-W', 'Jason Witten', 'WittJa00'), ('00-K', 'David Buehler', NULL),
        ('00-A', 'David Akers', NULL), ('00-J', 'Felix Jones', NULL), ('00-M', 'Mike Jenkins', NULL)""")
    con.execute("""INSERT INTO ref_pfr_rosters (season, pfr_player_id, player) VALUES
        (2010, 'RomoTo00', 'Antonio Romo')""")  # PFR's spelling wins over display_name
    # A PFR row for a pre-2007 game, which must not be re-derived.
    con.execute(f"""COPY (SELECT '2005_01_NYG_WAS' AS game_id, 2005 AS season, DATE '2005-09-11' AS gameday,
        1 AS play_seq, 1 AS quarter, '100' AS time, 'NYG' AS scoring_team, 0 AS home_score, 7 AS away_score,
        'Tiki Barber 1 yard rush (Jay Feely kick) ' AS description, NULL AS boxscore_url)
        TO '{silver / "historical_scoring" / "2005.parquet"}' (FORMAT parquet)""")

    g, hm, aw = "2010_01_DAL_PHI", "PHI", "DAL"
    pbp = pl.DataFrame([
        _pbp_row(g, 1, 1, 900, "kickoff", hm, aw, 0, 0, play_type="kickoff"),
        # Passing TD and a flagged PAT.
        _pbp_row(g, 2, 1, 600, "(10:00) T.Romo pass to J.Witten for 12 yards, TOUCHDOWN.", hm, aw, 0, 6,
                 play_type="pass", posteam=aw, td_team=aw, touchdown=1.0, pass_touchdown=1.0, yards_gained=12.0,
                 td_player_id="00-W", td_player_name="J.Witten", passer_player_id="00-R", passer_player_name="T.Romo",
                 receiver_player_id="00-W"),
        _pbp_row(g, 3, 1, 600, "D.Buehler extra point is GOOD", hm, aw, 0, 7, play_type="extra_point",
                 extra_point_attempt=1.0, extra_point_result="good", kicker_player_id="00-K"),
        # A glitch row dips the running score.
        _pbp_row(g, 4, 2, 500, "glitch", hm, aw, 0, 0),
        # FG on a penalty play (play_type NULL); the score lands a row late, on a timeout.
        _pbp_row(g, 5, 2, 400, "(6:40) D.Akers 40 yard field goal is GOOD. PENALTY ...", hm, aw, 0, 7,
                 field_goal_result="made", kick_distance=40.0, kicker_player_id="00-A", kicker_player_name="D.Akers"),
        _pbp_row(g, 6, 2, 390, "Timeout #1 by DAL", hm, aw, 3, 7, play_type="no_play"),
        # Rushing TD, then an unflagged PAT (after a penalty).
        _pbp_row(g, 7, 4, 300, "(5:00) F.Jones 2 yard run, TOUCHDOWN.", hm, aw, 3, 13, play_type="run",
                 posteam=aw, td_team=aw, touchdown=1.0, rush_touchdown=1.0, yards_gained=2.0, td_player_id="00-J"),
        _pbp_row(g, 8, 4, 300, "PENALTY ... D.Buehler kick GOOD", hm, aw, 3, 14, kicker_player_id="00-K"),
        # Interception return TD (return_yards 0, yardage only in the text), failed 2-pt run.
        _pbp_row(g, 9, 4, 120, "(2:00) M.Vick pass INTERCEPTED by M.Jenkins. M.Jenkins for 44 yards, TOUCHDOWN.",
                 hm, aw, 3, 20, play_type="pass", posteam=hm, td_team=aw, touchdown=1.0, interception=1.0,
                 return_touchdown=1.0, return_yards=0.0, td_player_id="00-M"),
        _pbp_row(g, 10, 4, 120, "TWO-POINT CONVERSION ATTEMPT. F.Jones rushes. ATTEMPT FAILS.", hm, aw, 3, 20,
                 play_type="run", two_point_attempt=1.0, two_point_conv_result="failure"),
        # Safety.
        _pbp_row(g, 11, 4, 30, "(0:30) M.Vick sacked in end zone, SAFETY.", hm, aw, 3, 22, play_type="pass",
                 posteam=hm, safety=1.0, safety_player_id="00-M"),
        # Derived final (3-3) doesn't match dim_games (3-0): skipped.
        _pbp_row("2010_01_NYG_WAS", 1, 1, 100, "FG GOOD", "WAS", "NYG", 3, 3, field_goal_result="made"),
    ])
    pbp.write_parquet(silver / "pbp" / "play_by_play_2010.parquet")

    loader.load_fact_game_scoring(con)

    rows = con.execute("""SELECT game_id, play_seq, quarter, time, scoring_team, home_score, away_score,
                                 description, source, scoring_type, scoring_method, yards, scorer, scorer_id,
                                 passer, try_type, try_result, try_player
                          FROM fact_game_scoring ORDER BY game_id, play_seq""").fetchall()
    assert rows == [
        ("2005_01_NYG_WAS", 1, 1, "100", "NYG", 0, 7, "Tiki Barber 1 yard rush (Jay Feely kick)", "pfr",
         "touchdown", "rush", 1, "Tiki Barber", None, None, "kick", "good", "Jay Feely"),
        (g, 1, 1, "600", "DAL", 0, 7, "Jason Witten 12 yard pass from Antonio Romo (David Buehler kick)", "nflverse",
         "touchdown", "pass", 12, "Jason Witten", "00-W", "Antonio Romo", "kick", "good", "David Buehler"),
        (g, 2, 2, "400", "PHI", 3, 7, "David Akers 40 yard field goal", "nflverse",
         "field_goal", "field_goal", 40, "David Akers", "00-A", None, None, None, None),
        (g, 3, 4, "300", "DAL", 3, 14, "Felix Jones 2 yard rush (David Buehler kick)", "nflverse",
         "touchdown", "rush", 2, "Felix Jones", "00-J", None, "kick", "good", "David Buehler"),
        (g, 4, 4, "120", "DAL", 3, 20, "Mike Jenkins 44 yard interception return (run failed)", "nflverse",
         "touchdown", "interception_return", 44, "Mike Jenkins", "00-M", None, "run", "failed", None),
        (g, 5, 4, "30", "DAL", 3, 22, "Safety", "nflverse",
         "safety", "safety", None, "Mike Jenkins", "00-M", None, None, None, None),
    ]
    play_desc = con.execute(
        f"SELECT play_description FROM fact_game_scoring WHERE game_id = '{g}' AND play_seq = 1").fetchone()[0]
    assert play_desc == "T.Romo pass to J.Witten for 12 yards, TOUCHDOWN."
    con.close()
