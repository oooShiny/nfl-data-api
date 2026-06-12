<?php
require_once __DIR__ . '/includes/api.php';

$page_title = 'QB Efficiency Comparator';
$page_subtitle = 'Compare quarterbacks side by side for a given season.';

$namesInput = trim($_GET['names'] ?? '');
$season = trim($_GET['season'] ?? '');

$meta = nfl_api_get('/meta');
$seasons = $meta['seasons'] ?? [];
if ($season === '' && !empty($seasons)) {
    $season = (string) max($seasons);
}

$qbs = [];
$notFound = [];

if ($namesInput !== '' && $season !== '') {
    $names = array_filter(array_map('trim', explode(',', $namesInput)));

    foreach ($names as $name) {
        $result = nfl_api_get('/players', ['name' => $name, 'position' => 'QB', 'limit' => 1]);
        if (empty($result['data'])) {
            $notFound[] = $name;
            continue;
        }

        $player = $result['data'][0];
        $gsisId = $player['gsis_id'];

        $seasonStats = nfl_api_get('/stats/season', [
            'player_id' => $gsisId,
            'season' => (int) $season,
            'limit' => 5,
        ]);
        $totals = null;
        foreach ($seasonStats['data'] ?? [] as $row) {
            if (in_array($row['season_type'], ['REG+POST', 'REG'], true)) {
                $totals = $row;
                break;
            }
        }

        $ngs = nfl_api_get('/stats/ngs/passing', [
            'player_gsis_id' => $gsisId,
            'season' => (int) $season,
            'season_type' => 'REG',
            'week' => 0,
            'limit' => 1,
        ]);
        $ngsRow = $ngs['data'][0] ?? null;

        $qbs[] = [
            'player' => $player,
            'totals' => $totals,
            'ngs' => $ngsRow,
        ];
    }
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

require __DIR__ . '/includes/header.php';
?>

<form method="GET" class="form-section">
    <div class="form-row">
        <label for="names">Quarterbacks (comma-separated)</label>
        <input type="text" id="names" name="names" style="width: 100%; max-width: 500px;"
               value="<?= htmlspecialchars($namesInput) ?>"
               placeholder="e.g. Patrick Mahomes, Josh Allen, Joe Burrow">
    </div>
    <div class="form-row">
        <label for="season">Season</label>
        <select id="season" name="season">
            <?php foreach (array_reverse($seasons) as $s): ?>
                <option value="<?= htmlspecialchars((string) $s) ?>" <?= ((string) $s === $season) ? 'selected' : '' ?>>
                    <?= htmlspecialchars((string) $s) ?>
                </option>
            <?php endforeach; ?>
        </select>
    </div>
    <button type="submit" class="submit-btn">Compare</button>
</form>

<?php if (!empty($notFound)): ?>
    <div class="error">Could not find a QB matching: <?= htmlspecialchars(implode(', ', $notFound)) ?></div>
<?php endif; ?>

<?php if (!empty($qbs)): ?>
    <div class="results-section">
        <?php
        $rows = [
            ['label' => 'Team', 'totals' => 'recent_team'],
            ['label' => 'Games', 'totals' => 'games'],
            ['label' => 'Completions', 'totals' => 'completions'],
            ['label' => 'Attempts', 'totals' => 'attempts'],
            ['label' => 'Pass Yards', 'totals' => 'passing_yards'],
            ['label' => 'Pass TDs', 'totals' => 'passing_tds'],
            ['label' => 'Interceptions', 'totals' => 'passing_interceptions'],
            ['label' => 'Pass EPA', 'totals' => 'passing_epa'],
            ['label' => 'Rush Yards', 'totals' => 'rushing_yards'],
            ['label' => 'Rush TDs', 'totals' => 'rushing_tds'],
            ['label' => 'Fantasy Points (PPR)', 'totals' => 'fantasy_points_ppr'],
            ['label' => 'Completion %', 'ngs' => 'completion_percentage'],
            ['label' => 'Expected Comp %', 'ngs' => 'expected_completion_percentage'],
            ['label' => 'CPOE', 'ngs' => 'completion_percentage_above_expectation'],
            ['label' => 'Avg Time to Throw', 'ngs' => 'avg_time_to_throw'],
            ['label' => 'Aggressiveness %', 'ngs' => 'aggressiveness'],
            ['label' => 'Passer Rating', 'ngs' => 'passer_rating'],
        ];
        ?>
        <div class="table-wrap">
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Stat</th>
                        <?php foreach ($qbs as $qb): ?>
                            <th><?= htmlspecialchars($qb['player']['display_name']) ?></th>
                        <?php endforeach; ?>
                    </tr>
                </thead>
                <tbody>
                    <?php foreach ($rows as $row): ?>
                        <tr>
                            <td><strong><?= htmlspecialchars($row['label']) ?></strong></td>
                            <?php foreach ($qbs as $qb): ?>
                                <?php
                                $source = isset($row['totals']) ? $qb['totals'] : $qb['ngs'];
                                $key = $row['totals'] ?? $row['ngs'];
                                $value = $source[$key] ?? null;
                                ?>
                                <td><?= fmt($value) ?></td>
                            <?php endforeach; ?>
                        </tr>
                    <?php endforeach; ?>
                </tbody>
            </table>
        </div>
        <?php foreach ($qbs as $qb): ?>
            <?php if ($qb['totals'] === null): ?>
                <div class="info">
                    No season totals found for <?= htmlspecialchars($qb['player']['display_name']) ?>
                    in <?= htmlspecialchars($season) ?> (may not have played that season).
                </div>
            <?php endif; ?>
        <?php endforeach; ?>
    </div>
<?php endif; ?>

<?php require __DIR__ . '/includes/footer.php'; ?>
