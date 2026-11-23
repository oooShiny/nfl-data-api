import duckdb

from api.routers import meta


def test_coverage_counts_per_season_and_tolerates_missing_tables():
    meta._coverage_cache.clear()
    con = duckdb.connect()
    con.execute("CREATE TABLE dim_games (game_id VARCHAR, season INT, result INT)")
    con.execute("""INSERT INTO dim_games VALUES
        ('1999_01_A_B', 1999, 3), ('1999_02_A_C', 1999, -7),
        ('2000_01_A_B', 2000, 1), ('2000_02_A_C', 2000, NULL)""")  # 2000 still being played
    con.execute("CREATE TABLE fact_plays (game_id VARCHAR, season INT)")
    con.execute("INSERT INTO fact_plays VALUES ('1999_01_A_B', 1999), ('1999_01_A_B', 1999), ('2000_01_A_B', 2000)")

    out = meta.coverage(con)

    assert out["current_season"] == 2000 and out["current_season_in_progress"] is True
    assert out["games_per_season"] == {1999: 2, 2000: 1}
    rows = {r["label"]: r["seasons"] for g in out["groups"] for r in g["rows"]}
    assert rows["Game results"] == {1999: 2, 2000: 1}
    assert rows["Play-by-play (EPA/WPA)"] == {1999: 2, 2000: 1}
    assert rows["Snap counts"] == {}  # table absent: empty row, not an error
    assert [g["name"] for g in out["groups"]][0] == "Games & Schedules"
    meta._coverage_cache.clear()
    con.close()
