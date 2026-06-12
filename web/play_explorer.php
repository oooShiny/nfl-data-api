<?php
require_once __DIR__ . '/includes/api.php';

$page_title = 'Drive & Play Explorer';
$page_subtitle = 'Pick a game to see every play with EPA/WPA and play-design tags (2022+).';

$meta = nfl_api_get('/meta');
$seasons = $meta['seasons'] ?? [];
$teams = $meta['teams'] ?? [];

$season = trim($_GET['season'] ?? '');
$team = trim($_GET['team'] ?? '');
$gameId = trim($_GET['game_id'] ?? '');

if ($season === '' && !empty($seasons)) {
    $season = (string) max($seasons);
}

$games = null;
$game = null;
$plays = null;
$chartingByPlay = [];

if ($gameId !== '') {
    $game = nfl_api_get('/games/' . urlencode($gameId));

    $playsResult = nfl_api_get('/plays', ['game_id' => $gameId, 'limit' => 500]);
    $plays = $playsResult['data'] ?? [];

    $chartingResult = nfl_api_get('/charting', ['game_id' => $gameId, 'limit' => 500]);
    foreach ($chartingResult['data'] ?? [] as $c) {
        $chartingByPlay[$c['play_id']] = $c;
    }
} elseif ($season !== '') {
    $games = nfl_api_get('/games', array_filter([
        'season' => (int) $season,
        'team' => $team !== '' ? $team : null,
        'limit' => 300,
    ]));
}

function fmt($value): string {
    if ($value === null) {
        return '-';
    }
    if (is_float($value)) {
        return number_format($value, 2);
    }
    if (is_bool($value)) {
        return $value ? 'Yes' : '';
    }
    return htmlspecialchars((string) $value);
}

/** Tags from the charting row that are worth highlighting. */
function charting_tags(?array $c): string {
    if ($c === null) {
        return '';
    }
    $tags = [
        'is_motion' => 'Motion',
        'is_play_action' => 'Play-Action',
        'is_screen_pass' => 'Screen',
        'is_rpo' => 'RPO',
        'is_no_huddle' => 'No Huddle',
        'is_trick_play' => 'Trick Play',
        'is_qb_out_of_pocket' => 'QB Out of Pocket',
    ];
    $out = [];
    foreach ($tags as $key => $label) {
        if (!empty($c[$key])) {
            $out[] = $label;
        }
    }
    if (!empty($c['n_blitzers'])) {
        $out[] = $c['n_blitzers'] . ' Blitzer' . ($c['n_blitzers'] > 1 ? 's' : '');
    }
    return htmlspecialchars(implode(', ', $out));
}

require __DIR__ . '/includes/header.php';
?>

<form method="GET" class="form-section">
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
    <div class="form-row">
        <label for="team">Team (optional)</label>
        <select id="team" name="team">
            <option value="">All teams</option>
            <?php foreach ($teams as $t): ?>
                <option value="<?= htmlspecialchars($t['abbr']) ?>" <?= ($t['abbr'] === $team) ? 'selected' : '' ?>>
                    <?= htmlspecialchars($t['name']) ?>
                </option>
            <?php endforeach; ?>
        </select>
    </div>
    <button type="submit" class="submit-btn">Find Games</button>
</form>

<?php if ($games !== null): ?>
    <div class="results-section">
        <?php if (empty($games['data'])): ?>
            <div class="no-results">No games found.</div>
        <?php else: ?>
            <div class="table-wrap">
                <table class="data-table sortable">
                    <thead>
                        <tr>
                            <th>Week</th>
                            <th>Date</th>
                            <th>Matchup</th>
                            <th>Score</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>
                        <?php foreach ($games['data'] as $g): ?>
                            <tr>
                                <td><?= htmlspecialchars((string) $g['week']) ?> (<?= htmlspecialchars($g['game_type']) ?>)</td>
                                <td><?= htmlspecialchars($g['gameday'] ?? '-') ?></td>
                                <td><?= htmlspecialchars($g['away_team']) ?> @ <?= htmlspecialchars($g['home_team']) ?></td>
                                <td><?= htmlspecialchars((string) ($g['away_score'] ?? '-')) ?> - <?= htmlspecialchars((string) ($g['home_score'] ?? '-')) ?></td>
                                <td><a href="?season=<?= urlencode($season) ?>&game_id=<?= urlencode($g['game_id']) ?>">View plays</a></td>
                            </tr>
                        <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
        <?php endif; ?>
    </div>
<?php endif; ?>

<?php if ($gameId !== ''): ?>
    <div class="results-section">
        <?php if ($game === null): ?>
            <div class="error">Game not found.</div>
        <?php else: ?>
            <div class="result-item">
                <div class="result-header">
                    Week <?= htmlspecialchars((string) $game['week']) ?> (<?= htmlspecialchars($game['game_type']) ?>):
                    <?= htmlspecialchars($game['away_team']) ?> <?= htmlspecialchars((string) $game['away_score']) ?>
                    @ <?= htmlspecialchars($game['home_team']) ?> <?= htmlspecialchars((string) $game['home_score']) ?>
                    (<?= htmlspecialchars($game['gameday'] ?? '') ?>)
                </div>
            </div>

            <?php if (empty($plays)): ?>
                <div class="no-results">No play-by-play data available for this game.</div>
            <?php else: ?>
                <div class="table-wrap">
                    <table class="data-table sortable">
                        <thead>
                            <tr>
                                <th>Q</th>
                                <th>Down</th>
                                <th>To Go</th>
                                <th>Yard Line</th>
                                <th>Pos</th>
                                <th>Type</th>
                                <th>Yards</th>
                                <th>EPA</th>
                                <th>WPA</th>
                                <th>Tags</th>
                            </tr>
                        </thead>
                        <tbody>
                            <?php foreach ($plays as $p): ?>
                                <?php
                                $rowClass = '';
                                if (!empty($p['touchdown'])) {
                                    $rowClass = 'win';
                                }
                                ?>
                                <tr class="<?= $rowClass ?>">
                                    <td><?= fmt($p['quarter']) ?></td>
                                    <td><?= fmt($p['down']) ?></td>
                                    <td><?= fmt($p['ydstogo']) ?></td>
                                    <td><?= fmt($p['yardline_100']) ?></td>
                                    <td><?= fmt($p['posteam']) ?></td>
                                    <td><?= fmt($p['play_type']) ?></td>
                                    <td><?= fmt($p['yards_gained']) ?></td>
                                    <td><?= fmt($p['epa']) ?></td>
                                    <td><?= fmt($p['wpa']) ?></td>
                                    <td><?= charting_tags($chartingByPlay[$p['play_id']] ?? null) ?></td>
                                </tr>
                            <?php endforeach; ?>
                        </tbody>
                    </table>
                </div>
            <?php endif; ?>
        <?php endif; ?>
    </div>
<?php endif; ?>

<?php require __DIR__ . '/includes/footer.php'; ?>
