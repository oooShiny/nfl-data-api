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

$teamNames = array_column($teams, 'name', 'abbr');

// When exactly one team is selected, compute aggregate stats across all of
// its trades (not just the current page) for the summary tiles/charts.
$statsData = null;
if ($team !== '' && $team2 === '') {
    $statsResult = nfl_api_get_cached('/trades', ['team' => $team, 'season' => $season, 'limit' => 1000, 'offset' => 0]);

    $statsByTrade = [];
    $statsOrder = [];
    foreach ($statsResult['data'] ?? [] as $row) {
        $id = $row['trade_id'];
        if (!isset($statsByTrade[$id])) {
            $statsByTrade[$id] = ['season' => $row['season'], 'assets' => []];
            $statsOrder[] = $id;
        }
        $statsByTrade[$id]['assets'][] = $row;
    }

    $tradesByYear = [];
    $partnerCounts = [];
    $playersDealt = 0;
    $playersAcquired = 0;
    $picksDealt = 0;
    $picksAcquired = 0;

    foreach ($statsOrder as $id) {
        $trade = $statsByTrade[$id];
        $tradesByYear[$trade['season']] = ($tradesByYear[$trade['season']] ?? 0) + 1;

        $partners = [];
        foreach ($trade['assets'] as $a) {
            if ($a['gave'] !== $team) {
                $partners[$a['gave']] = true;
            }
            if ($a['received'] !== $team) {
                $partners[$a['received']] = true;
            }

            if (!empty($a['pfr_name'])) {
                if ($a['gave'] === $team) $playersDealt++;
                if ($a['received'] === $team) $playersAcquired++;
            } elseif (!empty($a['pick_season'])) {
                if ($a['gave'] === $team) $picksDealt++;
                if ($a['received'] === $team) $picksAcquired++;
            }
        }
        foreach (array_keys($partners) as $p) {
            $partnerCounts[$p] = ($partnerCounts[$p] ?? 0) + 1;
        }
    }

    ksort($tradesByYear);
    arsort($partnerCounts);

    $statsData = [
        'total_trades' => count($statsOrder),
        'trades_by_year' => $tradesByYear,
        'partner_counts' => array_slice($partnerCounts, 0, 10, true),
        'players_dealt' => $playersDealt,
        'players_acquired' => $playersAcquired,
        'picks_dealt' => $picksDealt,
        'picks_acquired' => $picksAcquired,
    ];
}

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

    <?php if ($statsData !== null && $statsData['total_trades'] > 0): ?>
        <div class="section-header blue">
            <h2><?= htmlspecialchars($teamNames[$team] ?? $team) ?> Trade Activity</h2>
            <span class="endpoint-label"><?= number_format($statsData['total_trades']) ?> trade(s)</span>
        </div>
        <div class="section-body">
            <div class="ngs-tile-grid">
                <div class="ngs-tile">
                    <div class="tile-label">Players Acquired</div>
                    <div class="ngs-tile-value"><?= number_format($statsData['players_acquired']) ?></div>
                </div>
                <div class="ngs-tile">
                    <div class="tile-label">Players Dealt</div>
                    <div class="ngs-tile-value"><?= number_format($statsData['players_dealt']) ?></div>
                </div>
                <div class="ngs-tile">
                    <div class="tile-label">Picks Acquired</div>
                    <div class="ngs-tile-value"><?= number_format($statsData['picks_acquired']) ?></div>
                </div>
                <div class="ngs-tile">
                    <div class="tile-label">Picks Dealt</div>
                    <div class="ngs-tile-value"><?= number_format($statsData['picks_dealt']) ?></div>
                </div>
            </div>
            <div class="chart-grid" style="padding: 0 18px 18px;">
                <div class="chart-box">
                    <h3>Trades by Year</h3>
                    <canvas id="chart-trades-by-year"></canvas>
                </div>
                <div class="chart-box">
                    <h3>Most Frequent Trade Partners</h3>
                    <canvas id="chart-most-traded-with"></canvas>
                </div>
            </div>
        </div>
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
                <?php if (count($teamsInTrade) === 2): ?>
                    <?php
                    [$teamA, $teamB] = $teamsInTrade;
                    $receivedA = array_filter($trade['assets'], fn($a) => $a['received'] === $teamA);
                    $receivedB = array_filter($trade['assets'], fn($a) => $a['received'] === $teamB);
                    ?>
                    <div class="trade-columns">
                        <div class="trade-col">
                            <div class="trade-col-header"><?= htmlspecialchars($teamNames[$teamA] ?? $teamA) ?> Receive</div>
                            <ul class="trade-asset-list">
                                <?php if (empty($receivedA)): ?>
                                    <li class="trade-asset-none">Nothing</li>
                                <?php endif; ?>
                                <?php foreach ($receivedA as $a): ?>
                                    <li><?= htmlspecialchars(asset_label($a)) ?></li>
                                <?php endforeach; ?>
                            </ul>
                        </div>
                        <div class="trade-arrow">&#8644;</div>
                        <div class="trade-col">
                            <div class="trade-col-header"><?= htmlspecialchars($teamNames[$teamB] ?? $teamB) ?> Receive</div>
                            <ul class="trade-asset-list">
                                <?php if (empty($receivedB)): ?>
                                    <li class="trade-asset-none">Nothing</li>
                                <?php endif; ?>
                                <?php foreach ($receivedB as $a): ?>
                                    <li><?= htmlspecialchars(asset_label($a)) ?></li>
                                <?php endforeach; ?>
                            </ul>
                        </div>
                    </div>
                <?php else: ?>
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
                <?php endif; ?>
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

<?php if ($statsData !== null && $statsData['total_trades'] > 0): ?>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
        new Chart(document.getElementById('chart-trades-by-year'), {
            type: 'bar',
            data: {
                labels: <?= json_encode(array_map('strval', array_keys($statsData['trades_by_year']))) ?>,
                datasets: [{
                    label: 'Trades',
                    data: <?= json_encode(array_values($statsData['trades_by_year'])) ?>,
                    backgroundColor: 'rgba(91,163,230,0.6)',
                    borderColor: '#5BA3E6',
                    borderWidth: 1,
                }],
            },
            options: {
                responsive: true,
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { color: '#7C90B4' }, grid: { color: 'rgba(120,160,220,0.12)' } },
                    y: { ticks: { color: '#7C90B4', precision: 0 }, grid: { color: 'rgba(120,160,220,0.12)' } },
                },
            },
        });

        new Chart(document.getElementById('chart-most-traded-with'), {
            type: 'bar',
            data: {
                labels: <?= json_encode(array_keys($statsData['partner_counts'])) ?>,
                datasets: [{
                    label: 'Trades',
                    data: <?= json_encode(array_values($statsData['partner_counts'])) ?>,
                    backgroundColor: 'rgba(232,194,90,0.6)',
                    borderColor: '#e8c25a',
                    borderWidth: 1,
                }],
            },
            options: {
                responsive: true,
                indexAxis: 'y',
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { color: '#7C90B4', precision: 0 }, grid: { color: 'rgba(120,160,220,0.12)' } },
                    y: { ticks: { color: '#7C90B4' }, grid: { color: 'rgba(120,160,220,0.12)' } },
                },
            },
        });
    </script>
<?php endif; ?>

<?php require __DIR__ . '/includes/footer.php'; ?>
