<?php
require_once __DIR__ . '/includes/api.php';

$page_title = 'Player Career Explorer';
$page_subtitle = 'Search for a player to see season-by-season stats and Next Gen Stats.';

$name = trim($_GET['name'] ?? '');
$gsisId = trim($_GET['gsis_id'] ?? '');

$searchResults = null;
$player = null;
$seasonStats = null;
$ngsRows = null;

if ($gsisId !== '') {
    $player = nfl_api_get('/players/' . urlencode($gsisId));
    if ($player) {
        $seasonStats = nfl_api_get('/stats/season', ['player_id' => $gsisId, 'limit' => 60]);

        $posGroup = $player['position_group'] ?? '';
        if ($posGroup === 'QB') {
            $ngsRows = nfl_api_get('/stats/ngs/passing', ['player_gsis_id' => $gsisId, 'season_type' => 'REG', 'limit' => 30]);
        } elseif ($posGroup === 'RB') {
            $ngsRows = nfl_api_get('/stats/ngs/rushing', ['player_gsis_id' => $gsisId, 'season_type' => 'REG', 'limit' => 30]);
        } elseif (in_array($posGroup, ['WR', 'TE'], true)) {
            $ngsRows = nfl_api_get('/stats/ngs/receiving', ['player_gsis_id' => $gsisId, 'season_type' => 'REG', 'limit' => 30]);
        }
    }
} elseif ($name !== '') {
    $searchResults = nfl_api_get('/players', ['name' => $name, 'limit' => 25]);
}

function fmt($value): string {
    if ($value === null) {
        return '-';
    }
    if (is_float($value)) {
        return number_format($value, 1);
    }
    return htmlspecialchars((string) $value);
}

/**
 * Render a table given an array of rows and a [key => label] column map.
 */
function render_table(array $rows, array $columns): void {
    if (empty($rows)) {
        echo '<div class="no-results">No data available.</div>';
        return;
    }
    echo '<div class="table-wrap"><table class="data-table sortable"><thead><tr>';
    foreach ($columns as $label) {
        echo '<th>' . htmlspecialchars($label) . '</th>';
    }
    echo '</tr></thead><tbody>';
    foreach ($rows as $row) {
        echo '<tr>';
        foreach (array_keys($columns) as $key) {
            echo '<td>' . fmt($row[$key] ?? null) . '</td>';
        }
        echo '</tr>';
    }
    echo '</tbody></table></div>';
}

/**
 * Split season-total rows from playoff-only rows.
 * Each season has either a REG row (no playoffs) or both a
 * REG+POST row (full season totals) and a POST row (playoffs only).
 */
function split_season_rows(array $rows): array {
    $totals = [];
    $playoffs = [];
    foreach ($rows as $row) {
        if ($row['season_type'] === 'REG+POST' || $row['season_type'] === 'REG') {
            $totals[$row['season']] = $row;
        } elseif ($row['season_type'] === 'POST') {
            $playoffs[$row['season']] = $row;
        }
    }
    krsort($totals);
    krsort($playoffs);
    return [array_values($totals), array_values($playoffs)];
}

/** Season-stat columns to show, based on position group. */
function season_stat_columns(string $posGroup): array {
    $base = [
        'season' => 'Season',
        'season_type' => 'Type',
        'recent_team' => 'Team',
        'games' => 'G',
    ];

    return match ($posGroup) {
        'QB' => $base + [
            'completions' => 'Cmp',
            'attempts' => 'Att',
            'passing_yards' => 'Pass Yds',
            'passing_tds' => 'Pass TD',
            'passing_interceptions' => 'INT',
            'passing_epa' => 'Pass EPA',
            'rushing_yards' => 'Rush Yds',
            'rushing_tds' => 'Rush TD',
            'fantasy_points_ppr' => 'Fantasy (PPR)',
        ],
        'RB' => $base + [
            'carries' => 'Carries',
            'rushing_yards' => 'Rush Yds',
            'rushing_tds' => 'Rush TD',
            'rushing_epa' => 'Rush EPA',
            'receptions' => 'Rec',
            'receiving_yards' => 'Rec Yds',
            'receiving_tds' => 'Rec TD',
            'fantasy_points_ppr' => 'Fantasy (PPR)',
        ],
        'WR', 'TE' => $base + [
            'targets' => 'Tgt',
            'receptions' => 'Rec',
            'receiving_yards' => 'Rec Yds',
            'receiving_tds' => 'Rec TD',
            'racr' => 'RACR',
            'target_share' => 'Tgt Share',
            'fantasy_points_ppr' => 'Fantasy (PPR)',
        ],
        'DL', 'LB', 'DB' => $base + [
            'def_tackles_solo' => 'Solo Tkl',
            'def_tackles_with_assist' => 'Ast Tkl',
            'def_tackles_for_loss' => 'TFL',
            'def_sacks' => 'Sacks',
            'def_qb_hits' => 'QB Hits',
            'def_interceptions' => 'INT',
            'def_pass_defended' => 'PD',
            'def_tds' => 'TD',
        ],
        default => $base + [
            'fantasy_points_ppr' => 'Fantasy (PPR)',
        ],
    };
}

