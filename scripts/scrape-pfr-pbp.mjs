// Slowly scrapes play-by-play for EVERY game from pro-football-reference.com
// boxscore pages, one season at a time, newest season first (default 1998 -> 1970).
//
// Same browser approach as scrape-patriots-pbp.mjs: drives a real, already-
// authenticated Chrome over CDP (agent-browser --cdp 9222) so PFR's Cloudflare
// check passes. Start Chrome first:
//   open -a "Google Chrome" --args --remote-debugging-port=9222 --user-data-dir="$HOME/.chrome-debug-profile"
//
// The game list comes from our own silver historical_gamelogs (game_id +
// boxscore_url), so no team/season pages are fetched.
//
// Output: one CSV per game at data/scraped/pfr_pbp/<season>/<game_id>.csv
// (gitignored). A game whose boxscore has no play-by-play table gets an empty
// <game_id>.none marker so it isn't retried. Existing files = done, so the
// script is resumable: just restart it.
//
// Pace: deliberately slow (~1 page/min; PFR blocks clients above 20 req/min):
// 25-40s between pages, a 15-min rest every 40 pages, 30 min between seasons,
// and a hard stop on rate-limit pages or 3 failures in a row.
//
// Usage:
//   node scripts/scrape-pfr-pbp.mjs [FROM_SEASON] [TO_SEASON] [--limit N]
//   node scripts/scrape-pfr-pbp.mjs              # 1998 down to 1970
//   node scripts/scrape-pfr-pbp.mjs 1998 1998    # just 1998
//   node scripts/scrape-pfr-pbp.mjs 1998 1998 --limit 2   # smoke test

import { spawnSync } from 'child_process';
import { writeFileSync, existsSync, mkdirSync, renameSync, appendFileSync } from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const OUT_DIR = process.env.PBP_OUT_DIR || path.join(ROOT, 'data', 'scraped', 'pfr_pbp');
// Every failed attempt is appended here (see scripts/pbp-scrape-report.mjs).
const FAILURES_FILE = path.join(OUT_DIR, 'failures.csv');

const args = process.argv.slice(2);
const limitIdx = args.indexOf('--limit');
const LIMIT = limitIdx >= 0 ? Number(args.splice(limitIdx, 2)[1]) : Infinity;
const FROM = Number(args[0] || 1998);
const TO = Number(args[1] || 1970);

// Deliberately very conservative: ~1 page/minute including page load.
const BOX_DELAY_MS = 25000;        // base delay between boxscores
const BOX_JITTER_MS = 15000;       // + random 0-15s
const BATCH_SIZE = 40;             // after this many pages...
const BATCH_REST_MS = 15 * 60000;  // ...rest 15 min
const SEASON_DELAY_MS = 30 * 60000; // 30 min between seasons
const RETRY_PASS_DELAY_MS = 10 * 60000; // wait before retrying a season's failures
const PAGE_TIMEOUT_MS = 60000;          // agent-browser action timeout (its default is 25s)
const MAX_CF_RETRIES = 2;
const MAX_CONSECUTIVE_ERRORS = 3;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const ts = () => new Date().toISOString().slice(11, 19);

class RateLimited extends Error {}

function runBrowser(argv, input) {
  const result = spawnSync('agent-browser', ['--cdp', '9222', ...argv], {
    encoding: 'utf8',
    input,
    env: { ...process.env, AGENT_BROWSER_DEFAULT_TIMEOUT: String(PAGE_TIMEOUT_MS) },
    maxBuffer: 50 * 1024 * 1024,
  });
  if (result.status !== 0) {
    throw new Error((result.stderr || result.stdout || 'unknown agent-browser error').trim());
  }
  return result.stdout.trim();
}

function evalJS(js) {
  return JSON.parse(runBrowser(['eval', '--stdin'], js));
}

