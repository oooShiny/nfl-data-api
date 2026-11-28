import duckdb
import polars as pl
import pytest
from fastapi import HTTPException

from api.routers.games import list_historical_plays
from pipeline.gold import loader
from pipeline.gold.schema import SCHEMA_SQL
from pipeline.silver.cleaners import clean_dataset
from pipeline.silver.pfr_pbp_parser import parse_detail


@pytest.mark.parametrize("detail, expected", [
    ("Jamal Anderson middle for 3 yards (tackle by Sean Gilbert)",
     {"play_type": "run", "rusher": "Jamal Anderson", "yards_gained": 3, "tackler_1": "Sean Gilbert"}),
    ("Jamal Anderson right tackle for -3 yards (tackle by Kevin Greene)",
     {"play_type": "run", "yards_gained": -3}),
    ("Kerry Collins pass complete to Mark Carrier for 22 yards (tackle by Eugene Robinson)",
     {"play_type": "pass", "passer": "Kerry Collins", "receiver": "Mark Carrier", "yards_gained": 22}),
    ("Kerry Collins pass incomplete intended for Muhsin Muhammad",
     {"play_type": "pass", "passer": "Kerry Collins", "receiver": "Muhsin Muhammad", "yards_gained": None}),
    ("Tony Banks sacked by Jared Tomich for 9 yards",
     {"play_type": "pass", "passer": "Tony Banks", "sacker": "Jared Tomich", "yards_gained": -9}),
    ("Jake Plummer sacked by Kavika Pittman and Tony Tolbert for 8 yards",  # split sack
     {"play_type": "pass", "passer": "Jake Plummer", "sacker": "Kavika Pittman", "yards_gained": -8}),
    # A sack with no "for N yards" before the next sentence: the name stops there.
    ("John Elway sacked by Clyde Simmons. John Elway fumbles (forced by Clyde Simmons and Reggie White for 7 yards",
     {"play_type": "pass", "passer": "John Elway", "sacker": "Clyde Simmons"}),
    ("Troy Aikman pass intended for Eric Bjornson is intercepted by Ronald McKinnon at AC30 and returned for 4 yards",
     {"play_type": "pass", "passer": "Troy Aikman", "receiver": "Eric Bjornson", "interceptor": "Ronald McKinnon"}),
    # The defender fumbles on the return; the receiver has initials.
    ("J.J. Stokes pass intended for R.W. McQuarters. Ty Law fumbles is intercepted by Ty Law at NE40",
     {"play_type": "pass", "passer": "J.J. Stokes", "receiver": "R.W. McQuarters", "interceptor": "Ty Law"}),
    ("Elvis Grbac pass. Todd Lyght fumbles is intercepted by Todd Lyght at SL4 and returned for 14 yards",
     {"play_type": "pass", "passer": "Elvis Grbac", "receiver": None, "interceptor": "Todd Lyght"}),
    ("Curtis Conway 4 yard pass from Erik Kramer",  # unrecognized pass phrasing: type only
     {"play_type": "pass", "passer": None}),
    ("Tom Rouen aborted snap", {"play_type": "run", "rusher": "Tom Rouen", "yards_gained": 0}),
    ("Dan Marino fumbles, recovered by Dan Marino at NY50", {"play_type": "run", "rusher": "Dan Marino"}),
    ("Fred Lane left end for no gain. Penalty on Matt Elliott: False Start, 5 yards (accepted) (no play)",
     {"play_type": "no_play", "rusher": None}),
    ("Kerry Collins spiked the ball", {"play_type": "qb_spike", "passer": "Kerry Collins"}),
    ("John Kasay kicks off 71 yards, returned by Tim Dwight for 19 yards",
     {"play_type": "kickoff", "kicker": "John Kasay", "returner": "Tim Dwight"}),
    # 1980s text: the tackle before the return, or no kick at all.
    ("Neil O'Donoghue kicks off 58 yards, (tackle by Neil O'Donoghue) returned by Gary Allen for 34 yards",
     {"play_type": "kickoff", "kicker": "Neil O'Donoghue", "returner": "Gary Allen"}),
    ("returned by Gary Allen for 15 yards (tackle by Joe Hayes)",
     {"play_type": "kickoff", "kicker": None, "returner": "Gary Allen", "tackler_1": "Joe Hayes"}),
    ("Jason Elam 63 yard field goal good", {"play_type": "field_goal", "kicker": "Jason Elam"}),
    ("Penalty on Bob Whitfield: False Start, 4 yards (accepted)",
     {"play_type": "no_play", "penalized_player": "Bob Whitfield"}),
    ("Terrell Davis left end for 12 yards, touchdown",
     {"play_type": "run", "touchdown": True, "yards_gained": 12}),
    ("Two Point Attempt: Terrell Davis right guard for 2 yards, touchdown",
     {"play_type": "run", "two_point_attempt": True, "touchdown": False}),
    ("Falcons won the coin toss, Falcons to receive the opening kickoff.", {"play_type": None}),
    (None, {"play_type": None, "touchdown": False}),
])
def test_parse_detail(detail, expected):
    out = parse_detail(detail)
    for key, value in expected.items():
        assert out[key] == value, key


