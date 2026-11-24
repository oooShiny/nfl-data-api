<?php
require_once __DIR__ . '/includes/api.php';

$page_title = 'Data Coverage';
$page_subtitle = 'What\'s in the database, how far back it goes, and where the gaps are.';

$meta = nfl_api_get_cached('/meta', [], 86400);
$health = nfl_api_get_cached('/health', [], 3600);
$rows = $health['row_counts'] ?? [];

$seasons = $meta['seasons'] ?? [];
$seasonMin = $seasons ? min($seasons) : null;
$seasonMax = $seasons ? max($seasons) : null;

function nf($n) {
    return $n === null ? '&mdash;' : number_format($n);
}

// ── Coverage map ────────────────────────────────────────────────────────────
// One row per dataset, one column per season (1920-69 folded into one column).
// Each cell is shaded by that season's rows per game played, relative to the
// dataset's typical (median) season. Dividing by games keeps short schedules
// (14-game 1970s seasons, the 1982 strike, the season in progress) from
// looking incomplete when every game is covered.
$coverage = nfl_api_get_cached('/coverage', [], 21600);
$covFirst = 1970;  // seasons before this are folded into one "pre" column

function cov_median(array $values): float {
    sort($values);
    $n = count($values);
    if ($n === 0) return 0;
    return $n % 2 ? $values[intdiv($n, 2)] : ($values[$n / 2 - 1] + $values[$n / 2]) / 2;
}

function cov_level_ratio(float $rate, float $median): int {
    if ($median <= 0) return 3;
    $ratio = $rate / $median;
    return $ratio >= 0.8 ? 3 : ($ratio >= 0.35 ? 2 : 1);
}

$covLevelNames = [0 => 'No data', 1 => 'Sparse', 2 => 'Partial', 3 => 'Full season'];
$covGroups = [];
$covLast = null;
$covInProgress = false;
if ($coverage && !empty($coverage['groups'])) {
    $covLast = (int) $coverage['season_max'];
    $current = (int) ($coverage['current_season'] ?? $covLast);
    $covInProgress = !empty($coverage['current_season_in_progress']);
    $covGames = [];
    foreach (($coverage['games_per_season'] ?? []) as $season => $n) {
        $covGames[(int) $season] = max(1, (int) $n);
    }
    $perGame = fn(int $season, int $count): float => $count / ($covGames[$season] ?? 1);
    foreach ($coverage['groups'] as $group) {
        $rowsOut = [];
        foreach ($group['rows'] as $row) {
            $bySeason = [];
            foreach ($row['seasons'] as $season => $count) {
                $bySeason[(int) $season] = (int) $count;
            }
            // Typical rows per game, from 1970 on (games data starts there) and
            // ignoring the season still being played.
            $rates = [];
            foreach ($bySeason as $s => $c) {
                if ($s >= $covFirst && !($covInProgress && $s === $current)) {
                    $rates[] = $perGame($s, $c);
                }
            }
            $median = cov_median($rates);

            $present = array_keys($bySeason);
            $span = $present ? min($present) . '&ndash;' . max($present) : 'none';

            // Folded pre-1970 cell: share of those seasons with data.
            $preSeasons = array_filter($present, fn($s) => $s < $covFirst);
            $pre = null;
            if ($preSeasons) {
                $preRows = array_sum(array_intersect_key($bySeason, array_flip($preSeasons)));
                $preSpan = $covFirst - min($preSeasons);
                $pre = [
                    'level' => count($preSeasons) >= 0.9 * $preSpan ? 3 : (count($preSeasons) >= 0.35 * $preSpan ? 2 : 1),
                    'tip' => sprintf('%d of %d seasons, %s rows', count($preSeasons), $preSpan, number_format($preRows)),
                ];
            }

            $cells = [];
            for ($season = $covFirst; $season <= $covLast; $season++) {
                $count = $bySeason[$season] ?? 0;
                $level = $count ? cov_level_ratio($perGame($season, $count), $median) : 0;
                $note = ($covInProgress && $season === $current) ? ' (season in progress)' : '';
                $cells[] = [
                    'season' => $season,
                    'level' => $level,
                    'live' => $note !== '',
                    'tip' => $count ? number_format($count) . ' rows &middot; ' . $covLevelNames[$level] . $note : 'No data',
                ];
            }
            $rowsOut[] = ['label' => $row['label'], 'span' => $span, 'pre' => $pre, 'cells' => $cells];
        }
        $covGroups[] = ['name' => $group['name'], 'rows' => $rowsOut];
    }
}

