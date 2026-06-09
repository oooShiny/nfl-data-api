# nfl-data

Public NFL data API backed by a [nflverse](https://github.com/nflverse/nflverse-data) → DuckDB medallion pipeline.

**Live API:** https://nfl-data-api.fly.dev  
**Interactive docs:** https://nfl-data-api.fly.dev/docs

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
```

### Reference
```
GET /v1/combine?season=&position=
GET /v1/draft?season=&round=&team=
GET /v1/contracts?team=&position=&year_signed=
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

Sourced from [nflverse-data](https://github.com/nflverse/nflverse-data) public releases. Covers seasons 1999–present.

| Layer | Contents |
|---|---|
| Bronze | Raw parquet files from 24 nflverse release tags |
| Silver | Cleaned and type-normalized parquet |
| Gold | DuckDB star schema — dims, facts, refs, name resolution |

Key tables: `dim_players` (25K), `dim_games` (7.5K), `fact_plays` (1.28M), `fact_player_game_stats` (134K), `fact_weekly_rosters` (889K), plus combine, contracts, draft picks, trades, snap counts, depth charts, injuries.

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
