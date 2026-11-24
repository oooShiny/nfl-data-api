// Report on failed play-by-play scrape attempts (see scrape-pfr-pbp.mjs).
//
// Reads data/scraped/pfr_pbp/failures.csv (one row per failed attempt) and
// groups by game. A game counts as resolved once a later attempt produced its
// <game_id>.csv or .none file. Unresolved games are retried automatically the
// next time the scraper runs over that season.
//
// Usage:
//   node scripts/pbp-scrape-report.mjs          # unresolved failures only
//   node scripts/pbp-scrape-report.mjs --all    # include resolved ones
//
// Also writes data/scraped/pfr_pbp/failures_report.csv with the same rows.

import { existsSync, readFileSync, writeFileSync } from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const OUT_DIR = process.env.PBP_OUT_DIR || path.join(ROOT, 'data', 'scraped', 'pfr_pbp');
const FAILURES_FILE = path.join(OUT_DIR, 'failures.csv');
const REPORT_FILE = path.join(OUT_DIR, 'failures_report.csv');
const SHOW_ALL = process.argv.includes('--all');

function parseCsv(text) {
  const rows = [];
  let row = [], field = '', inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (inQuotes) {
      if (ch === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (ch === '"') inQuotes = false;
      else field += ch;
    } else if (ch === '"') inQuotes = true;
    else if (ch === ',') { row.push(field); field = ''; }
    else if (ch === '\n') { row.push(field); rows.push(row); row = []; field = ''; }
    else if (ch !== '\r') field += ch;
  }
  if (field || row.length) { row.push(field); rows.push(row); }
  const [header, ...body] = rows;
  return body.map((r) => Object.fromEntries(header.map((h, i) => [h, r[i] ?? ''])));
}

const csvEscape = (v) => {
  const s = String(v ?? '');
  return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
};

if (!existsSync(FAILURES_FILE)) {
  console.log('No failures recorded.');
  process.exit(0);
}

const byGame = new Map();
for (const f of parseCsv(readFileSync(FAILURES_FILE, 'utf8'))) {
  const g = byGame.get(f.game_id) || { season: f.season, game_id: f.game_id, url: f.url, attempts: 0 };
  g.attempts++;
  g.first_failed = g.first_failed || f.timestamp;
  g.last_failed = f.timestamp;
  g.last_error = f.error;
  byGame.set(f.game_id, g);
}

for (const g of byGame.values()) {
  const dir = path.join(OUT_DIR, g.season);
  g.status = existsSync(path.join(dir, `${g.game_id}.csv`)) || existsSync(path.join(dir, `${g.game_id}.none`))
    ? 'resolved'
    : 'unresolved';
}

const all = [...byGame.values()].sort((a, b) => b.season - a.season || a.game_id.localeCompare(b.game_id));
const shown = SHOW_ALL ? all : all.filter((g) => g.status === 'unresolved');
const unresolved = all.filter((g) => g.status === 'unresolved').length;

console.log(`${all.length} games with failed attempts: ${unresolved} unresolved, ${all.length - unresolved} resolved by a later attempt.\n`);
for (const g of shown) {
  console.log(`${g.game_id}  (${g.status}, ${g.attempts} attempt${g.attempts > 1 ? 's' : ''}, last ${g.last_failed.slice(0, 16).replace('T', ' ')} UTC)`);
  console.log(`  ${g.url}`);
  console.log(`  ${g.last_error}\n`);
}

const cols = ['season', 'game_id', 'url', 'status', 'attempts', 'first_failed', 'last_failed', 'last_error'];
writeFileSync(REPORT_FILE, [cols.join(','), ...shown.map((g) => cols.map((c) => csvEscape(g[c])).join(','))].join('\n') + '\n');
console.log(`Written to ${REPORT_FILE}`);
