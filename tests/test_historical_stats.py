import duckdb

from api.routers.advanced import player_season_stats, team_stats
from pipeline.gold.historical_stats import build_historical_season_stats
from pipeline.gold.schema import SCHEMA_SQL

G = "1998_01_NE_DEN"


def _db():
    con = duckdb.connect()
    con.execute(SCHEMA_SQL)
    con.execute("""INSERT INTO fact_rosters (season, team, player_name, player_id, position) VALUES
        (1998, 'DEN', 'John Elway', '00-E', 'QB'), (1998, 'DEN', 'Rod Smith', '00-S', 'WR'),
        (1998, 'DEN', 'Terrell Davis', '00-D', 'RB'), (1998, 'NE', 'Ty Law', '00-L', 'CB')""")
    plays = [
        # (seq, posteam, play_type, desc, yards, td, passer, rusher, receiver, home_score, away_score, extra)
        (1, "DEN", "pass", "John Elway pass complete to Rod Smith for 20 yards, touchdown", 20, True,
         "John Elway", None, "Rod Smith", 6, 0, {}),
        (2, "DEN", "pass", "John Elway pass incomplete intended for Rod Smith", None, False,
         "John Elway", None, "Rod Smith", 6, 0, {}),
        (3, "DEN", "pass", "John Elway sacked by Ty Law for 7 yards", -7, False,
         "John Elway", None, None, 6, 0, {"sacker": "Ty Law"}),
        # Accepted grounding: an attempt for the penalized passer.
        (4, "DEN", "no_play", "Penalty on John Elway: Intentional Grounding, 10 yards (accepted)", None, False,
         None, None, None, 6, 0, {"penalized_player": "John Elway", "penalized_player_id": "00-E"}),
        # Pick-six: an interception, not a passing TD.
        (5, "DEN", "pass", "John Elway pass intended for Rod Smith is intercepted by Ty Law and returned "
         "for 40 yards, touchdown", None, True, "John Elway", None, "Rod Smith", 6, 6, {"interceptor": "Ty Law"}),
        (6, "DEN", "run", "Terrell Davis left end for 5 yards, touchdown", 5, True,
         None, "Terrell Davis", None, 12, 6, {}),
        # Penalty-nullified play: doesn't count.
        (7, "DEN", "no_play", "Terrell Davis middle for 9 yards. Penalty on X: Holding (accepted) (no play)", None,
         False, None, None, None, 12, 6, {}),
        (8, "DEN", "qb_kneel", "John Elway kneels for -1 yards", -1, False, None, "John Elway", None, 12, 6, {}),
        # A botched snap PFR's expected points give to NE: Elway's row stays DEN.
        (9, "NE", "run", "John Elway fumbles, recovered by Rod Smith at NE0", 0, False,
         None, "John Elway", None, 12, 6, {}),
    ]
    for seq, pos, pt, desc, yds, td, passer, rusher, rec, h, a, extra in plays:
        ids = {"passer_id": "00-E" if passer == "John Elway" else None,
               "rusher_id": {"Terrell Davis": "00-D", "John Elway": "00-E"}.get(rusher),
               "receiver_id": "00-S" if rec else None}
        cols = dict(game_id=G, play_seq=seq, season=1998, week=1, game_type="REG", home_team="DEN",
                    away_team="NE", posteam=pos, defteam="NE" if pos == "DEN" else "DEN", quarter=1,
                    play_type=pt, description=desc, yards_gained=yds, touchdown=td, two_point_attempt=False,
                    passer=passer, rusher=rusher, receiver=rec, home_score=h, away_score=a, **ids, **extra)
        con.execute(f"INSERT INTO fact_historical_plays ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                    list(cols.values()))
    build_historical_season_stats(con)
    return con


def test_player_and_team_season_stats():
    con = _db()
    rows = {r[0]: r[1:] for r in con.execute("""
        SELECT player_name, team, position, completions, attempts, passing_yards, passing_tds,
               passing_interceptions, sacks_suffered, sack_yards_lost, carries, rushing_yards, rushing_tds,
               targets, receptions, receiving_yards, receiving_tds
        FROM fact_historical_player_season_stats""").fetchall()}
    assert rows["John Elway"] == ("DEN", "QB", 1, 4, 20, 1, 1, 1, 7, 2, -1, 0, 0, 0, 0, 0)
    assert rows["Terrell Davis"] == ("DEN", "RB", 0, 0, 0, 0, 0, 0, 0, 1, 5, 1, 0, 0, 0, 0)
    assert rows["Rod Smith"] == ("DEN", "WR", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 1, 20, 1)

    team = con.execute("""SELECT team, attempts, completions, passing_yards, sack_yards_lost, net_passing_yards,
                                 passing_tds, passing_interceptions, carries, rushing_yards, rushing_tds
                          FROM fact_historical_team_season_stats ORDER BY team""").fetchall()
    # The botched snap PFR gave to NE stays on NE's team line.
    assert team == [("DEN", 4, 1, 20, 7, 13, 1, 1, 2, 4, 1), ("NE", 0, 0, 0, 0, 0, 0, 0, 1, 0, 0)]


def test_stats_endpoints_read_historical_tables_before_1999():
    con = _db()
    out = player_season_stats(None, player_id=None, season=1998, season_type=None, position="QB",
                              limit=50, offset=0, db=con)
    assert [(d["player_name"], d["source"]) for d in out.data] == [("John Elway", "pfr_pbp")]
    out = player_season_stats(None, player_id="00-E", season=None, season_type=None, position=None,
                              limit=50, offset=0, db=con)
    assert out.total == 1  # both tables, no nflverse rows here
    out = team_stats(None, season=1998, team="DEN", season_type=None, limit=50, offset=0, db=con)
    assert out.data[0]["net_passing_yards"] == 13
