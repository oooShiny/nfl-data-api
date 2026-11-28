import duckdb
import polars as pl
import pytest
from fastapi import HTTPException

from api.routers.plays import list_plays
from pipeline.gold import loader
from pipeline.gold.schema import SCHEMA_SQL
from pipeline.silver.cleaners import clean_dataset
from tests.test_historical_pbp import _bronze_rows

# nflverse columns load_fact_plays reads; anything not given is NULL.
_NFLVERSE_STR = [
    "game_id", "posteam", "defteam", "play_type", "season_type", "home_team", "away_team", "time",
    "side_of_field", "desc",
    *[f"{r}_player_{k}" for r in ("passer", "rusher", "receiver", "interception", "sack", "kicker", "punter",
                                  "penalty", "half_sack_1", "kickoff_returner", "punt_returner",
                                  "solo_tackle_1", "solo_tackle_2", "tackle_with_assist_1", "tackle_with_assist_2",
                                  "assist_tackle_1", "assist_tackle_2", "forced_fumble_player_1", "fumble_recovery_1")
      for k in ("id", "name")],
]
_NFLVERSE_NUM = [
    "play_id", "season", "week", "qtr", "game_seconds_remaining", "half_seconds_remaining",
    "quarter_seconds_remaining", "down", "ydstogo", "yardline_100", "posteam_score", "defteam_score",
    "score_differential", "yards_gained", "touchdown", "interception", "fumble_lost", "penalty", "penalty_yards",
    "first_down", "ep", "epa", "wp", "wpa", "air_epa", "yac_epa", "comp_air_epa", "comp_yac_epa", "qb_epa",
    "xyac_epa", "series", "series_success", "drive", "sp", "total_home_score", "total_away_score",
    "two_point_attempt",
]


def _nflverse_rows(rows):
    return pl.DataFrame(
        [{**{c: None for c in _NFLVERSE_STR + _NFLVERSE_NUM}, **r} for r in rows],
        schema={**{c: pl.Utf8 for c in _NFLVERSE_STR}, **{c: pl.Float64 for c in _NFLVERSE_NUM},
                "game_date": pl.Date},
    )


@pytest.fixture
def con(tmp_path, monkeypatch):
    silver = tmp_path / "silver"
    (silver / "pbp").mkdir(parents=True)
    (silver / "historical_pbp").mkdir()
    base = dict(game_id="2005_01_OAK_NE", season=2005, week=1, season_type="REG", home_team="NE", away_team="LV",
                posteam="NE", defteam="LV", qtr=1, game_seconds_remaining=3300, interception=0, fumble_lost=0)
    _nflverse_rows([
        {**base, "play_id": 50, "play_type": "pass", "time": "10:00", "desc": "T.Brady pass to D.Branch for 18 yards",
         "passer_player_id": "00-TB", "passer_player_name": "T.Brady", "receiver_player_id": "00-DB",
         "receiver_player_name": "D.Branch", "solo_tackle_1_player_id": None,
         "assist_tackle_1_player_id": "00-A1", "assist_tackle_1_player_name": "A.One",
         "assist_tackle_2_player_id": "00-A2", "assist_tackle_2_player_name": "A.Two",
         "total_home_score": 0, "total_away_score": 0, "epa": 1.2, "wp": 0.6},
        {**base, "play_id": 75, "play_type": "punt", "punter_player_id": "00-P", "punter_player_name": "J.Miller",
         "punt_returner_player_id": "00-R", "punt_returner_player_name": "J.Rice",
         "total_home_score": 0, "total_away_score": 0},
    ]).write_parquet(silver / "pbp" / "play_by_play_2005.parquet")
    src = tmp_path / "1998.parquet"
    _bronze_rows().write_parquet(src)
    clean_dataset("historical_pbp", src).write_parquet(silver / "historical_pbp" / "1998.parquet")
    monkeypatch.setattr(loader, "SILVER_DIR", silver)

    c = duckdb.connect()
    c.execute(SCHEMA_SQL)
    c.execute("""INSERT INTO fact_rosters (season, team, player_name, player_id) VALUES
        (1998, 'NE', 'Drew Bledsoe', '00-B'), (1998, 'NE', 'Ben Coates', '00-C')""")
    c.execute("INSERT INTO dim_games (game_id, season, gameday) VALUES ('1998_01_NE_DEN', 1998, '1998-09-07')")
    loader.load_fact_plays(c)
    loader.load_fact_historical_plays(c)
    yield c
    c.close()


def _plays(db, **kw):
    args = dict(game_id=None, season=None, week=None, season_type=None, team=None, posteam=None, play_type=None,
                player_id=None, limit=50, offset=0)
    return list_plays(None, db=db, **(args | kw))


def test_fact_plays_carries_description_clock_and_player_roles(con):
    row = con.execute("""SELECT clock, description, home_score, passer_player_name, receiver_player_id,
                                tackler_1_player_name, tackler_2_player_name FROM fact_plays WHERE play_id = 50""").fetchone()
    assert row == ("10:00", "T.Brady pass to D.Branch for 18 yards", 0, "T.Brady", "00-DB", "A.One", "A.Two")
    # Punt and kickoff returners share one returner column.
    assert con.execute("SELECT returner_player_name FROM fact_plays WHERE play_id = 75").fetchone() == ("J.Rice",)


def test_plays_endpoint_serves_both_eras_in_one_shape(con):
    out = _plays(con, team="NE")
    assert out.total == 5
    assert [(r["source"], r["season"], r["play_id"]) for r in out.data] == [
        ("pfr", 1998, 1), ("pfr", 1998, 2), ("pfr", 1998, 3), ("nflverse", 2005, 50), ("nflverse", 2005, 75)]
    assert set(out.data[0]) == set(out.data[-1])  # same columns in both eras

    pfr = out.data[1]
    assert (pfr["passer_player_name"], pfr["passer_player_id"], pfr["receiver_player_id"]) == ("Drew Bledsoe", "00-B", "00-C")
    assert pfr["season_type"] == "REG" and str(pfr["game_date"]) == "1998-09-07"
    assert pfr["ep"] == 0 and pfr["epa"] == pytest.approx(0.38) and pfr["wp"] is None
    # Score before the play (PFR gives it after), and seconds left from the clock.
    assert out.data[0]["game_seconds_remaining"] == 3600
    assert out.data[2]["home_score"] == 6

    # Any player role, either era.
    assert _plays(con, player_id="00-C").total == 1
    assert _plays(con, player_id="00-R").data[0]["returner_player_name"] == "J.Rice"
    assert _plays(con, season=2005, play_type="punt").total == 1
    with pytest.raises(HTTPException):
        _plays(con)