async function openAndSettle(url) {
  for (let attempt = 1; attempt <= MAX_CF_RETRIES; attempt++) {
    // PFR's ads often keep the network busy, so load timeouts are not fatal:
    // fall through and check what actually loaded. The scraped data is then
    // validated against the game's known final score before it's saved.
    try {
      runBrowser(['open', url]);
    } catch (err) {
      if (!/timed out/i.test(err.message)) throw err;
    }
    try {
      runBrowser(['wait', '--load', 'networkidle']);
    } catch {
      await sleep(5000);
    }
    const title = runBrowser(['get', 'title']);
    if (/too many requests|rate limit/i.test(title)) throw new RateLimited(title);
    if (title && !/just a moment|verifying you are human|attention required/i.test(title)) return title;
    console.log(`    [cf-check] "${title || '(blank)'}" attempt ${attempt}, waiting...`);
    await sleep(60000 * attempt);
  }
  throw new Error(`Cloudflare check never cleared for ${url}`);
}

function seasonGames(season) {
  const py = `
import json, polars as pl
df = pl.read_parquet("data/silver/historical_gamelogs/${season}.parquet")
print(json.dumps(df.select("game_id", "week", "game_type", "home_team", "away_team", "home_score", "away_score", "boxscore_url").sort("game_id").to_dicts()))
`;
  const r = spawnSync('uv', ['run', '--quiet', 'python', '-c', py], { cwd: ROOT, encoding: 'utf8' });
  if (r.status !== 0) throw new Error(`could not read gamelogs for ${season}: ${r.stderr.trim()}`);
  return JSON.parse(r.stdout);
}