/** Build career summary tiles from season-total rows, based on position group. */
function career_tiles(array $totalsRows, string $posGroup): array {
    $games = 0;
    $sum = function (string $key) use ($totalsRows): float {
        $total = 0;
        foreach ($totalsRows as $row) {
            $total += (float) ($row[$key] ?? 0);
        }
        return $total;
    };
    foreach ($totalsRows as $row) {
        $games += (int) ($row['games'] ?? 0);
    }

    return match ($posGroup) {
        'QB' => [
            ['label' => 'Pass Yards', 'value' => number_format($sum('passing_yards')), 'sub' => 'Regular season'],
            ['label' => 'Pass TD', 'value' => number_format($sum('passing_tds')), 'sub' => number_format($sum('passing_interceptions')) . ' interceptions'],
            ['label' => 'Completion %', 'value' => $sum('attempts') > 0 ? number_format($sum('completions') / $sum('attempts') * 100, 1) : '-', 'sub' => number_format($sum('completions')) . ' / ' . number_format($sum('attempts'))],
            ['label' => 'Rush Yards', 'value' => number_format($sum('rushing_yards')), 'sub' => number_format($sum('rushing_tds')) . ' rushing TD'],
            ['label' => 'Games', 'value' => number_format($games), 'sub' => 'Career'],
            ['label' => 'Fantasy (PPR)', 'value' => number_format($sum('fantasy_points_ppr')), 'sub' => 'Career total'],
        ],
        'RB' => [
            ['label' => 'Rush Yards', 'value' => number_format($sum('rushing_yards')), 'sub' => number_format($sum('carries')) . ' carries'],
            ['label' => 'Rush TD', 'value' => number_format($sum('rushing_tds')), 'sub' => 'Career'],
            ['label' => 'Receptions', 'value' => number_format($sum('receptions')), 'sub' => number_format($sum('receiving_yards')) . ' yards'],
            ['label' => 'Receiving TD', 'value' => number_format($sum('receiving_tds')), 'sub' => 'Career'],
            ['label' => 'Games', 'value' => number_format($games), 'sub' => 'Career'],
            ['label' => 'Fantasy (PPR)', 'value' => number_format($sum('fantasy_points_ppr')), 'sub' => 'Career total'],
        ],
        'WR', 'TE' => [
            ['label' => 'Receiving Yards', 'value' => number_format($sum('receiving_yards')), 'sub' => number_format($sum('receptions')) . ' receptions'],
            ['label' => 'Receiving TD', 'value' => number_format($sum('receiving_tds')), 'sub' => 'Career'],
            ['label' => 'Targets', 'value' => number_format($sum('targets')), 'sub' => 'Career'],
            ['label' => 'Catch Rate', 'value' => $sum('targets') > 0 ? number_format($sum('receptions') / $sum('targets') * 100, 1) . '%' : '-', 'sub' => 'Career'],
            ['label' => 'Games', 'value' => number_format($games), 'sub' => 'Career'],
            ['label' => 'Fantasy (PPR)', 'value' => number_format($sum('fantasy_points_ppr')), 'sub' => 'Career total'],
        ],
        'DL', 'LB', 'DB' => [
            ['label' => 'Solo Tackles', 'value' => number_format($sum('def_tackles_solo')), 'sub' => number_format($sum('def_tackles_with_assist')) . ' assists'],
            ['label' => 'Sacks', 'value' => number_format($sum('def_sacks'), 1), 'sub' => number_format($sum('def_tackles_for_loss')) . ' TFL'],
            ['label' => 'Interceptions', 'value' => number_format($sum('def_interceptions')), 'sub' => number_format($sum('def_pass_defended')) . ' passes defended'],
            ['label' => 'Defensive TD', 'value' => number_format($sum('def_tds')), 'sub' => 'Career'],
            ['label' => 'QB Hits', 'value' => number_format($sum('def_qb_hits')), 'sub' => 'Career'],
            ['label' => 'Games', 'value' => number_format($games), 'sub' => 'Career'],
        ],
        default => [
            ['label' => 'Games', 'value' => number_format($games), 'sub' => 'Career'],
            ['label' => 'Fantasy (PPR)', 'value' => number_format($sum('fantasy_points_ppr')), 'sub' => 'Career total'],
        ],
    };
}

