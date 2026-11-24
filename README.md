# nfl-data

Public NFL data API backed by a [nflverse](https://github.com/nflverse/nflverse-data) → DuckDB medallion pipeline.

**Live API:** https://nfldata-api.br0wn.net  
**Interactive docs:** https://nfldata-api.br0wn.net/docs

---

## API

All endpoints are public, rate-limited to **100 requests/minute per IP**, and paginated (`limit` / `offset`).

### Players
```
GET /v1/players?name=&position=&team=&season=
GET /v1/players/{gsis_id}
GET /v1/players/{gsis_id}/stats?season=&week=&season_type=
```

### Games
```
GET /v1/games?season=&week=&team=&game_type=                # 1970-present
GET /v1/games/{game_id}
GET /v1/games/scoring?game_id=&season=&team=&scoring_type=&scoring_method=&scorer_id=   # scoring-play summaries, 1970-present
GET /v1/games/historical-plays?game_id=&season=&week=&team=&play_type=&posteam=&player_id=   # pre-1999 play-by-play (PFR); game_id or season required
GET /v1/games/head-to-head?team1=&team2=&season=&game_type=&top_n=   # matchup history, records, biggest wins, top performances
```

### Plays
Requires `game_id` **or** `season`. Max 500 per request.
```
GET /v1/plays?game_id=&season=&week=&play_type=
```

### Stats
Defaults to the most recent season if `season` is omitted.
```
GET /v1/stats/passing?season=&week=&season_type=&team=
GET /v1/stats/rushing?season=&week=&season_type=&team=
GET /v1/stats/receiving?season=&week=&season_type=&team=
GET /v1/stats/season?player_id=&season=&season_type=&position=     # season totals incl. defense/kicking; pre-1999 derived from PFR play-by-play
GET /v1/stats/team?season=&team=&season_type=                       # team box scores; pre-1999 derived from PFR play-by-play
```

### Advanced stats
```
GET /v1/stats/ngs/passing?season=&week=&season_type=&player_gsis_id=&team_abbr=
GET /v1/stats/ngs/rushing?season=&week=&season_type=&player_gsis_id=&team_abbr=
GET /v1/stats/ngs/receiving?season=&week=&season_type=&player_gsis_id=&team_abbr=
GET /v1/stats/advanced/passing?season=&pfr_id=&team=     # PFR season totals
GET /v1/stats/advanced/rushing?season=&pfr_id=&team=
GET /v1/stats/advanced/receiving?season=&pfr_id=&team=
GET /v1/stats/advanced/defense?season=&pfr_id=&team=
GET /v1/qbr/season?season=&season_type=&player_id=&team=
GET /v1/qbr/week?season=&season_type=&week=&player_id=&team=&game_id=
```

### Charting & participation
```
GET /v1/charting?game_id=&season=&week=          # play-design tags: motion, play-action, blitz, etc. (2022+)
GET /v1/participation?game_id=                    # personnel/formations/coverage per play (2016+)
```

### Reference
```
GET /v1/combine?season=&position=
GET /v1/draft?season=&round=&team=
GET /v1/contracts?team=&position=&year_signed=
GET /v1/rosters/pfr?season=&team=&position=
```

### Meta
```
GET /v1/meta      # available seasons and teams
GET /v1/health    # row counts per table, last refresh timestamp
```

All list endpoints return:
```json
{ "data": [...], "total": 123, "limit": 50, "offset": 0 }
```

---

## MCP server (query with AI tools)

The same database is available to AI clients over the [Model Context Protocol](https://modelcontextprotocol.io) at
`https://nfldata-api.br0wn.net/mcp` (Streamable HTTP, no auth, 60 requests/minute per IP).

```bash
# Claude Code
claude mcp add --transport http nfldata https://nfldata-api.br0wn.net/mcp
```

Other clients (Claude Desktop, Cursor, etc.) can add it as a remote/HTTP MCP server with that URL.

| Tool | What it does |
|---|---|
| `list_tables` | Every table with description, coverage, and row count |
| `describe_table` | Columns, types, join notes, sample rows |
| `search_players` | Name → `gsis_id` and other player IDs |
| `list_teams_and_seasons` | Team abbreviations and seasons with games |
| `query_sql` | One read-only DuckDB `SELECT` (max 500 rows, 15s timeout) |

`query_sql` is sandboxed by DuckDB itself: the connection is read-only, file/network access is disabled,
and settings are locked (`api/deps.py`). Table descriptions live in `api/mcp_catalog.py`; keep them in sync
with `web/data_coverage.php`.

---

## Data

Sourced from [nflverse-data](https://github.com/nflverse/nflverse-data) public releases.

**At a glance:** every regular-season and playoff game from **1999 to the current season** (~7,500 games), every play (**1.28M**) with EPA/WPA, weekly stats for **25K players**, plus rosters, depth charts, injuries, snap counts, draft history, combine results, contracts, and trades going back to 1999 (combine/contracts/trades coverage varies by source). Game results extend back to **1970** (pre-1999 via Pro-Football-Reference), with scoring-play detail for every season since 1970 and full Pro-Football-Reference play-by-play being back-filled from 1998 (see `fact_historical_plays`).

| Layer | Contents |
|---|---|
| Bronze | Raw parquet files from 24 nflverse release tags |
| Silver | Cleaned and type-normalized parquet |
| Gold | DuckDB star schema — dims, facts, refs, name resolution |

### Dimensions

| Table | Rows | Contents |
|---|---|---|
| `dim_players` | 25K | Player bio/draft info plus cross-reference IDs (gsis, esb, pfr, pff, sleeper, sportradar, yahoo, rotowire, fantasy_data) |
| `dim_teams` | 36 | Team names, conference/division, colors, logos |
| `dim_games` | 14K | Game results 1970-present; for 1999+ also schedule, stadium/weather, betting lines (spread/total/moneyline/odds), starting QBs, coaches, referee, rest days, cross-reference IDs |
| `fact_game_scoring` | 106K | One row per scoring play (try folded into the TD), 1970-present: PFR scoring summaries through part of 2007 (`source = 'pfr'`), then derived from nflverse play-by-play (`source = 'nflverse'`). Same PFR-style description for both, plus structured scoring type/method, yards, scorer, passer and try fields (gsis_ids on nflverse rows). For 1999+, `fact_plays` is the richer source |
| `ref_team_elo` | 17.4K | FiveThirtyEight game-by-game Elo and QB-Elo ratings, win probabilities, starting QBs, 1920-2022 |

### Play-by-play

| Table | Rows | Contents |
|---|---|---|
| `fact_plays` | 1.28M | Every play: down/distance, field position, score, EPA/WPA, drives/series |
| `fact_pass_plays` | 524K | Pass-specific detail: passer/receiver, air yards, YAC, completion, CPOE |
| `fact_rush_plays` | 385K | Rush-specific detail: rusher, run location/gap, TDs |
| `fact_kick_plays` | 314K | Punts, field goals, extra points, kickoffs, returns |
| `fact_historical_plays` | 128K | Pre-1999 play-by-play from Pro-Football-Reference (1996–1998 so far, back-filled one season at a time): down/distance, field position, score, description, PFR expected points, play type/yards/TD/player names parsed from the description with gsis_ids matched through rosters, and the team with the ball and drive number (inferred) |
| `fact_pbp_participation` | 486K | Personnel groupings, formations, pass rush/coverage detail per play (2016+) |
| `fact_ftn_charting` | 185K | Play-design charting — motion, play-action, RPO, blitz, pressure, drops (2022+) |

`v_pass_plays`, `v_rush_plays`, `v_kick_plays` join the play tables to canonical player names via `name_resolution`.

### Player & team stats

| Table | Rows | Contents |
|---|---|---|
| `fact_player_game_stats` | 134K | Weekly passing/rushing/receiving box-score stats, advanced metrics (EPA, PACR, DAKOTA, RACR, target/air-yards share, WOPR), fantasy points |
| `fact_player_season_stats` | 12K | Season-total player stats — adds defense, special teams, and kicking to the weekly stats above |
| `ref_team_stats` | 1.5K | Season-total team offense/defense box scores (REG, POST, and REG+POST) |
| `fact_historical_player_season_stats` | 2K | Pre-1999 player passing/rushing/receiving season totals summed from `fact_historical_plays` (`source = 'pfr_pbp'`), checked against PFR's official season tables |
| `fact_historical_team_season_stats` | 126 | Pre-1999 team passing/rushing season totals, same source |
| `fact_snap_counts` | 325K | Offense/defense/special-teams snap counts and percentages per player per game |
| `fact_ngs_passing` | 5.9K | NFL Next Gen Stats — time to throw, air yards, CPOE (2016+) |
| `fact_ngs_receiving` | 15K | NFL Next Gen Stats — separation, cushion, YAC over expected (2016+) |
| `fact_ngs_rushing` | 6.1K | NFL Next Gen Stats — efficiency, time to LOS, rush yards over expected (2018+) |
| `ref_pfr_adv_pass` | 844 | PFR advanced passing — pressure, blitz, play-action, RPO splits (season totals) |
| `ref_pfr_adv_rush` | 2.8K | PFR advanced rushing — yards before/after contact, broken tackles (season totals) |
| `ref_pfr_adv_rec` | 4.1K | PFR advanced receiving — air yards, drops, broken tackles (season totals) |
| `ref_pfr_adv_def` | 7.4K | PFR advanced defense — coverage stats, pressures, missed tackles (season totals) |
| `ref_qbr_season` | 1.5K | ESPN Total QBR, season totals |
| `ref_qbr_week` | 11K | ESPN Total QBR, per game |

### Rosters & personnel

| Table | Rows | Contents |
|---|---|---|
| `fact_weekly_rosters` | 889K | Weekly roster status, position, jersey number, experience |
| `fact_rosters` | 143K | Season-level roster snapshots, 1920-present (pre-1974 players use synthetic `hist_*` IDs, not joinable to `dim_players`) |
| `fact_depth_charts` | 725K | Weekly depth chart position/order by team |
| `fact_injuries` | 91K | Weekly injury reports (game and practice status, body part) |

### Draft, combine & contracts

| Table | Rows | Contents |
|---|---|---|
| `ref_draft_picks` | 13K | Draft history — round, pick, team, player, college |
| `ref_combine` | 9K | NFL Combine measurements and drill results |
| `ref_contracts` | 52K | Contract values (APY, guarantees, cap %, inflation-adjusted) |
| `ref_trades` | 5K | Player and draft-pick trade history |
| `ref_officials` | 22K | Game officiating crews by role |
| `ref_pfr_rosters` | 42K | Pro-Football-Reference season rosters — age, experience, approximate value, salary |

### Name resolution

| Table | Rows | Contents |
|---|---|---|
| `name_resolution` | 22K | Maps raw player-name strings (from play-by-play and other sources) to canonical `dim_players.gsis_id`, via ID anchors and fuzzy matching |

Data refreshes weekly on Tuesday mornings after nflverse publishes Monday night.

---

## Local development

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

### Pipeline commands

```bash
uv run nfl run              # full pipeline: ingest → clean → load → resolve → enrich
uv run nfl ingest           # download nflverse parquet files to bronze/
uv run nfl clean            # normalize bronze → silver
uv run nfl load             # load silver → DuckDB gold layer
uv run nfl resolve          # build player name resolution table
uv run nfl enrich           # back-fill player IDs in ref tables
uv run nfl check            # data quality report
uv run nfl audit            # freshness, gaps, missing games; --previous data/last_run_counts.json --strict fails on row-count drops
uv run nfl report           # pipeline report (--format json for CI use)
uv run nfl status           # bronze/silver file counts + DB size
uv run nfl query "SQL"      # run a query against the gold DB
```

### Run the API locally

```bash
uv run uvicorn api.main:app --reload
# → http://localhost:8000/docs
```

### Tests

```bash
uv run pytest
```

---

## Deployment

Hosted on [Fly.io](https://fly.io) (`shared-cpu-1x`, 512MB RAM, 3GB persistent volume). The machine auto-stops when idle and wakes on the first request.

Weekly refresh runs via GitHub Actions (`.github/workflows/refresh.yml`) — rebuilds the full pipeline, uploads the new `nfl.duckdb` to the Fly.io volume, and sends a report email.

Required secrets for the refresh workflow:
- `FLY_API_TOKEN` — from `fly tokens create deploy`
- `RESEND_API_KEY` — from [resend.com](https://resend.com)
- `RESEND_DOMAIN` — your verified sending domain
