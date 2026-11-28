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
  - dim_games before 1999 uses historical codes (OAK, RAI, SD, STL, PHX, SLC, LA, ...), and so
    do fact_rosters, fact_historical_plays and fact_game_scoring for those seasons.
  - ref_pfr_rosters uses fixed old codes in every season: OAK, SD, STL, JAC, WAS.
  - dim_teams lists both current and legacy codes (and LAR, WAS).

Conventions
- season is the year the season started (the Feb 2024 Super Bowl is season 2023).
- season_type is 'REG' or 'POST' (fact_player_season_stats also has 'REG+POST').
  dim_games.game_type is REG, WC, DIV, CON, or SB.
- v_plays has every play in one shape: 1999+ from fact_plays and pre-1999 from
  fact_historical_plays. Play-by-play (fact_plays and children) covers 1999 onward. Games (dim_games) go back to
  1970 with no missing seasons. Scoring-play summaries for every season are in fact_game_scoring, and
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
    "v_plays": {
        "description": "Every play in one shape, 1999+ (nflverse, fact_plays) and pre-1999 (PFR, fact_historical_plays): down, distance, field position, clock, score before and after, play_type, yards, description, EP/EPA, and each player role as <role>_player_id / <role>_player_name (passer, rusher, receiver, interception, sack, kicker, punter, returner, tackler_1, tackler_2, forced_fumble, fumble_recovery, penalty). Start here for play-level questions across eras.",
        "coverage": "1999-present plus the pre-1999 seasons back-filled so far (check SELECT DISTINCT season).",
        "notes": "A view. Key (game_id, play_id); before 1999 play_id is PFR's play order (play_seq). source = 'nflverse' or 'pfr'. Before 1999: no wp/wpa, air/yac EPA, series or turnover flags (NULL); ep/epa are PFR's expected points model, not nflfastR's, so compare EPA across eras with care; posteam is inferred; clock and game_seconds_remaining are NULL on most plays (PFR gives the time only on some). home_score/away_score are after the play, posteam_score/defteam_score before it. Team codes: current franchise codes from 1999 (LV, LAC, LA), codes of the time before (OAK, SLC, PHX, ...), as in dim_games. Player ids are gsis_ids; pre-1999 ones matched by name through rosters. Filter on season first: it's a union over 1.8M rows. Extra pfr-only columns: game_type, yardline, location_raw, exp_pts_after, boxscore_url.",
    },
    "fact_plays": {
        "description": "Every play: down, distance, field position, score, play_type, yards gained, EP/EPA, WP/WPA, drive and series info.",
        "coverage": "1999-present. v_plays combines it with pre-1999 plays.",
        "notes": "Key (game_id, play_id). Has the description, clock, home/away score after the play and each player role (<role>_player_id/_name). posteam = offense, defteam = defense. yardline_100 = yards from opponent end zone. play_type in pass, run, punt, kickoff, field_goal, extra_point, qb_kneel, qb_spike, no_play.",
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
        "description": "One row per scoring play (TD/FG/safety; a TD's PAT/2-pt try is folded into its row), with running score after the play and a description.",
        "coverage": "1970-present. source='pfr' (PFR scoring summaries) through part of 2007; source='nflverse' (derived from nflverse play-by-play) after that. A handful of 2007+ games whose nflverse running score is inconsistent are omitted. For 1999+ prefer fact_plays for play-level detail.",
        "notes": "description is PFR style for every row ('Rod Smith 22 yard pass from John Elway (Jason Elam kick)'); play_description has nflverse's original text on nflverse rows. Structured columns: scoring_type (touchdown/field_goal/safety/defensive_two_point), scoring_method (pass, rush, interception_return, punt_return, kickoff_return, defensive_fumble_return, *_fumble_recovery, blocked_punt_return, field_goal, safety, ...), yards (TD play/return yards or FG distance), scorer, passer, try_type (kick/pass/run), try_result (good/failed), try_player, try_passer. *_id columns are gsis_ids, filled on nflverse rows only; on PFR rows names are free text. Safeties on PFR rows have no scorer. time is seconds left in the quarter. Team codes follow dim_games: historical codes before 1999, current franchise codes (LV, LAC, LA) from 1999.",
    },
    "fact_historical_plays": {
        "description": "Full play-by-play for pre-1999 games from Pro-Football-Reference: down, distance, field position, running score, description, PFR expected points, plus play_type/yards_gained/touchdown and player names parsed from the description.",
        "coverage": "Pre-1999, back-filled one season at a time from 1998 backward; check SELECT DISTINCT season. Use fact_plays for 1999+, or v_plays for both in one shape.",
        "notes": "Key is (game_id, play_seq). Player columns (passer, rusher, receiver, ...) are names parsed from the description; each has a matching *_id gsis_id (passer_id, rusher_id, ...) matched by name against fact_rosters for the two teams that season, NULL when no single player matches (about 99.7% of names match). posteam/defteam are inferred (PFR has no possession column) from PFR's expected points, scores and field position; about 99.8% of plays are assigned (98.7% in 1993, which has no expected points in the source), with posteam = receiving team on kickoffs and kicking team on punts/FG/XP, as in fact_plays. drive numbers possessions from 1 within each game (new drive on each kickoff, change of posteam, and at the half and overtime). yardline_100 is distance to the opponent's goal line. quarter 5 = overtime. clock is often NULL in the source. Team codes match dim_games historical codes.",
    },
    "fact_historical_player_game_stats": {
        "description": "Pre-1999 player game stat lines (offense, fumbles, defense, kicking, punting, returns) derived from fact_historical_plays; source = 'pfr_pbp'.",
        "coverage": "The seasons in fact_historical_plays (being back-filled from 1998); REG and POST. Use fact_player_game_stats for 1999+.",
        "notes": "Derived, not official: one row per player, team and game, from the same counting rules as fact_historical_player_season_stats (which sums these rows). Column names follow fact_player_season_stats (passing_interceptions, sacks_suffered, def_sacks, fg_made_40_49, pat_made, kickoff_returns, ...); team (not recent_team) and opponent are historical dim_games codes. No tackles: PFR's '(tackle by ...)' text doesn't reproduce the official tackle counts (tacklers are named per play in fact_historical_plays). Split sacks are 0.5 each; a fumble is lost when the recoverer is on the other team; blocked punts count as punts of 0 yards. player_id is NULL when the name didn't match a roster. /v1/stats/game serves this for seasons before 1999, and /v1/players/{id}/stats includes these games (as recent_team, interceptions, sacks).",
    },
    "fact_historical_player_season_stats": {
        "description": "Pre-1999 player season totals (passing, rushing, receiving, fumbles, defense, kicking, punting, returns) summed from fact_historical_player_game_stats; source = 'pfr_pbp'.",
        "coverage": "The seasons in fact_historical_plays (being back-filled from 1998); REG and POST. Use fact_player_season_stats for 1999+.",
        "notes": "Derived, not official: checked against PFR's season pages (scripts/check_historical_stats.py) for 1985-1998: passing/rushing/receiving TDs and interceptions 97-100% of players exact, completions and receptions 90-100%, yards and attempts within 2% (or 2) for 98-100%; field goals and extra points (made, attempted, by distance) exact; interceptions, interception and return TDs and forced fumbles 97-100% exact; sacks within 2 for 99%+ of players but 2-3% short in total (PFR's text doesn't always name the sacker); fumble recoveries 88-95% exact, short where the text doesn't name the recoverer (most in 1993-95); return and interception yards 1-5% short; punts 81-100% of punters exact (as on PFR, a blocked punt is not counted in punts); punts_blocked is NULL for 1987-1988 (PFR's text doesn't record blocked punts those seasons). One row per player and team (team = historical dim_games code); games = games with any stat. Column names match fact_player_season_stats (passing_interceptions, sacks_suffered, sack_yards_lost, def_sacks, fg_made, pat_made, punt_returns, ...); extra columns def_interception_tds, punts, punt_yards, punt_long, punts_blocked, kickoff_return_tds, punt_return_tds, fumbles, fumbles_lost. player_id is NULL when the name didn't match a roster. Attempts include spikes and accepted intentional grounding; carries include kneels and aborted snaps; passing_yards and punt_yards are gross. No first downs, EPA or fantasy points. /v1/stats/season serves this for seasons before 1999.",
    },
    "fact_historical_team_season_stats": {
        "description": "Pre-1999 team season offense totals (passing, rushing, sacks) summed from fact_historical_plays; source = 'pfr_pbp'.",
        "coverage": "The seasons in fact_historical_plays; REG and POST. Use ref_team_stats for 1999+.",
        "notes": "Derived, not official (checked against PFR's team pages). net_passing_yards = passing_yards - sack_yards_lost, which is what PFR calls team passing yards. Plays with no inferred posteam (about 0.5%) aren't counted. Team codes are dim_games historical codes. /v1/stats/team serves this for seasons before 1999.",
    },
    # --- player stats ---
    "fact_player_game_stats": {
        "description": "One row per player per game: passing, rushing, receiving, and fantasy stat lines with EPA.",
        "coverage": "1999-present (current season through the latest completed week).",
        "notes": "player_id is a gsis_id. recent_team = team for that game (uses WSH, LA codes). Offensive/fantasy rows only; defense and kicking are in fact_player_season_stats. dakota is NULL from 2025. Pre-1999 game lines (with defense and kicking) are in fact_historical_player_game_stats.",
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
        "notes": "team uses today's franchise codes from 1999 (LV, LAC, LA, WSH) and dim_games' historical codes before 1999 (OAK/RAI, SD, SLC/PHX for the Cardinals, LA/STL for the Rams, HOU for the Oilers), so old rosters join dim_games and fact_historical_plays on team. A player traded mid-season has a row for each team. Older players with no gsis_id get dim_players' id when exactly one player there has the same name and birth date (so it joins dim_players and search_players), otherwise a synthetic 'hist_...' id that is the same for every team and season the player was on (not in dim_players).",
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
        "coverage": "1999-present. Pre-1999 team totals are in fact_historical_team_season_stats.",
        "notes": "One row per team, season and season_type: REG (every team), POST (playoff teams) and REG+POST (playoff teams only; for other teams REG is the whole season).",
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
