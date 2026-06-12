<?php
require_once __DIR__ . '/includes/api.php';

$page_title = 'Draft Pick Value Tracker';
$page_subtitle = 'See how a draft class turned out — career games played and fantasy production by pick.';

$meta = nfl_api_get_cached('/meta', [], 86400);
$seasons = $meta['seasons'] ?? [];
// Draft data goes back further than play-by-play; extend the range.
$draftSeasons = range(max($seasons ?: [2026]), 1980);

$season = trim($_GET['season'] ?? '');
$round = trim($_GET['round'] ?? '1');
$view = trim($_GET['view'] ?? 'class');

$picks = [];
$topByPick = [];

if ($view === 'top' && $round !== '') {
    $topResult = nfl_api_get_cached('/draft/top-by-pick', ['round' => (int) $round, 'limit' => 50], 86400);
    $topByPick = $topResult['data'] ?? [];
}

if ($view === 'class' && $season !== '') {
    $draftResult = nfl_api_get_cached('/draft', ['season' => (int) $season, 'round' => (int) $round, 'limit' => 50]);

    foreach ($draftResult['data'] ?? [] as $pick) {
        $career = ['games' => 0, 'fantasy_points_ppr' => 0.0, 'seasons_played' => 0];

        if (!empty($pick['gsis_id'])) {
            $statsResult = nfl_api_get_cached('/stats/season', ['player_id' => $pick['gsis_id'], 'limit' => 60], 86400);
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

        $picks[] = ['pick' => $pick, 'career' => $career];
    }
}

require __DIR__ . '/includes/header.php';
?>

<div class="site-nav" style="margin-bottom: 20px;">
    <a href="?<?= htmlspecialchars(http_build_query(array_filter(['view' => 'class', 'season' => $season, 'round' => $round]))) ?>" <?= $view === 'class' ? 'style="font-weight:bold; text-decoration:underline;"' : '' ?>>Draft Class by Year</a>
    <a href="?<?= htmlspecialchars(http_build_query(array_filter(['view' => 'top', 'season' => $season, 'round' => $round]))) ?>" <?= $view === 'top' ? 'style="font-weight:bold; text-decoration:underline;"' : '' ?>>Best Player by Pick</a>
</div>

<form method="GET" class="form-section">
    <input type="hidden" name="view" value="<?= htmlspecialchars($view) ?>">
    <?php if ($view === 'class'): ?>
        <div class="form-row">
            <label for="season">Draft year</label>
            <select id="season" name="season">
                <option value="">Select a draft year</option>
                <?php foreach ($draftSeasons as $s): ?>
                    <option value="<?= $s ?>" <?= ((string) $s === $season) ? 'selected' : '' ?>><?= $s ?></option>
                <?php endforeach; ?>
            </select>
        </div>
    <?php endif; ?>
    <div class="form-row">
        <label for="round">Round</label>
        <select id="round" name="round">
            <?php for ($r = 1; $r <= 7; $r++): ?>
                <option value="<?= $r ?>" <?= ((string) $r === $round) ? 'selected' : '' ?>>Round <?= $r ?></option>
            <?php endfor; ?>
        </select>
    </div>
    <button type="submit" class="submit-btn"><?= $view === 'top' ? 'View Best Players by Pick' : 'View Draft Class' ?></button>
</form>

<?php if ($view === 'top'): ?>
    <div class="results-section">
        <?php if (empty($topByPick)): ?>
            <div class="no-results">No draft pick data found for round <?= htmlspecialchars($round) ?>.</div>
        <?php else: ?>
            <h2>Round <?= htmlspecialchars($round) ?> &mdash; Best Player by Pick</h2>
            <p style="color:#666;">
                For each pick number in this round (across all draft years), the player with the most career
                regular-season + playoff PPR fantasy points. "Career" totals reflect seasons in our data (1999+).
            </p>
            <div class="table-wrap">
                <table class="data-table sortable">
                    <thead>
                        <tr>
                            <th>Pick</th>
                            <th>Year</th>
                            <th>Team</th>
                            <th>Player</th>
                            <th>Position</th>
                            <th>College</th>
                            <th>Career Games</th>
                            <th>Career Fantasy Pts (PPR)</th>
                        </tr>
                    </thead>
                    <tbody>
                        <?php foreach ($topByPick as $row): ?>
                            <tr>
                                <td><?= htmlspecialchars((string) $row['pick']) ?></td>
                                <td><?= htmlspecialchars((string) $row['season']) ?></td>
                                <td><?= htmlspecialchars($row['team'] ?? '-') ?></td>
                                <td>
                                    <?php if (!empty($row['gsis_id'])): ?>
                                        <a href="player_explorer.php?gsis_id=<?= urlencode($row['gsis_id']) ?>">
                                            <?= htmlspecialchars($row['player_name'] ?? '-') ?>
                                        </a>
                                    <?php else: ?>
                                        <?= htmlspecialchars($row['player_name'] ?? '-') ?>
                                    <?php endif; ?>
                                </td>
                                <td><?= htmlspecialchars($row['position'] ?? '-') ?></td>
                                <td><?= htmlspecialchars($row['college'] ?? '-') ?></td>
                                <td><?= (int) $row['career_games'] ?></td>
                                <td><?= number_format($row['career_fantasy_points_ppr'], 1) ?></td>
                            </tr>
                        <?php endforeach; ?>
                    </tbody>
                </table>
            </div>

            <h2 style="margin-top:40px;">Career Fantasy Points (PPR) by Pick</h2>
            <div class="chart-grid">
                <div class="chart-box" style="grid-column: 1 / -1;">
                    <canvas id="chart-top-by-pick"></canvas>
                </div>
            </div>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <script>
                new Chart(document.getElementById('chart-top-by-pick'), {
                    type: 'bar',
                    data: {
                        labels: <?= json_encode(array_map(fn($r) => 'Pick ' . $r['pick'], $topByPick)) ?>,
                        datasets: [{
                            label: 'Career Fantasy Pts (PPR)',
                            data: <?= json_encode(array_map(fn($r) => round($r['career_fantasy_points_ppr'], 1), $topByPick)) ?>,
                            backgroundColor: 'rgba(44, 62, 80, 0.6)',
                        }],
                    },
                    options: {
                        responsive: true,
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                callbacks: {
                                    afterLabel: (ctx) => {
                                        const players = <?= json_encode(array_map(fn($r) => $r['player_name'] ?? '-', $topByPick)) ?>;
                                        return players[ctx.dataIndex];
                                    },
                                },
                            },
                        },
                        scales: { x: { ticks: { maxTicksLimit: 16 } } },
                    },
                });
            </script>
        <?php endif; ?>
    </div>