def _bronze_rows():
    # All-string, as the bronze importer writes them.
    base = dict(game_id="1998_01_NE_DEN", season="1998", week="1", game_type="REG",
                home_team="DEN", away_team="NE",
                boxscore_url="https://www.pro-football-reference.com/boxscores/199809070den.htm",
                time="", down="", yds_to_go="", exp_pts_before="0.000", exp_pts_after="0.380")
    return pl.DataFrame([
        {**base, "play_seq": "1", "quarter": "1", "time": "15:00", "location": "DEN 30",
         "away_score": "0", "home_score": "0", "detail": "Jason Elam kicks off 70 yards"},
        {**base, "play_seq": "2", "quarter": "1", "down": "1", "yds_to_go": "10", "location": "NWE 25",
         "away_score": "0", "home_score": "0", "detail": "Drew Bledsoe pass complete to Ben Coates for 8 yards"},
        # Description truncated before ", touchdown": the score jump marks it.
        {**base, "play_seq": "3", "quarter": "OT", "location": "",
         "away_score": "0", "home_score": "6", "detail": "Drew Bledsoe fumbles, recovered by Bill Romanowski at"},
    ])


def test_clean_historical_pbp(tmp_path):
    src = tmp_path / "1998.parquet"
    _bronze_rows().write_parquet(src)

    df = clean_dataset("historical_pbp", src)

    assert df["quarter"].to_list() == [1, 1, 5]
    assert df["yardline_side"].to_list() == ["DEN", "NE", None]  # NWE -> NE
    assert df["yardline"].to_list() == [30, 25, None]
    assert df["play_type"].to_list() == ["kickoff", "pass", "run"]  # a botched snap is a rush
    assert df["touchdown"].to_list() == [False, False, True]
    assert df["clock"].to_list() == ["15:00", None, None]
    assert df.schema["exp_pts_after"] == pl.Float64


def test_score_lag_after_touchdown_is_not_a_second_touchdown(tmp_path):
    # 1989-90: with a failed conversion PFR puts the 6 on the row after the
    # touchdown (the missed kick, or a blank row).
    base = dict(game_id="1989_06_NE_ATL", season="1989", week="6", game_type="REG",
                home_team="ATL", away_team="NE", quarter="2", time="", down="", yds_to_go="",
                location="", exp_pts_before="", exp_pts_after="", home_score="0",
                boxscore_url="https://www.pro-football-reference.com/boxscores/198910150atl.htm")
    rows = [
        ("1", "0", "Doug Flutie pass complete to Cedric Jones for 15 yards, touchdown"),
        ("2", "6", "Greg Davis kicks extra point no good"),
        ("3", "6", "Doug Flutie pass complete to Cedric Jones for 15 yards, touchdown"),
        ("4", "12", None),
        ("5", "12", "Greg Davis kicks off 55 yards"),
        # A blank row with a 6-point jump after a play not called a touchdown
        # (a fumble return cut short) is still the touchdown.
        ("6", "12", "Doug Flutie fumbles, recovered by John Stephens at"),
        ("7", "18", None),
    ]
    src = tmp_path / "1989.parquet"
    pl.DataFrame([{**base, "play_seq": q, "away_score": a, "detail": d} for q, a, d in rows]).write_parquet(src)

    df = clean_dataset("historical_pbp", src)

    assert df["touchdown"].to_list() == [True, False, True, False, False, False, True]


