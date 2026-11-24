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
        ('2010_01_DAL_PHI', 2010, 1, 'REG', DATE '2010-09-12', 'PHI', 'DAL', 3, 14, '201009120phi'),
        ('2010_01_NYG_WAS', 2010, 1, 'REG', DATE '2010-09-12', 'WAS', 'NYG', 3, 0, NULL),
        ('2005_01_NYG_WAS', 2005, 1, 'REG', DATE '2005-09-11', 'WAS', 'NYG', 0, 7, NULL)""")
    # A PFR row for a pre-2007 game, which must not be re-derived.
    con.execute(f"""COPY (SELECT '2005_01_NYG_WAS' AS game_id, 2005 AS season, DATE '2005-09-11' AS gameday,
        1 AS play_seq, 1 AS quarter, '100' AS time, 'NYG' AS scoring_team, 0 AS home_score, 7 AS away_score,
        'X 1 yard rush (Y kick)' AS description, NULL AS boxscore_url)
        TO '{silver / "historical_scoring" / "2005.parquet"}' (FORMAT parquet)""")
    cols = ("game_id, play_id, season, qtr, quarter_seconds_remaining, \"desc\", home_team, away_team, "
            "touchdown, extra_point_attempt, two_point_attempt, total_home_score, total_away_score")
    con.execute(f"""COPY (SELECT * FROM (VALUES
        -- DAL TD + flagged PAT; a glitch row dips the score; FG; DAL TD + an
        -- unflagged PAT (after a penalty).
        ('2010_01_DAL_PHI', 1, 2010, 1, 900, 'kickoff', 'PHI', 'DAL', 0, 0, 0, 0, 0),
        ('2010_01_DAL_PHI', 2, 2010, 1, 600, '(10:00) T.Romo pass to J.Witten, TOUCHDOWN.', 'PHI', 'DAL', 1, 0, 0, 0, 6),
        ('2010_01_DAL_PHI', 3, 2010, 1, 600, 'D.Buehler extra point is GOOD', 'PHI', 'DAL', 0, 1, 0, 0, 7),
        ('2010_01_DAL_PHI', 4, 2010, 2, 500, 'glitch', 'PHI', 'DAL', 0, 0, 0, 0, 0),
        ('2010_01_DAL_PHI', 5, 2010, 2, 400, '(6:40) D.Akers 40 yard field goal is GOOD', 'PHI', 'DAL', 0, 0, 0, 3, 7),
        ('2010_01_DAL_PHI', 6, 2010, 4, 300, '(5:00) F.Jones 2 yard run, TOUCHDOWN.', 'PHI', 'DAL', 1, 0, 0, 3, 13),
        ('2010_01_DAL_PHI', 7, 2010, 4, 300, 'PENALTY ... D.Buehler kick GOOD', 'PHI', 'DAL', 0, 0, 0, 3, 14),
        -- Derived final (3-3) doesn't match dim_games (3-0): skipped.
        ('2010_01_NYG_WAS', 1, 2010, 1, 100, 'FG GOOD', 'WAS', 'NYG', 0, 0, 0, 3, 3)
        ) t({cols})) TO '{silver / "pbp" / "play_by_play_2010.parquet"}' (FORMAT parquet)""")

    loader.load_fact_game_scoring(con)

    rows = con.execute("""SELECT game_id, play_seq, quarter, time, scoring_team, home_score, away_score,
                                 description, boxscore_url, source
                          FROM fact_game_scoring ORDER BY game_id, play_seq""").fetchall()
    url = "https://www.pro-football-reference.com/boxscores/201009120phi.htm"
    assert rows == [
        ("2005_01_NYG_WAS", 1, 1, "100", "NYG", 0, 7, "X 1 yard rush (Y kick)", None, "pfr"),
        ("2010_01_DAL_PHI", 1, 1, "600", "DAL", 0, 7, "T.Romo pass to J.Witten, TOUCHDOWN.", url, "nflverse"),
        ("2010_01_DAL_PHI", 2, 2, "400", "PHI", 3, 7, "D.Akers 40 yard field goal is GOOD", url, "nflverse"),
        ("2010_01_DAL_PHI", 3, 4, "300", "DAL", 3, 14, "F.Jones 2 yard run, TOUCHDOWN.", url, "nflverse"),
    ]
    con.close()
