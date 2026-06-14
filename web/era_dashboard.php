<?php
require_once __DIR__ . '/includes/api.php';

$page_title = 'Era Comparison Dashboard';
$page_subtitle = 'League-wide trends by season since 1999: scoring, pass rate, and efficiency.';

$meta = nfl_api_get_cached('/meta', [], 86400);
$seasons = $meta['seasons'] ?? [];

$rows = [];

foreach ($seasons as $season) {
    if ($season < 1999) {
        continue;
    }

    $teamStats = nfl_api_get_cached('/stats/team', ['season' => $season, 'season_type' => 'REG', 'limit' => 40]);
    $games = nfl_api_get_cached('/games', ['season' => $season, 'game_type' => 'REG', 'limit' => 300]);

    if (empty($teamStats['data']) || empty($games['data'])) {
        continue;
    }

    $totalAttempts = 0;
    $totalCarries = 0;
    $totalPassYards = 0;
    $totalSacks = 0;
    $totalPassEpa = 0.0;
    $totalRushEpa = 0.0;

    foreach ($teamStats['data'] as $t) {
        $totalAttempts += $t['attempts'] ?? 0;
        $totalCarries += $t['carries'] ?? 0;
        $totalPassYards += $t['passing_yards'] ?? 0;
        $totalSacks += $t['sacks_suffered'] ?? 0;
        $totalPassEpa += $t['passing_epa'] ?? 0.0;
        $totalRushEpa += $t['rushing_epa'] ?? 0.0;
    }

    $totalPoints = 0;
    $gameCount = 0;
    foreach ($games['data'] as $g) {
        if ($g['home_score'] === null || $g['away_score'] === null) {
            continue;
        }
        $totalPoints += $g['home_score'] + $g['away_score'];
        $gameCount++;
    }

    if ($gameCount === 0 || ($totalAttempts + $totalCarries) === 0) {
        continue;
    }

    $rows[] = [
        'season' => $season,
        'avg_points' => $totalPoints / ($gameCount * 2),
        'pass_rate' => $totalAttempts / ($totalAttempts + $totalCarries) * 100,
        'yards_per_attempt' => $totalAttempts > 0 ? $totalPassYards / $totalAttempts : 0,
        'sack_rate' => ($totalAttempts + $totalSacks) > 0 ? $totalSacks / ($totalAttempts + $totalSacks) * 100 : 0,
        'epa_per_play' => ($totalAttempts + $totalCarries) > 0
            ? ($totalPassEpa + $totalRushEpa) / ($totalAttempts + $totalCarries)
            : 0,
    ];
}

usort($rows, fn($a, $b) => $b['season'] <=> $a['season']);

// Min/max per metric, used to color-code each cell relative to all other eras.
$metrics = ['avg_points', 'pass_rate', 'yards_per_attempt', 'sack_rate', 'epa_per_play'];
$ranges = [];
foreach ($metrics as $m) {
    $values = array_column($rows, $m);
    $ranges[$m] = ['min' => !empty($values) ? min($values) : 0, 'max' => !empty($values) ? max($values) : 1];
}

/**
 * Background color for a table cell, on a blue (low) -> red (high) scale
 * relative to the range of that metric across all displayed eras.
 */
function heat_color(float $value, array $range): string {
    $min = $range['min'];
    $max = $range['max'];
    if ($max <= $min) {
        return '';
    }
    $pct = ($value - $min) / ($max - $min);
    $r = (int) round(120 + 135 * $pct);
    $g = (int) round(120 + 60 * (1 - abs($pct - 0.5) * 2));
    $b = (int) round(255 - 135 * $pct);
    return "background-color: rgba($r, $g, $b, 0.35);";
}

// Chart data, oldest-to-newest for a natural left-to-right timeline.
$chartRows = array_reverse($rows);
$chartLabels = array_column($chartRows, 'season');

// KPI tiles: latest season value + change vs. earliest season shown.
$kpiDefs = [];
if (!empty($rows)) {
    $latest = $rows[0];
    $earliest = $rows[count($rows) - 1];
    $kpiDefs = [
        ['label' => 'Points / Game', 'value' => number_format($latest['avg_points'], 1), 'unit' => '', 'delta' => number_format($latest['avg_points'] - $earliest['avg_points'], 1)],
        ['label' => 'Pass Rate', 'value' => number_format($latest['pass_rate'], 1), 'unit' => '%', 'delta' => number_format($latest['pass_rate'] - $earliest['pass_rate'], 1)],
        ['label' => 'Yards / Attempt', 'value' => number_format($latest['yards_per_attempt'], 2), 'unit' => '', 'delta' => number_format($latest['yards_per_attempt'] - $earliest['yards_per_attempt'], 2)],
        ['label' => 'EPA / Play', 'value' => number_format($latest['epa_per_play'], 3), 'unit' => '', 'delta' => number_format($latest['epa_per_play'] - $earliest['epa_per_play'], 3)],
    ];

    $ticker_items = [
        'ERA SPAN: ' . $earliest['season'] . '&ndash;' . $latest['season'],
        'POINTS/GAME ' . $earliest['season'] . ': ' . number_format($earliest['avg_points'], 1) . ' &rarr; ' . $latest['season'] . ': ' . number_format($latest['avg_points'], 1),
        'PASS RATE ' . $earliest['season'] . ': ' . number_format($earliest['pass_rate'], 1) . '% &rarr; ' . $latest['season'] . ': ' . number_format($latest['pass_rate'], 1) . '%',
        'ONE SCHEMA ACROSS ' . count($rows) . ' SEASONS',
    ];
}