def test_1987_score_jumps_next_to_a_touchdown_are_not_another_one(tmp_path):
    base = dict(game_id="1987_13_KC_CIN", season="1987", week="13", game_type="REG",
                home_team="CIN", away_team="KC", quarter="2", time="", down="", yds_to_go="",
                location="", exp_pts_before="", exp_pts_after="", home_score="0",
                boxscore_url="https://www.pro-football-reference.com/boxscores/198712060cin.htm")
    rows = [
        # The 6 lands on the play before the touchdown...
        ("1", "6", "Bill Kenney pass incomplete intended for Stephone Paige"),
        ("2", "7", "Bill Kenney pass complete to Stephone Paige for 24 yards, touchdown"),
        # ...or on an offsetting penalty after the try.
        ("3", "7", "Bill Kenney pass complete to Stephone Paige for 24 yards, touchdown"),
        ("4", "7", "Nick Lowery kicks extra point no good"),
        ("5", "13", "Penalty on Louis Breeden: Unnecessary Roughness (offset)"),
        # A touchdown whose text is only the declined penalty still counts.
        ("6", "13", "Christian Okoye middle for 3 yards"),
        ("7", "19", "Penalty on CIN: Offside (declined)"),
    ]
    src = tmp_path / "1987.parquet"
    pl.DataFrame([{**base, "play_seq": q, "away_score": a, "detail": d} for q, a, d in rows]).write_parquet(src)

    assert clean_dataset("historical_pbp", src)["touchdown"].to_list() == [False, True, True, False, False, False, True]


def test_load_fact_historical_plays_and_endpoint(tmp_path, monkeypatch):
    silver = tmp_path / "silver"
    (silver / "historical_pbp").mkdir(parents=True)
    src = tmp_path / "1998.parquet"
    _bronze_rows().write_parquet(src)
    clean_dataset("historical_pbp", src).write_parquet(silver / "historical_pbp" / "1998.parquet")
    monkeypatch.setattr(loader, "SILVER_DIR", silver)

    con = duckdb.connect()
    con.execute(SCHEMA_SQL)
    con.execute("""INSERT INTO fact_rosters (season, team, player_name, player_id) VALUES
        (1998, 'NE', 'Drew Bledsoe', '00-B'), (1998, 'NE', 'Ben Coates', '00-C')""")
    loader.load_fact_historical_plays(con)

    rows = con.execute("SELECT play_seq, play_type, passer, touchdown FROM fact_historical_plays ORDER BY 1").fetchall()
    assert rows == [(1, "kickoff", None, False), (2, "pass", "Drew Bledsoe", False), (3, "run", None, True)]

    out = list_historical_plays(None, season=1998, team="NE", play_type="pass", limit=50, offset=0, db=con,
                                game_id=None, week=None, posteam=None, player_id=None)
    assert out.total == 1 and out.data[0]["receiver"] == "Ben Coates"
    assert (out.data[0]["passer_id"], out.data[0]["receiver_id"]) == ("00-B", "00-C")
    out = list_historical_plays(None, season=1998, player_id="00-C", limit=50, offset=0, db=con,
                                game_id=None, week=None, team=None, play_type=None, posteam=None)
    assert out.total == 1
    with pytest.raises(HTTPException):
        list_historical_plays(None, game_id=None, season=None, week=None, team=None, play_type=None,
                              posteam=None, player_id=None, limit=50, offset=0, db=con)
    con.close()


def test_pfr_stl_is_the_cardinals_through_1987(tmp_path):
    rows = _bronze_rows().with_columns(pl.lit("1987").alias("season"), pl.lit("1987_01_DAL_SLC").alias("game_id"),
                                       pl.lit("SLC").alias("home_team"), pl.lit("DAL").alias("away_team"),
                                       pl.Series("location", ["STL 30", "DAL 25", ""]))
    src = tmp_path / "1987.parquet"
    rows.write_parquet(src)
    assert clean_dataset("historical_pbp", src)["yardline_side"].to_list() == ["SLC", "DAL", None]

    rams = _bronze_rows().with_columns(pl.lit("STL").alias("home_team"), pl.Series("location", ["STL 30", "NWE 25", ""]))
    rams.write_parquet(src)
    assert clean_dataset("historical_pbp", src)["yardline_side"].to_list() == ["STL", "NE", None]
