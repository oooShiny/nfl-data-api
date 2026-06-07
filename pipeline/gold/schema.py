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
    pick_season     SMALLINT,
    pick_round      SMALLINT,
    pick_number     SMALLINT,
    conditional     BOOLEAN
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
