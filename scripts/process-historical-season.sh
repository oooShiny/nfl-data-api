#!/usr/bin/env bash
# Import a freshly scraped pre-1999 season and run the checks on it.
#
# Run after the scraper logs "SEASON_READY <season>": imports every complete
# season's play-by-play into bronze, re-cleans silver, rebuilds the historical
# gold tables, then prints the play-by-play check and the season's block of the
# stats check (against PFR's season tables). Exits non-zero if any step
# fails. It doesn't commit anything: review the output, then open a PR with
# data/bronze/historical_pbp/<season>.parquet.
#
# Usage: scripts/process-historical-season.sh SEASON
set -euo pipefail
season=${1:?usage: scripts/process-historical-season.sh SEASON}
cd "$(dirname "$0")/.."

for f in data/scraped/pfr_season_stats/"$season"/{passing,rushing,receiving,team_stats,defense,kicking,punting,returns}.csv; do
  [[ -f $f ]] || { echo "missing $f (run scripts/scrape-pfr-season-stats.mjs $season)"; exit 1; }
done

echo "== import / clean / load $season"
uv run nfl ingest-historical | tail -3
[[ -f data/bronze/historical_pbp/$season.parquet ]] || { echo "no bronze file for $season (season incomplete?)"; exit 1; }
uv run nfl clean historical_pbp --force | tail -2
uv run nfl load "dim_games (historical)" fact_historical_plays "historical season stats" "historical win probability" | tail -6

echo; echo "== play-by-play check"
uv run --quiet python scripts/check_historical_pbp.py | sed -n "1p;/^ *$season /p"

echo; echo "== stats check, $season"
uv run --quiet python scripts/check_historical_stats.py \
  | awk -v s="$season" '/^[0-9][0-9][0-9][0-9]$/ {on = ($1 == s)} on'

echo; echo "== audit"
uv run nfl audit --strict > /dev/null && echo "audit ok"
