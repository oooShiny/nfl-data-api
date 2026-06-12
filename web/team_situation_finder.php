<?php
require_once __DIR__ . '/includes/api.php';

$page_title = 'Team Situation Finder';
$page_subtitle = 'Find games matching specific situations for a team — blowouts, comebacks, shootouts, and more.';

$meta = nfl_api_get('/meta');
$seasons = $meta['seasons'] ?? [];
$teams = $meta['teams'] ?? [];

$team = trim($_GET['team'] ?? '');
$season = trim($_GET['season'] ?? '');
$result = trim($_GET['result'] ?? 'any');
$location = trim($_GET['location'] ?? 'any');
$minMargin = trim($_GET['min_margin'] ?? '');
$minPoints = trim($_GET['min_points'] ?? '');
$minTotal = trim($_GET['min_total'] ?? '');
$overtimeOnly = isset($_GET['overtime_only']);
$divGameOnly = isset($_GET['div_game_only']);
$submitted = isset($_GET['team']) && $team !== '';

$matches = [];

if ($submitted) {
    $seasonsToSearch = $season !== '' ? [(int) $season] : array_reverse($seasons);

    foreach ($seasonsToSearch as $s) {
        $gamesResult = nfl_api_get('/games', ['team' => $team, 'season' => $s, 'limit' => 50]);
        foreach ($gamesResult['data'] ?? [] as $g) {
            if ($g['home_score'] === null || $g['away_score'] === null) {
                continue;
            }

            $isHome = $g['home_team'] === $team;
            $teamScore = $isHome ? $g['home_score'] : $g['away_score'];
            $oppScore = $isHome ? $g['away_score'] : $g['home_score'];
            $opponent = $isHome ? $g['away_team'] : $g['home_team'];
            $margin = $teamScore - $oppScore;
            $total = $teamScore + $oppScore;

            $gameResult = $margin > 0 ? 'win' : ($margin < 0 ? 'loss' : 'tie');

            if ($result !== 'any' && $gameResult !== $result) {
                continue;
            }
            if ($location === 'home' && !$isHome) {
                continue;
            }
            if ($location === 'away' && $isHome) {
                continue;
            }
            if ($minMargin !== '' && $margin < (int) $minMargin) {
                continue;
            }
            if ($minPoints !== '' && $teamScore < (int) $minPoints) {
                continue;
            }
            if ($minTotal !== '' && $total < (int) $minTotal) {
                continue;
            }
            if ($overtimeOnly && empty($g['overtime'])) {
                continue;
            }
            if ($divGameOnly && empty($g['div_game'])) {
                continue;
            }

            $matches[] = [
                'game' => $g,
                'is_home' => $isHome,
                'team_score' => $teamScore,
                'opp_score' => $oppScore,
                'opponent' => $opponent,
                'margin' => $margin,
                'result' => $gameResult,
            ];
        }
    }

    usort($matches, function ($a, $b) {
        return [$b['game']['season'], $b['game']['week']] <=> [$a['game']['season'], $a['game']['week']];
    });
}

require __DIR__ . '/includes/header.php';
?>

