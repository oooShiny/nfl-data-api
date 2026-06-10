# nfl-data

Public NFL data API backed by a [nflverse](https://github.com/nflverse/nflverse-data) → DuckDB medallion pipeline.

**Live API:** https://api.nfldata.org  
**Interactive docs:** https://api.nfldata.org/docs

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
GET /v1/games?season=&week=&team=&game_type=
GET /v1/games/{game_id}
GET /v1/games/historical?season=&week=&team=&game_type=   # 1970-2022 results (2000 missing), pre-1999 only here
GET /v1/games/scoring?game_id=&season=&team=               # scoring-play summaries, 1970-1997
```

### Plays
Requires `game_id` **or** `season`. Max 500 per request.
```
GET /v1/plays?game_id=&season=&week=&play_type=
```

### Stats
Defaults to the most recent season if `season` is omitted.
```
GET /v1/stats/passing?season=&week=&season_type=
GET /v1/stats/rushing?season=&week=&season_type=
GET /v1/stats/receiving?season=&week=&season_type=
GET /v1/stats/season?player_id=&season=&season_type=&position=     # season totals incl. defense/kicking
GET /v1/stats/team?season=&team=&season_type=                       # team box scores
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

## Data

Sourced from [nflverse-data](https://github.com/nflverse/nflverse-data) public releases.

**At a glance:** every regular-season and playoff game from **1999 to the current season** (~7,500 games), every play (**1.28M**) with EPA/WPA, weekly stats for **25K players**, plus rosters, depth charts, injuries, snap counts, draft history, combine results, contracts, and trades going back to 1999 (combine/contracts/trades coverage varies by source). Game results extend back to **1970** (2000 missing) via Pro-Football-Reference, with scoring-play detail for 1970-1997.

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
| `dim_games` | 7.5K | Game results, schedule, stadium/weather, betting lines (spread, total) |
| `fact_historical_games` | 12.4K | Game results 1970-2022 (2000 missing) from Pro-Football-Reference, pre-1999 not in `dim_games` |
| `fact_game_scoring` | 44.7K | Scoring-play summaries for historical games, 1970-1997 |

### Play-by-play

| Table | Rows | Contents |
|---|---|---|
| `fact_plays` | 1.28M | Every play: down/distance, field position, score, EPA/WPA, drives/series |
| `fact_pass_plays` | 524K | Pass-specific detail: passer/receiver, air yards, YAC, completion, CPOE |
| `fact_rush_plays` | 385K | Rush-specific detail: rusher, run location/gap, TDs |
| `fact_kick_plays` | 314K | Punts, field goals, extra points, kickoffs, returns |
| `fact_pbp_participation` | 486K | Personnel groupings, formations, pass rush/coverage detail per play (2016+) |
| `fact_ftn_charting` | 185K | Play-design charting — motion, play-action, RPO, blitz, pressure, drops (2022+) |

`v_pass_plays`, `v_rush_plays`, `v_kick_plays` join the play tables to canonical player names via `name_resolution`.

### Player & team stats

| Table | Rows | Contents |
|---|---|---|
| `fact_player_game_stats` | 134K | Weekly passing/rushing/receiving box-score stats, advanced metrics (EPA, PACR, DAKOTA, RACR, target/air-yards share, WOPR), fantasy points |
| `fact_player_season_stats` | 12K | Season-total player stats — adds defense, special teams, and kicking to the weekly stats above |
| `ref_team_stats` | 336 | Season-total team offense/defense box scores |
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
| `fact_rosters` | 89K | Season-level roster snapshots |
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
