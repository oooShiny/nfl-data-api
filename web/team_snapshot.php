<?php
require_once __DIR__ . '/includes/api.php';

$page_title = 'Team Cap & Roster Snapshot';
$page_subtitle = 'Biggest contracts and roster makeup for a team, by season.';

$meta = nfl_api_get_cached('/meta', [], 86400);
$teams = $meta['teams'] ?? [];

$team = trim($_GET['team'] ?? '');
$season = trim($_GET['season'] ?? '');

$teamInfo = null;
$contractTeamName = null;
$topContracts = [];
$rosterSeasons = [];
$roster = [];

if ($team !== '') {
    foreach ($teams as $t) {
        if ($t['abbr'] === $team) {
            $teamInfo = $t;
            break;
        }
    }

    if ($teamInfo) {
        // ref_contracts stores teams by nickname (e.g. "Chiefs"), not abbreviation.
        $nameParts = explode(' ', $teamInfo['name']);
        $contractTeamName = end($nameParts);

        $contractsResult = nfl_api_get_cached('/contracts', ['team' => $contractTeamName, 'limit' => 15]);
        $topContracts = $contractsResult['data'] ?? [];

        // Discover which seasons of roster data exist for this team.
        $allRosters = nfl_api_get_cached('/rosters/pfr', ['team' => $team, 'limit' => 1000], 86400);
        foreach ($allRosters['data'] ?? [] as $r) {
            $rosterSeasons[$r['season']] = true;
        }
        $rosterSeasons = array_keys($rosterSeasons);
        rsort($rosterSeasons);

        $rosterSeason = $season !== '' ? (int) $season : ($rosterSeasons[0] ?? null);
        if ($rosterSeason !== null) {
            $rosterResult = nfl_api_get_cached('/rosters/pfr', ['team' => $team, 'season' => $rosterSeason, 'limit' => 100], 86400);
            $roster = $rosterResult['data'] ?? [];
            usort($roster, fn($a, $b) => ($b['approximate_value'] ?? -1) <=> ($a['approximate_value'] ?? -1));
        }
    }
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
    <?php if (!empty($rosterSeasons)): ?>
        <div class="form-row">
            <label for="season">Roster season</label>
            <select id="season" name="season">
                <?php foreach ($rosterSeasons as $s): ?>
                    <option value="<?= $s ?>" <?= ((string) $s === $season || ($season === '' && $s === $rosterSeasons[0])) ? 'selected' : '' ?>>
                        <?= $s ?>
                    </option>
                <?php endforeach; ?>
            </select>
        </div>
    <?php endif; ?>
    <button type="submit" class="submit-btn">View Snapshot</button>
</form>

<?php if ($team !== '' && !$teamInfo): ?>
    <div class="error">Unknown team.</div>
<?php elseif ($teamInfo): ?>
    <div class="results-section">
        <h2><?= htmlspecialchars($teamInfo['name']) ?></h2>
        <p style="color:#666;"><?= htmlspecialchars($teamInfo['conf']) ?> &mdash; <?= htmlspecialchars($teamInfo['division']) ?></p>

        <h3>Top Contracts</h3>
        <?php if (empty($topContracts)): ?>
            <div class="no-results">No contract data found for the <?= htmlspecialchars($contractTeamName) ?>.</div>
        <?php else: ?>
            <div class="table-wrap">
                <table class="data-table sortable">
                    <thead>
                        <tr>
                            <th>Player</th>
                            <th>Position</th>
                            <th>Year Signed</th>
                            <th>Years</th>
                            <th>Total Value ($M)</th>
                            <th>APY ($M)</th>
                            <th>Guaranteed ($M)</th>
                            <th>Cap %</th>
                        </tr>
                    </thead>
                    <tbody>
                        <?php foreach ($topContracts as $c): ?>
                            <tr>
                                <td><?= htmlspecialchars($c['player_name'] ?? '-') ?></td>
                                <td><?= htmlspecialchars($c['position'] ?? '-') ?></td>
                                <td><?= htmlspecialchars((string) ($c['year_signed'] ?? '-')) ?></td>
                                <td><?= htmlspecialchars((string) ($c['years'] ?? '-')) ?></td>
                                <td><?= isset($c['value']) ? number_format($c['value']) : '-' ?></td>
                                <td><?= isset($c['apy']) ? number_format($c['apy']) : '-' ?></td>
                                <td><?= isset($c['guaranteed']) ? number_format($c['guaranteed']) : '-' ?></td>
                                <td><?= isset($c['apy_cap_pct']) ? number_format($c['apy_cap_pct'] * 100, 1) . '%' : '-' ?></td>
                            </tr>
                        <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
        <?php endif; ?>

        <h3 style="margin-top:30px;"><?= htmlspecialchars((string) ($rosterSeason ?? '')) ?> Roster</h3>
        <?php if (empty($roster)): ?>
            <div class="no-results">No roster data found for this season.</div>
        <?php else: ?>
            <div class="table-wrap">
                <table class="data-table sortable">
                    <thead>
                        <tr>
                            <th>Player</th>
                            <th>Position</th>
                            <th>Age</th>
                            <th>Exp</th>
                            <th>College</th>
                            <th>AV</th>
                            <th>Drafted</th>
                        </tr>
                    </thead>
                    <tbody>
                        <?php foreach ($roster as $r): ?>
                            <tr>
                                <td><?= htmlspecialchars($r['player'] ?? '-') ?></td>
                                <td><?= htmlspecialchars($r['position'] ?? '-') ?></td>
                                <td><?= htmlspecialchars((string) ($r['age'] ?? '-')) ?></td>
                                <td><?= htmlspecialchars((string) ($r['years_exp'] ?? '-')) ?></td>
                                <td><?= htmlspecialchars($r['college'] ?? '-') ?></td>
                                <td><?= htmlspecialchars((string) ($r['approximate_value'] ?? '-')) ?></td>
                                <td><?= htmlspecialchars($r['drafted_tm_rnd_yr'] ?? 'Undrafted') ?></td>
                            </tr>
                        <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
        <?php endif; ?>
    </div>
<?php endif; ?>

<?php require __DIR__ . '/includes/footer.php'; ?>
