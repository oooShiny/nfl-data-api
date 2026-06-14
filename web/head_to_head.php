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
$gameTypeTags = ['WC' => 'Wild Card', 'DIV' => 'Divisional', 'CON' => 'Conf. Champ', 'SB' => 'Super Bowl'];

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

// Splits "City Name Nickname" into ["City Name", "Nickname"] for the scoreboard.
function team_city_nick(string $fullName): array {
    $parts = explode(' ', $fullName);
    if (count($parts) < 2) {
        return ['', $fullName];
    }
    $nick = array_pop($parts);
    return [implode(' ', $parts), $nick];
}

function perf_rows(array $rows, string $yardsCol, string $tdsCol, string $t1, bool $withGames): string {
    if (empty($rows)) {
        return '<div class="no-results">No data.</div>';
    }
    $html = '';
    foreach ($rows as $i => $row) {
        $team = $row['recent_team'] ?? '';
        $badgeClass = ($team === $t1) ? 'team1' : 'team2';
        $tds = (int) ($row[$tdsCol] ?? 0);
        $rowClass = $withGames ? 'perf-row career' : 'perf-row';
        $html .= '<div class="' . $rowClass . '">';
        $html .= '<span class="perf-rank">' . ($i + 1) . '</span>';
        $html .= '<span class="perf-player">';
        $html .= '<span class="perf-team-badge ' . $badgeClass . '">' . htmlspecialchars($team) . '</span>';
        $html .= '<span class="perf-name">' . htmlspecialchars($row['player_name'] ?? '') . '</span>';
        $html .= '</span>';
        if ($withGames) {
            $html .= '<span class="perf-games">' . htmlspecialchars((string) ($row['games'] ?? '')) . '</span>';
        } else {
            $html .= '<span class="perf-game">' . htmlspecialchars((string) ($row['season'] ?? '')) . ' &middot; Wk ' . htmlspecialchars((string) ($row['week'] ?? '')) . '</span>';
        }
        $html .= '<span class="perf-yards">' . number_format((int) ($row[$yardsCol] ?? 0)) . '</span>';
        $html .= '<span class="perf-tds' . ($tds === 0 ? ' zero' : '') . '">' . $tds . '</span>';
        $html .= '</div>';
    }
    return $html;
}

require __DIR__ . '/includes/header.php';
?>

<div class="selector-header">
    <span class="dot"></span>
    <span class="label">Matchup Selector</span>
    <span class="endpoint">GET /v1/games/head-to-head</span>
