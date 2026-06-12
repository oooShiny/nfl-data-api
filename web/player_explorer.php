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
    <div class="results-section">
        <div class="result-item">
            <div class="result-header"><?= htmlspecialchars($player['display_name'] ?? $gsisId) ?></div>
            <div style="padding: 15px;">
                <strong>Position:</strong> <?= htmlspecialchars($player['position'] ?? '-') ?>
                &nbsp;|&nbsp;
                <strong>College:</strong> <?= htmlspecialchars($player['college'] ?? '-') ?>
                &nbsp;|&nbsp;
                <strong>Height/Weight:</strong>
                <?= htmlspecialchars((string) ($player['height'] ?? '-')) ?> in /
                <?= htmlspecialchars((string) ($player['weight'] ?? '-')) ?> lbs
                <br>
                <strong>Born:</strong> <?= htmlspecialchars($player['birth_date'] ?? '-') ?>
                &nbsp;|&nbsp;
                <strong>Status:</strong> <?= htmlspecialchars($player['status'] ?? '-') ?>
                &nbsp;|&nbsp;
                <strong>Experience:</strong> <?= htmlspecialchars((string) ($player['years_exp'] ?? '-')) ?> years
                <?php if (!empty($player['draft_year'])): ?>
                    <br>
                    <strong>Drafted:</strong> <?= htmlspecialchars((string) $player['draft_year']) ?>,
                    Round <?= htmlspecialchars((string) ($player['draft_round'] ?? '?')) ?>,
                    Pick <?= htmlspecialchars((string) ($player['draft_pick'] ?? '?')) ?>
                    by <?= htmlspecialchars($player['draft_club'] ?? '?') ?>
                <?php endif; ?>
            </div>
        </div>

        <?php
        $posGroup = $player['position_group'] ?? '';
        [$totalsRows, $playoffRows] = split_season_rows($seasonStats['data'] ?? []);
        $columns = season_stat_columns($posGroup);
        ?>

        <h2>Season stats</h2>
        <?php render_table($totalsRows, $columns); ?>

        <?php if (!empty($playoffRows)): ?>
            <h2>Playoffs</h2>
            <?php render_table($playoffRows, $columns); ?>
        <?php endif; ?>

        <?php if ($ngsRows !== null && !empty($ngsRows['data'])): ?>
            <?php
            // Season totals are reported as week 0.
            $seasonTotals = array_values(array_filter($ngsRows['data'], fn($r) => ($r['week'] ?? null) === 0));
            ?>
            <h2>Next Gen Stats (season totals)</h2>
            <?php render_table($seasonTotals, ngs_columns($posGroup)); ?>
        <?php endif; ?>
    </div>
<?php endif; ?>

<?php require __DIR__ . '/includes/footer.php'; ?>
