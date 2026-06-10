"""DuckDB schema DDL for the gold layer."""

SCHEMA_SQL = """
-- ─────────────────────────────────────────────
-- Dimensions
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS dim_teams (
    team_abbr       VARCHAR PRIMARY KEY,
    team_name       VARCHAR,
    team_nick       VARCHAR,
    team_conf       VARCHAR,
    team_division   VARCHAR,
    team_color      VARCHAR,
    team_color2     VARCHAR,
    team_logo_url   VARCHAR,
    team_wordmark   VARCHAR
);

CREATE TABLE IF NOT EXISTS dim_players (
    gsis_id         VARCHAR PRIMARY KEY,
    display_name    VARCHAR,
    first_name      VARCHAR,
    last_name       VARCHAR,
    position        VARCHAR,
    position_group  VARCHAR,
    birth_date      DATE,
    height          INTEGER,
    weight          INTEGER,
    college         VARCHAR,
    high_school     VARCHAR,
    draft_year      SMALLINT,
    draft_round     SMALLINT,
    draft_pick      SMALLINT,
    draft_club      VARCHAR,
    esb_id          VARCHAR,
    pfr_id          VARCHAR,
    pff_id          VARCHAR,
    sleeper_id      VARCHAR,
    sportradar_id   VARCHAR,
    yahoo_id        VARCHAR,
    rotowire_id     VARCHAR,
    fantasy_data_id VARCHAR,
    status          VARCHAR,
    years_exp       SMALLINT,
    rookie_year     SMALLINT
);

CREATE TABLE IF NOT EXISTS dim_games (
    game_id         VARCHAR PRIMARY KEY,  -- nflverse format: "YYYY_WW_AWAY_HOME"
    season          SMALLINT,
    week            SMALLINT,
    game_type       VARCHAR,              -- REG, POST, SB, etc.
    gameday         DATE,
    gametime        VARCHAR,
    home_team       VARCHAR,
    away_team       VARCHAR,
    home_score      SMALLINT,
    away_score      SMALLINT,
    result          SMALLINT,             -- home_score - away_score
    total           SMALLINT,
    overtime        BOOLEAN,
    stadium         VARCHAR,
    location        VARCHAR,              -- home/away/neutral
    roof            VARCHAR,
    surface         VARCHAR,
    temp            SMALLINT,
    wind            SMALLINT,
    spread_line     FLOAT,
    total_line      FLOAT,
    div_game        BOOLEAN
);

-- ─────────────────────────────────────────────
-- Fact tables
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS fact_plays (
    play_id             INTEGER,
    game_id             VARCHAR,
    season              SMALLINT,
    week                SMALLINT,
    game_date           DATE,
    quarter             SMALLINT,
    game_seconds_remaining INTEGER,
    half_seconds_remaining INTEGER,
    quarter_seconds_remaining INTEGER,
    down                SMALLINT,
    ydstogo             SMALLINT,
    yardline_100        SMALLINT,         -- yards from opponent end zone
    posteam             VARCHAR,
    defteam             VARCHAR,
    posteam_score       SMALLINT,
    defteam_score       SMALLINT,
    score_differential  SMALLINT,
    play_type           VARCHAR,          -- pass, run, punt, field_goal, kickoff, no_play, etc.
    yards_gained        SMALLINT,
    touchdown           BOOLEAN,
    turnover            BOOLEAN,
    penalty             BOOLEAN,
    penalty_yards       SMALLINT,
    first_down          BOOLEAN,
    ep                  FLOAT,            -- expected points
    epa                 FLOAT,            -- expected points added
    wp                  FLOAT,            -- win probability before
    wpa                 FLOAT,            -- win probability added
    air_epa             FLOAT,
    yac_epa             FLOAT,
    comp_air_epa        FLOAT,
    comp_yac_epa        FLOAT,
    qb_epa              FLOAT,
    xyac_epa            FLOAT,
    series              SMALLINT,
    series_success      BOOLEAN,
    drive               SMALLINT,
    sp                  BOOLEAN,          -- scoring play
    PRIMARY KEY (game_id, play_id)
);

CREATE TABLE IF NOT EXISTS fact_pass_plays (
    game_id             VARCHAR,
    play_id             INTEGER,
    passer_player_id    VARCHAR,
    passer_player_name  VARCHAR,
    receiver_player_id  VARCHAR,
    receiver_player_name VARCHAR,
    pass_length         VARCHAR,          -- short/deep
    pass_location       VARCHAR,          -- left/middle/right
    air_yards           SMALLINT,
    yards_after_catch   SMALLINT,
    complete_pass       BOOLEAN,
    incomplete_pass     BOOLEAN,
    interception        BOOLEAN,
    sack                BOOLEAN,
    qb_hit              BOOLEAN,
    qb_scramble         BOOLEAN,
    pass_touchdown      BOOLEAN,
    cpoe                FLOAT,
    air_yards_epa       FLOAT,
    PRIMARY KEY (game_id, play_id),
);

CREATE TABLE IF NOT EXISTS fact_rush_plays (
    game_id             VARCHAR,
    play_id             INTEGER,
    rusher_player_id    VARCHAR,
    rusher_player_name  VARCHAR,
    run_location        VARCHAR,          -- left/middle/right
    run_gap             VARCHAR,          -- end/tackle/guard
    rush_touchdown      BOOLEAN,
    stuffed_run         BOOLEAN,
    PRIMARY KEY (game_id, play_id),
);

CREATE TABLE IF NOT EXISTS fact_kick_plays (
    game_id                 VARCHAR,
    play_id                 INTEGER,
    play_subtype            VARCHAR,       -- punt, field_goal, kickoff, extra_point
    kicker_player_id        VARCHAR,
    kicker_player_name      VARCHAR,
    kick_distance           SMALLINT,
    field_goal_result       VARCHAR,       -- made/missed/blocked
    field_goal_attempt      BOOLEAN,
    extra_point_result      VARCHAR,
    extra_point_attempt     BOOLEAN,
    punt_blocked            BOOLEAN,
    return_player_id        VARCHAR,
    return_player_name      VARCHAR,
    return_yards            SMALLINT,
    PRIMARY KEY (game_id, play_id),
);

CREATE TABLE IF NOT EXISTS fact_player_game_stats (
    game_id                 VARCHAR,
    player_id               VARCHAR,
    player_name             VARCHAR,
    recent_team             VARCHAR,
    season                  SMALLINT,
    week                    SMALLINT,
    season_type             VARCHAR,
    -- passing
    completions             SMALLINT,
    attempts                SMALLINT,
    passing_yards           SMALLINT,
    passing_tds             SMALLINT,
    interceptions           SMALLINT,
    sacks                   FLOAT,
    sack_yards              SMALLINT,
    sack_fumbles            SMALLINT,
    sack_fumbles_lost       SMALLINT,
    passing_air_yards       SMALLINT,
    passing_yards_after_catch SMALLINT,
    passing_first_downs     SMALLINT,
    passing_epa             FLOAT,
    passing_2pt_conversions SMALLINT,
    pacr                    FLOAT,
    dakota                  FLOAT,
    -- rushing
    carries                 SMALLINT,
    rushing_yards           SMALLINT,
    rushing_tds             SMALLINT,
    rushing_fumbles         SMALLINT,
    rushing_fumbles_lost    SMALLINT,
    rushing_first_downs     SMALLINT,
    rushing_epa             FLOAT,
    rushing_2pt_conversions SMALLINT,
    -- receiving
    receptions              SMALLINT,
    targets                 SMALLINT,
    receiving_yards         SMALLINT,
    receiving_tds           SMALLINT,
    receiving_fumbles       SMALLINT,
    receiving_fumbles_lost  SMALLINT,
    receiving_air_yards     SMALLINT,
    receiving_yards_after_catch SMALLINT,
    receiving_first_downs   SMALLINT,
    receiving_epa           FLOAT,
    receiving_2pt_conversions SMALLINT,
    racr                    FLOAT,
    target_share            FLOAT,
    air_yards_share         FLOAT,
    wopr                    FLOAT,
    special_teams_tds       SMALLINT,
    fantasy_points          FLOAT,
    fantasy_points_ppr      FLOAT,
    PRIMARY KEY (player_id, season, week, season_type)
);

CREATE TABLE IF NOT EXISTS fact_rosters (
    season          SMALLINT,
    team            VARCHAR,
    position        VARCHAR,
    depth_chart_position VARCHAR,
    jersey_number   SMALLINT,
    status          VARCHAR,
    player_name     VARCHAR,
    player_id       VARCHAR,
    birth_date      DATE,
    height          VARCHAR,
    weight          SMALLINT,
    college         VARCHAR,
    years_exp       SMALLINT,
    entry_year      SMALLINT,
    rookie_year     SMALLINT,
    draft_club      VARCHAR,
    draft_number    SMALLINT,
    PRIMARY KEY (season, team, player_id)
);

-- Reference tables (enrichment, not time-series facts)

CREATE TABLE IF NOT EXISTS ref_draft_picks (
    season          SMALLINT,
    round           SMALLINT,
    pick            SMALLINT,
    team            VARCHAR,
    player_name     VARCHAR,
    gsis_id         VARCHAR,
    pfr_player_id   VARCHAR,
    position        VARCHAR,
    category        VARCHAR,
    side            VARCHAR,
    college         VARCHAR,
    PRIMARY KEY (season, round, pick)
);

CREATE TABLE IF NOT EXISTS ref_combine (
    season          SMALLINT,
    player_name     VARCHAR,
    player_id       VARCHAR,
    pos             VARCHAR,
    school          VARCHAR,
    ht              VARCHAR,
    wt              SMALLINT,
    forty           FLOAT,
    bench           SMALLINT,
    vertical        FLOAT,
    broad_jump      SMALLINT,
    cone            FLOAT,
    shuttle         FLOAT,
    draft_year      SMALLINT,
    draft_round     SMALLINT,
    draft_pick      SMALLINT,
    draft_ovr       SMALLINT,
    PRIMARY KEY (season, player_name)
);

CREATE TABLE IF NOT EXISTS ref_contracts (
    player_name         VARCHAR,
    player_id           VARCHAR,
    team                VARCHAR,
    position            VARCHAR,
    year_signed         SMALLINT,
    years               SMALLINT,
    value               BIGINT,
    apy                 BIGINT,
    guaranteed          BIGINT,
    apy_cap_pct         FLOAT,
    inflated_value      BIGINT,
    inflated_apy        BIGINT,
    inflated_guaranteed BIGINT
);

CREATE TABLE IF NOT EXISTS fact_snap_counts (
    game_id         VARCHAR,
    pfr_game_id     VARCHAR,
    season          SMALLINT,
    game_type       VARCHAR,
    week            SMALLINT,
    player          VARCHAR,
    pfr_player_id   VARCHAR,
    position        VARCHAR,
    team            VARCHAR,
    opponent        VARCHAR,
    offense_snaps   SMALLINT,
    offense_pct     FLOAT,
    defense_snaps   SMALLINT,
    defense_pct     FLOAT,
    st_snaps        SMALLINT,
    st_pct          FLOAT,
    PRIMARY KEY (game_id, pfr_player_id)
);

CREATE TABLE IF NOT EXISTS fact_depth_charts (
    season          SMALLINT,
    club_code       VARCHAR,
    week            SMALLINT,
    game_type       VARCHAR,
    gsis_id         VARCHAR,
    full_name       VARCHAR,
    position        VARCHAR,
    depth_team      SMALLINT,
    depth_position  VARCHAR,
    last_name       VARCHAR,
    first_name      VARCHAR,
    jersey_number   SMALLINT,
    PRIMARY KEY (season, week, club_code, gsis_id, position)
);

CREATE TABLE IF NOT EXISTS fact_injuries (
    season                  SMALLINT,
    game_type               VARCHAR,
    team                    VARCHAR,
    week                    SMALLINT,
    gsis_id                 VARCHAR,
    position                VARCHAR,
    full_name               VARCHAR,
    report_primary_injury   VARCHAR,
    report_secondary_injury VARCHAR,
    report_status           VARCHAR,
    practice_primary_injury VARCHAR,
    practice_secondary_injury VARCHAR,
    practice_status         VARCHAR,
    date_modified           TIMESTAMP,
    PRIMARY KEY (season, week, team, gsis_id)
);

CREATE TABLE IF NOT EXISTS fact_weekly_rosters (
    season          SMALLINT,
    team            VARCHAR,
    week            SMALLINT,
    position        VARCHAR,
    depth_chart_position VARCHAR,
    jersey_number   SMALLINT,
    status          VARCHAR,
    full_name       VARCHAR,
    gsis_id         VARCHAR,
    years_exp       SMALLINT,
    entry_year      SMALLINT,
    rookie_year     SMALLINT,
    draft_club      VARCHAR,
    draft_number    SMALLINT,
    PRIMARY KEY (season, week, team, gsis_id)
);

CREATE TABLE IF NOT EXISTS ref_officials (
    season          SMALLINT,
    game_id         VARCHAR,
    official_id     VARCHAR,
    official_name   VARCHAR,
    position        VARCHAR,
    jersey_number   SMALLINT,
    PRIMARY KEY (game_id, official_id)
);

CREATE TABLE IF NOT EXISTS ref_trades (
    trade_id        INTEGER,
    season          SMALLINT,
    trade_date      DATE,
    gave            VARCHAR,
    received        VARCHAR,
    pfr_id          VARCHAR,
    pfr_name        VARCHAR,
    gsis_id         VARCHAR,
    pick_season     SMALLINT,
    pick_round      SMALLINT,
    pick_number     SMALLINT,
    conditional     BOOLEAN
);
ALTER TABLE ref_trades ADD COLUMN IF NOT EXISTS gsis_id VARCHAR;

CREATE TABLE IF NOT EXISTS ref_team_stats (
    season              SMALLINT,
    team                VARCHAR,
    season_type         VARCHAR,
    games               SMALLINT,
    -- passing
    completions         INTEGER,
    attempts            INTEGER,
    passing_yards       INTEGER,
    passing_tds         SMALLINT,
    passing_interceptions SMALLINT,
    sacks_suffered      SMALLINT,
    sack_yards_lost     INTEGER,
    sack_fumbles        SMALLINT,
    sack_fumbles_lost   SMALLINT,
    passing_air_yards   INTEGER,
    passing_yards_after_catch INTEGER,
    passing_first_downs SMALLINT,
    passing_epa         FLOAT,
    passing_2pt_conversions SMALLINT,
    -- rushing
    carries             INTEGER,
    rushing_yards       INTEGER,
    rushing_tds         SMALLINT,
    rushing_fumbles     SMALLINT,
    rushing_fumbles_lost SMALLINT,
    rushing_first_downs SMALLINT,
    rushing_epa         FLOAT,
    rushing_2pt_conversions SMALLINT,
    -- receiving
    receptions          INTEGER,
    targets             INTEGER,
    receiving_yards     INTEGER,
    receiving_tds       SMALLINT,
    receiving_fumbles   SMALLINT,
    receiving_fumbles_lost SMALLINT,
    receiving_air_yards INTEGER,
    receiving_yards_after_catch INTEGER,
    receiving_first_downs SMALLINT,
    receiving_epa       FLOAT,
    receiving_2pt_conversions SMALLINT,
    special_teams_tds   SMALLINT,
    -- defense
    def_tackles_solo    INTEGER,
    def_tackles_with_assist INTEGER,
    def_tackle_assists  INTEGER,
    def_tackles_for_loss INTEGER,
    def_tackles_for_loss_yards INTEGER,
    def_fumbles_forced  SMALLINT,
    def_sacks           FLOAT,
    def_sack_yards      FLOAT,
    def_qb_hits         SMALLINT,
    def_interceptions   SMALLINT,
    def_interception_yards INTEGER,
    def_pass_defended   SMALLINT,
    def_tds             SMALLINT,
    def_fumbles         SMALLINT,
    def_safeties        SMALLINT,
    -- misc / fumbles / penalties
    misc_yards          INTEGER,
    fumble_recovery_own SMALLINT,
    fumble_recovery_yards_own INTEGER,
    fumble_recovery_opp SMALLINT,
    fumble_recovery_yards_opp INTEGER,
    fumble_recovery_tds SMALLINT,
    penalties           SMALLINT,
    penalty_yards       INTEGER,
    timeouts            SMALLINT,
    -- returns
    punt_returns        SMALLINT,
    punt_return_yards   INTEGER,
    kickoff_returns     SMALLINT,
    kickoff_return_yards INTEGER,
    -- kicking
    fg_made             SMALLINT,
    fg_att              SMALLINT,
    fg_missed           SMALLINT,
    fg_blocked          SMALLINT,
    fg_long             SMALLINT,
    fg_pct              FLOAT,
    fg_made_0_19        SMALLINT,
    fg_made_20_29       SMALLINT,
    fg_made_30_39       SMALLINT,
    fg_made_40_49       SMALLINT,
    fg_made_50_59       SMALLINT,
    fg_made_60_         SMALLINT,
    fg_missed_0_19      SMALLINT,
    fg_missed_20_29     SMALLINT,
    fg_missed_30_39     SMALLINT,
    fg_missed_40_49     SMALLINT,
    fg_missed_50_59     SMALLINT,
    fg_missed_60_       SMALLINT,
    fg_made_list        VARCHAR,
    fg_missed_list      VARCHAR,
    fg_blocked_list     VARCHAR,
    fg_made_distance    INTEGER,
    fg_missed_distance  INTEGER,
    fg_blocked_distance INTEGER,
    pat_made            SMALLINT,
    pat_att             SMALLINT,
    pat_missed          SMALLINT,
    pat_blocked         SMALLINT,
    pat_pct             FLOAT,
    gwfg_made           SMALLINT,
    gwfg_att            SMALLINT,
    gwfg_missed         SMALLINT,
    gwfg_blocked        SMALLINT,
    PRIMARY KEY (season, team, season_type)
);

CREATE TABLE IF NOT EXISTS fact_pbp_participation (
    game_id             VARCHAR,    -- nflverse game_id, joins to fact_plays.game_id
    play_id             INTEGER,    -- joins to fact_plays.play_id
    possession_team     VARCHAR,
    offense_formation   VARCHAR,
    offense_personnel   VARCHAR,
    defense_personnel   VARCHAR,
    defenders_in_box    SMALLINT,
    number_of_pass_rushers SMALLINT,
    n_offense           SMALLINT,
    n_defense           SMALLINT,
    offense_players     VARCHAR,    -- space-separated gsis_ids
    defense_players     VARCHAR,    -- space-separated gsis_ids
    ngs_air_yards       FLOAT,
    time_to_throw       FLOAT,
    was_pressure        BOOLEAN,
    route                VARCHAR,
    defense_man_zone_type VARCHAR,
    defense_coverage_type VARCHAR,
    PRIMARY KEY (game_id, play_id)
);

CREATE TABLE IF NOT EXISTS fact_ftn_charting (
    game_id             VARCHAR,    -- nflverse game_id, joins to fact_plays.game_id
    play_id             INTEGER,    -- nflverse play_id, joins to fact_plays.play_id
    ftn_game_id         INTEGER,
    ftn_play_id         INTEGER,
    season              SMALLINT,
    week                SMALLINT,
    starting_hash       VARCHAR,
    qb_location         VARCHAR,
    n_offense_backfield SMALLINT,
    n_defense_box       SMALLINT,
    n_blitzers          SMALLINT,
    n_pass_rushers      SMALLINT,
    is_no_huddle        BOOLEAN,
    is_motion           BOOLEAN,
    is_play_action      BOOLEAN,
    is_screen_pass      BOOLEAN,
    is_rpo              BOOLEAN,
    is_trick_play       BOOLEAN,
    is_qb_sneak         BOOLEAN,
    is_qb_out_of_pocket BOOLEAN,
    is_qb_fault_sack    BOOLEAN,
    is_throw_away       BOOLEAN,
    is_catchable_ball   BOOLEAN,
    is_contested_ball   BOOLEAN,
    is_created_reception BOOLEAN,
    is_drop             BOOLEAN,
    is_interception_worthy BOOLEAN,
    read_thrown         VARCHAR,
    PRIMARY KEY (game_id, play_id)
);

CREATE TABLE IF NOT EXISTS ref_pfr_rosters (
    season              SMALLINT,
    pfr_team            VARCHAR,    -- PFR team code
    nfl_team            VARCHAR,    -- nflverse team abbr
    pfr_player_id       VARCHAR,
    player              VARCHAR,
    jersey_number       SMALLINT,
    age                 SMALLINT,
    position            VARCHAR,
    games               SMALLINT,
    games_started       SMALLINT,
    weight              SMALLINT,
    height              VARCHAR,
    college             VARCHAR,
    birth_date          VARCHAR,
    years_exp           VARCHAR,
    approximate_value   SMALLINT,
    drafted_tm_rnd_yr   VARCHAR,
    salary              VARCHAR,
    PRIMARY KEY (season, pfr_player_id)
);

CREATE TABLE IF NOT EXISTS ref_pfr_adv_pass (
    season              SMALLINT,
    pfr_id              VARCHAR,
    player              VARCHAR,
    team                VARCHAR,
    pass_attempts       SMALLINT,
    throwaways          SMALLINT,
    spikes              SMALLINT,
    drops               SMALLINT,
    drop_pct            FLOAT,
    bad_throws          SMALLINT,
    bad_throw_pct       FLOAT,
    on_tgt_throws       SMALLINT,
    on_tgt_pct          FLOAT,
    pocket_time         FLOAT,
    times_blitzed       SMALLINT,
    times_hurried       SMALLINT,
    times_hit           SMALLINT,
    times_pressured     SMALLINT,
    pressure_pct        FLOAT,
    batted_balls        SMALLINT,
    scrambles           SMALLINT,
    scramble_yards_per_attempt FLOAT,
    intended_air_yards  INTEGER,
    intended_air_yards_per_pass_attempt FLOAT,
    completed_air_yards INTEGER,
    completed_air_yards_per_completion FLOAT,
    completed_air_yards_per_pass_attempt FLOAT,
    pass_yards_after_catch INTEGER,
    pass_yards_after_catch_per_completion FLOAT,
    rpo_plays           SMALLINT,
    rpo_yards           INTEGER,
    rpo_pass_att        SMALLINT,
    rpo_pass_yards      INTEGER,
    rpo_rush_att        SMALLINT,
    rpo_rush_yards      INTEGER,
    pa_pass_att         SMALLINT,
    pa_pass_yards       INTEGER,
    PRIMARY KEY (season, pfr_id)
);

CREATE TABLE IF NOT EXISTS ref_pfr_adv_rush (
    season              SMALLINT,
    pfr_id              VARCHAR,
    player              VARCHAR,
    team                VARCHAR,
    age                 SMALLINT,
    position            VARCHAR,
    games               SMALLINT,
    games_started       SMALLINT,
    attempts            INTEGER,
    yards               INTEGER,
    tds                 SMALLINT,
    first_downs         SMALLINT,
    yards_before_contact INTEGER,
    yards_before_contact_per_att FLOAT,
    yards_after_contact INTEGER,
    yards_after_contact_per_att FLOAT,
    broken_tackles      SMALLINT,
    attempts_per_broken_tackle FLOAT,
    loaded_at           DATE,
    PRIMARY KEY (season, pfr_id)
);

CREATE TABLE IF NOT EXISTS ref_pfr_adv_rec (
    season              SMALLINT,
    pfr_id              VARCHAR,
    player              VARCHAR,
    team                VARCHAR,
    age                 SMALLINT,
    position            VARCHAR,
    games               SMALLINT,
    games_started       SMALLINT,
    targets             INTEGER,
    receptions          INTEGER,
    yards               INTEGER,
    tds                 SMALLINT,
    first_downs         SMALLINT,
    yards_before_catch  INTEGER,
    yards_before_catch_per_rec FLOAT,
    yards_after_catch   INTEGER,
    yards_after_catch_per_rec FLOAT,
    avg_depth_of_target FLOAT,
    broken_tackles      SMALLINT,
    receptions_per_broken_tackle FLOAT,
    drops               SMALLINT,
    drop_pct            FLOAT,
    interceptions_when_targeted SMALLINT,
    passer_rating_when_targeted FLOAT,
    loaded_at           DATE,
    PRIMARY KEY (season, pfr_id)
);

CREATE TABLE IF NOT EXISTS ref_pfr_adv_def (
    season              SMALLINT,
    pfr_id              VARCHAR,
    player              VARCHAR,
    team                VARCHAR,
    age                 SMALLINT,
    position            VARCHAR,
    games               SMALLINT,
    games_started       SMALLINT,
    interceptions       SMALLINT,
    targets             INTEGER,
    completions_allowed INTEGER,
    completion_pct_allowed FLOAT,
    yards_allowed       INTEGER,
    yards_per_completion_allowed FLOAT,
    yards_per_target_allowed FLOAT,
    tds_allowed         SMALLINT,
    passer_rating_allowed FLOAT,
    avg_depth_of_target_allowed FLOAT,
    air_yards_allowed   INTEGER,
    yards_after_catch_allowed INTEGER,
    blitzes             SMALLINT,
    hurries             SMALLINT,
    qb_knockdowns       SMALLINT,
    sacks               FLOAT,
    pressures           SMALLINT,
    combined_tackles    SMALLINT,
    missed_tackles      SMALLINT,
    missed_tackle_pct   FLOAT,
    batted_passes       SMALLINT,
    loaded_at           DATE,
    PRIMARY KEY (season, pfr_id)
);

CREATE TABLE IF NOT EXISTS fact_ngs_passing (
    season              SMALLINT,
    season_type         VARCHAR,
    week                SMALLINT,       -- 0 = season total
    player_gsis_id      VARCHAR,
    player_display_name VARCHAR,
    player_first_name   VARCHAR,
    player_last_name    VARCHAR,
    player_short_name   VARCHAR,
    player_jersey_number SMALLINT,
    player_position     VARCHAR,
    team_abbr           VARCHAR,
    attempts            SMALLINT,
    completions         SMALLINT,
    pass_yards          INTEGER,
    pass_touchdowns     SMALLINT,
    interceptions       SMALLINT,
    passer_rating       FLOAT,
    completion_percentage FLOAT,
    expected_completion_percentage FLOAT,
    completion_percentage_above_expectation FLOAT,
    avg_time_to_throw   FLOAT,
    avg_completed_air_yards FLOAT,
    avg_intended_air_yards FLOAT,
    avg_air_yards_differential FLOAT,
    avg_air_yards_to_sticks FLOAT,
    avg_air_distance    FLOAT,
    max_air_distance    FLOAT,
    max_completed_air_distance FLOAT,
    aggressiveness      FLOAT,
    PRIMARY KEY (season, season_type, week, player_gsis_id)
);

CREATE TABLE IF NOT EXISTS fact_ngs_receiving (
    season              SMALLINT,
    season_type         VARCHAR,
    week                SMALLINT,       -- 0 = season total
    player_gsis_id      VARCHAR,
    player_display_name VARCHAR,
    player_first_name   VARCHAR,
    player_last_name    VARCHAR,
    player_short_name   VARCHAR,
    player_jersey_number SMALLINT,
    player_position     VARCHAR,
    team_abbr           VARCHAR,
    targets             SMALLINT,
    receptions          SMALLINT,
    yards               INTEGER,
    rec_touchdowns      SMALLINT,
    catch_percentage    FLOAT,
    avg_cushion         FLOAT,
    avg_separation      FLOAT,
    avg_intended_air_yards FLOAT,
    percent_share_of_intended_air_yards FLOAT,
    avg_yac             FLOAT,
    avg_expected_yac    FLOAT,
    avg_yac_above_expectation FLOAT,
    PRIMARY KEY (season, season_type, week, player_gsis_id)
);

CREATE TABLE IF NOT EXISTS fact_ngs_rushing (
    season              SMALLINT,
    season_type         VARCHAR,
    week                SMALLINT,       -- 0 = season total
    player_gsis_id      VARCHAR,
    player_display_name VARCHAR,
    player_first_name   VARCHAR,
    player_last_name    VARCHAR,
    player_short_name   VARCHAR,
    player_jersey_number SMALLINT,
    player_position     VARCHAR,
    team_abbr           VARCHAR,
    rush_attempts       SMALLINT,
    rush_yards          INTEGER,
    rush_touchdowns     SMALLINT,
    avg_rush_yards      FLOAT,
    efficiency          FLOAT,
    percent_attempts_gte_eight_defenders FLOAT,
    avg_time_to_los     FLOAT,
    expected_rush_yards FLOAT,
    rush_yards_over_expected FLOAT,
    rush_yards_over_expected_per_att FLOAT,
    rush_pct_over_expected FLOAT,
    PRIMARY KEY (season, season_type, week, player_gsis_id)
);

CREATE TABLE IF NOT EXISTS fact_player_season_stats (
    player_id           VARCHAR,
    player_name         VARCHAR,
    player_display_name VARCHAR,
    position            VARCHAR,
    position_group      VARCHAR,
    headshot_url        VARCHAR,
    season              SMALLINT,
    season_type         VARCHAR,
    recent_team         VARCHAR,
    games               SMALLINT,
    -- passing
    completions         INTEGER,
    attempts            INTEGER,
    passing_yards       INTEGER,
    passing_tds         SMALLINT,
    passing_interceptions SMALLINT,
    sacks_suffered      SMALLINT,
    sack_yards_lost     INTEGER,
    sack_fumbles        SMALLINT,
    sack_fumbles_lost   SMALLINT,
    passing_air_yards   INTEGER,
    passing_yards_after_catch INTEGER,
    passing_first_downs SMALLINT,
    passing_epa         FLOAT,
    passing_2pt_conversions SMALLINT,
    pacr                FLOAT,
    -- rushing
    carries             INTEGER,
    rushing_yards       INTEGER,
    rushing_tds         SMALLINT,
    rushing_fumbles     SMALLINT,
    rushing_fumbles_lost SMALLINT,
    rushing_first_downs SMALLINT,
    rushing_epa         FLOAT,
    rushing_2pt_conversions SMALLINT,
    -- receiving
    receptions          INTEGER,
    targets             INTEGER,
    receiving_yards     INTEGER,
    receiving_tds       SMALLINT,
    receiving_fumbles   SMALLINT,
    receiving_fumbles_lost SMALLINT,
    receiving_air_yards INTEGER,
    receiving_yards_after_catch INTEGER,
    receiving_first_downs SMALLINT,
    receiving_epa       FLOAT,
    receiving_2pt_conversions SMALLINT,
    racr                FLOAT,
    target_share        FLOAT,
    air_yards_share     FLOAT,
    wopr                FLOAT,
    special_teams_tds   SMALLINT,
    -- defense
    def_tackles_solo    INTEGER,
    def_tackles_with_assist INTEGER,
    def_tackle_assists  INTEGER,
    def_tackles_for_loss INTEGER,
    def_tackles_for_loss_yards INTEGER,
    def_fumbles_forced  SMALLINT,
    def_sacks           FLOAT,
    def_sack_yards      FLOAT,
    def_qb_hits         SMALLINT,
    def_interceptions   SMALLINT,
    def_interception_yards INTEGER,
    def_pass_defended   SMALLINT,
    def_tds             SMALLINT,
    def_fumbles         SMALLINT,
    def_safeties        SMALLINT,
    -- misc / fumbles / penalties
    misc_yards          INTEGER,
    fumble_recovery_own SMALLINT,
    fumble_recovery_yards_own INTEGER,
    fumble_recovery_opp SMALLINT,
    fumble_recovery_yards_opp INTEGER,
    fumble_recovery_tds SMALLINT,
    penalties           SMALLINT,
    penalty_yards       INTEGER,
    -- returns
    punt_returns        SMALLINT,
    punt_return_yards   INTEGER,
    kickoff_returns     SMALLINT,
    kickoff_return_yards INTEGER,
    -- kicking
    fg_made             SMALLINT,
    fg_att              SMALLINT,
    fg_missed           SMALLINT,
    fg_blocked          SMALLINT,
    fg_long             SMALLINT,
    fg_pct              FLOAT,
    fg_made_0_19        SMALLINT,
    fg_made_20_29       SMALLINT,
    fg_made_30_39       SMALLINT,
    fg_made_40_49       SMALLINT,
    fg_made_50_59       SMALLINT,
    fg_made_60_         SMALLINT,
    fg_missed_0_19      SMALLINT,
    fg_missed_20_29     SMALLINT,
    fg_missed_30_39     SMALLINT,
    fg_missed_40_49     SMALLINT,
    fg_missed_50_59     SMALLINT,
    fg_missed_60_       SMALLINT,
    fg_made_list        VARCHAR,
    fg_missed_list      VARCHAR,
    fg_blocked_list     VARCHAR,
    fg_made_distance    INTEGER,
    fg_missed_distance  INTEGER,
    fg_blocked_distance INTEGER,
    pat_made            SMALLINT,
    pat_att             SMALLINT,
    pat_missed          SMALLINT,
    pat_blocked         SMALLINT,
    pat_pct             FLOAT,
    gwfg_made           SMALLINT,
    gwfg_att            SMALLINT,
    gwfg_missed         SMALLINT,
    gwfg_blocked        SMALLINT,
    fantasy_points      FLOAT,
    fantasy_points_ppr  FLOAT,
    PRIMARY KEY (player_id, season, season_type)
);

CREATE TABLE IF NOT EXISTS ref_qbr_season (
    season          SMALLINT,
    season_type     VARCHAR,        -- Regular | Playoffs
    game_week       VARCHAR,        -- 'Season Total'
    team_abb        VARCHAR,
    team            VARCHAR,
    player_id       VARCHAR,        -- ESPN player id
    name_display    VARCHAR,
    name_first      VARCHAR,
    name_last       VARCHAR,
    name_short      VARCHAR,
    headshot_href   VARCHAR,
    qbr_rank        SMALLINT,
    qbr_total       FLOAT,
    qbr_raw         FLOAT,
    pts_added       FLOAT,
    qb_plays        SMALLINT,
    epa_total       FLOAT,
    epa_pass        FLOAT,
    epa_run         FLOAT,
    epa_sack        FLOAT,
    exp_sack        FLOAT,
    penalty         FLOAT,
    qualified       BOOLEAN,
    PRIMARY KEY (season, season_type, game_week, player_id)
);

CREATE TABLE IF NOT EXISTS ref_qbr_week (
    season          SMALLINT,
    season_type     VARCHAR,        -- Regular | Playoffs
    game_id         VARCHAR,        -- ESPN game id
    week_num        SMALLINT,
    week_text       VARCHAR,
    team_abb        VARCHAR,
    team            VARCHAR,
    opp_abb         VARCHAR,
    opp_team        VARCHAR,
    opp_name        VARCHAR,
    player_id       VARCHAR,        -- ESPN player id
    name_display    VARCHAR,
    name_first      VARCHAR,
    name_last       VARCHAR,
    name_short      VARCHAR,
    headshot_href   VARCHAR,
    qbr_rank        SMALLINT,
    qbr_total       FLOAT,
    qbr_raw         FLOAT,
    pts_added       FLOAT,
    qb_plays        SMALLINT,
    epa_total       FLOAT,
    epa_pass        FLOAT,
    epa_run         FLOAT,
    epa_sack        FLOAT,
    exp_sack        FLOAT,
    penalty         FLOAT,
    qualified       BOOLEAN,
    PRIMARY KEY (game_id, player_id)
);

-- ─────────────────────────────────────────────
-- Name resolution lookup table
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS name_resolution (
    raw_name            VARCHAR,
    source              VARCHAR,    -- e.g. 'fact_pass_plays.passer_player_name'
    resolved_gsis_id    VARCHAR,
    canonical_name      VARCHAR,    -- dim_players.display_name
    confidence          FLOAT,      -- 1.0 = exact ID anchor, <1.0 = fuzzy
    method              VARCHAR,    -- id_anchor | fuzzy | fuzzy_review | manual | rejected
    PRIMARY KEY (raw_name, source)
);

-- ─────────────────────────────────────────────
-- Views: play tables with canonical names
-- ─────────────────────────────────────────────

CREATE OR REPLACE VIEW v_pass_plays AS
SELECT
    pp.*,
    COALESCE(nr_p.canonical_name, pp.passer_player_name)   AS canonical_passer_name,
    COALESCE(nr_r.canonical_name, pp.receiver_player_name) AS canonical_receiver_name
FROM fact_pass_plays pp
LEFT JOIN name_resolution nr_p
    ON pp.passer_player_name = nr_p.raw_name
   AND nr_p.source = 'fact_pass_plays.passer_player_name'
   AND nr_p.method != 'rejected'
LEFT JOIN name_resolution nr_r
    ON pp.receiver_player_name = nr_r.raw_name
   AND nr_r.source = 'fact_pass_plays.receiver_player_name'
   AND nr_r.method != 'rejected';

CREATE OR REPLACE VIEW v_rush_plays AS
SELECT
    rp.*,
    COALESCE(nr.canonical_name, rp.rusher_player_name) AS canonical_rusher_name
FROM fact_rush_plays rp
LEFT JOIN name_resolution nr
    ON rp.rusher_player_name = nr.raw_name
   AND nr.source = 'fact_rush_plays.rusher_player_name'
   AND nr.method != 'rejected';

CREATE OR REPLACE VIEW v_kick_plays AS
SELECT
    kp.*,
    COALESCE(nr_k.canonical_name, kp.kicker_player_name) AS canonical_kicker_name,
    COALESCE(nr_r.canonical_name, kp.return_player_name) AS canonical_return_name
FROM fact_kick_plays kp
LEFT JOIN name_resolution nr_k
    ON kp.kicker_player_name = nr_k.raw_name
   AND nr_k.source = 'fact_kick_plays.kicker_player_name'
   AND nr_k.method != 'rejected'
LEFT JOIN name_resolution nr_r
    ON kp.return_player_name = nr_r.raw_name
   AND nr_r.source = 'fact_kick_plays.return_player_name'
   AND nr_r.method != 'rejected';
"""