/** NGS columns to show, based on position group. */
function ngs_columns(string $posGroup): array {
    return match ($posGroup) {
        'QB' => [
            'season' => 'Season',
            'avg_time_to_throw' => 'Avg Time to Throw',
            'avg_completed_air_yards' => 'Avg Comp Air Yds',
            'aggressiveness' => 'Aggressiveness %',
            'completion_percentage' => 'Comp %',
            'expected_completion_percentage' => 'Exp Comp %',
            'completion_percentage_above_expectation' => 'CPOE',
            'passer_rating' => 'Passer Rating',
        ],
        'RB' => [
            'season' => 'Season',
            'efficiency' => 'Efficiency',
            'avg_time_to_los' => 'Avg Time to LOS',
            'rush_yards_over_expected' => 'RYOE',
            'rush_yards_over_expected_per_att' => 'RYOE/Att',
            'rush_pct_over_expected' => 'Rush % Over Exp',
        ],
        default => [
            'season' => 'Season',
            'avg_separation' => 'Avg Separation',
            'avg_cushion' => 'Avg Cushion',
            'avg_yac' => 'Avg YAC',
            'avg_expected_yac' => 'Avg Exp YAC',
            'avg_yac_above_expectation' => 'YAC Above Exp',
        ],
    };
}

/** Build Next Gen Stat tiles from the most recent season-total row. */
function ngs_tiles(array $row, string $posGroup): array {
    $tiles = [];
    foreach (ngs_columns($posGroup) as $key => $label) {
        if ($key === 'season') {
            continue;
        }
        $tiles[] = ['label' => $label, 'value' => fmt($row[$key] ?? null)];
    }
    return $tiles;
}

require __DIR__ . '/includes/header.php';
?>

<form method="GET" class="form-section">
    <div class="form-row">
        <label for="name">Player name</label>
        <input type="text" id="name" name="name" value="<?= htmlspecialchars($name) ?>" placeholder="e.g. Mahomes">
    </div>
    <button type="submit" class="submit-btn">Search</button>
</form>

<?php if ($searchResults !== null): ?>
    <div class="results-section">
        <?php if (empty($searchResults['data'])): ?>
            <div class="no-results">No players found matching "<?= htmlspecialchars($name) ?>".</div>
        <?php else: ?>
            <h2>Search results</h2>
            <div class="table-wrap">
                <table class="data-table sortable">
                    <thead>
                        <tr>
                            <th>Name</th>
                            <th>Position</th>
                            <th>College</th>
                            <th>Draft</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>
                        <?php foreach ($searchResults['data'] as $p): ?>
                            <tr>
                                <td><?= htmlspecialchars($p['display_name'] ?? '') ?></td>
                                <td><?= htmlspecialchars($p['position'] ?? '-') ?></td>
                                <td><?= htmlspecialchars($p['college'] ?? '-') ?></td>
                                <td>
                                    <?php if (!empty($p['draft_year'])): ?>
                                        <?= htmlspecialchars((string) $p['draft_year']) ?>
                                        Rd <?= htmlspecialchars((string) ($p['draft_round'] ?? '?')) ?>,
                                        Pick <?= htmlspecialchars((string) ($p['draft_pick'] ?? '?')) ?>
                                        (<?= htmlspecialchars($p['draft_club'] ?? '?') ?>)
                                    <?php else: ?>
                                        Undrafted
                                    <?php endif; ?>
                                </td>
                                <td><a href="?gsis_id=<?= urlencode($p['gsis_id']) ?>">View career</a></td>
                            </tr>
                        <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
        <?php endif; ?>
    </div>
<?php endif; ?>

<?php if ($gsisId !== '' && $player === null): ?>
    <div class="error">Player not found.</div>
<?php endif; ?>

