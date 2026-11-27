import duckdb

from api.routers.advanced import player_game_stats, player_season_stats, team_stats
from api.routers.players import get_player_stats
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


def test_rushing_tds_follow_the_running_score_through_its_quirks():
    con = duckdb.connect()
    con.execute(SCHEMA_SQL)
    g = "1990_01_MIA_NE"
    rows = [  # (seq, play_type, description, rusher, home_score, away_score)
        # 1989-90: the 6 lands on the conversion, after a penalty row.
        (1, "run", "John Stephens left guard for 1 yard, touchdown", "John Stephens", 0, 0),
        (2, "no_play", "Penalty on NE: Illegal Procedure, 5 yards (accepted)", None, 0, 0),
        (3, "extra_point", "Jason Staurovsky kicks extra point good", None, 7, 0),
        # The running score misses this one entirely.
        (4, "run", "John Stephens middle for 4 yards, touchdown", "John Stephens", 7, 0),
        (5, "extra_point", "Jason Staurovsky kicks extra point good", None, 7, 0),
        # A fumble recovered in the end zone is the recoverer's touchdown.
        (6, "run", "John Stephens middle for 1 yard. John Stephens fumbles, recovered by "
            "Bruce Armstrong at MIA0, touchdown", "John Stephens", 13, 0),
        (7, "extra_point", "Jason Staurovsky kicks extra point good", None, 14, 0),
    ]
    for seq, pt, desc, rusher, h, a in rows:
        cols = dict(game_id=g, play_seq=seq, season=1990, week=1, game_type="REG", home_team="NE",
                    away_team="MIA", posteam="NE", defteam="MIA", quarter=1, play_type=pt, description=desc,
                    yards_gained=1 if rusher else None, touchdown="touchdown" in desc,
                    two_point_attempt=False, rusher=rusher, home_score=h, away_score=a)
        con.execute(f"INSERT INTO fact_historical_plays ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                    list(cols.values()))
    build_historical_season_stats(con)
    rows = con.execute("""SELECT player_name, carries, rushing_tds, fumbles, fumbles_lost,
                                 fumble_recovery_own, fumble_recovery_tds
                          FROM fact_historical_player_season_stats ORDER BY player_name""").fetchall()
    # Armstrong has no roster row here, so his team is unknown and the
    # fumble isn't called lost.
    assert rows == [("Bruce Armstrong", 0, 0, 0, 0, 0, 1), ("John Stephens", 3, 2, 1, 0, 0, 0)]


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

    # Game lines: every column before 1999 by season or game_id...
    out = player_game_stats(None, player_id=None, game_id=G, season=None, week=None, season_type=None,
                            team="DEN", limit=50, offset=0, db=con)
    assert {d["player_name"] for d in out.data} == {"John Elway", "Rod Smith", "Terrell Davis"}
    assert all(d["source"] == "pfr_pbp" for d in out.data)
    # ...and, with nflverse's column names, in the player's game log.
    out = get_player_stats("00-E", season=None, week=None, season_type=None, limit=50, offset=0, db=con)
    elway = out.data[0]
    assert (elway.recent_team, elway.attempts, elway.interceptions) == ("DEN", 4, 1)


def test_defense_kicking_punting_and_return_lines():
    con = duckdb.connect()
    con.execute(SCHEMA_SQL)
    g = "1995_01_NE_DEN"
    roster = [("DEN", "John Elway", "00-E"), ("DEN", "Terrell Davis", "00-D"), ("DEN", "Jason Elam", "00-K"),
              ("DEN", "Tom Rouen", "00-P"), ("DEN", "Glyn Milburn", "00-M"),
              ("NE", "Willie McGinest", "00-W"), ("NE", "Chris Slade", "00-C"), ("NE", "Ty Law", "00-L"),
              ("NE", "Tom Tupa", "00-T"), ("NE", "Dave Meggett", "00-G")]
    con.executemany("INSERT INTO fact_rosters (season, team, player_name, player_id, position) VALUES (1995, ?, ?, ?, 'X')",
                    roster)
    ids = {n: i for _, n, i in roster}
    rows = [  # (seq, posteam, play_type, description, yards, td, roles, home_score, away_score)
        (1, "DEN", "pass", "John Elway sacked by Willie McGinest and Chris Slade for 8 yards", -8, False,
         {"passer": "John Elway", "sacker": "Willie McGinest"}, 0, 0),
        (2, "DEN", "pass", "John Elway pass intended for Glyn Milburn is intercepted by Ty Law at DEN40 and "
         "returned for 40 yards, touchdown", None, True,
         {"passer": "John Elway", "receiver": "Glyn Milburn", "interceptor": "Ty Law"}, 0, 7),
        (3, "DEN", "run", "Terrell Davis left end for 4 yards (tackle by Chris Slade)", 4, False,
         {"rusher": "Terrell Davis", "tackler_1": "Chris Slade"}, 0, 7),
        (4, "DEN", "run", "Terrell Davis middle for 2 yards (tackle by Chris Slade and Ty Law)", 2, False,
         {"rusher": "Terrell Davis", "tackler_1": "Chris Slade", "tackler_2": "Ty Law"}, 0, 7),
        (5, "DEN", "run", "Terrell Davis middle for 1 yard. Terrell Davis fumbles (forced by Ty Law), "
         "recovered by Willie McGinest at DEN30", 1, False,
         {"rusher": "Terrell Davis", "forced_fumble_player": "Ty Law",
          "fumble_recovery_player": "Willie McGinest"}, 0, 7),
        (6, "DEN", "field_goal", "Jason Elam 43 yard field goal good", None, False, {"kicker": "Jason Elam"}, 3, 7),
        (7, "DEN", "field_goal", "Jason Elam 52 yard field goal no good blocked by Chris Slade", None, False,
         {"kicker": "Jason Elam"}, 3, 7),
        (8, "DEN", "extra_point", "Jason Elam kicks extra point no good", None, False, {"kicker": "Jason Elam"}, 3, 7),
        (9, "DEN", "punt", "Tom Rouen punts 45 yards, returned by Dave Meggett for 60 yards, touchdown", None, True,
         {"punter": "Tom Rouen", "returner": "Dave Meggett"}, 3, 14),
        (10, "DEN", "punt", "Tom Rouen punts 50 yards, muffed catch by Dave Meggett. Dave Meggett fumbles, "
         "recovered by Dave Meggett at NE20", None, False, {"punter": "Tom Rouen"}, 3, 14),
        (11, "DEN", "other", "Tom Rouen punts blocked by Chris Slade", None, False, {}, 3, 14),
        (12, "DEN", "other", "Tom Rouen punts, recovered by Ty Law", None, False, {}, 3, 14),
        (13, "DEN", "kickoff", "Tom Tupa kicks off 65 yards, returned by Glyn Milburn for 25 yards "
         "(tackle by Dave Meggett)", None, False,
         {"kicker": "Tom Tupa", "returner": "Glyn Milburn", "tackler_1": "Dave Meggett"}, 3, 14),
        # No recoverer named: lost, because NE has the ball next.
        (14, "DEN", "run", "Terrell Davis middle for 3 yards. Terrell Davis fumbles", 3, False,
         {"rusher": "Terrell Davis"}, 3, 14),
        (15, "NE", "run", "Curtis Martin left end for 2 yards", 2, False, {"rusher": "Curtis Martin"}, 3, 14),
    ]
    for seq, pos, pt, desc, yds, td, roles, h, a in rows:
        cols = dict(game_id=g, play_seq=seq, season=1995, week=1, game_type="REG", home_team="DEN", away_team="NE",
                    posteam=pos, defteam="NE", quarter=1, play_type=pt, description=desc, yards_gained=yds,
                    touchdown=td, two_point_attempt=False, home_score=h, away_score=a,
                    **roles, **{f"{r}_id": ids.get(n) for r, n in roles.items()})
        con.execute(f"INSERT INTO fact_historical_plays ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                    list(cols.values()))
    build_historical_season_stats(con)

    def line(name, *cols):
        return con.execute(f"SELECT team, {', '.join(cols)} FROM fact_historical_player_game_stats "
                           "WHERE player_name = ?", [name]).fetchone()

    assert line("Willie McGinest", "def_sacks", "def_sack_yards", "fumble_recovery_opp") == ("NE", 0.5, 4.0, 1)
    assert line("Chris Slade", "def_sacks") == ("NE", 0.5)
    assert line("Ty Law", "def_interceptions", "def_interception_yards", "def_interception_tds",
                "def_fumbles_forced") == ("NE", 1, 40, 1, 1)
    assert line("Terrell Davis", "carries", "fumbles", "fumbles_lost") == ("DEN", 4, 2, 2)
    assert line("Jason Elam", "fg_made", "fg_att", "fg_blocked", "fg_long", "fg_made_40_49", "fg_missed_50_59",
                "pat_made", "pat_att") == ("DEN", 1, 2, 1, 43, 1, 1, 0, 1)
    # Two punts with distances plus two blocked ones (both wordings), which
    # PFR doesn't count as punts.
    assert line("Tom Rouen", "punts", "punt_yards", "punt_long", "punts_blocked") == ("DEN", 2, 95, 50, 2)
    # The muff is a return of 0 yards and a fumble he recovered himself.
    assert line("Dave Meggett", "punt_returns", "punt_return_yards", "punt_return_tds", "fumbles", "fumbles_lost",
                "fumble_recovery_own") == ("NE", 2, 60, 1, 1, 0, 1)
    assert line("Glyn Milburn", "kickoff_returns", "kickoff_return_yards", "targets") == ("DEN", 1, 25, 1)
    assert line("John Elway", "attempts", "sacks_suffered", "passing_interceptions") == ("DEN", 1, 1, 1)

    season = con.execute("""SELECT games, punts, punt_returns FROM fact_historical_player_season_stats
                            WHERE player_name = 'Dave Meggett'""").fetchone()
    assert season == (1, 0, 2)
    assert con.execute("SELECT opponent FROM fact_historical_player_game_stats WHERE player_name = 'Ty Law'"
                       ).fetchone() == ("DEN",)


def test_blocked_punts_are_unknown_in_1987_and_1988():
    # PFR's 1987-88 text (nearly) never records a blocked punt, so 0 would be a guess.
    con = duckdb.connect()
    con.execute(SCHEMA_SQL)
    for season in (1986, 1988, 1989):
        cols = dict(game_id=f"{season}_01_NE_DEN", play_seq=1, season=season, week=1, game_type="REG",
                    home_team="DEN", away_team="NE", posteam="DEN", defteam="NE", quarter=1, play_type="punt",
                    description="Mike Horan punts 40 yards", touchdown=False, two_point_attempt=False,
                    punter="Mike Horan", home_score=0, away_score=0)
        con.execute(f"INSERT INTO fact_historical_plays ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                    list(cols.values()))
    build_historical_season_stats(con)
    for t in ("fact_historical_player_game_stats", "fact_historical_player_season_stats"):
        assert con.execute(f"SELECT season, punts, punts_blocked FROM {t} ORDER BY season").fetchall() == [
            (1986, 1, 0), (1988, 1, None), (1989, 1, 0)]
