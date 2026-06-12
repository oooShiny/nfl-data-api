<?php
require_once __DIR__ . '/includes/api.php';

$page_title = 'Trade History Browser';
$page_subtitle = 'Browse player and draft pick trades by team and season.';

$meta = nfl_api_get_cached('/meta', [], 86400);
$seasons = $meta['seasons'] ?? [];
$teams = $meta['teams'] ?? [];

$team = trim($_GET['team'] ?? '');
$team2 = trim($_GET['team2'] ?? '');
$season = trim($_GET['season'] ?? '');
$page = max(1, (int) ($_GET['page'] ?? 1));
$limit = 25;
$offset = ($page - 1) * $limit;

$trades = [];
$total = 0;

$apiParams = [
    'team' => $team,
    'season' => $season,
    'limit' => $limit,
    'offset' => $offset,
];
if ($team !== '' && $team2 !== '') {
    $apiParams['team2'] = $team2;
}

$result = nfl_api_get('/trades', $apiParams);
$total = $result['total'] ?? 0;

// Group the flat asset rows by trade_id.
$byTrade = [];
$order = [];
foreach ($result['data'] ?? [] as $row) {
    $id = $row['trade_id'];
    if (!isset($byTrade[$id])) {
        $byTrade[$id] = [
            'trade_id' => $id,
            'season' => $row['season'],
            'trade_date' => $row['trade_date'],
            'assets' => [],
        ];
        $order[] = $id;
    }
    $byTrade[$id]['assets'][] = $row;
}
foreach ($order as $id) {
    $trades[] = $byTrade[$id];
}

function asset_label(array $row): string {
    if (!empty($row['pfr_name'])) {
        return $row['pfr_name'];
    }
    if (!empty($row['pick_season'])) {
        $label = $row['pick_season'] . ' Round ' . $row['pick_round'];
        if (!empty($row['pick_number'])) {
            $label .= ' (Pick ' . $row['pick_number'] . ')';
        }
        if (!empty($row['conditional'])) {
            $label .= ' [conditional]';
        }
        return $label;
    }
    return 'Unspecified asset';
}

require __DIR__ . '/includes/header.php';
?>

<form method="GET" class="form-section">
    <div class="form-row">
        <label for="team">Team</label>
        <select id="team" name="team">
            <option value="">All teams</option>
            <?php foreach ($teams as $t): ?>
                <option value="<?= htmlspecialchars($t['abbr']) ?>" <?= ($t['abbr'] === $team) ? 'selected' : '' ?>>
                    <?= htmlspecialchars($t['name']) ?>
                </option>
            <?php endforeach; ?>
        </select>
    </div>
    <div class="form-row">
        <label for="team2">Trade partner (optional)</label>
        <select id="team2" name="team2">
            <option value="">Any team</option>
            <?php foreach ($teams as $t): ?>
                <option value="<?= htmlspecialchars($t['abbr']) ?>" <?= ($t['abbr'] === $team2) ? 'selected' : '' ?>>
                    <?= htmlspecialchars($t['name']) ?>
                </option>
            <?php endforeach; ?>
        </select>
    </div>
    <div class="form-row">
        <label for="season">Season</label>
        <select id="season" name="season">
            <option value="">All seasons</option>
            <?php foreach (array_reverse($seasons) as $s): ?>
                <option value="<?= htmlspecialchars((string) $s) ?>" <?= ((string) $s === $season) ? 'selected' : '' ?>>
                    <?= htmlspecialchars((string) $s) ?>
                </option>
            <?php endforeach; ?>
        </select>
    </div>
    <button type="submit" class="submit-btn">Browse Trades</button>
</form>

<div class="results-section">
    <?php if ($team === '' && $team2 !== ''): ?>
        <div class="info">Select a primary team above to find trades between it and the trade partner.</div>
    <?php endif; ?>
    <?php if (empty($trades)): ?>
        <div class="no-results">No trades found matching these criteria.</div>
    <?php else: ?>
        <h2><?= number_format($total) ?> trade(s) found</h2>
        <?php foreach ($trades as $trade): ?>
            <?php
            $teamsInTrade = [];
            foreach ($trade['assets'] as $a) {
                $teamsInTrade[$a['gave']] = true;
                $teamsInTrade[$a['received']] = true;
            }
            $teamsInTrade = array_keys($teamsInTrade);
            ?>
            <div class="result-item">
                <div class="result-header">
                    <?= htmlspecialchars(implode(' ↔ ', $teamsInTrade)) ?>
                    &mdash; <?= htmlspecialchars($trade['trade_date'] ?? (string) $trade['season']) ?>
                </div>
                <div class="table-wrap">
                    <table class="data-table sortable">
                        <thead>
                            <tr>
                                <th>From</th>
                                <th>To</th>
                                <th>Asset</th>
                            </tr>
                        </thead>
                        <tbody>
                            <?php foreach ($trade['assets'] as $a): ?>
                                <tr>
                                    <td><?= htmlspecialchars($a['gave']) ?></td>
                                    <td><?= htmlspecialchars($a['received']) ?></td>
                                    <td><?= htmlspecialchars(asset_label($a)) ?></td>
                                </tr>
                            <?php endforeach; ?>
                        </tbody>
                    </table>
                </div>
            </div>
        <?php endforeach; ?>

        <?php
        $totalPages = (int) ceil($total / $limit);
        $qs = array_filter(['team' => $team, 'team2' => $team2, 'season' => $season]);
        ?>
        <?php if ($totalPages > 1): ?>
            <div style="text-align:center; margin-top:20px;">
                <?php if ($page > 1): ?>
                    <a href="?<?= htmlspecialchars(http_build_query($qs + ['page' => $page - 1])) ?>">&laquo; Previous</a>
                <?php endif; ?>
                <span style="margin: 0 15px;">Page <?= $page ?> of <?= $totalPages ?></span>
                <?php if ($page < $totalPages): ?>
                    <a href="?<?= htmlspecialchars(http_build_query($qs + ['page' => $page + 1])) ?>">Next &raquo;</a>
                <?php endif; ?>
            </div>
        <?php endif; ?>
    <?php endif; ?>
</div>

<?php require __DIR__ . '/includes/footer.php'; ?>
