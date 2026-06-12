<?php
require_once __DIR__ . '/includes/api.php';

$page_title = 'Head-to-Head Matchup Explorer';
$page_subtitle = 'See how two teams have fared against each other &mdash; results, biggest wins, and top player performances.';

$meta = nfl_api_get_cached('/meta', [], 86400);
$seasons = $meta['seasons'] ?? [];
$teams = $meta['teams'] ?? [];
usort($teams, fn($a, $b) => strcmp($a['abbr'], $b['abbr']));

$team1 = trim($_GET['team1'] ?? '');
$team2 = trim($_GET['team2'] ?? '');
$season = trim($_GET['season'] ?? '');
$gameType = trim($_GET['game_type'] ?? '');
$topN = max(1, min(20, (int) ($_GET['top_n'] ?? 5)));

$gameTypes = ['REG' => 'Regular season', 'WC' => 'Wild Card', 'DIV' => 'Divisional', 'CON' => 'Conference', 'SB' => 'Super Bowl'];

$result = null;
$error = null;

if ($team1 !== '' && $team2 !== '') {
    if ($team1 === $team2) {
        $error = 'Please select two different teams.';
    } else {
        $apiParams = ['team1' => $team1, 'team2' => $team2, 'top_n' => $topN];
        if ($season !== '') {
            $apiParams['season'] = $season;
        }
        if ($gameType !== '') {
            $apiParams['game_type'] = $gameType;
        }
        $result = nfl_api_get('/games/head-to-head', $apiParams);
        if ($result === null || isset($result['detail'])) {
            $error = $result['detail'] ?? 'Unable to load matchup data right now.';
            $result = null;
        }
    }
}

function team_name(array $teams, string $abbr): string {
    foreach ($teams as $t) {
        if ($t['abbr'] === $abbr) {
            return $t['name'];
        }
    }
    return $abbr;
}

function stat_table_rows(array $rows, string $yardsCol, string $tdsCol, bool $withGames): string {
    if (empty($rows)) {
        return '<p class="no-results">No data.</p>';
    }
    $html = '<table class="data-table sortable"><thead><tr><th>Player</th><th>Team</th>';
    if ($withGames) {
        $html .= '<th>Games</th>';
    } else {
        $html .= '<th>Season</th><th>Week</th>';
    }
    $html .= '<th>Yards</th><th>TDs</th></tr></thead><tbody>';
    foreach ($rows as $row) {
        $html .= '<tr>';
        $html .= '<td>' . htmlspecialchars($row['player_name'] ?? '') . '</td>';
        $html .= '<td>' . htmlspecialchars($row['recent_team'] ?? '') . '</td>';
        if ($withGames) {
            $html .= '<td>' . htmlspecialchars((string) ($row['games'] ?? '')) . '</td>';
        } else {
            $html .= '<td>' . htmlspecialchars((string) ($row['season'] ?? '')) . '</td>';
            $html .= '<td>' . htmlspecialchars((string) ($row['week'] ?? '')) . '</td>';
        }
        $html .= '<td>' . htmlspecialchars((string) ($row[$yardsCol] ?? 0)) . '</td>';
        $html .= '<td>' . htmlspecialchars((string) ($row[$tdsCol] ?? 0)) . '</td>';
        $html .= '</tr>';
    }
    $html .= '</tbody></table>';
    return $html;
}

require __DIR__ . '/includes/header.php';
?>

