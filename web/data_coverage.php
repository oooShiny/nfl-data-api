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
            nfldata.org combines several public NFL data sources &mdash; nflverse, Pro-Football-Reference, FiveThirtyEight, and others &mdash; into one normalized schema. Coverage varies by dataset: games and final scores go back to <?= htmlspecialchars((string) $seasonMin) ?>, while play-by-play, advanced stats, and betting data generally start in 1999 or later. The table below breaks down what's available for each part of the database, with current row counts.
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
                        <td>1970&ndash;<?= htmlspecialchars((string) $seasonMax) ?> <span class="endpoint-label" style="font-size: 10px;">2000 missing</span></td>
                        <td class="text-right"><?= nf($rows['dim_games'] ?? null) ?></td>
                        <td>Final scores, dates, and a Pro-Football-Reference box score link for every game back to 1970. The 2000 season is missing from the source and isn't recoverable from this pipeline.</td>
                    </tr>
                    <tr>
                        <td>Stadium, weather, betting lines, refs, coaches</td>
                        <td>1999&ndash;<?= htmlspecialchars((string) $seasonMax) ?></td>
                        <td class="text-right">&mdash;</td>
                        <td>Roof/surface/temp/wind, spread &amp; total lines, moneylines, rest days, starting QBs, coaches, and officiating crews are only populated for 1999+. Pre-1999 rows leave these fields <code>null</code>.</td>
                    </tr>
                    <tr>
                        <td>Scoring-play summaries</td>
                        <td>1970&ndash;1997</td>
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
                        <td>1999&ndash;2025</td>
                        <td class="text-right"><?= nf($rows['fact_plays'] ?? null) ?></td>
                        <td>No pre-1999 play-by-play exists publicly, so this is the earliest possible start.</td>
                    </tr>
                    <tr>
                        <td>Pass / rush / kick play splits</td>
                        <td>1999&ndash;2025</td>
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
                        <td>2022&ndash;2025</td>
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
                        <td>1999&ndash;2024</td>
                        <td class="text-right"><?= nf($rows['fact_player_game_stats'] ?? null) ?></td>
                        <td>Passing/rushing/receiving/defense/kicking, one row per player per game. 2025 not yet published upstream.</td>
                    </tr>
                    <tr>
                        <td>Season stat totals</td>
                        <td>1999&ndash;2025</td>
                        <td class="text-right"><?= nf($rows['fact_player_season_stats'] ?? null) ?></td>
                        <td><code>GET /v1/stats/season</code> &mdash; REG, POST, and combined REG+POST rows per player-season.</td>
                    </tr>
                    <tr>
                        <td>Next Gen Stats (passing/receiving/rushing)</td>
                        <td>2016&ndash;2025</td>
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
                        <td>2002&ndash;2025</td>
                        <td class="text-right"><?= nf($rows['fact_weekly_rosters'] ?? null) ?></td>
                        <td>Active/inactive status by week.</td>
                    </tr>
                    <tr>
                        <td>Depth charts</td>
                        <td>2001&ndash;2024</td>
                        <td class="text-right"><?= nf($rows['fact_depth_charts'] ?? null) ?></td>
                        <td>Listed depth-chart position by week.</td>
                    </tr>
                    <tr>
                        <td>Snap counts</td>
                        <td>2013&ndash;2025</td>
                        <td class="text-right"><?= nf($rows['fact_snap_counts'] ?? null) ?></td>
                        <td>Offensive/defensive/special teams snap percentages by game.</td>
                    </tr>
                    <tr>
                        <td>Injury reports</td>
                        <td>2009&ndash;2025</td>
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
            Row counts last refreshed: <?= htmlspecialchars($health['last_refresh'] ?? 'unknown') ?>. See <a href="https://api.nfldata.org/docs">the API docs</a> for full endpoint &amp; field reference.
        </p>
    </div>
</section>

<?php require __DIR__ . '/includes/footer.php'; ?>