<?php if ($player !== null): ?>
    <?php
    $posGroup = $player['position_group'] ?? '';
    [$totalsRows, $playoffRows] = split_season_rows($seasonStats['data'] ?? []);
    $columns = season_stat_columns($posGroup);
    $tiles = career_tiles($totalsRows, $posGroup);

    $bio = [
        ['k' => 'Position', 'v' => htmlspecialchars($player['position'] ?? '-')],
        ['k' => 'Ht / Wt', 'v' => htmlspecialchars((string) ($player['height'] ?? '-')) . ' in / ' . htmlspecialchars((string) ($player['weight'] ?? '-')) . ' lb'],
        ['k' => 'Born', 'v' => htmlspecialchars($player['birth_date'] ?? '-')],
        ['k' => 'College', 'v' => htmlspecialchars($player['college'] ?? '-')],
        ['k' => 'Status', 'v' => htmlspecialchars($player['status'] ?? '-')],
        ['k' => 'Experience', 'v' => htmlspecialchars((string) ($player['years_exp'] ?? '-')) . ' seasons'],
    ];
    if (!empty($player['draft_year'])) {
        $bio[] = ['k' => 'Draft', 'v' => htmlspecialchars((string) $player['draft_year']) . ' &middot; Rd ' . htmlspecialchars((string) ($player['draft_round'] ?? '?')) . ', #' . htmlspecialchars((string) ($player['draft_pick'] ?? '?')) . ' (' . htmlspecialchars($player['draft_club'] ?? '?') . ')'];
    }

    $displayName = $player['display_name'] ?? $gsisId;
    $nameParts = explode(' ', $displayName, 2);
    $initials = '';
    foreach ($nameParts as $part) {
        if ($part !== '') {
            $initials .= $part[0];
        }
    }
    ?>

    <div class="section-header red">
        <h2><?= htmlspecialchars($displayName) ?></h2>
        <span class="endpoint-label">GET /v1/players/<?= htmlspecialchars($gsisId) ?></span>
    </div>
    <div class="page-pinstripe"></div>
    <div class="section-body">
        <div class="identity-grid">
            <div class="identity-panel">
                <div class="identity-head">
                    <div class="identity-pos-badge"><?= htmlspecialchars($initials) ?></div>
                    <div>
                        <div class="identity-name"><?= htmlspecialchars($displayName) ?></div>
                        <div class="identity-sub"><?= htmlspecialchars($player['position'] ?? '-') ?></div>
                    </div>
                </div>
                <?php foreach ($bio as $b): ?>
                    <div class="bio-row">
                        <span><?= htmlspecialchars($b['k']) ?></span>
                        <span><?= $b['v'] ?></span>
                    </div>
                <?php endforeach; ?>
            </div>
            <div class="career-tiles">
                <?php foreach ($tiles as $t): ?>
                    <div class="tile">
                        <div class="tile-label"><?= htmlspecialchars($t['label']) ?></div>
                        <div class="tile-value"><?= htmlspecialchars($t['value']) ?></div>
                        <div class="tile-sub"><?= htmlspecialchars($t['sub']) ?></div>
                    </div>
                <?php endforeach; ?>
            </div>
        </div>
    </div>

    <div class="section-header blue">
        <h2>Season by season</h2>
        <span class="endpoint-label">GET /v1/stats/season</span>
    </div>
    <div class="page-pinstripe"></div>
    <div class="section-body">
        <?php render_table($totalsRows, $columns); ?>
    </div>

    <?php if (!empty($playoffRows)): ?>
        <div class="section-header blue">
            <h2>Playoffs</h2>
        </div>
        <div class="page-pinstripe"></div>
        <div class="section-body">
            <?php render_table($playoffRows, $columns); ?>
        </div>
    <?php endif; ?>

    <?php if ($ngsRows !== null && !empty($ngsRows['data'])): ?>
        <?php
        // Season totals are reported as week 0.
        $seasonTotals = array_values(array_filter($ngsRows['data'], fn($r) => ($r['week'] ?? null) === 0));
        usort($seasonTotals, fn($a, $b) => ($b['season'] ?? 0) <=> ($a['season'] ?? 0));
        $latestNgs = $seasonTotals[0] ?? null;
        ?>
        <?php if ($latestNgs !== null): ?>
            <div class="section-header blue">
                <h2>Next Gen Stats</h2>
                <span class="endpoint-label"><?= htmlspecialchars((string) $latestNgs['season']) ?> season</span>
            </div>
            <div class="page-pinstripe"></div>
            <div class="section-body">
                <div class="ngs-tile-grid">
                    <?php foreach (ngs_tiles($latestNgs, $posGroup) as $n): ?>
                        <div class="ngs-tile">
                            <div class="ngs-tile-value"><?= htmlspecialchars($n['value']) ?></div>
                            <div class="ngs-tile-label"><?= htmlspecialchars($n['label']) ?></div>
                        </div>
                    <?php endforeach; ?>
                </div>
            </div>

            <h3>Next Gen Stats &mdash; season history</h3>
            <?php render_table($seasonTotals, ngs_columns($posGroup)); ?>
        <?php endif; ?>
    <?php endif; ?>

    <?php
    $ticker_items = [
        strtoupper($displayName) . ' &middot; ' . htmlspecialchars($player['position'] ?? '-'),
        count($totalsRows) . ' SEASON' . (count($totalsRows) === 1 ? '' : 'S') . ' OF DATA',
        'GET /v1/players/' . $gsisId,
        'NORMALIZED FROM ONE PLAYER RECORD',
    ];
    ?>
<?php endif; ?>

<?php require __DIR__ . '/includes/footer.php'; ?>