<form method="GET" class="form-section">
    <div class="form-row">
        <label for="team1">Team 1</label>
        <select id="team1" name="team1">
            <option value="">Select a team</option>
            <?php foreach ($teams as $t): ?>
                <option value="<?= htmlspecialchars($t['abbr']) ?>" <?= ($t['abbr'] === $team1) ? 'selected' : '' ?>>
                    <?= htmlspecialchars($t['name']) ?>
                </option>
            <?php endforeach; ?>
        </select>
    </div>
    <div class="form-row">
        <label for="team2">Team 2</label>
        <select id="team2" name="team2">
            <option value="">Select a team</option>
            <?php foreach ($teams as $t): ?>
                <option value="<?= htmlspecialchars($t['abbr']) ?>" <?= ($t['abbr'] === $team2) ? 'selected' : '' ?>>
                    <?= htmlspecialchars($t['name']) ?>
                </option>
            <?php endforeach; ?>
        </select>
    </div>
    <div class="form-row">
        <label for="season">Season (optional)</label>
        <select id="season" name="season">
            <option value="">All seasons</option>
            <?php foreach (array_reverse($seasons) as $s): ?>
                <option value="<?= htmlspecialchars((string) $s) ?>" <?= ((string) $s === $season) ? 'selected' : '' ?>>
                    <?= htmlspecialchars((string) $s) ?>
                </option>
            <?php endforeach; ?>
        </select>
    </div>
    <div class="form-row">
        <label for="game_type">Game type (optional)</label>
        <select id="game_type" name="game_type">
            <option value="">All game types</option>
            <?php foreach ($gameTypes as $code => $label): ?>
                <option value="<?= htmlspecialchars($code) ?>" <?= ($code === $gameType) ? 'selected' : '' ?>>
                    <?= htmlspecialchars($label) ?>
                </option>
            <?php endforeach; ?>
        </select>
    </div>
    <div class="form-row">
        <label for="top_n">Top performances to show</label>
        <input type="number" id="top_n" name="top_n" min="1" max="20" value="<?= htmlspecialchars((string) $topN) ?>">
    </div>
    <button type="submit" class="submit-btn">Compare</button>
</form>

<div class="results-section">
<?php if ($error !== null): ?>
    <div class="error"><?= htmlspecialchars($error) ?></div>
<?php elseif ($result === null): ?>
    <div class="info">Select two teams to see their head-to-head history.</div>
<?php elseif ($result['total_games'] === 0): ?>
    <div class="no-results">No games found between <?= htmlspecialchars(team_name($teams, $team1)) ?> and <?= htmlspecialchars(team_name($teams, $team2)) ?> matching these filters.</div>
