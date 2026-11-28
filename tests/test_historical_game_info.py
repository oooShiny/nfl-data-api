"""PFR boxscore game info (Vegas line, weather, scorebox) -> dim_games for pre-1999 games."""
import json

import duckdb
import polars as pl

from pipeline.bronze import local_sources
from pipeline.gold import loader
from pipeline.gold.schema import SCHEMA_SQL
from pipeline.silver.cleaners import clean_dataset


def _page(line, over_under, weather=None, roof="outdoors", teams=None):
    info = [{"info": "Roof", "stat": roof}, {"info": "Surface", "stat": "grass"},
            {"info": "Vegas Line", "stat": line}, {"info": "Over/Under", "stat": over_under}]
    if weather:
        info.append({"info": "Weather*", "stat": weather})
    page = {"game_info": info, "scoring": []}
    if teams:
        page["_scorebox"] = [{
            "meta": ["Sunday Sep 8, 1985", "Start Time: 4:05pm", "Stadium: Texas Stadium",
                     "Attendance: 63,855", "Time of Game: 3:12"],
            "teams": [{"team_href": f"/teams/{t}/1985.htm", "coach": c, "coach_href": ""} for t, c in teams],
        }]
    return page


def test_game_info_fills_pre_1999_dim_games(tmp_path, monkeypatch):
    pages = {
        # Dallas favored by 3 on the road; the scorebox lists the away team first.
        "1985_01_DAL_NYG": _page("Dallas Cowboys -3.0", "41.5 (over)",
                                 "35 degrees, relative humidity 63%, wind 10 mph, wind chill 28",
                                 teams=[("dal", "Tom Landry"), ("nyg", "Bill Parcells")]),
        # Dallas favored at home.
        "1985_02_WSH_DAL": _page("Dallas Cowboys -6.5", "38.0 (under)", roof="dome",
                                 teams=[("was", "Joe Gibbs"), ("dal", "Tom Landry")]),
        "1985_03_NYG_WSH": _page("Pick", "40.0 (push)", "60 degrees, relative humidity 50%, wind 5 mph",
                                 teams=[("nyg", "Bill Parcells"), ("was", "Joe Gibbs")]),
    }
    box = tmp_path / "scraped" / "1985"
    box.mkdir(parents=True)
    for game_id, page in pages.items():
        (box / f"{game_id}.json").write_text(json.dumps(page))
    bronze = tmp_path / "bronze"
    monkeypatch.setattr(local_sources, "SCRAPED_BOXSCORE_DIR", tmp_path / "scraped")
    monkeypatch.setattr(local_sources, "BRONZE_DIR", bronze)
    assert local_sources.import_historical_game_info() == 1

    silver = tmp_path / "silver"
    (silver / "historical_game_info").mkdir(parents=True)
    (silver / "historical_gamelogs").mkdir(parents=True)
    info = clean_dataset("historical_game_info", bronze / "historical_game_info" / "1985.parquet")
    info.write_parquet(silver / "historical_game_info" / "1985.parquet")
    row = info.filter(pl.col("game_id") == "1985_01_DAL_NYG").row(0, named=True)
    assert (row["temp"], row["humidity"], row["wind"], row["wind_chill"]) == (35, 63, 10, 28)
    assert (row["favorite"], row["favorite_by"], row["total_line"], row["total_result"]) == \
        ("Dallas Cowboys", 3.0, 41.5, "over")
    assert (row["stadium"], row["attendance"], row["start_time"], row["game_duration"]) == \
        ("Texas Stadium", 63855, "16:05", "3:12")

    pl.DataFrame({
        "game_id": list(pages),
        "season": [1985] * 3, "week": [1, 2, 3], "game_type": ["REG"] * 3,
        "gameday": pl.Series(["1985-09-08", "1985-09-15", "1985-09-22"]).str.to_date(),
        "home_team": ["NYG", "DAL", "WSH"], "away_team": ["DAL", "WSH", "NYG"],
        "home_score": [10, 20, 14], "away_score": [17, 3, 14], "result": [-7, 17, 0], "total": [27, 23, 28],
        "boxscore_url": ["u1", "u2", "u3"],
    }).write_parquet(silver / "historical_gamelogs" / "1985.parquet")
    monkeypatch.setattr(loader, "SILVER_DIR", silver)

    con = duckdb.connect()
    con.execute(SCHEMA_SQL)
    loader.load_historical_games(con)
    rows = con.execute("""
        SELECT game_id, spread_line, total_line, roof, temp, humidity, weekday, home_coach, away_coach, attendance
        FROM dim_games ORDER BY game_id""").fetchall()
    assert rows == [
        ("1985_01_DAL_NYG", -3.0, 41.5, "outdoors", 35, 63, "Sunday", "Bill Parcells", "Tom Landry", 63855),
        ("1985_02_WSH_DAL", 6.5, 38.0, "dome", None, None, "Sunday", "Tom Landry", "Joe Gibbs", 63855),
        ("1985_03_NYG_WSH", 0.0, 40.0, "outdoors", 60, 50, "Sunday", "Joe Gibbs", "Bill Parcells", 63855),
    ]
    con.close()