require __DIR__ . '/includes/header.php';
?>

<!-- ===== OVERVIEW ===== -->
<section>
    <div class="section-header red">
        <h2>Overview</h2>
        <span class="endpoint-label">GET /v1/meta &middot; GET /v1/health</span>
    </div>
    <div class="page-pinstripe"></div>
    <div class="section-body" style="padding: 16px 20px;">
        <p style="font-family: 'Barlow Semi Condensed', sans-serif; font-size: 15.5px; color: var(--text-muted); line-height: 1.6; margin: 0 0 14px;">
            nfldata.br0wn.net combines several public NFL data sources &mdash; nflverse, Pro-Football-Reference, FiveThirtyEight, and others &mdash; into one normalized schema. Coverage varies by dataset: games and final scores go back to <?= htmlspecialchars((string) $seasonMin) ?>, while play-by-play, advanced stats, and betting data generally start in 1999 or later. The table below breaks down what's available for each part of the database, with current row counts.
        </p>
        <div class="coverage-chips">
            <div class="chip">
                <div class="chip-value"><?= htmlspecialchars((string) $seasonMin) ?>&ndash;<?= htmlspecialchars((string) $seasonMax) ?></div>
                <div class="chip-label">Season range (games)</div>
            </div>
            <div class="chip">
                <div class="chip-value"><?= nf($rows['dim_games'] ?? null) ?></div>
                <div class="chip-label">Games</div>
            </div>
            <div class="chip">
                <div class="chip-value"><?= nf($rows['dim_players'] ?? null) ?></div>
                <div class="chip-label">Players all-time</div>
            </div>
            <div class="chip">
                <div class="chip-value"><?= nf($rows['fact_plays'] ?? null) ?></div>
                <div class="chip-label">Plays (1999&ndash;present)</div>
            </div>
            <div class="chip">
                <div class="chip-value"><?= count($meta['teams'] ?? []) ?></div>
                <div class="chip-label">Teams (incl. defunct codes)</div>
            </div>
        </div>
    </div>
</section>

