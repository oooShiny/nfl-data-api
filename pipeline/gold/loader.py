"""Load silver parquet files into the gold DuckDB database."""

from pathlib import Path

import duckdb
from rich.console import Console

from pipeline.config import SILVER_DIR, GOLD_DB
from pipeline.gold.schema import SCHEMA_SQL

console = Console()


def get_connection() -> duckdb.DuckDBPyConnection:
    GOLD_DB.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(GOLD_DB))


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(SCHEMA_SQL)


def _silver_files(tag: str) -> list[Path]:
    d = SILVER_DIR / tag
    return sorted(d.glob("*.parquet")) if d.exists() else []


def _load_via_select(con: duckdb.DuckDBPyConnection, table: str, parquet_glob: str, cols: list[str]) -> int:
    col_list = ", ".join(cols)
    sql = f"""
        INSERT OR REPLACE INTO {table} ({col_list})
        SELECT {col_list}
        FROM read_parquet('{parquet_glob}', hive_partitioning=false)
        WHERE {cols[0]} IS NOT NULL
    """
    con.execute(sql)
    return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# ── Per-table loaders ────────────────────────────────────────────────────────

def load_dim_teams(con: duckdb.DuckDBPyConnection) -> None:
    files = _silver_files("teams")
    if not files:
        console.print("  [yellow]dim_teams: no silver files found[/yellow]")
        return
    glob = str(files[0])
    con.execute(f"""
        INSERT OR REPLACE INTO dim_teams
        SELECT
            team_abbr,
            team_name,
            team_nick,
            team_conf,
            team_division,
            team_color,
            team_color2,
            team_logo_espn     AS team_logo_url,
            team_wordmark
        FROM read_parquet('{glob}')
        WHERE team_abbr IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM dim_teams").fetchone()[0]
    console.print(f"  [green]✓[/green] dim_teams: {n} rows")


def load_dim_players(con: duckdb.DuckDBPyConnection) -> None:
    files = _silver_files("players")
    if not files:
        console.print("  [yellow]dim_players: no silver files found[/yellow]")
        return
    glob = str(files[0])
    con.execute(f"""
        INSERT OR REPLACE INTO dim_players
        SELECT
            gsis_id,
            display_name,
            first_name,
            last_name,
            position,
            position_group,
            birth_date,
            height,
            weight,
            college_name                    AS college,
            NULL                            AS high_school,
            draft_year::SMALLINT,
            draft_round::SMALLINT,
            draft_pick::SMALLINT,
            draft_team                      AS draft_club,
            esb_id,
            pfr_id,
            pff_id,
            NULL                            AS sleeper_id,
            NULL                            AS sportradar_id,
            NULL                            AS yahoo_id,
            NULL                            AS rotowire_id,
            NULL                            AS fantasy_data_id,
            status,
            years_of_experience::SMALLINT   AS years_exp,
            rookie_season::SMALLINT         AS rookie_year
        FROM read_parquet('{glob}')
        WHERE gsis_id IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM dim_players").fetchone()[0]
    console.print(f"  [green]✓[/green] dim_players: {n} rows")


def load_dim_games(con: duckdb.DuckDBPyConnection) -> None:
    files = _silver_files("schedules")
    if not files:
        console.print("  [yellow]dim_games: no silver files found[/yellow]")
        return
    glob = str(files[0])
    con.execute(f"""
        INSERT OR REPLACE INTO dim_games
        SELECT
            game_id,
            season::SMALLINT,
            week::SMALLINT,
            game_type,
            gameday,
            gametime,
            home_team,
            away_team,
            home_score::SMALLINT,
            away_score::SMALLINT,
            result::SMALLINT,
            total::SMALLINT,
            overtime,
            stadium,
            location,
            roof,
            surface,
            temp::SMALLINT,
            wind::SMALLINT,
            spread_line,
            total_line,
            div_game
        FROM read_parquet('{glob}')
        WHERE game_id IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM dim_games").fetchone()[0]
    console.print(f"  [green]✓[/green] dim_games: {n} rows")


def load_fact_player_game_stats(con: duckdb.DuckDBPyConnection) -> None:
    files = _silver_files("player_stats")
    if not files:
        console.print("  [yellow]fact_player_game_stats: no silver files found[/yellow]")
        return
    # Only non-kicking files (kicking stats use a different schema)
    non_kicking = [str(f) for f in files if "kicking" not in f.name]
    if not non_kicking:
        return
    glob = str(SILVER_DIR / "player_stats" / "player_stats_[0-9]*.parquet")
    con.execute(f"""
        INSERT OR REPLACE INTO fact_player_game_stats
        SELECT
            NULL                            AS game_id,
            player_id,
            player_display_name             AS player_name,
            recent_team,
            season::SMALLINT,
            week::SMALLINT,
            season_type,
            completions::SMALLINT,
            attempts::SMALLINT,
            passing_yards::SMALLINT,
            passing_tds::SMALLINT,
            interceptions::SMALLINT,
            sacks,
            sack_yards::SMALLINT,
            sack_fumbles::SMALLINT,
            sack_fumbles_lost::SMALLINT,
            passing_air_yards::SMALLINT,
            passing_yards_after_catch::SMALLINT,
            passing_first_downs::SMALLINT,
            passing_epa,
            passing_2pt_conversions::SMALLINT,
            pacr,
            dakota,
            carries::SMALLINT,
            rushing_yards::SMALLINT,
            rushing_tds::SMALLINT,
            rushing_fumbles::SMALLINT,
            rushing_fumbles_lost::SMALLINT,
            rushing_first_downs::SMALLINT,
            rushing_epa,
            rushing_2pt_conversions::SMALLINT,
            receptions::SMALLINT,
            targets::SMALLINT,
            receiving_yards::SMALLINT,
            receiving_tds::SMALLINT,
            receiving_fumbles::SMALLINT,
            receiving_fumbles_lost::SMALLINT,
            receiving_air_yards::SMALLINT,
            receiving_yards_after_catch::SMALLINT,
            receiving_first_downs::SMALLINT,
            receiving_epa,
            receiving_2pt_conversions::SMALLINT,
            racr,
            target_share,
            air_yards_share,
            wopr,
            special_teams_tds::SMALLINT,
            fantasy_points,
            fantasy_points_ppr
        FROM read_parquet('{glob}', hive_partitioning=false, union_by_name=true)
        WHERE player_id IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM fact_player_game_stats").fetchone()[0]
    console.print(f"  [green]✓[/green] fact_player_game_stats: {n} rows")


def load_fact_plays(con: duckdb.DuckDBPyConnection) -> None:
    """Load core play-by-play facts (common columns for every play)."""
    glob = str(SILVER_DIR / "pbp" / "play_by_play_*.parquet")
    pbp_files = list((SILVER_DIR / "pbp").glob("play_by_play_*.parquet"))
    if not pbp_files:
        console.print("  [yellow]fact_plays: no silver PBP files found[/yellow]")
        return

    con.execute(f"""
        INSERT OR REPLACE INTO fact_plays
        SELECT
            play_id::INTEGER,
            game_id,
            season::SMALLINT,
            week::SMALLINT,
            game_date,
            qtr::SMALLINT                       AS quarter,
            game_seconds_remaining::INTEGER,
            half_seconds_remaining::INTEGER,
            quarter_seconds_remaining::INTEGER,
            down::SMALLINT,
            ydstogo::SMALLINT,
            yardline_100::SMALLINT,
            posteam,
            defteam,
            posteam_score::SMALLINT,
            defteam_score::SMALLINT,
            score_differential::SMALLINT,
            play_type,
            yards_gained::SMALLINT,
            touchdown::BOOLEAN,
            (interception OR fumble_lost)::BOOLEAN  AS turnover,
            penalty::BOOLEAN,
            penalty_yards::SMALLINT,
            first_down::BOOLEAN,
            ep,
            epa,
            wp,
            wpa,
            air_epa,
            yac_epa,
            comp_air_epa,
            comp_yac_epa,
            qb_epa,
            xyac_epa,
            series::SMALLINT,
            series_success::BOOLEAN,
            drive::SMALLINT,
            sp::BOOLEAN
        FROM read_parquet('{glob}', hive_partitioning=false, union_by_name=true)
        WHERE play_id IS NOT NULL AND game_id IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM fact_plays").fetchone()[0]
    console.print(f"  [green]✓[/green] fact_plays: {n:,} rows")


def load_fact_pass_plays(con: duckdb.DuckDBPyConnection) -> None:
    glob = str(SILVER_DIR / "pbp" / "play_by_play_*.parquet")
    pbp_files = list((SILVER_DIR / "pbp").glob("play_by_play_*.parquet"))
    if not pbp_files:
        return

    con.execute(f"""
        INSERT OR REPLACE INTO fact_pass_plays
        SELECT
            game_id,
            play_id::INTEGER,
            passer_player_id,
            passer_player_name,
            receiver_player_id,
            receiver_player_name,
            pass_length,
            pass_location,
            air_yards::SMALLINT,
            yards_after_catch::SMALLINT,
            complete_pass::BOOLEAN,
            incomplete_pass::BOOLEAN,
            interception::BOOLEAN,
            sack::BOOLEAN,
            qb_hit::BOOLEAN,
            qb_scramble::BOOLEAN,
            pass_touchdown::BOOLEAN,
            cpoe,
            air_yards * epa  AS air_yards_epa
        FROM read_parquet('{glob}', hive_partitioning=false, union_by_name=true)
        WHERE play_type = 'pass' AND play_id IS NOT NULL AND game_id IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM fact_pass_plays").fetchone()[0]
    console.print(f"  [green]✓[/green] fact_pass_plays: {n:,} rows")


def load_fact_rush_plays(con: duckdb.DuckDBPyConnection) -> None:
    glob = str(SILVER_DIR / "pbp" / "play_by_play_*.parquet")
    pbp_files = list((SILVER_DIR / "pbp").glob("play_by_play_*.parquet"))
    if not pbp_files:
        return

    con.execute(f"""
        INSERT OR REPLACE INTO fact_rush_plays
        SELECT
            game_id,
            play_id::INTEGER,
            rusher_player_id,
            rusher_player_name,
            run_location,
            run_gap,
            rush_touchdown::BOOLEAN,
            (yards_gained <= 0 AND down IN (1,2,3))::BOOLEAN AS stuffed_run
        FROM read_parquet('{glob}', hive_partitioning=false, union_by_name=true)
        WHERE play_type = 'run' AND play_id IS NOT NULL AND game_id IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM fact_rush_plays").fetchone()[0]
    console.print(f"  [green]✓[/green] fact_rush_plays: {n:,} rows")


def load_fact_kick_plays(con: duckdb.DuckDBPyConnection) -> None:
    glob = str(SILVER_DIR / "pbp" / "play_by_play_*.parquet")
    pbp_files = list((SILVER_DIR / "pbp").glob("play_by_play_*.parquet"))
    if not pbp_files:
        return

    con.execute(f"""
        INSERT OR REPLACE INTO fact_kick_plays
        SELECT
            game_id,
            play_id::INTEGER,
            play_type                           AS play_subtype,
            kicker_player_id,
            kicker_player_name,
            kick_distance::SMALLINT,
            field_goal_result,
            field_goal_attempt::BOOLEAN,
            extra_point_result,
            extra_point_attempt::BOOLEAN,
            punt_blocked::BOOLEAN,
            punt_returner_player_id             AS return_player_id,
            punt_returner_player_name           AS return_player_name,
            return_yards::SMALLINT
        FROM read_parquet('{glob}', hive_partitioning=false, union_by_name=true)
        WHERE play_type IN ('punt', 'field_goal', 'kickoff', 'extra_point', 'no_play')
          AND (field_goal_attempt = true OR extra_point_attempt = true OR punt_blocked IS NOT NULL)
          AND play_id IS NOT NULL AND game_id IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM fact_kick_plays").fetchone()[0]
    console.print(f"  [green]✓[/green] fact_kick_plays: {n:,} rows")


def load_fact_rosters(con: duckdb.DuckDBPyConnection) -> None:
    glob = str(SILVER_DIR / "rosters" / "roster_*.parquet")
    files = list((SILVER_DIR / "rosters").glob("roster_*.parquet"))
    if not files:
        console.print("  [yellow]fact_rosters: no silver files[/yellow]")
        return
    con.execute(f"""
        INSERT OR REPLACE INTO fact_rosters
        SELECT
            season::SMALLINT,
            team,
            position,
            depth_chart_position,
            jersey_number::SMALLINT,
            status,
            full_name               AS player_name,
            gsis_id                 AS player_id,
            birth_date,
            height,
            weight::SMALLINT,
            college,
            years_exp::SMALLINT,
            entry_year::SMALLINT,
            rookie_year::SMALLINT,
            draft_club,
            draft_number::SMALLINT
        FROM read_parquet('{glob}', hive_partitioning=false, union_by_name=true)
        WHERE team IS NOT NULL AND full_name IS NOT NULL AND gsis_id IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM fact_rosters").fetchone()[0]
    console.print(f"  [green]✓[/green] fact_rosters: {n:,} rows")


def load_ref_draft_picks(con: duckdb.DuckDBPyConnection) -> None:
    files = _silver_files("draft_picks")
    if not files:
        return
    glob = str(files[0])
    con.execute(f"""
        INSERT OR REPLACE INTO ref_draft_picks
        SELECT
            season::SMALLINT,
            round::SMALLINT,
            pick::SMALLINT,
            team,
            pfr_player_name     AS player_name,
            gsis_id,
            pfr_player_id,
            position,
            category,
            side,
            college
        FROM read_parquet('{glob}')
        WHERE season IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM ref_draft_picks").fetchone()[0]
    console.print(f"  [green]✓[/green] ref_draft_picks: {n:,} rows")


def load_ref_combine(con: duckdb.DuckDBPyConnection) -> None:
    files = _silver_files("combine")
    if not files:
        return
    glob = str(files[0])
    con.execute(f"""
        INSERT OR REPLACE INTO ref_combine
        SELECT
            season::SMALLINT,
            player_name,
            NULL                AS player_id,
            pos,
            school,
            ht,
            wt::SMALLINT,
            forty,
            bench::SMALLINT,
            vertical,
            broad_jump::SMALLINT,
            cone,
            shuttle,
            draft_year::SMALLINT,
            draft_round::SMALLINT,
            NULL::SMALLINT       AS draft_pick,
            draft_ovr::SMALLINT
        FROM read_parquet('{glob}')
        WHERE season IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM ref_combine").fetchone()[0]
    console.print(f"  [green]✓[/green] ref_combine: {n:,} rows")


def load_ref_contracts(con: duckdb.DuckDBPyConnection) -> None:
    files = _silver_files("contracts")
    if not files:
        return
    glob = str(files[0])
    con.execute("DELETE FROM ref_contracts")
    con.execute(f"""
        INSERT INTO ref_contracts
        SELECT
            player             AS player_name,
            gsis_id            AS player_id,
            team,
            position,
            year_signed::SMALLINT,
            years::SMALLINT,
            value::BIGINT,
            apy::BIGINT,
            guaranteed::BIGINT,
            apy_cap_pct,
            inflated_value::BIGINT,
            inflated_apy::BIGINT,
            inflated_guaranteed::BIGINT
        FROM read_parquet('{glob}')
    """)
    n = con.execute("SELECT COUNT(*) FROM ref_contracts").fetchone()[0]
    console.print(f"  [green]✓[/green] ref_contracts: {n:,} rows")


def load_fact_snap_counts(con: duckdb.DuckDBPyConnection) -> None:
    import polars as pl
    valid = [
        str(f) for f in sorted((SILVER_DIR / "snap_counts").glob("snap_counts_*.parquet"))
        if pl.read_parquet_schema(f)  # non-empty schema means valid file
        and f.stat().st_size > 1000
    ]
    if not valid:
        console.print("  [yellow]fact_snap_counts: no silver files[/yellow]")
        return
    files_list = "', '".join(valid)
    con.execute(f"""
        INSERT OR REPLACE INTO fact_snap_counts
        SELECT
            game_id,
            pfr_game_id,
            season::SMALLINT,
            game_type,
            week::SMALLINT,
            player,
            pfr_player_id,
            position,
            team,
            opponent,
            offense_snaps::SMALLINT,
            offense_pct,
            defense_snaps::SMALLINT,
            defense_pct,
            st_snaps::SMALLINT,
            st_pct
        FROM read_parquet(['{files_list}'], hive_partitioning=false)
        WHERE game_id IS NOT NULL AND pfr_player_id IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM fact_snap_counts").fetchone()[0]
    console.print(f"  [green]✓[/green] fact_snap_counts: {n:,} rows")


def load_fact_depth_charts(con: duckdb.DuckDBPyConnection) -> None:
    glob = str(SILVER_DIR / "depth_charts" / "depth_charts_*.parquet")
    if not list((SILVER_DIR / "depth_charts").glob("*.parquet")):
        console.print("  [yellow]fact_depth_charts: no silver files[/yellow]")
        return
    con.execute(f"""
        INSERT OR REPLACE INTO fact_depth_charts
        SELECT
            season::SMALLINT,
            club_code,
            week::SMALLINT,
            game_type,
            gsis_id,
            full_name,
            position,
            depth_team::SMALLINT,
            depth_position,
            last_name,
            first_name,
            jersey_number::SMALLINT
        FROM read_parquet('{glob}', hive_partitioning=false, union_by_name=true)
        WHERE gsis_id IS NOT NULL AND club_code IS NOT NULL AND week IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM fact_depth_charts").fetchone()[0]
    console.print(f"  [green]✓[/green] fact_depth_charts: {n:,} rows")


def load_fact_injuries(con: duckdb.DuckDBPyConnection) -> None:
    glob = str(SILVER_DIR / "injuries" / "injuries_*.parquet")
    if not list((SILVER_DIR / "injuries").glob("*.parquet")):
        console.print("  [yellow]fact_injuries: no silver files[/yellow]")
        return
    con.execute(f"""
        INSERT OR REPLACE INTO fact_injuries
        SELECT
            season::SMALLINT,
            game_type,
            team,
            week::SMALLINT,
            gsis_id,
            position,
            full_name,
            report_primary_injury,
            report_secondary_injury,
            report_status,
            practice_primary_injury,
            practice_secondary_injury,
            practice_status,
            date_modified
        FROM read_parquet('{glob}', hive_partitioning=false, union_by_name=true)
        WHERE gsis_id IS NOT NULL AND team IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM fact_injuries").fetchone()[0]
    console.print(f"  [green]✓[/green] fact_injuries: {n:,} rows")


def load_fact_weekly_rosters(con: duckdb.DuckDBPyConnection) -> None:
    glob = str(SILVER_DIR / "weekly_rosters" / "roster_weekly_*.parquet")
    if not list((SILVER_DIR / "weekly_rosters").glob("*.parquet")):
        console.print("  [yellow]fact_weekly_rosters: no silver files[/yellow]")
        return
    con.execute(f"""
        INSERT OR REPLACE INTO fact_weekly_rosters
        SELECT
            season::SMALLINT,
            team,
            week::SMALLINT,
            position,
            depth_chart_position,
            TRY_CAST(jersey_number AS SMALLINT),
            status,
            full_name,
            gsis_id,
            years_exp::SMALLINT,
            entry_year::SMALLINT,
            rookie_year::SMALLINT,
            draft_club,
            draft_number::SMALLINT
        FROM read_parquet('{glob}', hive_partitioning=false, union_by_name=true)
        WHERE gsis_id IS NOT NULL AND team IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM fact_weekly_rosters").fetchone()[0]
    console.print(f"  [green]✓[/green] fact_weekly_rosters: {n:,} rows")


def load_ref_officials(con: duckdb.DuckDBPyConnection) -> None:
    files = _silver_files("officials")
    if not files:
        return
    glob = str(files[0])
    con.execute(f"""
        INSERT OR REPLACE INTO ref_officials
        SELECT
            season::SMALLINT,
            game_id,
            official_id,
            official_name,
            position,
            jersey_number::SMALLINT
        FROM read_parquet('{glob}')
        WHERE game_id IS NOT NULL AND official_id IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM ref_officials").fetchone()[0]
    console.print(f"  [green]✓[/green] ref_officials: {n:,} rows")


def load_ref_trades(con: duckdb.DuckDBPyConnection) -> None:
    files = _silver_files("trades")
    if not files:
        return
    glob = str(files[0])
    con.execute("DELETE FROM ref_trades")
    con.execute(f"""
        INSERT INTO ref_trades
        SELECT
            trade_id::INTEGER,
            season::SMALLINT,
            trade_date,
            gave,
            received,
            pfr_id,
            pfr_name,
            pick_season::SMALLINT,
            pick_round::SMALLINT,
            pick_number::SMALLINT,
            (conditional = 1)::BOOLEAN     AS conditional
        FROM read_parquet('{glob}')
        WHERE season IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM ref_trades").fetchone()[0]
    console.print(f"  [green]✓[/green] ref_trades: {n:,} rows")


# ── Main orchestrator ────────────────────────────────────────────────────────

LOADERS = [
    ("dim_teams", load_dim_teams),
    ("dim_players", load_dim_players),
    ("dim_games", load_dim_games),
    ("fact_player_game_stats", load_fact_player_game_stats),
    ("fact_rosters", load_fact_rosters),
    ("fact_weekly_rosters", load_fact_weekly_rosters),
    ("fact_snap_counts", load_fact_snap_counts),
    ("fact_depth_charts", load_fact_depth_charts),
    ("fact_injuries", load_fact_injuries),
    ("ref_draft_picks", load_ref_draft_picks),
    ("ref_combine", load_ref_combine),
    ("ref_contracts", load_ref_contracts),
    ("ref_officials", load_ref_officials),
    ("ref_trades", load_ref_trades),
    # PBP last — largest tables
    ("fact_plays", load_fact_plays),
    ("fact_pass_plays", load_fact_pass_plays),
    ("fact_rush_plays", load_fact_rush_plays),
    ("fact_kick_plays", load_fact_kick_plays),
]


def load_all(tables: list[str] | None = None) -> None:
    con = get_connection()
    init_schema(con)
    console.print("[bold]Loading gold layer into DuckDB[/bold]")
    for name, fn in LOADERS:
        if tables and name not in tables:
            continue
        try:
            fn(con)
        except Exception as e:
            console.print(f"  [red]✗[/red] {name}: {e}")
    con.close()
    console.print(f"\n[bold green]Done.[/bold green] Database: {GOLD_DB}")