<?php else: ?>
    <?php
    $t1 = $team1;
    $t2 = $team2;
    $rec = $result['record'];
    $home = $result['home_record'];
    $bigWin = $result['biggest_win'];
    ?>
    <h2><?= htmlspecialchars(team_name($teams, $t1)) ?> vs <?= htmlspecialchars(team_name($teams, $t2)) ?></h2>
    <p><?= number_format($result['total_games']) ?> game(s) found.</p>

    <div class="chart-grid">
        <div class="chart-box">
            <h3>Overall record</h3>
            <table class="data-table">
                <thead><tr><th>Team</th><th>W</th><th>L</th><th>T</th></tr></thead>
                <tbody>
                    <tr><td><?= htmlspecialchars($t1) ?></td><td><?= $rec[$t1]['wins'] ?></td><td><?= $rec[$t1]['losses'] ?></td><td><?= $rec[$t1]['ties'] ?></td></tr>
                    <tr><td><?= htmlspecialchars($t2) ?></td><td><?= $rec[$t2]['wins'] ?></td><td><?= $rec[$t2]['losses'] ?></td><td><?= $rec[$t2]['ties'] ?></td></tr>
                </tbody>
            </table>
        </div>
        <div class="chart-box">
            <h3>Record at home (vs this opponent)</h3>
            <table class="data-table">
                <thead><tr><th>Team</th><th>W</th><th>L</th><th>T</th></tr></thead>
                <tbody>
                    <tr><td><?= htmlspecialchars($t1) ?></td><td><?= $home[$t1]['wins'] ?></td><td><?= $home[$t1]['losses'] ?></td><td><?= $home[$t1]['ties'] ?></td></tr>
                    <tr><td><?= htmlspecialchars($t2) ?></td><td><?= $home[$t2]['wins'] ?></td><td><?= $home[$t2]['losses'] ?></td><td><?= $home[$t2]['ties'] ?></td></tr>
                </tbody>
            </table>
        </div>
        <div class="chart-box">
            <h3>Biggest win &mdash; <?= htmlspecialchars($t1) ?></h3>
            <?php if ($bigWin[$t1]): ?>
                <p>
                    <?= htmlspecialchars($bigWin[$t1]['score']) ?> vs <?= htmlspecialchars($bigWin[$t1]['opponent']) ?>
                    (margin of <?= $bigWin[$t1]['margin'] ?>)<br>
                    Season <?= htmlspecialchars((string) $bigWin[$t1]['season']) ?>, Week <?= htmlspecialchars((string) $bigWin[$t1]['week']) ?>
                    &mdash; <?= htmlspecialchars((string) $bigWin[$t1]['gameday']) ?><br>
                    <a href="play_explorer.php?season=<?= urlencode((string) $bigWin[$t1]['season']) ?>&game_id=<?= urlencode($bigWin[$t1]['game_id']) ?>">View plays</a>
                </p>
            <?php else: ?>
                <p class="no-results">No wins in this matchup.</p>
            <?php endif; ?>
        </div>
        <div class="chart-box">
            <h3>Biggest win &mdash; <?= htmlspecialchars($t2) ?></h3>
            <?php if ($bigWin[$t2]): ?>
                <p>
                    <?= htmlspecialchars($bigWin[$t2]['score']) ?> vs <?= htmlspecialchars($bigWin[$t2]['opponent']) ?>
                    (margin of <?= $bigWin[$t2]['margin'] ?>)<br>
                    Season <?= htmlspecialchars((string) $bigWin[$t2]['season']) ?>, Week <?= htmlspecialchars((string) $bigWin[$t2]['week']) ?>
                    &mdash; <?= htmlspecialchars((string) $bigWin[$t2]['gameday']) ?><br>
                    <a href="play_explorer.php?season=<?= urlencode((string) $bigWin[$t2]['season']) ?>&game_id=<?= urlencode($bigWin[$t2]['game_id']) ?>">View plays</a>
                </p>
            <?php else: ?>
                <p class="no-results">No wins in this matchup.</p>
            <?php endif; ?>
        </div>
    </div>

    <h3>Game history</h3>
    <div class="table-wrap">
        <table class="data-table sortable">
            <thead><tr><th>Season</th><th>Week</th><th>Type</th><th>Date</th><th>Home</th><th>Away</th><th>Score</th><th>Plays</th></tr></thead>
            <tbody>
                <?php foreach ($result['games'] as $g): ?>
                    <tr>
                        <td><?= htmlspecialchars((string) $g['season']) ?></td>
                        <td><?= htmlspecialchars((string) $g['week']) ?></td>
                        <td><?= htmlspecialchars((string) $g['game_type']) ?></td>
                        <td><?= htmlspecialchars((string) $g['gameday']) ?></td>
                        <td><?= htmlspecialchars((string) $g['home_team']) ?></td>
                        <td><?= htmlspecialchars((string) $g['away_team']) ?></td>
                        <td>
                            <?php if ($g['home_score'] !== null && $g['away_score'] !== null): ?>
                                <?= htmlspecialchars((string) $g['home_score']) ?> - <?= htmlspecialchars((string) $g['away_score']) ?>
                            <?php else: ?>
                                &mdash;
                            <?php endif; ?>
                        </td>
                        <td><a href="play_explorer.php?season=<?= urlencode((string) $g['season']) ?>&game_id=<?= urlencode($g['game_id']) ?>">View</a></td>
                    </tr>
                <?php endforeach; ?>
            </tbody>
        </table>
    </div>

    <h3>Top single-game performances</h3>
    <div class="chart-grid">
        <div class="chart-box">
            <h3>Passing</h3>
            <?= stat_table_rows($result['top_performances']['passing'], 'passing_yards', 'passing_tds', false) ?>
        </div>
        <div class="chart-box">
            <h3>Rushing</h3>
            <?= stat_table_rows($result['top_performances']['rushing'], 'rushing_yards', 'rushing_tds', false) ?>
        </div>
        <div class="chart-box">
            <h3>Receiving</h3>
            <?= stat_table_rows($result['top_performances']['receiving'], 'receiving_yards', 'receiving_tds', false) ?>
        </div>
    </div>

    <h3>Career totals vs. this opponent</h3>
    <div class="chart-grid">
        <div class="chart-box">
            <h3>Passing</h3>
            <?= stat_table_rows($result['career_totals']['passing'], 'passing_yards', 'passing_tds', true) ?>
        </div>
        <div class="chart-box">
            <h3>Rushing</h3>
            <?= stat_table_rows($result['career_totals']['rushing'], 'rushing_yards', 'rushing_tds', true) ?>
        </div>
        <div class="chart-box">
            <h3>Receiving</h3>
            <?= stat_table_rows($result['career_totals']['receiving'], 'receiving_yards', 'receiving_tds', true) ?>
        </div>
    </div>
<?php endif; ?>
</div>

<?php require __DIR__ . '/includes/footer.php'; ?>