<?php elseif ($season !== ''): ?>
    <div class="results-section">
        <?php if (empty($picks)): ?>
            <div class="no-results">No draft picks found for <?= htmlspecialchars($season) ?>, round <?= htmlspecialchars($round) ?>.</div>
        <?php else: ?>
            <h2><?= htmlspecialchars($season) ?> Draft &mdash; Round <?= htmlspecialchars($round) ?></h2>
            <p style="color:#666;">
                "Career" totals are regular-season + playoff games and PPR fantasy points across all seasons in our data
                (1999+). Players drafted before 1999 or whose careers predate our coverage will show 0.
            </p>
            <div class="table-wrap">
                <table class="data-table sortable">
                    <thead>
                        <tr>
                            <th>Pick</th>
                            <th>Team</th>
                            <th>Player</th>
                            <th>Position</th>
                            <th>College</th>
                            <th>Seasons Played</th>
                            <th>Career Games</th>
                            <th>Career Fantasy Pts (PPR)</th>
                        </tr>
                    </thead>
                    <tbody>
                        <?php foreach ($picks as $p): ?>
                            <?php $pick = $p['pick']; $career = $p['career']; ?>
                            <tr>
                                <td><?= htmlspecialchars((string) $pick['pick']) ?></td>
                                <td><?= htmlspecialchars($pick['team'] ?? '-') ?></td>
                                <td>
                                    <?php if (!empty($pick['gsis_id'])): ?>
                                        <a href="player_explorer.php?gsis_id=<?= urlencode($pick['gsis_id']) ?>">
                                            <?= htmlspecialchars($pick['player_name'] ?? '-') ?>
                                        </a>
                                    <?php else: ?>
                                        <?= htmlspecialchars($pick['player_name'] ?? '-') ?>
                                    <?php endif; ?>
                                </td>
                                <td><?= htmlspecialchars($pick['position'] ?? '-') ?></td>
                                <td><?= htmlspecialchars($pick['college'] ?? '-') ?></td>
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
