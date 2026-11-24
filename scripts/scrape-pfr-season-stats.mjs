// Fetches PFR's official season stat tables, used to check the stats we
// derive from pre-1999 play-by-play (scripts/check_historical_stats.py).
//
// Per season, 4 pages:
//   years/<season>/passing.htm    table#passing
//   years/<season>/rushing.htm    table#rushing
//   years/<season>/receiving.htm  table#receiving
//   years/<season>/               table#team_stats (team offense)
//
// Same browser and pace as scrape-pfr-pbp.mjs (agent-browser over CDP 9222,
// 25-40s between pages, hard stop on rate-limit pages). Don't run it while
// scrape-pfr-pbp.mjs is running: stop that one between games first, so PFR
// only ever sees one request at a time.
//
// Output: data/scraped/pfr_season_stats/<season>/<table>.csv with every
// data-stat cell plus player_href (e.g. /players/E/ElwaJo00.htm). Existing
// files are skipped, so the script is resumable.
//
// Usage: node scripts/scrape-pfr-season-stats.mjs FROM_SEASON [TO_SEASON]

import { spawnSync } from 'child_process';
import { writeFileSync, existsSync, mkdirSync, renameSync } from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const OUT_DIR = path.join(ROOT, 'data', 'scraped', 'pfr_season_stats');

const FROM = Number(process.argv[2]);
const TO = Number(process.argv[3] || FROM);
if (!FROM) {
  console.error('usage: node scripts/scrape-pfr-season-stats.mjs FROM_SEASON [TO_SEASON]');
  process.exit(1);
}

const DELAY_MS = 25000;
const JITTER_MS = 15000;
const PAGE_TIMEOUT_MS = 60000;
const MAX_CF_RETRIES = 2;

const PAGES = [
  { table: 'passing', url: (s) => `https://www.pro-football-reference.com/years/${s}/passing.htm` },
  { table: 'rushing', url: (s) => `https://www.pro-football-reference.com/years/${s}/rushing.htm` },
  { table: 'receiving', url: (s) => `https://www.pro-football-reference.com/years/${s}/receiving.htm` },
  { table: 'team_stats', url: (s) => `https://www.pro-football-reference.com/years/${s}/` },
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const ts = () => new Date().toISOString().slice(11, 19);

function runBrowser(argv, input) {
  const result = spawnSync('agent-browser', ['--cdp', '9222', ...argv], {
    encoding: 'utf8',
    input,
    env: { ...process.env, AGENT_BROWSER_DEFAULT_TIMEOUT: String(PAGE_TIMEOUT_MS) },
    maxBuffer: 50 * 1024 * 1024,
  });
  if (result.status !== 0) throw new Error((result.stderr || result.stdout || 'agent-browser error').trim());
  return result.stdout.trim();
}

async function openAndSettle(url) {
  for (let attempt = 1; attempt <= MAX_CF_RETRIES; attempt++) {
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
    if (/too many requests|rate limit/i.test(title)) {
      console.log(`Rate limited by PFR ("${title}"). Stopping.`);
      process.exit(2);
    }
    if (title && !/just a moment|verifying you are human|attention required/i.test(title)) return;
    console.log(`    [cf-check] "${title || '(blank)'}" attempt ${attempt}, waiting...`);
    await sleep(60000 * attempt);
  }
  throw new Error(`Cloudflare check never cleared for ${url}`);
}

// PFR ships some tables inside HTML comments; look there too.
function readTable(id) {
  const js = `(() => {
    let t = document.querySelector('table#${id}');
    if (!t) {
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_COMMENT);
      for (let n = walker.nextNode(); n; n = walker.nextNode()) {
        if (n.textContent.includes('id="${id}"')) {
          const d = document.createElement('div');
          d.innerHTML = n.textContent;
          t = d.querySelector('table#${id}');
          if (t) break;
        }
      }
    }
    if (!t) return null;
    return Array.from(t.querySelectorAll('tbody tr'))
      .filter(r => !r.classList.contains('thead') && !r.classList.contains('over_header'))
      .map(r => {
        const c = {};
        r.querySelectorAll('[data-stat]').forEach(e => c[e.getAttribute('data-stat')] = e.innerText.trim());
        const a = r.querySelector('a[href^="/players/"]');
        c.player_href = a ? a.getAttribute('href') : '';
        return c;
      });
  })()`;
  return JSON.parse(runBrowser(['eval', '--stdin'], js));
}

function csvEscape(v) {
  if (v === null || v === undefined) return '';
  const s = String(v);
  return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

function writeCsv(file, rows) {
  const cols = [...new Set(rows.flatMap((r) => Object.keys(r)))];
  const body = [cols.join(','), ...rows.map((r) => cols.map((c) => csvEscape(r[c])).join(','))].join('\n') + '\n';
  writeFileSync(file + '.tmp', body);
  renameSync(file + '.tmp', file);
}

async function main() {
  const step = FROM >= TO ? -1 : 1;
  let first = true;
  for (let season = FROM; step < 0 ? season >= TO : season <= TO; season += step) {
    const dir = path.join(OUT_DIR, String(season));
    mkdirSync(dir, { recursive: true });
    for (const p of PAGES) {
      const file = path.join(dir, `${p.table}.csv`);
      if (existsSync(file)) continue;
      if (!first) await sleep(DELAY_MS + Math.random() * JITTER_MS);
      first = false;
      process.stdout.write(`  [${ts()}] ${season} ${p.table}...`);
      await openAndSettle(p.url(season));
      const rows = readTable(p.table);
      if (!rows || rows.length === 0) {
        console.log(' ERROR: table not found; stopping');
        process.exit(1);
      }
      writeCsv(file, rows);
      console.log(` ${rows.length} rows`);
    }
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