<!-- ===== COVERAGE MAP ===== -->
<?php if ($covGroups): $covCols = $covLast - $covFirst + 1; ?>
<style>
    .cov-intro { padding-top: var(--sp-3, 16px); }
    .cov-wrap { overflow-x: auto; padding-bottom: var(--sp-3, 16px); }
    .cov-map {
        --lvl-0: #ececec; --lvl-1: #86b6ef; --lvl-2: #3987e5; --lvl-3: #184f95;
        display: grid;
        grid-template-columns: max-content 64px repeat(var(--cols), minmax(6px, 1fr));
        gap: 2px;
        min-width: 640px;
        align-items: center;
        font-size: var(--fs-small, 1rem);
    }
    .cov-axis { font-family: var(--font-mono, monospace); font-size: 0.8125rem; color: var(--text-muted); white-space: nowrap; line-height: 1.2; overflow: visible; }
    .cov-axis.pre { text-align: left; }
    .cov-group span { position: sticky; left: 0; }
    .cov-group { grid-column: 1 / -1; font-weight: 700; margin: var(--sp-3, 16px) 0 var(--sp-1, 4px); border-bottom: 1px solid var(--border-light); }
    .cov-label { color: var(--text); white-space: nowrap; padding-right: var(--sp-3, 16px); line-height: 1.35;
                 position: sticky; left: 0; z-index: 1; background: var(--bg, #fff); }
    .cov-cell { height: 16px; border-radius: 2px; background: var(--lvl-0); }
    .cov-cell.l1 { background: var(--lvl-1); }
    .cov-cell.l2 { background: var(--lvl-2); }
    .cov-cell.l3 { background: var(--lvl-3); }
    .cov-cell.pre { margin-right: 4px; }
    .cov-cell.none-pre { background: transparent; }
    .cov-cell.live { background-image: repeating-linear-gradient(135deg, rgba(255,255,255,0.65) 0 2px, transparent 2px 5px); }
    .cov-cell[data-t]:hover { outline: 2px solid var(--text); outline-offset: 1px; }
    .cov-legend { display: flex; flex-wrap: wrap; gap: var(--sp-1, 4px) var(--sp-4, 24px); margin: 0 0 var(--sp-2, 8px); font-size: var(--fs-small, 1rem); color: var(--text-muted); }
    .cov-legend span { display: inline-flex; align-items: center; gap: var(--sp-2, 8px); }
    .cov-legend i { display: inline-block; width: 16px; height: 16px; border-radius: 2px; }
    .cov-tip {
        position: fixed; z-index: 80; pointer-events: none; display: none; max-width: 300px;
        background: var(--bg, #fff); color: var(--text); border: 1px solid var(--border); border-radius: var(--radius, 2px);
        padding: var(--sp-2, 8px) var(--sp-3, 16px); font-size: var(--fs-small, 1rem); line-height: 1.4;
        box-shadow: 0 2px 10px rgba(0,0,0,0.18);
    }
    .cov-tip b { display: block; }
    .cov-tip small { display: block; color: var(--text-muted); font-size: inherit; }
</style>
<section style="margin-top: 38px;">
    <div class="section-header blue">
        <h2>Coverage Map</h2>
        <span class="endpoint-label">GET /v1/coverage</span>
    </div>
    <div class="page-pinstripe"></div>
    <div class="section-body">
        <div class="cov-intro">
            <p>
                Each square is one season of one dataset, shaded by how much data it has per game played, compared with a typical season for that dataset. Hover over or tap a square for the row count. The tables below list the same coverage in detail.
            </p>
            <div class="cov-legend" aria-hidden="true">
                <span><i style="background: #184f95;"></i>Full season (80%+ of typical)</span>
                <span><i style="background: #3987e5;"></i>Partial (35&ndash;80% of typical)</span>
                <span><i style="background: #86b6ef;"></i>Sparse (under 35%)</span>
                <span><i style="background: #ececec;"></i>No data</span>
                <?php if ($covInProgress): ?>
                <span><i style="background: #3987e5 repeating-linear-gradient(135deg, rgba(255,255,255,0.65) 0 2px, transparent 2px 5px);"></i><?= $covLast ?> season in progress</span>
                <?php endif; ?>
            </div>
        </div>
        <div class="cov-wrap">
            <div class="cov-map" style="--cols: <?= $covCols ?>;" role="img"
                 aria-label="Coverage map: rows per season for each dataset from 1920 to <?= $covLast ?>. The tables below give the same coverage as text.">
                <div></div>
                <div class="cov-axis pre">1920&ndash;69</div>
                <?php for ($season = $covFirst; $season <= $covLast; $season++): ?>
                    <div class="cov-axis"><?= ($season % 10 === 0) ? $season : '' ?></div>
                <?php endfor; ?>
                <?php foreach ($covGroups as $group): ?>
                    <div class="cov-group"><span><?= htmlspecialchars($group['name']) ?></span></div>
                    <?php foreach ($group['rows'] as $row): $label = htmlspecialchars($row['label']); ?>
                        <div class="cov-label"><?= $label ?></div>
                        <?php if ($row['pre']): ?>
                            <div class="cov-cell pre l<?= $row['pre']['level'] ?>" data-t="<?= $label ?>" data-s="1920&ndash;1969" data-r="<?= $row['span'] ?>" data-d="<?= $row['pre']['tip'] ?>"></div>
                        <?php else: ?>
                            <div class="cov-cell pre none-pre"></div>
                        <?php endif; ?>
                        <?php foreach ($row['cells'] as $c): ?><div class="cov-cell l<?= $c['level'] ?><?= $c['live'] ? ' live' : '' ?>" data-t="<?= $label ?>" data-s="<?= $c['season'] ?>" data-r="<?= $row['span'] ?>" data-d="<?= $c['tip'] ?>"></div><?php endforeach; ?>
                    <?php endforeach; ?>
                <?php endforeach; ?>
            </div>
        </div>
    </div>
</section>
<div class="cov-tip" id="cov-tip" role="tooltip"></div>
<script>
(function () {
    var tip = document.getElementById('cov-tip');
    var map = document.querySelector('.cov-map');
    if (!tip || !map) return;
    // On narrow screens the map scrolls sideways; start at the most recent seasons.
    var wrap = map.parentElement;
    if (wrap.scrollWidth > wrap.clientWidth) wrap.scrollLeft = wrap.scrollWidth;
    function show(e) {
        var cell = e.target.closest('.cov-cell[data-t]');
        if (!cell) { tip.style.display = 'none'; return; }
        tip.innerHTML = '<b>' + cell.dataset.t + ', ' + cell.dataset.s + '</b>' + cell.dataset.d + '<small>Dataset covers ' + cell.dataset.r + '</small>';
        tip.style.display = 'block';
        var x = e.clientX + 14, y = e.clientY + 14, r = tip.getBoundingClientRect();
        if (x + r.width > window.innerWidth - 8) x = e.clientX - r.width - 14;
        if (y + r.height > window.innerHeight - 8) y = e.clientY - r.height - 14;
        tip.style.left = x + 'px'; tip.style.top = y + 'px';
    }
    map.addEventListener('pointermove', show);
    map.addEventListener('pointerdown', show);  // taps on touch screens
    wrap.addEventListener('scroll', function () { tip.style.display = 'none'; });
    map.addEventListener('pointerleave', function () { tip.style.display = 'none'; });
})();
</script>
<?php endif; ?>

<!-- ===== GAMES & SCHEDULES ===== -->
<section style="margin-top: 38px;">
    <div class="section-header blue">
        <h2>Games &amp; Schedules</h2>
        <span class="endpoint-label">GET /v1/games</span>
    </div>
    <div class="page-pinstripe"></div>
    <div class="section-body">
        <div class="table-wrap">
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Dataset</th>
                        <th>Coverage</th>
                        <th class="text-right">Rows</th>
                        <th>Notes</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>Game results &amp; box scores</td>
                        <td>1970&ndash;<?= htmlspecialchars((string) $seasonMax) ?></td>
                        <td class="text-right"><?= nf($rows['dim_games'] ?? null) ?></td>
                        <td>Final scores and dates for every game back to 1970, each linked to its Pro-Football-Reference box score.</td>
                    </tr>
                    <tr>
                        <td>Stadium, weather, betting lines, refs, coaches</td>
                        <td>1999&ndash;<?= htmlspecialchars((string) $seasonMax) ?></td>
                        <td class="text-right">&mdash;</td>
                        <td>Roof/surface/temp/wind, spread &amp; total lines, moneylines, rest days, starting QBs, coaches, and officiating crews are only populated for 1999+. Pre-1999 rows leave these fields <code>null</code>.</td>
                    </tr>
                    <tr>
                        <td>Scoring-play summaries</td>
                        <td>1970&ndash;1998</td>
                        <td class="text-right"><?= nf($rows['fact_game_scoring'] ?? null) ?></td>
                        <td>One row per scoring play (TD/FG/safety etc.) for pre-1999 games &mdash; coarser than full play-by-play. <code>GET /v1/games/scoring</code>.</td>
                    </tr>
                    <tr>
                        <td>Officiating crews</td>
                        <td>2015&ndash;<?= htmlspecialchars((string) $seasonMax) ?></td>
                        <td class="text-right"><?= nf($rows['ref_officials'] ?? null) ?></td>
                        <td>Per-game officiating assignments by role.</td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
</section>

<!-- ===== PLAY-BY-PLAY ===== -->
<section style="margin-top: 38px;">
    <div class="section-header blue">
        <h2>Play-by-Play</h2>
        <span class="endpoint-label">GET /v1/plays</span>
    </div>
    <div class="page-pinstripe"></div>
    <div class="section-body">
        <div class="table-wrap">
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Dataset</th>
                        <th>Coverage</th>
                        <th class="text-right">Rows</th>
                        <th>Notes</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>Every play (EPA/WPA, down &amp; distance, etc.)</td>
                        <td>1999&ndash;<?= htmlspecialchars((string) $seasonMax) ?></td>
                        <td class="text-right"><?= nf($rows['fact_plays'] ?? null) ?></td>
                        <td>No pre-1999 play-by-play exists publicly, so this is the earliest possible start.</td>
                    </tr>
                    <tr>
                        <td>Pass / rush / kick play splits</td>
                        <td>1999&ndash;<?= htmlspecialchars((string) $seasonMax) ?></td>
                        <td class="text-right"><?= nf($rows['fact_pass_plays'] ?? null) ?> / <?= nf($rows['fact_rush_plays'] ?? null) ?> / <?= nf($rows['fact_kick_plays'] ?? null) ?></td>
                        <td>Convenience views over <code>fact_plays</code> filtered &amp; widened by play type.</td>
                    </tr>
                    <tr>
                        <td>Tracking-data participation (personnel, formations)</td>
                        <td>2016&ndash;2025</td>
                        <td class="text-right"><?= nf($rows['fact_pbp_participation'] ?? null) ?></td>
                        <td>Offense/defense personnel groupings, pass rush counts, coverage type.</td>
                    </tr>
                    <tr>
                        <td>FTN charting (route, motion, blitz tags)</td>
                        <td>2022&ndash;<?= htmlspecialchars((string) $seasonMax) ?></td>
                        <td class="text-right"><?= nf($rows['fact_ftn_charting'] ?? null) ?></td>
                        <td>Manually charted play attributes not derivable from the box score.</td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
</section>

<!-- ===== PLAYERS & STATS ===== -->
<section style="margin-top: 38px;">
    <div class="section-header blue">
        <h2>Players &amp; Stats</h2>
        <span class="endpoint-label">GET /v1/players &middot; GET /v1/stats/*</span>
    </div>
    <div class="page-pinstripe"></div>
    <div class="section-body">
        <div class="table-wrap">
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Dataset</th>
                        <th>Coverage</th>
                        <th class="text-right">Rows</th>
                        <th>Notes</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>Player bios &amp; IDs</td>
                        <td>All-time</td>
                        <td class="text-right"><?= nf($rows['dim_players'] ?? null) ?></td>
                        <td>Every player with a known nflverse ID, with cross-source name matching (<code>name_resolution</code>: <?= nf($rows['name_resolution'] ?? null) ?> mappings).</td>
                    </tr>
                    <tr>
                        <td>Game-by-game stat lines</td>
                        <td>1999&ndash;<?= htmlspecialchars((string) $seasonMax) ?></td>
                        <td class="text-right"><?= nf($rows['fact_player_game_stats'] ?? null) ?></td>
                        <td>Passing/rushing/receiving and fantasy points, one row per player per game. Updated weekly during the season.</td>
                    </tr>
                    <tr>
                        <td>Season stat totals</td>
                        <td>1999&ndash;<?= htmlspecialchars((string) $seasonMax) ?></td>
                        <td class="text-right"><?= nf($rows['fact_player_season_stats'] ?? null) ?></td>
                        <td><code>GET /v1/stats/season</code> &mdash; REG, POST, and combined REG+POST rows per player-season.</td>
                    </tr>
                    <tr>
                        <td>Next Gen Stats (passing/receiving/rushing)</td>
                        <td>2016&ndash;<?= htmlspecialchars((string) $seasonMax) ?></td>
                        <td class="text-right"><?= nf($rows['fact_ngs_passing'] ?? null) ?> / <?= nf($rows['fact_ngs_receiving'] ?? null) ?> / <?= nf($rows['fact_ngs_rushing'] ?? null) ?></td>
                        <td>Tracking-derived metrics (CPOE, time to throw, separation, etc.) &mdash; only exist from 2016 on.</td>
                    </tr>
                    <tr>
                        <td>PFR advanced stats (season totals)</td>
                        <td>Varies, recent seasons</td>
                        <td class="text-right"><?= nf($rows['ref_pfr_adv_pass'] ?? null) ?> / <?= nf($rows['ref_pfr_adv_rush'] ?? null) ?> / <?= nf($rows['ref_pfr_adv_rec'] ?? null) ?> / <?= nf($rows['ref_pfr_adv_def'] ?? null) ?></td>
                        <td>Pass/rush/rec/def advanced metrics (pressure rate, broken tackles, etc.), season-level only.</td>
                    </tr>
                    <tr>
                        <td>QBR (season &amp; weekly)</td>
                        <td>Recent seasons</td>
                        <td class="text-right"><?= nf($rows['ref_qbr_season'] ?? null) ?> / <?= nf($rows['ref_qbr_week'] ?? null) ?></td>
                        <td>ESPN Total QBR.</td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
</section>

<!-- ===== ROSTERS & PERSONNEL ===== -->
<section style="margin-top: 38px;">
    <div class="section-header blue">
        <h2>Rosters &amp; Personnel</h2>
        <span class="endpoint-label">GET /v1/rosters &middot; GET /v1/teams/*</span>
    </div>
    <div class="page-pinstripe"></div>
    <div class="section-body">
        <div class="table-wrap">
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Dataset</th>
                        <th>Coverage</th>
                        <th class="text-right">Rows</th>
                        <th>Notes</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>Season rosters</td>
                        <td>1920&ndash;<?= htmlspecialchars((string) $seasonMax) ?></td>
                        <td class="text-right"><?= nf($rows['fact_rosters'] ?? null) ?></td>
                        <td>Full historical roster data, including pre-1999 players (some without a modern player ID).</td>
                    </tr>
                    <tr>
                        <td>Weekly rosters</td>
                        <td>2002&ndash;<?= htmlspecialchars((string) $seasonMax) ?></td>
                        <td class="text-right"><?= nf($rows['fact_weekly_rosters'] ?? null) ?></td>
                        <td>Active/inactive status by week.</td>
                    </tr>
                    <tr>
                        <td>Depth charts</td>
                        <td>2001&ndash;<?= htmlspecialchars((string) $seasonMax) ?></td>
                        <td class="text-right"><?= nf($rows['fact_depth_charts'] ?? null) ?></td>
                        <td>Listed depth-chart position heading into each game. From 2025 this comes from daily ESPN depth charts, so bye weeks have no rows.</td>
                    </tr>
                    <tr>
                        <td>Snap counts</td>
                        <td>2013&ndash;<?= htmlspecialchars((string) $seasonMax) ?></td>
                        <td class="text-right"><?= nf($rows['fact_snap_counts'] ?? null) ?></td>
                        <td>Offensive/defensive/special teams snap percentages by game.</td>
                    </tr>
                    <tr>
                        <td>Injury reports</td>
                        <td>2009&ndash;<?= htmlspecialchars((string) $seasonMax) ?></td>
                        <td class="text-right"><?= nf($rows['fact_injuries'] ?? null) ?></td>
                        <td>Weekly injury report status (Questionable/Out/etc.).</td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
</section>

<!-- ===== DRAFT, COMBINE, CONTRACTS & TRADES ===== -->
<section style="margin-top: 38px;">
    <div class="section-header blue">
        <h2>Draft, Combine, Contracts &amp; Trades</h2>
        <span class="endpoint-label">GET /v1/draft &middot; GET /v1/combine &middot; GET /v1/contracts &middot; GET /v1/trades</span>
    </div>
    <div class="page-pinstripe"></div>
    <div class="section-body">
        <div class="table-wrap">
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Dataset</th>
                        <th>Coverage</th>
                        <th class="text-right">Rows</th>
                        <th>Notes</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>Draft picks</td>
                        <td>1980&ndash;<?= htmlspecialchars((string) $seasonMax) ?></td>
                        <td class="text-right"><?= nf($rows['ref_draft_picks'] ?? null) ?></td>
                        <td>Every pick by round/team, linked to the player's modern ID where resolvable.</td>
                    </tr>
                    <tr>
                        <td>Combine results</td>
                        <td>2000&ndash;<?= htmlspecialchars((string) $seasonMax) ?></td>
                        <td class="text-right"><?= nf($rows['ref_combine'] ?? null) ?></td>
                        <td>Height/weight/40-time/etc. for drafted and undrafted invitees.</td>
                    </tr>
                    <tr>
                        <td>Contracts</td>
                        <td>~1991&ndash;<?= htmlspecialchars((string) $seasonMax) ?></td>
                        <td class="text-right"><?= nf($rows['ref_contracts'] ?? null) ?></td>
                        <td>Contract value, APY, guarantees, and salary-cap percentage (nominal and inflation-adjusted).</td>
                    </tr>
                    <tr>
                        <td>Trades</td>
                        <td>2002&ndash;<?= htmlspecialchars((string) $seasonMax) ?></td>
                        <td class="text-right"><?= nf($rows['ref_trades'] ?? null) ?></td>
                        <td>Player and draft-pick trades between teams.</td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
</section>

<!-- ===== TEAMS & RATINGS ===== -->
<section style="margin-top: 38px; margin-bottom: 38px;">
    <div class="section-header blue">
        <h2>Teams &amp; Ratings</h2>
        <span class="endpoint-label">GET /v1/teams &middot; GET /v1/teams/elo</span>
    </div>
    <div class="page-pinstripe"></div>
    <div class="section-body">
        <div class="table-wrap">
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Dataset</th>
                        <th>Coverage</th>
                        <th class="text-right">Rows</th>
                        <th>Notes</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>Team reference (names, colors, logos)</td>
                        <td>&mdash;</td>
                        <td class="text-right"><?= nf($rows['dim_teams'] ?? null) ?></td>
                        <td>Includes current franchises plus legacy codes used by pre-1999 games (e.g. <code>SLC</code>, <code>PHX</code>, <code>RAI</code>) &mdash; see Games coverage above.</td>
                    </tr>
                    <tr>
                        <td>FiveThirtyEight Elo / QB-Elo ratings</td>
                        <td>1920&ndash;2022</td>
                        <td class="text-right"><?= nf($rows['ref_team_elo'] ?? null) ?></td>
                        <td>Pre- and post-game Elo and QB-adjusted Elo ratings for every game back to 1920.</td>
                    </tr>
                </tbody>
            </table>
        </div>
        <p style="font-family: 'Barlow Semi Condensed', sans-serif; font-size: 13px; color: var(--text-dim); margin: 14px 0 0;">
            Row counts last refreshed: <?= htmlspecialchars($health['last_refresh'] ?? 'unknown') ?>. See <a href="https://nfldata-api.br0wn.net/docs">the API docs</a> for full endpoint &amp; field reference.
        </p>
    </div>
</section>

<?php require __DIR__ . '/includes/footer.php'; ?>
