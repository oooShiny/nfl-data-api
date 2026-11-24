import duckdb
import pytest

from pipeline.gold import loader
from pipeline.gold.schema import SCHEMA_SQL


@pytest.fixture
def con(tmp_path, monkeypatch):
    silver = tmp_path / "silver"
    monkeypatch.setattr(loader, "SILVER_DIR", silver)
    c = duckdb.connect()
    c.execute(SCHEMA_SQL)
    c.execute("""INSERT INTO dim_games (game_id, season, week, game_type, gameday, home_team, away_team) VALUES
        ('2025_01_DAL_PHI', 2025, 1, 'REG', DATE '2025-09-04', 'PHI', 'DAL'),
        ('2025_02_KC_PHI',  2025, 2, 'REG', DATE '2025-09-14', 'PHI', 'KC'),
        ('2025_03_PHI_LA',  2025, 3, 'REG', DATE '2025-09-21', 'LA', 'PHI')""")
    c.execute("INSERT INTO dim_players (gsis_id, display_name, first_name, last_name, position) VALUES "
              "('00-1', 'Jalen Hurts', 'Jalen', 'Hurts', 'QB'), ('00-2', 'Saquon Barkley', 'Saquon', 'Barkley', 'RB')")
    yield c, silver
    c.close()


def _write(c, path, sql):
    path.parent.mkdir(parents=True, exist_ok=True)
    c.execute(f"COPY ({sql}) TO '{path}' (FORMAT parquet)")


def test_depth_charts_snapshot_format_maps_to_game_weeks(con):
    c, silver = con
    # Legacy weekly file for 2024 plus a 2025 snapshot file: an offseason snapshot,
    # one the day before week 1, one before week 2 (with a special-teams listing
    # for the same player), and nothing before week 3.
    _write(c, silver / "depth_charts" / "depth_charts_2024.parquet", """
        SELECT 2024 AS season, 'PHI' AS club_code, 1 AS week, 'REG' AS game_type, '1' AS depth_team,
               'Hurts' AS last_name, 'Jalen' AS first_name, '00-1' AS gsis_id, '1' AS jersey_number,
               'QB' AS position, 'QB' AS depth_position, 'Jalen Hurts' AS full_name""")
    _write(c, silver / "depth_charts" / "depth_charts_2025.parquet", """
        SELECT * FROM (VALUES
          ('2025-06-01T08:00:00Z', 'PHI', 'Old Backup', '9', '00-9', '1', '3WR 1TE', '1', 'Quarterback', 'QB', 1, 1),
          ('2025-09-03T08:00:00Z', 'PHI', 'Jalen Hurts', '1', '00-1', '1', '3WR 1TE', '1', 'Quarterback', 'QB', 1, 1),
          ('2025-09-13T08:00:00Z', 'PHI', 'Jalen Hurts', '1', '00-1', '1', '3WR 1TE', '1', 'Quarterback', 'QB', 1, 1),
          ('2025-09-13T08:00:00Z', 'PHI', 'Saquon Barkley', '2', '00-2', '1', '3WR 1TE', '2', 'Running Back', 'RB', 1, 1),
          ('2025-09-13T08:00:00Z', 'PHI', 'Saquon Barkley', '2', '00-2', '4', 'Special Teams', '20', 'Kick Returner', 'KR', 1, 1)
        ) t(dt, team, player_name, espn_id, gsis_id, pos_grp_id, pos_grp, pos_id, pos_name, pos_abb, pos_slot, pos_rank)""")

    loader.load_fact_depth_charts(c)
    rows = c.execute("""SELECT season, week, club_code, full_name, depth_position, depth_team, position, game_type
                        FROM fact_depth_charts ORDER BY season, week, full_name""").fetchall()
    assert rows == [
        (2024, 1, "PHI", "Jalen Hurts", "QB", 1, "QB", "REG"),
        (2025, 1, "PHI", "Jalen Hurts", "QB", 1, "QB", "REG"),       # day-before snapshot, not the June one
        (2025, 2, "PHI", "Jalen Hurts", "QB", 1, "QB", "REG"),
        (2025, 2, "PHI", "Saquon Barkley", "RB", 1, "RB", "REG"),    # offensive slot preferred over KR
    ]  # week 3 has no snapshot in the prior 7 days, so no rows


