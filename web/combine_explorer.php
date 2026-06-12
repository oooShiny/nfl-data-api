<?php
require_once __DIR__ . '/includes/api.php';

$page_title = 'Combine vs. Production';
$page_subtitle = 'See how combine measurables for a draft class compare to career NFL production.';

const COMBINE_POSITIONS = [
    'QB', 'RB', 'FB', 'WR', 'TE', 'OT', 'OG', 'OL', 'C', 'G',
    'DE', 'DT', 'DL', 'EDGE', 'LB', 'ILB', 'OLB',
    'CB', 'S', 'SAF', 'DB', 'K', 'P', 'LS',
];

$currentYear = (int) date('Y');
$combineSeasons = range($currentYear, 2000);

$season = trim($_GET['season'] ?? '');
$position = trim($_GET['position'] ?? 'WR');

$players = [];

if ($season !== '') {
    $combineResult = nfl_api_get_cached('/combine', ['season' => (int) $season, 'position' => $position, 'limit' => 100]);

    foreach ($combineResult['data'] ?? [] as $c) {
        $career = ['games' => 0, 'fantasy_points_ppr' => 0.0, 'seasons_played' => 0, 'gsis_id' => null];

        $playerResult = nfl_api_get_cached('/players', ['name' => $c['player_name'], 'position' => $position, 'limit' => 1]);
        $player = $playerResult['data'][0] ?? null;

        if ($player) {
            $career['gsis_id'] = $player['gsis_id'];
            $statsResult = nfl_api_get_cached('/stats/season', ['player_id' => $player['gsis_id'], 'limit' => 60], 86400);
            $seenSeasons = [];
            foreach ($statsResult['data'] ?? [] as $row) {
                if (!in_array($row['season_type'], ['REG', 'REG+POST'], true)) {
                    continue;
                }
                $career['games'] += $row['games'] ?? 0;
                $career['fantasy_points_ppr'] += $row['fantasy_points_ppr'] ?? 0.0;
                $seenSeasons[$row['season']] = true;
            }
            $career['seasons_played'] = count($seenSeasons);
        }

        $players[] = ['combine' => $c, 'career' => $career];
    }

    // Players with more career games are likely the more relevant comparisons.
    usort($players, fn($a, $b) => $b['career']['games'] <=> $a['career']['games']);
}

require __DIR__ . '/includes/header.php';
?>

<form method="GET" class="form-section">
    <div class="form-row">
        <label for="season">Combine year</label>
        <select id="season" name="season">
            <option value="">Select a year</option>
            <?php foreach ($combineSeasons as $s): ?>
                <option value="<?= $s ?>" <?= ((string) $s === $season) ? 'selected' : '' ?>><?= $s ?></option>
            <?php endforeach; ?>
        </select>
    </div>
    <div class="form-row">
        <label for="position">Position</label>
        <select id="position" name="position">
            <?php foreach (COMBINE_POSITIONS as $p): ?>
                <option value="<?= $p ?>" <?= ($p === $position) ? 'selected' : '' ?>><?= $p ?></option>
            <?php endforeach; ?>
        </select>
    </div>
    <button type="submit" class="submit-btn">View Combine Class</button>
</form>

<?php if ($season !== ''): ?>
    <div class="results-section">
        <?php if (empty($players)): ?>
            <div class="no-results">No combine data found for <?= htmlspecialchars($season) ?>, position <?= htmlspecialchars($position) ?>.</div>
        <?php else: ?>
            <h2><?= htmlspecialchars($season) ?> Combine &mdash; <?= htmlspecialchars($position) ?></h2>
            <p style="color:#666;">
                "Career" totals are regular-season + playoff games and PPR fantasy points across all seasons in our
                data (1999+). Players who didn't reach the NFL or whose careers predate our coverage will show 0.
            </p>
            <div class="table-wrap">
                <table class="data-table sortable">
                    <thead>
                        <tr>
                            <th>Player</th>
                            <th>School</th>
                            <th>Ht</th>
                            <th>Wt</th>
                            <th>40-yd</th>
                            <th>Vertical</th>
                            <th>Bench</th>
                            <th>Broad Jump</th>
                            <th>3-Cone</th>
                            <th>Shuttle</th>
                            <th>Seasons Played</th>
                            <th>Career Games</th>
                            <th>Career Fantasy Pts (PPR)</th>
                        </tr>
                    </thead>
                    <tbody>
                        <?php foreach ($players as $p): ?>
                            <?php $c = $p['combine']; $career = $p['career']; ?>
                            <tr>
                                <td>
                                    <?php if (!empty($career['gsis_id'])): ?>
                                        <a href="player_explorer.php?gsis_id=<?= urlencode($career['gsis_id']) ?>">
                                            <?= htmlspecialchars($c['player_name'] ?? '-') ?>
                                        </a>
                                    <?php else: ?>
                                        <?= htmlspecialchars($c['player_name'] ?? '-') ?>
                                    <?php endif; ?>
                                </td>
                                <td><?= htmlspecialchars($c['school'] ?? '-') ?></td>
                                <td><?= htmlspecialchars($c['ht'] ?? '-') ?></td>
                                <td><?= htmlspecialchars((string) ($c['wt'] ?? '-')) ?></td>
                                <td><?= isset($c['forty']) ? number_format($c['forty'], 2) : '-' ?></td>
                                <td><?= isset($c['vertical']) ? number_format($c['vertical'], 1) : '-' ?></td>
                                <td><?= htmlspecialchars((string) ($c['bench'] ?? '-')) ?></td>
                                <td><?= htmlspecialchars((string) ($c['broad_jump'] ?? '-')) ?></td>
                                <td><?= isset($c['cone']) ? number_format($c['cone'], 2) : '-' ?></td>
                                <td><?= isset($c['shuttle']) ? number_format($c['shuttle'], 2) : '-' ?></td>
                                <td><?= $career['seasons_played'] ?></td>
                                <td><?= $career['games'] ?></td>
                                <td><?= number_format($career['fantasy_points_ppr'], 1) ?></td>
                            </tr>
                        <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
        <?php endif; ?>
    </div>
<?php endif; ?>

<?php require __DIR__ . '/includes/footer.php'; ?>
