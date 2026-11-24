"""Hand-written data dictionary for the gold layer, served to AI clients by the MCP server.

Column names and types are read live from DuckDB; this file only adds what the
schema can't say: what each table is, how far back it goes, and how to join it.
Keep it in sync with web/data_coverage.php when tables or coverage change.
"""

SCHEMA_GUIDE = """\
NFL data warehouse (DuckDB, read-only). Sources: nflverse, Pro-Football-Reference (PFR),
FiveThirtyEight, ESPN, FTN. Table prefixes: dim_ = entities, fact_ = events/stat lines,
ref_ = reference datasets from other sources.

Identifiers
- Player: gsis_id, formatted like '00-0033873' (Patrick Mahomes). It is called gsis_id,
  player_id, player_gsis_id, passer_player_id, rusher_player_id, etc. depending on the table.
  dim_players maps it to pfr_id (used by ref_pfr_* tables) and other vendor IDs.
  ref_qbr_* player_id is an ESPN ID, NOT a gsis_id; join on name or via dim_players carefully.
  Use the search_players tool to turn a name into a gsis_id.
- Game: game_id, formatted 'SEASON_WEEK_AWAY_HOME', e.g. '2023_01_DET_KC' (week zero-padded).
  Exceptions: ref_officials.game_id is the NFL game key (join dim_games.old_game_id) and
  ref_qbr_week.game_id is an ESPN ID (join dim_games.espn).
- Play: (game_id, play_id) is the key for fact_plays and all play-level tables.
- Team: abbreviations like KC, SF, PHI. Codes differ between sources, so check
  SELECT DISTINCT on the table you query before joining tables on team:
  - dim_games (1999+), play-by-play and stat tables use today's code for each franchise in
    every season: LV (Raiders, even in Oakland years), LAC (Chargers, even in San Diego years),
    LA (Rams, even in St. Louis years), JAX, WSH.
  - dim_games before 1999 uses historical codes (OAK, RAI, SD, STL, PHX, SLC, LA, ...).
  - ref_pfr_rosters uses fixed old codes in every season: OAK, SD, STL, JAC, WAS.
  - dim_teams lists both current and legacy codes (and LAR, WAS).

Conventions
- season is the year the season started (the Feb 2024 Super Bowl is season 2023).
- season_type is 'REG' or 'POST' (fact_player_season_stats also has 'REG+POST').
  dim_games.game_type is REG, WC, DIV, CON, or SB.
- Play-by-play (fact_plays and children) covers 1999 onward. Games (dim_games) go back to
  1970 with no missing seasons. Pre-1999 scoring plays are in fact_game_scoring, and
  pre-1999 full play-by-play (being back-filled season by season) is in fact_historical_plays.
- EPA = expected points added, WPA = win probability added, CPOE = completion % over expected.
"""