function csvEscape(v) {
  if (v === null || v === undefined) return '';
  const s = String(v);
  return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

const CSV_COLUMNS = [
  'game_id', 'season', 'week', 'game_type', 'home_team', 'away_team', 'boxscore_url',
  'play_seq', 'quarter', 'time', 'down', 'yds_to_go', 'location',
  'away_score', 'home_score', 'detail', 'exp_pts_before', 'exp_pts_after',
];

async function scrapeBoxscore(url) {
  await openAndSettle(url);
  return evalJS(`({
    // The scoring table is on every boxscore page; if it's missing the page
    // didn't load properly, so an empty pbp table means nothing.
    pageLoaded: !!document.querySelector('table#scoring'),
    rows: Array.from(document.querySelectorAll('table#pbp tbody tr'))
      .filter(r => !r.classList.contains('thead'))
      .map(r => {
        const c = {};
        r.querySelectorAll('[data-stat]').forEach(e => c[e.getAttribute('data-stat')] = e.innerText.trim());
        return c;
      }),
  })`);
}

function logFailure(g, season, err) {
  if (!existsSync(FAILURES_FILE)) {
    writeFileSync(FAILURES_FILE, 'timestamp,season,game_id,url,error\n');
  }
  const msg = err.message.replace(/\s+/g, ' ').slice(0, 300);
  appendFileSync(
    FAILURES_FILE,
    [new Date().toISOString(), season, g.game_id, g.boxscore_url, msg].map(csvEscape).join(',') + '\n',
  );
}

function writeAtomic(file, content) {
  writeFileSync(file + '.tmp', content);
  renameSync(file + '.tmp', file);
}

async function main() {
  const step = FROM >= TO ? -1 : 1;
  let attempts = 0; // pages requested this run (successes and failures)
  let consecutiveErrors = 0;

  // Fetches one game. Returns true on success (CSV or .none written).
  async function fetchGame(g, season, dir) {
    attempts++;
    process.stdout.write(`  [${ts()}] ${g.game_id}...`);
    try {
      const { pageLoaded, rows } = await scrapeBoxscore(g.boxscore_url);
      if (rows.length === 0 && !pageLoaded) throw new Error('page did not finish loading (no scoring table)');
      if (rows.length === 0) {
        writeAtomic(path.join(dir, `${g.game_id}.none`), '');
        process.stdout.write(' no play-by-play\n');
      } else {
        // Guard against a partially loaded table: the last score shown must
        // match the game's final score from our gamelogs.
        const last = [...rows].reverse().find((r) => r.pbp_score_aw && r.pbp_score_hm);
        if (!last || Number(last.pbp_score_aw) !== g.away_score || Number(last.pbp_score_hm) !== g.home_score) {
          throw new Error(
            `final score mismatch: pbp ${last ? `${last.pbp_score_aw}-${last.pbp_score_hm}` : 'none'}, ` +
            `expected ${g.away_score}-${g.home_score} (${rows.length} rows)`,
          );
        }
        const lines = rows.map((r, i) =>
          [
            g.game_id, season, g.week, g.game_type, g.home_team, g.away_team, g.boxscore_url,
            i + 1, r.quarter, r.qtr_time_remain, r.down, r.yds_to_go, r.location,
            r.pbp_score_aw, r.pbp_score_hm, r.detail, r.exp_pts_before, r.exp_pts_after,
          ].map(csvEscape).join(','),
        );
        writeAtomic(path.join(dir, `${g.game_id}.csv`), [CSV_COLUMNS.join(','), ...lines].join('\n') + '\n');
        process.stdout.write(` ${rows.length} plays\n`);
      }
      consecutiveErrors = 0;
      return true;
    } catch (err) {
      logFailure(g, season, err);
      if (err instanceof RateLimited) {
        console.log(`\nRate limited by PFR ("${err.message}"). Stopping; wait a few hours (up to a day) before restarting.`);
        process.exit(2);
      }
      consecutiveErrors++;
      process.stdout.write(` ERROR: ${err.message.slice(0, 160)}\n`);
      if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
        console.log(`\n${consecutiveErrors} errors in a row. Stopping; check Chrome (port 9222) and restart.`);
        process.exit(3);
      }
      return false;
    } finally {
      // Pace on every request, success or failure.
      if (attempts % BATCH_SIZE === 0) {
        console.log(`  [${ts()}] ${attempts} pages this run, resting ${BATCH_REST_MS / 60000} min`);
        await sleep(BATCH_REST_MS);
      } else {
        await sleep(BOX_DELAY_MS + Math.random() * BOX_JITTER_MS);
      }
    }
  }

  for (let season = FROM; step < 0 ? season >= TO : season <= TO; season += step) {
    const dir = path.join(OUT_DIR, String(season));
    mkdirSync(dir, { recursive: true });
    const games = seasonGames(season);
    const todo = games.filter(
      (g) => !existsSync(path.join(dir, `${g.game_id}.csv`)) && !existsSync(path.join(dir, `${g.game_id}.none`)),
    );
    console.log(`\n[${ts()}] === ${season}: ${games.length} games, ${todo.length} to fetch ===`);

    const failed = [];
    for (const g of todo) {
      if (attempts >= LIMIT) {
        console.log(`\nReached --limit ${LIMIT}, stopping.`);
        return;
      }
      if (!(await fetchGame(g, season, dir))) failed.push(g);
    }

    // One slow retry pass over this season's failures.
    if (failed.length && attempts < LIMIT) {
      console.log(`  [${ts()}] ${failed.length} failed in ${season}; retrying once after ${RETRY_PASS_DELAY_MS / 60000} min`);
      await sleep(RETRY_PASS_DELAY_MS);
      let stillFailed = 0;
      for (const g of failed) {
        if (attempts >= LIMIT) break;
        if (!(await fetchGame(g, season, dir))) stillFailed++;
      }
      console.log(`  [${ts()}] retry pass: ${failed.length - stillFailed} recovered, ${stillFailed} still failing (see pbp-scrape-report.mjs)`);
    }

    if (season !== TO) {
      console.log(`  [${ts()}] ${season} done, pausing ${SEASON_DELAY_MS / 60000} min before next season`);
      await sleep(SEASON_DELAY_MS);
    }
  }
  console.log(`\nDone. Output in ${OUT_DIR}`);
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