<form method="GET" class="form-section">
    <div class="form-row">
        <label for="team">Team</label>
        <select id="team" name="team" required>
            <option value="">Select a team</option>
            <?php foreach ($teams as $t): ?>
                <option value="<?= htmlspecialchars($t['abbr']) ?>" <?= ($t['abbr'] === $team) ? 'selected' : '' ?>>
                    <?= htmlspecialchars($t['name']) ?>
                </option>
            <?php endforeach; ?>
        </select>
    </div>
    <div class="form-row">
        <label for="season">Season</label>
        <select id="season" name="season">
            <option value="">All seasons (1999+)</option>
            <?php foreach (array_reverse($seasons) as $s): ?>
                <option value="<?= htmlspecialchars((string) $s) ?>" <?= ((string) $s === $season) ? 'selected' : '' ?>>
                    <?= htmlspecialchars((string) $s) ?>
                </option>
            <?php endforeach; ?>
        </select>
    </div>
    <div class="form-row">
        <label for="result">Result</label>
        <select id="result" name="result">
            <option value="any" <?= $result === 'any' ? 'selected' : '' ?>>Any</option>
            <option value="win" <?= $result === 'win' ? 'selected' : '' ?>>Win</option>
            <option value="loss" <?= $result === 'loss' ? 'selected' : '' ?>>Loss</option>
            <option value="tie" <?= $result === 'tie' ? 'selected' : '' ?>>Tie</option>
        </select>
    </div>
    <div class="form-row">
        <label for="location">Location</label>
        <select id="location" name="location">
            <option value="any" <?= $location === 'any' ? 'selected' : '' ?>>Any</option>
            <option value="home" <?= $location === 'home' ? 'selected' : '' ?>>Home</option>
            <option value="away" <?= $location === 'away' ? 'selected' : '' ?>>Away</option>
        </select>
    </div>
    <div class="form-row">
        <label for="min_margin">Minimum margin of victory (e.g. 14 for "won by 14+")</label>
        <input type="number" id="min_margin" name="min_margin" value="<?= htmlspecialchars($minMargin) ?>">
    </div>
    <div class="form-row">
        <label for="min_points">Minimum points scored by this team</label>
        <input type="number" id="min_points" name="min_points" value="<?= htmlspecialchars($minPoints) ?>">
    </div>
    <div class="form-row">
        <label for="min_total">Minimum combined score (shootout finder)</label>
        <input type="number" id="min_total" name="min_total" value="<?= htmlspecialchars($minTotal) ?>">
    </div>
    <div class="form-row">
        <label><input type="checkbox" name="overtime_only" <?= $overtimeOnly ? 'checked' : '' ?>> Overtime games only</label>
    </div>
    <div class="form-row">
        <label><input type="checkbox" name="div_game_only" <?= $divGameOnly ? 'checked' : '' ?>> Division games only</label>
    </div>
    <button type="submit" class="submit-btn">Find Games</button>
</form>

<?php if ($submitted): ?>
    <div class="results-section">
        <?php if (empty($matches)): ?>
            <div class="no-results">No games found matching these criteria.</div>
        <?php else: ?>
            <h2>Found <?= count($matches) ?> game(s)</h2>
            <div class="table-wrap">
                <table class="data-table sortable">
                    <thead>
                        <tr>
                            <th>Season</th>
                            <th>Week</th>
                            <th>Date</th>
                            <th>Opponent</th>
                            <th>Location</th>
                            <th>Score</th>
                            <th>Result</th>
                            <th>Margin</th>
                        </tr>
                    </thead>
                    <tbody>
                        <?php foreach ($matches as $m): ?>
                            <?php $g = $m['game']; ?>
                            <tr class="<?= $m['result'] === 'win' ? 'win' : '' ?>">
                                <td><?= htmlspecialchars((string) $g['season']) ?></td>
                                <td><?= htmlspecialchars((string) $g['week']) ?> (<?= htmlspecialchars($g['game_type']) ?>)</td>
                                <td><?= htmlspecialchars($g['gameday'] ?? '-') ?></td>
                                <td><?= $m['is_home'] ? 'vs' : '@' ?> <?= htmlspecialchars($m['opponent']) ?></td>
                                <td><?= $m['is_home'] ? 'Home' : 'Away' ?></td>
                                <td><?= htmlspecialchars((string) $m['team_score']) ?> - <?= htmlspecialchars((string) $m['opp_score']) ?></td>
                                <td><?= ucfirst($m['result']) ?><?= !empty($g['overtime']) ? ' (OT)' : '' ?></td>
                                <td><?= $m['margin'] > 0 ? '+' : '' ?><?= htmlspecialchars((string) $m['margin']) ?></td>
                            </tr>
                        <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
        <?php endif; ?>
    </div>
<?php endif; ?>

<?php require __DIR__ . '/includes/footer.php'; ?>