require __DIR__ . '/includes/header.php';
?>

<?php if (empty($rows)): ?>
    <div class="no-results">
        Era data is not available yet. This view depends on REG season-total team stats
        (<code>ref_team_stats</code>), which may still be propagating to the live API.
    </div>
<?php else: ?>
    <div class="kpi-tiles">
        <?php foreach ($kpiDefs as $k): ?>
            <div class="kpi-tile">
                <div class="tile-label"><?= htmlspecialchars($k['label']) ?></div>
                <div class="kpi-tile-value"><?= htmlspecialchars($k['value']) ?><span class="unit"><?= htmlspecialchars($k['unit']) ?></span></div>
                <div class="kpi-tile-delta">&#9650; <?= htmlspecialchars($k['delta']) ?> <span class="since">vs <?= htmlspecialchars((string) $earliest['season']) ?></span></div>
            </div>
        <?php endforeach; ?>
    </div>

    <div class="section-header blue">
        <h2>Trends Over Time</h2>
        <span class="endpoint-label">GET /v1/stats/team</span>
    </div>
    <div class="page-pinstripe"></div>
    <div class="section-body" style="padding: 18px;">
        <div class="chart-grid">
            <div class="chart-box">
                <h3>Avg Points / Team / Game</h3>
                <canvas id="chart-avg_points"></canvas>
            </div>
            <div class="chart-box">
                <h3>Pass Rate (%)</h3>
                <canvas id="chart-pass_rate"></canvas>
            </div>
            <div class="chart-box">
                <h3>Yards / Attempt</h3>
                <canvas id="chart-yards_per_attempt"></canvas>
            </div>
            <div class="chart-box">
                <h3>Sack Rate (%)</h3>
                <canvas id="chart-sack_rate"></canvas>
            </div>
            <div class="chart-box">
                <h3>EPA / Play</h3>
                <canvas id="chart-epa_per_play"></canvas>
            </div>
        </div>
    </div>

    <div class="section-header red">
        <h2>Season Detail</h2>
        <span class="endpoint-label">Heat-mapped vs. range shown</span>
    </div>
    <div class="page-pinstripe"></div>
    <div class="section-body">
        <div class="table-wrap">
            <table class="data-table sortable">
                <thead>
                    <tr>
                        <th>Season</th>
                        <th>Avg Points/Team/Game</th>
                        <th>Pass Rate</th>
                        <th>Yards/Attempt</th>
                        <th>Sack Rate</th>
                        <th>EPA/Play</th>
                    </tr>
                </thead>
                <tbody>
                    <?php foreach ($rows as $r): ?>
                        <tr>
                            <td><?= htmlspecialchars((string) $r['season']) ?></td>
                            <td style="<?= heat_color($r['avg_points'], $ranges['avg_points']) ?>"><?= number_format($r['avg_points'], 1) ?></td>
                            <td style="<?= heat_color($r['pass_rate'], $ranges['pass_rate']) ?>"><?= number_format($r['pass_rate'], 1) ?>%</td>
                            <td style="<?= heat_color($r['yards_per_attempt'], $ranges['yards_per_attempt']) ?>"><?= number_format($r['yards_per_attempt'], 2) ?></td>
                            <td style="<?= heat_color($r['sack_rate'], $ranges['sack_rate']) ?>"><?= number_format($r['sack_rate'], 1) ?>%</td>
                            <td style="<?= heat_color($r['epa_per_play'], $ranges['epa_per_play']) ?>"><?= number_format($r['epa_per_play'], 3) ?></td>
                        </tr>
                    <?php endforeach; ?>
                </tbody>
            </table>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
        const eraLabels = <?= json_encode($chartLabels) ?>;
        const eraCharts = {
            avg_points: { label: 'Avg Points', data: <?= json_encode(array_column($chartRows, 'avg_points')) ?> },
            pass_rate: { label: 'Pass Rate %', data: <?= json_encode(array_column($chartRows, 'pass_rate')) ?> },
            yards_per_attempt: { label: 'Yards/Attempt', data: <?= json_encode(array_column($chartRows, 'yards_per_attempt')) ?> },
            sack_rate: { label: 'Sack Rate %', data: <?= json_encode(array_column($chartRows, 'sack_rate')) ?> },
            epa_per_play: { label: 'EPA/Play', data: <?= json_encode(array_column($chartRows, 'epa_per_play')) ?> },
        };

        Object.keys(eraCharts).forEach((key) => {
            const cfg = eraCharts[key];
            new Chart(document.getElementById('chart-' + key), {
                type: 'line',
                data: {
                    labels: eraLabels,
                    datasets: [{
                        label: cfg.label,
                        data: cfg.data,
                        borderColor: '#e8c25a',
                        backgroundColor: 'rgba(232,194,90,0.15)',
                        tension: 0.2,
                        fill: true,
                        pointRadius: 2,
                        pointBackgroundColor: '#e8c25a',
                    }],
                },
                options: {
                    responsive: true,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: {
                            ticks: { maxTicksLimit: 10, color: '#7C90B4' },
                            grid: { color: 'rgba(120,160,220,0.12)' },
                        },
                        y: {
                            ticks: { color: '#7C90B4' },
                            grid: { color: 'rgba(120,160,220,0.12)' },
                        },
                    },
                },
            });
        });
    </script>
<?php endif; ?>

<?php require __DIR__ . '/includes/footer.php'; ?>
