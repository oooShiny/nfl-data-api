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