TABLES: dict[str, dict[str, str]] = {
    # --- dimensions ---
    "dim_games": {
        "description": "One row per game: date, teams, final score, stadium/weather, betting lines, starting QBs, coaches, referee.",
        "coverage": "1970-present. Stadium, weather, lines, QBs, coaches, referee are 1999+ only. Future games of the current season are included with NULL scores.",
        "notes": (
            "result = home_score - away_score; total = combined points. spread_line is from the home team's perspective (positive = home favored). "
            "roof is one of outdoors, dome, closed (retractable roof closed), open (retractable roof open). "
            "location is 'Home' or 'Neutral' (London/Mexico/Germany games, Super Bowls); exclude Neutral for home-field questions."
        ),
    },
    "dim_players": {
        "description": "One row per player with a known gsis_id: name, position, bio, draft info, and cross-reference IDs (pfr_id, esb_id, sleeper_id, ...).",
        "coverage": "All-time, players with an nflverse ID.",
        "notes": "Primary key gsis_id. Use pfr_id to join to ref_pfr_* tables.",
    },
    "dim_teams": {
        "description": "Team reference: abbreviation, full name, nickname, conference, division, colors, logos.",
        "coverage": "Current franchises plus legacy codes used in older games.",
        "notes": "",
    },
    # --- play-by-play ---
    "fact_plays": {
        "description": "Every play: down, distance, field position, score, play_type, yards gained, EP/EPA, WP/WPA, drive and series info.",
        "coverage": "1999-present.",
        "notes": "Key (game_id, play_id). posteam = offense, defteam = defense. yardline_100 = yards from opponent end zone. play_type in pass, run, punt, kickoff, field_goal, extra_point, qb_kneel, qb_spike, no_play.",
    },
    "fact_pass_plays": {
        "description": "Pass-play detail joined 1:1 to fact_plays: passer, receiver, air yards, YAC, completion/INT/sack flags, CPOE.",
        "coverage": "1999-present.",
        "notes": "Join to fact_plays on (game_id, play_id) for down/distance/EPA/season.",
    },
    "fact_rush_plays": {
        "description": "Rush-play detail joined 1:1 to fact_plays: rusher, run location/gap, TD and stuffed flags.",
        "coverage": "1999-present.",
        "notes": "Join to fact_plays on (game_id, play_id).",
    },
    "fact_kick_plays": {
        "description": "Kicking plays: field goals, extra points, punts, kickoffs; kicker, distance, result, returner.",
        "coverage": "1999-present.",
        "notes": "Join to fact_plays on (game_id, play_id).",
    },
    "fact_pbp_participation": {
        "description": "Per-play personnel and formations from tracking data: offense/defense personnel, box count, pass rushers, coverage type, pressure, player ID lists.",
        "coverage": "2016-present.",
        "notes": "offense_players/defense_players are delimited gsis_id lists.",
    },
    "fact_ftn_charting": {
        "description": "FTN manual charting per play: motion, play action, RPO, screen, blitzers, drops, catchable/contested ball, etc.",
        "coverage": "2022-present.",
        "notes": "Join to fact_plays on (game_id, play_id).",
    },
    "fact_game_scoring": {
        "description": "One row per scoring play (TD/FG/safety) from Pro-Football-Reference scoring summaries, with running score and description.",
        "coverage": "1970-2007; 2007 stops partway through week 13. For 1999+ prefer fact_plays (full play-by-play with player IDs and EPA).",
        "notes": "Team codes follow dim_games: historical codes before 1999, current franchise codes (LV, LAC, LA) from 1999.",
    },
    "fact_historical_plays": {
        "description": "Full play-by-play for pre-1999 games from Pro-Football-Reference: down, distance, field position, running score, description, PFR expected points, plus play_type/yards_gained/touchdown and player names parsed from the description.",
        "coverage": "Pre-1999, back-filled one season at a time from 1998 backward; check SELECT DISTINCT season. Use fact_plays for 1999+.",
        "notes": "Key is (game_id, play_seq). Player columns (passer, rusher, receiver, ...) are free-text names, not gsis_ids. No possession team column. quarter 5 = overtime. clock is often NULL in the source. Team codes match dim_games historical codes.",
    },
    # --- player stats ---
    "fact_player_game_stats": {
        "description": "One row per player per game: passing, rushing, receiving, and fantasy stat lines with EPA.",
        "coverage": "1999-present (current season through the latest completed week).",
        "notes": "player_id is a gsis_id. recent_team = team for that game (uses WSH, LA codes). Offensive/fantasy rows only; defense and kicking are in fact_player_season_stats. dakota is NULL from 2025.",
    },
    "fact_player_season_stats": {
        "description": "Season totals per player including defense and kicking (111 columns).",
        "coverage": "1999-present.",
        "notes": "season_type has REG, POST, and REG+POST rows; filter to one to avoid double counting.",
    },
    "fact_ngs_passing": {
        "description": "Next Gen Stats passing: time to throw, air yards, CPOE, aggressiveness.",
        "coverage": "2016-present.",
        "notes": "week = 0 rows are season totals.",
    },
    "fact_ngs_receiving": {
        "description": "Next Gen Stats receiving: separation, cushion, YAC over expected.",
        "coverage": "2016-present.",
        "notes": "week = 0 rows are season totals.",
    },
    "fact_ngs_rushing": {
        "description": "Next Gen Stats rushing: rush yards over expected, time to line of scrimmage, 8+ defenders in box %.",
        "coverage": "2016-present.",
        "notes": "week = 0 rows are season totals.",
    },
    # --- rosters & personnel ---
    "fact_rosters": {
        "description": "Season rosters: player, team, position, jersey, bio, draft info.",
        "coverage": "1920-present; older players may lack a gsis_id.",
        "notes": "",
    },
    "fact_weekly_rosters": {
        "description": "Roster status by team and week (active, inactive, reserve, ...).",
        "coverage": "2002-present.",
        "notes": "",
    },
    "fact_depth_charts": {
        "description": "Depth chart position per player heading into each game.",
        "coverage": "2001-present.",
        "notes": "club_code is the team; depth_team 1 = starter; depth_position is the slot (LT, WR, CB, ...). Through 2024 this is the weekly NFL depth chart and includes bye weeks; from 2025 it is the ESPN depth chart from the week before each game, so bye weeks have no rows and jersey_number is NULL.",
    },
    "fact_snap_counts": {
        "description": "Offense/defense/special-teams snaps and snap share per player per game.",
        "coverage": "2013-present.",
        "notes": "Keyed by pfr_player_id, not gsis_id.",
    },
    "fact_injuries": {
        "description": "Weekly injury reports: injury, practice participation, game status.",
        "coverage": "2009-present.",
        "notes": "",
    },
    # --- reference ---
    "ref_draft_picks": {
        "description": "Every draft pick: season, round, pick, team, player, position, college.",
        "coverage": "1980-present.",
        "notes": "gsis_id where resolvable.",
    },
    "ref_combine": {
        "description": "Combine measurements: height, weight, 40, bench, vertical, broad jump, cone, shuttle, plus draft outcome.",
        "coverage": "2000-present.",
        "notes": "",
    },
    "ref_contracts": {
        "description": "Player contracts: years, total value, APY, guarantees, APY as % of cap, and inflation-adjusted values.",
        "coverage": "1983-present (most rows 1990s onward).",
        "notes": "player_id is a gsis_id where known. year_signed = 0 means unknown.",
    },
    "ref_trades": {
        "description": "Trades: one row per asset (player or pick) moving between teams in a trade_id.",
        "coverage": "2002-present.",
        "notes": "gave and received are the two team abbreviations for that asset; rows sharing a trade_id form one trade. Pick rows have pick_season/pick_round/pick_number.",
    },
    "ref_team_stats": {
        "description": "Team season totals (offense and defense box-score aggregates).",
        "coverage": "1999-present.",
        "notes": "",
    },
    "ref_team_elo": {
        "description": "FiveThirtyEight Elo and QB-adjusted Elo before/after every game, with win probabilities.",
        "coverage": "1920-2022.",
        "notes": "team1 is the home team; neutral = true for neutral-site games."
    },
    "ref_qbr_season": {
        "description": "ESPN Total QBR season ratings.",
        "coverage": "Recent seasons (2006+).",
        "notes": "player_id is an ESPN ID, not a gsis_id.",
    },
    "ref_qbr_week": {
        "description": "ESPN Total QBR per game.",
        "coverage": "Recent seasons (2006+).",
        "notes": "player_id is an ESPN ID, not a gsis_id. game_id is an ESPN game ID: join with dim_games.espn, not dim_games.game_id.",
    },
    "ref_pfr_adv_pass": {
        "description": "PFR advanced passing season totals: drops, bad throws, pressures, pocket time, RPO and play-action splits.",
        "coverage": "2018-present.",
        "notes": "Keyed by pfr_id; join dim_players.pfr_id for gsis_id.",
    },
    "ref_pfr_adv_rush": {
        "description": "PFR advanced rushing: yards before/after contact, broken tackles.",
        "coverage": "2018-present.",
        "notes": "Keyed by pfr_id.",
    },
    "ref_pfr_adv_rec": {
        "description": "PFR advanced receiving: ADOT, YBC/YAC, broken tackles, drops, passer rating when targeted.",
        "coverage": "2018-present.",
        "notes": "Keyed by pfr_id.",
    },
    "ref_pfr_adv_def": {
        "description": "PFR advanced defense: coverage allowed, pressures, blitzes, missed tackles.",
        "coverage": "2018-present.",
        "notes": "Keyed by pfr_id.",
    },
    "ref_pfr_rosters": {
        "description": "PFR season rosters with approximate value (AV), games played, games started, salary. The only table with actual games started per player-season.",
        "coverage": "2002-2022.",
        "notes": (
            "Keyed by pfr_player_id. games_started = regular-season starts (about 22 x games per team-season); use it for "
            "'starters' questions (fact_depth_charts shows depth listings, not starts). nfl_team uses one fixed code per "
            "franchise for every season: OAK = Raiders (incl. Las Vegas), SD = Chargers (incl. LA), STL = Rams (incl. LA), "
            "JAC = Jaguars, WAS = Washington. pfr_team holds PFR's own codes (RAI, SDG, RAM, ...)."
        ),
    },
    "ref_officials": {
        "description": "Officiating crew assignments per game by position.",
        "coverage": "2015-present.",
        "notes": "game_id is the NFL's 10-digit game key (e.g. '2015091000'): join with dim_games.old_game_id, not dim_games.game_id.",
    },
    "name_resolution": {
        "description": "Pipeline mapping from raw player names in non-nflverse sources to gsis_id, with match method and confidence.",
        "coverage": "Internal.",
        "notes": "Rarely needed for analysis.",
    },
}
