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
        FROM read_parquet('{parquet_glob}', hive_partitioning=false, union_by_name=true)
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
            (conditional = 1)::BOOLEAN     AS conditional,
            NULL                            AS gsis_id
        FROM read_parquet('{glob}')
        WHERE season IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM ref_trades").fetchone()[0]
    console.print(f"  [green]✓[/green] ref_trades: {n:,} rows")


def load_fact_pbp_participation(con: duckdb.DuckDBPyConnection) -> None:
    glob = str(SILVER_DIR / "pbp_participation" / "pbp_participation_*.parquet")
    if not list((SILVER_DIR / "pbp_participation").glob("*.parquet")):
        console.print("  [yellow]fact_pbp_participation: no silver files[/yellow]")
        return
    con.execute(f"""
        INSERT OR REPLACE INTO fact_pbp_participation
        SELECT
            nflverse_game_id    AS game_id,
            play_id::INTEGER,
            possession_team,
            offense_formation,
            offense_personnel,
            defense_personnel,
            defenders_in_box::SMALLINT,
            number_of_pass_rushers::SMALLINT,
            n_offense::SMALLINT,
            n_defense::SMALLINT,
            offense_players,
            defense_players,
            ngs_air_yards,
            time_to_throw,
            was_pressure::BOOLEAN,
            route,
            defense_man_zone_type,
            defense_coverage_type
        FROM read_parquet('{glob}', hive_partitioning=false, union_by_name=true)
        WHERE nflverse_game_id IS NOT NULL AND play_id IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM fact_pbp_participation").fetchone()[0]
    console.print(f"  [green]✓[/green] fact_pbp_participation: {n:,} rows")


def load_fact_ftn_charting(con: duckdb.DuckDBPyConnection) -> None:
    glob = str(SILVER_DIR / "ftn_charting" / "ftn_charting_*.parquet")
    if not list((SILVER_DIR / "ftn_charting").glob("*.parquet")):
        console.print("  [yellow]fact_ftn_charting: no silver files[/yellow]")
        return
    con.execute(f"""
        INSERT OR REPLACE INTO fact_ftn_charting
        SELECT
            nflverse_game_id    AS game_id,
            nflverse_play_id::INTEGER AS play_id,
            ftn_game_id::INTEGER,
            ftn_play_id::INTEGER,
            season::SMALLINT,
            week::SMALLINT,
            starting_hash,
            qb_location,
            n_offense_backfield::SMALLINT,
            n_defense_box::SMALLINT,
            n_blitzers::SMALLINT,
            n_pass_rushers::SMALLINT,
            is_no_huddle::BOOLEAN,
            is_motion::BOOLEAN,
            is_play_action::BOOLEAN,
            is_screen_pass::BOOLEAN,
            is_rpo::BOOLEAN,
            is_trick_play::BOOLEAN,
            is_qb_sneak::BOOLEAN,
            is_qb_out_of_pocket::BOOLEAN,
            is_qb_fault_sack::BOOLEAN,
            is_throw_away::BOOLEAN,
            is_catchable_ball::BOOLEAN,
            is_contested_ball::BOOLEAN,
            is_created_reception::BOOLEAN,
            is_drop::BOOLEAN,
            is_interception_worthy::BOOLEAN,
            read_thrown
        FROM read_parquet('{glob}', hive_partitioning=false, union_by_name=true)
        WHERE nflverse_game_id IS NOT NULL AND nflverse_play_id IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM fact_ftn_charting").fetchone()[0]
    console.print(f"  [green]✓[/green] fact_ftn_charting: {n:,} rows")


def load_ref_pfr_rosters(con: duckdb.DuckDBPyConnection) -> None:
    files = _silver_files("misc")
    f = next((p for p in files if p.name == "pfr_rosters.parquet"), None)
    if not f:
        console.print("  [yellow]ref_pfr_rosters: no silver file[/yellow]")
        return
    con.execute(f"""
        INSERT OR REPLACE INTO ref_pfr_rosters
        SELECT
            season::SMALLINT,
            pfr                 AS pfr_team,
            nfl                 AS nfl_team,
            pfr_player_id,
            player,
            "no"::SMALLINT      AS jersey_number,
            age::SMALLINT,
            pos                 AS position,
            g::SMALLINT         AS games,
            gs::SMALLINT        AS games_started,
            wt::SMALLINT        AS weight,
            ht                  AS height,
            college_univ        AS college,
            birth_date,
            yrs                 AS years_exp,
            av::SMALLINT        AS approximate_value,
            drafted_tm_rnd_yr,
            salary
        FROM read_parquet('{f}')
        WHERE pfr_player_id IS NOT NULL AND season IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM ref_pfr_rosters").fetchone()[0]
    console.print(f"  [green]✓[/green] ref_pfr_rosters: {n:,} rows")


def load_ref_pfr_adv_pass(con: duckdb.DuckDBPyConnection) -> None:
    files = _silver_files("pfr_advstats")
    f = next((p for p in files if p.name == "advstats_season_pass.parquet"), None)
    if not f:
        console.print("  [yellow]ref_pfr_adv_pass: no silver file[/yellow]")
        return
    con.execute(f"""
        INSERT OR REPLACE INTO ref_pfr_adv_pass
        SELECT
            season::SMALLINT,
            pfr_id,
            player,
            team,
            pass_attempts::SMALLINT,
            throwaways::SMALLINT,
            spikes::SMALLINT,
            drops::SMALLINT,
            drop_pct,
            bad_throws::SMALLINT,
            bad_throw_pct,
            on_tgt_throws::SMALLINT,
            on_tgt_pct,
            pocket_time,
            times_blitzed::SMALLINT,
            times_hurried::SMALLINT,
            times_hit::SMALLINT,
            times_pressured::SMALLINT,
            pressure_pct,
            batted_balls::SMALLINT,
            scrambles::SMALLINT,
            scramble_yards_per_attempt,
            intended_air_yards::INTEGER,
            intended_air_yards_per_pass_attempt,
            completed_air_yards::INTEGER,
            completed_air_yards_per_completion,
            completed_air_yards_per_pass_attempt,
            pass_yards_after_catch::INTEGER,
            pass_yards_after_catch_per_completion,
            rpo_plays::SMALLINT,
            rpo_yards::INTEGER,
            rpo_pass_att::SMALLINT,
            rpo_pass_yards::INTEGER,
            rpo_rush_att::SMALLINT,
            rpo_rush_yards::INTEGER,
            pa_pass_att::SMALLINT,
            pa_pass_yards::INTEGER
        FROM read_parquet('{f}')
        WHERE pfr_id IS NOT NULL AND season IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM ref_pfr_adv_pass").fetchone()[0]
    console.print(f"  [green]✓[/green] ref_pfr_adv_pass: {n:,} rows")


def load_ref_pfr_adv_rush(con: duckdb.DuckDBPyConnection) -> None:
    files = _silver_files("pfr_advstats")
    f = next((p for p in files if p.name == "advstats_season_rush.parquet"), None)
    if not f:
        console.print("  [yellow]ref_pfr_adv_rush: no silver file[/yellow]")
        return
    con.execute(f"""
        INSERT OR REPLACE INTO ref_pfr_adv_rush
        SELECT
            season::SMALLINT,
            pfr_id,
            player,
            tm                  AS team,
            age::SMALLINT,
            pos                 AS position,
            g::SMALLINT         AS games,
            gs::SMALLINT        AS games_started,
            att::INTEGER        AS attempts,
            yds::INTEGER        AS yards,
            td::SMALLINT        AS tds,
            x1d::SMALLINT       AS first_downs,
            ybc::INTEGER        AS yards_before_contact,
            ybc_att             AS yards_before_contact_per_att,
            yac::INTEGER        AS yards_after_contact,
            yac_att             AS yards_after_contact_per_att,
            brk_tkl::SMALLINT   AS broken_tackles,
            att_br              AS attempts_per_broken_tackle,
            loaded              AS loaded_at
        FROM read_parquet('{f}')
        WHERE pfr_id IS NOT NULL AND season IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM ref_pfr_adv_rush").fetchone()[0]
    console.print(f"  [green]✓[/green] ref_pfr_adv_rush: {n:,} rows")


def load_ref_pfr_adv_rec(con: duckdb.DuckDBPyConnection) -> None:
    files = _silver_files("pfr_advstats")
    f = next((p for p in files if p.name == "advstats_season_rec.parquet"), None)
    if not f:
        console.print("  [yellow]ref_pfr_adv_rec: no silver file[/yellow]")
        return
    con.execute(f"""
        INSERT OR REPLACE INTO ref_pfr_adv_rec
        SELECT
            season::SMALLINT,
            pfr_id,
            player,
            tm                  AS team,
            age::SMALLINT,
            pos                 AS position,
            g::SMALLINT         AS games,
            gs::SMALLINT        AS games_started,
            tgt::INTEGER        AS targets,
            rec::INTEGER        AS receptions,
            yds::INTEGER        AS yards,
            td::SMALLINT        AS tds,
            x1d::SMALLINT       AS first_downs,
            ybc::INTEGER        AS yards_before_catch,
            ybc_r               AS yards_before_catch_per_rec,
            yac::INTEGER        AS yards_after_catch,
            yac_r               AS yards_after_catch_per_rec,
            adot                AS avg_depth_of_target,
            brk_tkl::SMALLINT   AS broken_tackles,
            rec_br              AS receptions_per_broken_tackle,
            drop::SMALLINT      AS drops,
            drop_percent        AS drop_pct,
            int::SMALLINT       AS interceptions_when_targeted,
            rat                 AS passer_rating_when_targeted,
            loaded              AS loaded_at
        FROM read_parquet('{f}')
        WHERE pfr_id IS NOT NULL AND season IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM ref_pfr_adv_rec").fetchone()[0]
    console.print(f"  [green]✓[/green] ref_pfr_adv_rec: {n:,} rows")


def load_ref_pfr_adv_def(con: duckdb.DuckDBPyConnection) -> None:
    files = _silver_files("pfr_advstats")
    f = next((p for p in files if p.name == "advstats_season_def.parquet"), None)
    if not f:
        console.print("  [yellow]ref_pfr_adv_def: no silver file[/yellow]")
        return
    con.execute(f"""
        INSERT OR REPLACE INTO ref_pfr_adv_def
        SELECT
            season::SMALLINT,
            pfr_id,
            player,
            tm                  AS team,
            age::SMALLINT,
            pos                 AS position,
            g::SMALLINT         AS games,
            gs::SMALLINT        AS games_started,
            int::SMALLINT       AS interceptions,
            tgt::INTEGER        AS targets,
            cmp::INTEGER        AS completions_allowed,
            cmp_percent         AS completion_pct_allowed,
            yds::INTEGER        AS yards_allowed,
            yds_cmp             AS yards_per_completion_allowed,
            yds_tgt             AS yards_per_target_allowed,
            td::SMALLINT        AS tds_allowed,
            rat                 AS passer_rating_allowed,
            dadot               AS avg_depth_of_target_allowed,
            air::INTEGER        AS air_yards_allowed,
            yac::INTEGER        AS yards_after_catch_allowed,
            bltz::SMALLINT      AS blitzes,
            hrry::SMALLINT      AS hurries,
            qbkd::SMALLINT      AS qb_knockdowns,
            sk                  AS sacks,
            prss::SMALLINT      AS pressures,
            comb::SMALLINT      AS combined_tackles,
            m_tkl::SMALLINT     AS missed_tackles,
            m_tkl_percent       AS missed_tackle_pct,
            bats::SMALLINT      AS batted_passes,
            loaded              AS loaded_at
        FROM read_parquet('{f}')
        WHERE pfr_id IS NOT NULL AND season IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM ref_pfr_adv_def").fetchone()[0]
    console.print(f"  [green]✓[/green] ref_pfr_adv_def: {n:,} rows")


def load_fact_ngs_passing(con: duckdb.DuckDBPyConnection) -> None:
    files = _silver_files("nextgen_stats")
    f = next((p for p in files if p.name == "ngs_passing.parquet"), None)
    if not f:
        console.print("  [yellow]fact_ngs_passing: no silver file[/yellow]")
        return
    con.execute(f"""
        INSERT OR REPLACE INTO fact_ngs_passing
        SELECT
            season::SMALLINT,
            season_type,
            week::SMALLINT,
            player_gsis_id,
            player_display_name,
            player_first_name,
            player_last_name,
            player_short_name,
            player_jersey_number::SMALLINT,
            player_position,
            team_abbr,
            attempts::SMALLINT,
            completions::SMALLINT,
            pass_yards::INTEGER,
            pass_touchdowns::SMALLINT,
            interceptions::SMALLINT,
            passer_rating,
            completion_percentage,
            expected_completion_percentage,
            completion_percentage_above_expectation,
            avg_time_to_throw,
            avg_completed_air_yards,
            avg_intended_air_yards,
            avg_air_yards_differential,
            avg_air_yards_to_sticks,
            avg_air_distance,
            max_air_distance,
            max_completed_air_distance,
            aggressiveness
        FROM read_parquet('{f}')
        WHERE player_gsis_id IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM fact_ngs_passing").fetchone()[0]
    console.print(f"  [green]✓[/green] fact_ngs_passing: {n:,} rows")


def load_fact_ngs_receiving(con: duckdb.DuckDBPyConnection) -> None:
    files = _silver_files("nextgen_stats")
    f = next((p for p in files if p.name == "ngs_receiving.parquet"), None)
    if not f:
        console.print("  [yellow]fact_ngs_receiving: no silver file[/yellow]")
        return
    con.execute(f"""
        INSERT OR REPLACE INTO fact_ngs_receiving
        SELECT
            season::SMALLINT,
            season_type,
            week::SMALLINT,
            player_gsis_id,
            player_display_name,
            player_first_name,
            player_last_name,
            player_short_name,
            player_jersey_number::SMALLINT,
            player_position,
            team_abbr,
            targets::SMALLINT,
            receptions::SMALLINT,
            yards::INTEGER,
            rec_touchdowns::SMALLINT,
            catch_percentage,
            avg_cushion,
            avg_separation,
            avg_intended_air_yards,
            percent_share_of_intended_air_yards,
            avg_yac,
            avg_expected_yac,
            avg_yac_above_expectation
        FROM read_parquet('{f}')
        WHERE player_gsis_id IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM fact_ngs_receiving").fetchone()[0]
    console.print(f"  [green]✓[/green] fact_ngs_receiving: {n:,} rows")


def load_fact_ngs_rushing(con: duckdb.DuckDBPyConnection) -> None:
    files = _silver_files("nextgen_stats")
    f = next((p for p in files if p.name == "ngs_rushing.parquet"), None)
    if not f:
        console.print("  [yellow]fact_ngs_rushing: no silver file[/yellow]")
        return
    con.execute(f"""
        INSERT OR REPLACE INTO fact_ngs_rushing
        SELECT
            season::SMALLINT,
            season_type,
            week::SMALLINT,
            player_gsis_id,
            player_display_name,
            player_first_name,
            player_last_name,
            player_short_name,
            player_jersey_number::SMALLINT,
            player_position,
            team_abbr,
            rush_attempts::SMALLINT,
            rush_yards::INTEGER,
            rush_touchdowns::SMALLINT,
            avg_rush_yards,
            efficiency,
            percent_attempts_gte_eight_defenders,
            avg_time_to_los,
            expected_rush_yards,
            rush_yards_over_expected,
            rush_yards_over_expected_per_att,
            rush_pct_over_expected
        FROM read_parquet('{f}')
        WHERE player_gsis_id IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM fact_ngs_rushing").fetchone()[0]
    console.print(f"  [green]✓[/green] fact_ngs_rushing: {n:,} rows")


def load_fact_player_season_stats(con: duckdb.DuckDBPyConnection) -> None:
    glob = str(SILVER_DIR / "stats_player" / "stats_player_regpost_*.parquet")
    if not list((SILVER_DIR / "stats_player").glob("*.parquet")):
        console.print("  [yellow]fact_player_season_stats: no silver files[/yellow]")
        return
    cols = [
        "player_id", "player_name", "player_display_name", "position", "position_group",
        "headshot_url", "season", "season_type", "recent_team", "games",
        "completions", "attempts", "passing_yards", "passing_tds", "passing_interceptions",
        "sacks_suffered", "sack_yards_lost", "sack_fumbles", "sack_fumbles_lost",
        "passing_air_yards", "passing_yards_after_catch", "passing_first_downs",
        "passing_epa", "passing_2pt_conversions", "pacr",
        "carries", "rushing_yards", "rushing_tds", "rushing_fumbles", "rushing_fumbles_lost",
        "rushing_first_downs", "rushing_epa", "rushing_2pt_conversions",
        "receptions", "targets", "receiving_yards", "receiving_tds", "receiving_fumbles",
        "receiving_fumbles_lost", "receiving_air_yards", "receiving_yards_after_catch",
        "receiving_first_downs", "receiving_epa", "receiving_2pt_conversions",
        "racr", "target_share", "air_yards_share", "wopr", "special_teams_tds",
        "def_tackles_solo", "def_tackles_with_assist", "def_tackle_assists",
        "def_tackles_for_loss", "def_tackles_for_loss_yards", "def_fumbles_forced",
        "def_sacks", "def_sack_yards", "def_qb_hits", "def_interceptions",
        "def_interception_yards", "def_pass_defended", "def_tds", "def_fumbles", "def_safeties",
        "misc_yards", "fumble_recovery_own", "fumble_recovery_yards_own",
        "fumble_recovery_opp", "fumble_recovery_yards_opp", "fumble_recovery_tds",
        "penalties", "penalty_yards",
        "punt_returns", "punt_return_yards", "kickoff_returns", "kickoff_return_yards",
        "fg_made", "fg_att", "fg_missed", "fg_blocked", "fg_long", "fg_pct",
        "fg_made_0_19", "fg_made_20_29", "fg_made_30_39", "fg_made_40_49",
        "fg_made_50_59", "fg_made_60_",
        "fg_missed_0_19", "fg_missed_20_29", "fg_missed_30_39", "fg_missed_40_49",
        "fg_missed_50_59", "fg_missed_60_",
        "fg_made_list", "fg_missed_list", "fg_blocked_list",
        "fg_made_distance", "fg_missed_distance", "fg_blocked_distance",
        "pat_made", "pat_att", "pat_missed", "pat_blocked", "pat_pct",
        "gwfg_made", "gwfg_att", "gwfg_missed", "gwfg_blocked",
        "fantasy_points", "fantasy_points_ppr",
    ]
    n = _load_via_select(con, "fact_player_season_stats", glob, cols)
    console.print(f"  [green]✓[/green] fact_player_season_stats: {n:,} rows")


def load_ref_team_stats(con: duckdb.DuckDBPyConnection) -> None:
    glob = str(SILVER_DIR / "stats_team" / "stats_team_post_*.parquet")
    if not list((SILVER_DIR / "stats_team").glob("*.parquet")):
        console.print("  [yellow]ref_team_stats: no silver files[/yellow]")
        return
    cols = [
        "season", "team", "season_type", "games",
        "completions", "attempts", "passing_yards", "passing_tds", "passing_interceptions",
        "sacks_suffered", "sack_yards_lost", "sack_fumbles", "sack_fumbles_lost",
        "passing_air_yards", "passing_yards_after_catch", "passing_first_downs",
        "passing_epa", "passing_2pt_conversions",
        "carries", "rushing_yards", "rushing_tds", "rushing_fumbles", "rushing_fumbles_lost",
        "rushing_first_downs", "rushing_epa", "rushing_2pt_conversions",
        "receptions", "targets", "receiving_yards", "receiving_tds", "receiving_fumbles",
        "receiving_fumbles_lost", "receiving_air_yards", "receiving_yards_after_catch",
        "receiving_first_downs", "receiving_epa", "receiving_2pt_conversions",
        "special_teams_tds",
        "def_tackles_solo", "def_tackles_with_assist", "def_tackle_assists",
        "def_tackles_for_loss", "def_tackles_for_loss_yards", "def_fumbles_forced",
        "def_sacks", "def_sack_yards", "def_qb_hits", "def_interceptions",
        "def_interception_yards", "def_pass_defended", "def_tds", "def_fumbles", "def_safeties",
        "misc_yards", "fumble_recovery_own", "fumble_recovery_yards_own",
        "fumble_recovery_opp", "fumble_recovery_yards_opp", "fumble_recovery_tds",
        "penalties", "penalty_yards", "timeouts",
        "punt_returns", "punt_return_yards", "kickoff_returns", "kickoff_return_yards",
        "fg_made", "fg_att", "fg_missed", "fg_blocked", "fg_long", "fg_pct",
        "fg_made_0_19", "fg_made_20_29", "fg_made_30_39", "fg_made_40_49",
        "fg_made_50_59", "fg_made_60_",
        "fg_missed_0_19", "fg_missed_20_29", "fg_missed_30_39", "fg_missed_40_49",
        "fg_missed_50_59", "fg_missed_60_",
        "fg_made_list", "fg_missed_list", "fg_blocked_list",
        "fg_made_distance", "fg_missed_distance", "fg_blocked_distance",
        "pat_made", "pat_att", "pat_missed", "pat_blocked", "pat_pct",
        "gwfg_made", "gwfg_att", "gwfg_missed", "gwfg_blocked",
    ]
    n = _load_via_select(con, "ref_team_stats", glob, cols)
    console.print(f"  [green]✓[/green] ref_team_stats: {n:,} rows")


def load_ref_qbr_season(con: duckdb.DuckDBPyConnection) -> None:
    files = _silver_files("espn_data")
    f = next((p for p in files if p.name == "qbr_season_level.parquet"), None)
    if not f:
        console.print("  [yellow]ref_qbr_season: no silver file[/yellow]")
        return
    con.execute(f"""
        INSERT OR REPLACE INTO ref_qbr_season
        SELECT
            season::SMALLINT,
            season_type,
            game_week,
            team_abb,
            team,
            player_id,
            name_display,
            name_first,
            name_last,
            name_short,
            headshot_href,
            rank::SMALLINT      AS qbr_rank,
            qbr_total,
            qbr_raw,
            pts_added,
            qb_plays::SMALLINT,
            epa_total,
            pass                AS epa_pass,
            run                 AS epa_run,
            sack                AS epa_sack,
            exp_sack,
            penalty,
            qualified
        FROM read_parquet('{f}')
        WHERE player_id IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM ref_qbr_season").fetchone()[0]
    console.print(f"  [green]✓[/green] ref_qbr_season: {n:,} rows")


def load_ref_qbr_week(con: duckdb.DuckDBPyConnection) -> None:
    files = _silver_files("espn_data")
    f = next((p for p in files if p.name == "qbr_week_level.parquet"), None)
    if not f:
        console.print("  [yellow]ref_qbr_week: no silver file[/yellow]")
        return
    con.execute(f"""
        INSERT OR REPLACE INTO ref_qbr_week
        SELECT
            season::SMALLINT,
            season_type,
            game_id,
            week_num::SMALLINT,
            week_text,
            team_abb,
            team,
            opp_abb,
            opp_team,
            opp_name,
            player_id,
            name_display,
            name_first,
            name_last,
            name_short,
            headshot_href,
            rank::SMALLINT      AS qbr_rank,
            qbr_total,
            qbr_raw,
            pts_added,
            qb_plays::SMALLINT,
            epa_total,
            pass                AS epa_pass,
            run                 AS epa_run,
            sack                AS epa_sack,
            exp_sack,
            penalty,
            qualified
        FROM read_parquet('{f}')
        WHERE player_id IS NOT NULL AND game_id IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM ref_qbr_week").fetchone()[0]
    console.print(f"  [green]✓[/green] ref_qbr_week: {n:,} rows")


def load_fact_historical_games(con: duckdb.DuckDBPyConnection) -> None:
    files = _silver_files("historical_gamelogs")
    if not files:
        console.print("  [yellow]fact_historical_games: no silver files found[/yellow]")
        return
    glob = str(SILVER_DIR / "historical_gamelogs" / "*.parquet")
    con.execute("DELETE FROM fact_historical_games")
    con.execute(f"""
        INSERT INTO fact_historical_games
        SELECT
            game_id,
            season::SMALLINT,
            week::SMALLINT,
            game_type,
            gameday,
            home_team,
            away_team,
            home_score::SMALLINT,
            away_score::SMALLINT,
            result::SMALLINT,
            total::SMALLINT,
            boxscore_url
        FROM read_parquet('{glob}', union_by_name=true)
        WHERE game_id IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM fact_historical_games").fetchone()[0]
    console.print(f"  [green]✓[/green] fact_historical_games: {n:,} rows")


def load_fact_game_scoring(con: duckdb.DuckDBPyConnection) -> None:
    files = _silver_files("historical_scoring")
    if not files:
        console.print("  [yellow]fact_game_scoring: no silver files found[/yellow]")
        return
    glob = str(SILVER_DIR / "historical_scoring" / "*.parquet")
    con.execute("DELETE FROM fact_game_scoring")
    con.execute(f"""
        INSERT INTO fact_game_scoring
        SELECT
            game_id,
            season::SMALLINT,
            gameday,
            play_seq::INTEGER,
            quarter::SMALLINT,
            time,
            scoring_team,
            home_score::SMALLINT,
            away_score::SMALLINT,
            description,
            boxscore_url
        FROM read_parquet('{glob}', union_by_name=true)
        WHERE game_id IS NOT NULL
    """)
    n = con.execute("SELECT COUNT(*) FROM fact_game_scoring").fetchone()[0]
    console.print(f"  [green]✓[/green] fact_game_scoring: {n:,} rows")


# ── Name resolution back-fill ────────────────────────────────────────────────

def apply_name_resolution(con: duckdb.DuckDBPyConnection) -> None:
    """Back-fill player ID columns in ref tables using resolved name_resolution data."""
    updates = [
        ("ref_combine",     "player_id", "player_name", "ref_combine"),
        ("ref_contracts",   "player_id", "player_name", "ref_contracts"),
        ("ref_draft_picks", "gsis_id",   "player_name", "ref_draft_picks"),
        ("ref_trades",      "gsis_id",   "pfr_name",    "ref_trades"),
    ]
    for table, id_col, name_col, source in updates:
        result = con.execute(f"""
            UPDATE {table} t
            SET {id_col} = nr.resolved_gsis_id
            FROM name_resolution nr
            WHERE t.{name_col} = nr.raw_name
              AND nr.source = '{source}'
              AND nr.resolved_gsis_id IS NOT NULL
              AND t.{id_col} IS NULL
        """)
        n = con.execute(f"SELECT COUNT(*) FROM {table} WHERE {id_col} IS NOT NULL").fetchone()[0]
        total = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        console.print(f"  [green]✓[/green] {table}.{id_col}: {n:,} / {total:,} resolved")


# ── Main orchestrator ────────────────────────────────────────────────────────

LOADERS = [
    ("dim_teams", load_dim_teams),
    ("dim_players", load_dim_players),
    ("dim_games", load_dim_games),
    ("fact_historical_games", load_fact_historical_games),
    ("fact_game_scoring", load_fact_game_scoring),
    ("fact_player_game_stats", load_fact_player_game_stats),
    ("fact_player_season_stats", load_fact_player_season_stats),
    ("fact_ngs_passing", load_fact_ngs_passing),
    ("fact_ngs_receiving", load_fact_ngs_receiving),
    ("fact_ngs_rushing", load_fact_ngs_rushing),
    ("ref_pfr_adv_pass", load_ref_pfr_adv_pass),
    ("ref_pfr_adv_rush", load_ref_pfr_adv_rush),
    ("ref_pfr_adv_rec", load_ref_pfr_adv_rec),
    ("ref_pfr_adv_def", load_ref_pfr_adv_def),
    ("ref_pfr_rosters", load_ref_pfr_rosters),
    ("fact_ftn_charting", load_fact_ftn_charting),
    ("fact_pbp_participation", load_fact_pbp_participation),
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
    ("ref_team_stats", load_ref_team_stats),
    ("ref_qbr_season", load_ref_qbr_season),
    ("ref_qbr_week", load_ref_qbr_week),
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