# Every source column the stats_player loader reads.
STATS_PLAYER_COLS = """player_id player_display_name team season week season_type game_id completions attempts
passing_yards passing_tds passing_interceptions sacks_suffered sack_yards_lost sack_fumbles sack_fumbles_lost
passing_air_yards passing_yards_after_catch passing_first_downs passing_epa passing_2pt_conversions pacr carries
rushing_yards rushing_tds rushing_fumbles rushing_fumbles_lost rushing_first_downs rushing_epa rushing_2pt_conversions
receptions targets receiving_yards receiving_tds receiving_fumbles receiving_fumbles_lost receiving_air_yards
receiving_yards_after_catch receiving_first_downs receiving_epa receiving_2pt_conversions racr target_share
air_yards_share wopr special_teams_tds fantasy_points fantasy_points_ppr""".split()


def _stats_row(**values):
    base = {c: 0 for c in STATS_PLAYER_COLS}
    base.update(season=2025, week=1, season_type="REG", game_id="2025_01_DAL_PHI", team="PHI")
    base.update(values)
    lit = lambda v: f"'{v}'" if isinstance(v, str) else repr(v)
    return "SELECT " + ", ".join(f"{lit(base[c])} AS {c}" for c in STATS_PLAYER_COLS)


def test_player_game_stats_from_stats_player(con):
    c, silver = con
    _write(c, silver / "stats_player" / "stats_player_week_2025.parquet", " UNION ALL ".join([
        _stats_row(player_id="00-1", player_display_name="Jalen Hurts", completions=20, attempts=30,
                   passing_yards=250, passing_interceptions=1, sacks_suffered=2.0, sack_yards_lost=12,
                   carries=5, rushing_yards=30, fantasy_points=20.5),
        _stats_row(player_id="00-3", player_display_name="Some Linebacker"),
    ]))
    _write(c, silver / "player_stats" / "player_stats_2024.parquet", """
        SELECT '00-1' AS player_id, 2024 AS season, 1 AS week, 'REG' AS season_type, 0.12 AS dakota""")

    loader.load_fact_player_game_stats(c)
    rows = c.execute("""SELECT player_id, recent_team, game_id, passing_yards, interceptions, sacks, sack_yards, carries, dakota
                        FROM fact_player_game_stats""").fetchall()
    # Defender with no offensive production is filtered out; renamed columns map back;
    # dakota comes only from legacy files (none for 2025).
    assert rows == [("00-1", "PHI", "2025_01_DAL_PHI", 250, 1, 2.0, 12, 5, None)]


def test_roster_team_codes_follow_dim_games_before_1999():
    import polars as pl

    from pipeline.silver.cleaners import _clean_rosters

    df = pl.DataFrame({
        "season": [1975, 1975, 1985, 1990, 1970, 1998, 1998, 2005, 2005],
        "team":   ["STL", "LA", "RAM", "PHO", "BOS", "STL", "OAK", "STL", "OAK"],
    })
    # STL is the Cardinals through 1987 and the Rams from 1995; 1999+ uses today's codes.
    assert _clean_rosters(df)["team"].to_list() == ["SLC", "LA", "LA", "PHX", "NE", "STL", "OAK", "LA", "LV"]


def test_ref_team_stats_keeps_playoff_teams_in_reg(tmp_path, monkeypatch):
    import duckdb
    import polars as pl

    from pipeline.gold import loader
    from pipeline.gold.schema import SCHEMA_SQL

    con = duckdb.connect()
    con.execute(SCHEMA_SQL)
    cols = [r[0] for r in con.execute("DESCRIBE ref_team_stats").fetchall()]
    (tmp_path / "stats_team").mkdir()

    def write(kind, rows):
        df = pl.DataFrame([{c: None for c in cols} | r for r in rows],
                          schema={c: (pl.Int64 if c in ("season", "games", "attempts") else pl.Utf8) for c in cols})
        df.write_parquet(tmp_path / "stats_team" / f"stats_team_{kind}_2024.parquet")

    # KC made the playoffs, NYG didn't: nflverse's regpost file has KC only as REG+POST.
    write("reg", [dict(season=2024, team="KC", season_type="REG", attempts=500),
                  dict(season=2024, team="NYG", season_type="REG", attempts=520)])
    write("post", [dict(season=2024, team="KC", season_type="POST", attempts=90)])
    write("regpost", [dict(season=2024, team="KC", season_type="REG+POST", attempts=590),
                      dict(season=2024, team="NYG", season_type="REG", attempts=520)])
    monkeypatch.setattr(loader, "SILVER_DIR", tmp_path)
    loader.load_ref_team_stats(con)

    rows = con.execute("SELECT team, season_type, attempts FROM ref_team_stats ORDER BY 1, 2").fetchall()
    assert rows == [("KC", "POST", 90), ("KC", "REG", 500), ("KC", "REG+POST", 590), ("NYG", "REG", 520)]