</div>
<div class="selector-body">
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
</div>

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
    $games = $result['games'];

    [$t1City, $t1Nick] = team_city_nick(team_name($teams, $t1));
    [$t2City, $t2Nick] = team_city_nick(team_name($teams, $t2));

    $t1W = (int) $rec[$t1]['wins'];
    $t1L = (int) $rec[$t1]['losses'];
    $t2W = (int) $rec[$t2]['wins'];
    $t2L = (int) $rec[$t2]['losses'];

    $decided = $t1W + $t1L;
    $t1Pct = $decided > 0 ? round(($t1W / $decided) * 100) : 50;
    $t2Pct = 100 - $t1Pct;

    if ($t1W > $t2W) {
        $leadLine = "$t1City $t1Nick lead the all-time series $t1W&ndash;$t2W";
    } elseif ($t2W > $t1W) {
        $leadLine = "$t2City $t2Nick lead the all-time series $t2W&ndash;$t1W";
    } else {
        $leadLine = "The series is dead even at $t1W&ndash;$t2W";
    }

    // Tale of the tape: compute totals/playoff splits from the games array.
    $t1Pts = 0;
    $t2Pts = 0;
    $t1Max = 0;
    $t2Max = 0;
    $playedGames = 0;
    $t1PoW = 0;
    $poGames = 0;
    foreach ($games as $g) {
        if ($g['home_score'] === null || $g['away_score'] === null) {
            continue;
        }
        $playedGames++;
        if ($g['home_team'] === $t1) {
            $s1 = (int) $g['home_score'];
            $s2 = (int) $g['away_score'];
        } else {
            $s1 = (int) $g['away_score'];
            $s2 = (int) $g['home_score'];
        }
        $t1Pts += $s1;
        $t2Pts += $s2;
        $t1Max = max($t1Max, $s1);
        $t2Max = max($t2Max, $s2);
        if ($g['game_type'] !== 'REG') {
            $poGames++;
            if ($s1 > $s2) {
                $t1PoW++;
            }
        }
    }
    $ppg1 = $playedGames > 0 ? number_format($t1Pts / $playedGames, 1) : '0.0';
    $ppg2 = $playedGames > 0 ? number_format($t2Pts / $playedGames, 1) : '0.0';

    $tape = [
        ['label' => 'Series Wins', 'v1' => $t1W, 'v2' => $t2W],
        ['label' => 'Home Record', 'v1' => "{$home[$t1]['wins']}&ndash;{$home[$t1]['losses']}", 'v2' => "{$home[$t2]['wins']}&ndash;{$home[$t2]['losses']}"],
        ['label' => 'Playoff Record', 'v1' => "$t1PoW&ndash;" . ($poGames - $t1PoW), 'v2' => ($poGames - $t1PoW) . "&ndash;$t1PoW"],
        ['label' => 'Total Points', 'v1' => number_format($t1Pts), 'v2' => number_format($t2Pts)],
        ['label' => 'Points / Game', 'v1' => $ppg1, 'v2' => $ppg2],
        ['label' => 'Most In A Game', 'v1' => $t1Max, 'v2' => $t2Max],
    ];
    ?>
    <!-- ===== SCOREBOARD HERO ===== -->
    <section style="margin-bottom: 22px;">
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px;">
            <span class="gold-pill">All-Time Series</span>
            <span style="font-family: 'Barlow Semi Condensed', sans-serif; font-weight: 500; font-size: 13px; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-dim);"><?= number_format($result['total_games']) ?> meetings</span>
        </div>
        <div class="scoreboard">
            <div class="scoreboard-grid">
                <div class="scoreboard-team team1">
                    <span class="team-shield team1"><?= htmlspecialchars($t1) ?></span>
                    <div class="team-meta">
                        <div class="team-city"><?= htmlspecialchars($t1City) ?></div>
                        <div class="team-nick"><?= htmlspecialchars($t1Nick) ?></div>
                        <div class="team-record">
                            <span class="num"><?= $t1W ?></span>
                            <span class="losses">&ndash;<?= $t1L ?></span>
                            <span class="wl-label">W&ndash;L</span>
                        </div>
                    </div>
                </div>
                <div class="scoreboard-center">
                    <span class="count"><?= $result['total_games'] ?></span>
                    <span class="count-label">Games Played</span>
                    <span class="vs-badge"><span>VS</span></span>
                </div>
                <div class="scoreboard-team team2">
                    <div class="team-meta">
                        <div class="team-city"><?= htmlspecialchars($t2City) ?></div>
                        <div class="team-nick"><?= htmlspecialchars($t2Nick) ?></div>
                        <div class="team-record">
                            <span class="wl-label">W&ndash;L</span>
                            <span class="num"><?= $t2W ?></span>
                            <span class="losses">&ndash;<?= $t2L ?></span>
                        </div>
                    </div>
                    <span class="team-shield team2"><?= htmlspecialchars($t2) ?></span>
                </div>
            </div>
            <div class="winshare">
                <div class="winshare-labels">
                    <span class="t1"><?= htmlspecialchars($t1) ?> <?= $t1Pct ?>%</span>
                    <span class="mid">Series Win Share</span>
                    <span class="t2"><?= $t2Pct ?>% <?= htmlspecialchars($t2) ?></span>
                </div>
                <div class="winshare-bar">
                    <div class="fill1" style="width: <?= $t1Pct ?>%;"></div>
                    <div class="fill2" style="width: <?= $t2Pct ?>%;"></div>
                </div>
                <div class="winshare-lead"><span class="gold"><?= $leadLine ?></span></div>
            </div>
        </div>
    </section>

    <!-- ===== TALE OF THE TAPE ===== -->
    <section style="margin-bottom: 24px;">
        <div class="section-header blue">
            <h2>Tale of the Tape</h2>
            <span class="endpoint-label">Head-to-head splits</span>
        </div>
        <div class="page-pinstripe"></div>
        <div class="section-body">
            <div class="tape-table-header">
                <span><?= htmlspecialchars($t1) ?></span>
                <span></span>
                <span><?= htmlspecialchars($t2) ?></span>
            </div>
            <?php foreach ($tape as $row): ?>
            <div class="tape-row">
                <span class="tape-val left"><?= $row['v1'] ?></span>
                <span class="tape-label-mid"><?= htmlspecialchars($row['label']) ?></span>
                <span class="tape-val right"><?= $row['v2'] ?></span>
            </div>
            <?php endforeach; ?>
        </div>
    </section>

    <!-- ===== SIGNATURE WINS ===== -->
    <?php if ($bigWin[$t1] || $bigWin[$t2]): ?>
    <section style="margin-bottom: 24px;">
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 14px;">
            <span class="gold-pill">Signature Wins</span>
            <h2 style="font-family: 'Oswald', sans-serif; font-weight: 600; font-size: 24px; text-transform: uppercase; color: #fff; margin: 0;">Biggest blowout each way</h2>
        </div>
        <div class="bigwin-grid">
            <?php foreach ([[$t1, 'team1'], [$t2, 'team2']] as [$team, $class]): ?>
                <?php if ($bigWin[$team]): ?>
                    <?php
                    $bw = $bigWin[$team];
                    [$winScore, $loseScore] = explode('-', $bw['score']);
                    ?>
                    <div class="bigwin-card <?= $class ?>">
                        <div class="bigwin-head">
                            <span class="label"><?= htmlspecialchars($team) ?> &middot; Biggest Win</span>
                            <span class="bigwin-margin">+<?= $bw['margin'] ?> Margin</span>
                        </div>
                        <div class="bigwin-score">
                            <span class="win"><?= htmlspecialchars($winScore) ?></span>
                            <span class="lose">&ndash; <?= htmlspecialchars($loseScore) ?></span>
                        </div>
                        <div class="bigwin-foot">
                            <span class="context">vs <?= htmlspecialchars($bw['opponent']) ?> &middot; Season <?= htmlspecialchars((string) $bw['season']) ?>, Week <?= htmlspecialchars((string) $bw['week']) ?> &mdash; <?= htmlspecialchars((string) $bw['gameday']) ?></span>
                            <a href="play_explorer.php?season=<?= urlencode((string) $bw['season']) ?>&game_id=<?= urlencode($bw['game_id']) ?>">View Plays &rarr;</a>
                        </div>
                    </div>
                <?php endif; ?>
            <?php endforeach; ?>
        </div>
    </section>
    <?php endif; ?>

    <!-- ===== GAME LOG ===== -->
    <section style="margin-bottom: 24px;">
        <div class="section-header red">
            <h2>Game Log</h2>
            <span class="endpoint-label">Result from <?= htmlspecialchars($t1) ?> perspective</span>
        </div>
        <div class="page-pinstripe"></div>
        <div class="section-body">
            <div class="gamelog-header">
                <span>Res</span>
                <span>When</span>
                <span>Matchup</span>
                <span>Date</span>
                <span></span>
            </div>
            <?php foreach ($games as $g): ?>
                <?php
                $weekLabel = ((int) $g['week'] >= 19) ? 'Playoffs' : 'Week ' . $g['week'];
                $tag = $gameTypeTags[$g['game_type']] ?? '';
                $hasScore = $g['home_score'] !== null && $g['away_score'] !== null;
                if ($g['home_team'] === $t1) {
                    $s1 = $g['home_score'];
                    $s2 = $g['away_score'];
                    $venue = $g['away_team'];
                } else {
                    $s1 = $g['away_score'];
                    $s2 = $g['home_score'];
                    $venue = $g['home_team'];
                }
                $t1Won = $hasScore && $s1 > $s2;
                $tied = $hasScore && $s1 == $s2;
                $resultClass = !$hasScore ? '' : ($tied ? 'tie' : ($t1Won ? 'win' : 'loss'));
                $resultLabel = !$hasScore ? '&mdash;' : ($tied ? 'T' : ($t1Won ? 'W' : 'L'));
                ?>
                <div class="gamelog-row">
                    <span class="gamelog-result <?= $resultClass ?>"><?= $resultLabel ?></span>
                    <div class="gamelog-when">
                        <div class="season"><?= htmlspecialchars((string) $g['season']) ?></div>
                        <div class="week"><?= htmlspecialchars($weekLabel) ?></div>
                    </div>
                    <div class="gamelog-matchup">
                        <div class="gamelog-score">
                            <span class="abbr1"><?= htmlspecialchars($t1) ?></span>
                            <?php if ($hasScore): ?>
                                <span class="score <?= $t1Won || $tied ? 'bright' : 'fade' ?>"><?= htmlspecialchars((string) $s1) ?></span>
                                <span class="dash">&ndash;</span>
                                <span class="score <?= !$t1Won ? 'bright' : 'fade' ?>"><?= htmlspecialchars((string) $s2) ?></span>
                            <?php else: ?>
                                <span class="score fade">&mdash;</span>
                            <?php endif; ?>
                            <span class="abbr2"><?= htmlspecialchars($t2) ?></span>
                        </div>
                        <?php if ($tag !== ''): ?>
                            <span class="gamelog-tag"><?= htmlspecialchars($tag) ?></span>
                        <?php endif; ?>
                    </div>
                    <div class="gamelog-date">
                        <div class="date"><?= htmlspecialchars((string) $g['gameday']) ?></div>
                        <div class="venue">@ <?= htmlspecialchars($venue) ?></div>
                    </div>
                    <a class="gamelog-view" href="play_explorer.php?season=<?= urlencode((string) $g['season']) ?>&game_id=<?= urlencode($g['game_id']) ?>">View &rarr;</a>
                </div>
            <?php endforeach; ?>
        </div>
    </section>

    <!-- ===== TOP SINGLE-GAME PERFORMANCES ===== -->
    <section style="margin-bottom: 24px;" data-tab-group>
        <div class="section-header red">
            <h2>Top Single-Game Performances</h2>
            <div class="tab-bar">
                <button type="button" class="tab-btn active" data-tab="sg-passing">Passing</button>
                <button type="button" class="tab-btn" data-tab="sg-rushing">Rushing</button>
                <button type="button" class="tab-btn" data-tab="sg-receiving">Receiving</button>
            </div>
        </div>
        <div class="page-pinstripe"></div>
        <div class="section-body">
            <div class="tab-panel active" data-tabpanel="sg-passing">
                <div class="perf-header">
                    <span>Rk</span><span>Player</span><span>Game</span><span class="text-right">Pass Yds</span><span class="text-right">TD</span>
                </div>
                <?= perf_rows($result['top_performances']['passing'], 'passing_yards', 'passing_tds', $t1, false) ?>
            </div>
            <div class="tab-panel" data-tabpanel="sg-rushing">
                <div class="perf-header">
                    <span>Rk</span><span>Player</span><span>Game</span><span class="text-right">Rush Yds</span><span class="text-right">TD</span>
                </div>
                <?= perf_rows($result['top_performances']['rushing'], 'rushing_yards', 'rushing_tds', $t1, false) ?>
            </div>
            <div class="tab-panel" data-tabpanel="sg-receiving">
                <div class="perf-header">
                    <span>Rk</span><span>Player</span><span>Game</span><span class="text-right">Rec Yds</span><span class="text-right">TD</span>
                </div>
                <?= perf_rows($result['top_performances']['receiving'], 'receiving_yards', 'receiving_tds', $t1, false) ?>
            </div>
        </div>
    </section>

    <!-- ===== CAREER TOTALS ===== -->
    <section style="margin-bottom: 24px;" data-tab-group>
        <div class="section-header blue">
            <h2>Career Totals vs. Opponent</h2>
            <div class="tab-bar">
                <button type="button" class="tab-btn active" data-tab="car-passing">Passing</button>
                <button type="button" class="tab-btn" data-tab="car-rushing">Rushing</button>
                <button type="button" class="tab-btn" data-tab="car-receiving">Receiving</button>
            </div>
        </div>
        <div class="page-pinstripe"></div>
        <div class="section-body">
            <div class="tab-panel active" data-tabpanel="car-passing">
                <div class="perf-header career">
                    <span>Rk</span><span>Player</span><span class="text-right">GP</span><span class="text-right">Pass Yds</span><span class="text-right">TD</span>
                </div>
                <?= perf_rows($result['career_totals']['passing'], 'passing_yards', 'passing_tds', $t1, true) ?>
            </div>
            <div class="tab-panel" data-tabpanel="car-rushing">
                <div class="perf-header career">
                    <span>Rk</span><span>Player</span><span class="text-right">GP</span><span class="text-right">Rush Yds</span><span class="text-right">TD</span>
                </div>
                <?= perf_rows($result['career_totals']['rushing'], 'rushing_yards', 'rushing_tds', $t1, true) ?>
            </div>
            <div class="tab-panel" data-tabpanel="car-receiving">
                <div class="perf-header career">
                    <span>Rk</span><span>Player</span><span class="text-right">GP</span><span class="text-right">Rec Yds</span><span class="text-right">TD</span>
                </div>
                <?= perf_rows($result['career_totals']['receiving'], 'receiving_yards', 'receiving_tds', $t1, true) ?>
            </div>
        </div>
    </section>
<?php endif; ?>
</div>

<?php
if ($result !== null && $result['total_games'] > 0) {
    $ticker_items = [
        "$leadLine",
        "PLAYOFFS: " . htmlspecialchars($t1) . " $t1PoW&ndash;" . ($poGames - $t1PoW) . " vs " . htmlspecialchars($t2),
        number_format($result['total_games']) . " MEETINGS",
        "TOTAL POINTS: " . htmlspecialchars($t1) . " " . number_format($t1Pts) . " &middot; " . htmlspecialchars($t2) . " " . number_format($t2Pts),
    ];
}
require __DIR__ . '/includes/footer.php';
?>
