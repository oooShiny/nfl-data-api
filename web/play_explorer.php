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

/** Tags from the charting row, as a list of labels. */
function charting_tags(?array $c): array {
    if ($c === null) {
        return [];
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
    return $out;
}

/** A short human-readable description of a play, built from its core fields. */
function play_desc(array $p): string {
    $team = htmlspecialchars($p['posteam'] ?? '');
    $yards = $p['yards_gained'] ?? null;
    $yardsStr = $yards !== null ? (($yards >= 0 ? '+' : '') . $yards . ' yds') : '';
    $td = !empty($p['touchdown']) ? ' &mdash; TOUCHDOWN' : '';
    $turnover = !empty($p['turnover']) ? ' &mdash; TURNOVER' : '';

    return match ($p['play_type'] ?? '') {
        'pass' => trim("$team pass, $yardsStr$td"),
        'run' => trim("$team run, $yardsStr$td"),
        'punt' => "$team punt",
        'field_goal' => "$team field goal attempt",
        'kickoff' => "$team kickoff",
        'extra_point' => "$team extra point attempt",
        'qb_kneel' => "$team QB kneel",
        'no_play' => 'No play (penalty)',
        default => trim($team . ' ' . str_replace('_', ' ', $p['play_type'] ?? 'play') . " $yardsStr$turnover"),
    };
}

/** Grouped result label + style class for a drive, based on its last play. */
function drive_result(array $plays): array {
    foreach ($plays as $p) {
        if (!empty($p['touchdown'])) {
            return ['TD', 'td'];
        }
    }
    $last = $plays[count($plays) - 1];
    if (!empty($last['turnover'])) {
        return ['TURNOVER', 'int'];
    }
    return match ($last['play_type'] ?? '') {
        'field_goal' => ['FG', 'fg'],
        'punt' => ['PUNT', 'punt'],
        default => ['END OF DRIVE', 'punt'],
    };
}

/** Build an SVG win-probability line chart from a sequence of 0-1 wp values. */
function wp_chart_svg(array $values, array $quarterMarks): string {
    $vw = 1036;
    $vh = 200;
    $padL = 40;
    $padR = 16;
    $padT = 14;
    $padB = 24;
    $plotW = $vw - $padL - $padR;
    $plotH = $vh - $padT - $padB;
    $n = count($values);
    if ($n < 2) {
        return '';
    }

    $x = fn($i) => $padL + ($i / ($n - 1)) * $plotW;
    $y = fn($v) => $padT + (1 - $v) * $plotH;

    $points = [];
    foreach ($values as $i => $v) {
        $points[] = sprintf('%.1f,%.1f', $x($i), $y($v));
    }
    $yb = $padT + $plotH;
    $areaD = sprintf('M %.1f,%.1f L ', $x(0), $yb) . implode(' L ', $points) . sprintf(' L %.1f,%.1f Z', $x($n - 1), $yb);

    $svg = '<svg viewBox="0 0 ' . $vw . ' ' . $vh . '" width="100%" style="display:block;height:auto;">';
    $svg .= '<defs><linearGradient id="wpgrad" x1="0" y1="0" x2="0" y2="1">'
        . '<stop offset="0" stop-color="rgba(227,24,55,0.30)"/>'
        . '<stop offset="1" stop-color="rgba(227,24,55,0)"/></linearGradient></defs>';

    foreach ([0, 50, 100] as $tick) {
        $ty = $y($tick / 100);
        $dash = $tick === 50 ? ' stroke-dasharray="4 4"' : '';
        $stroke = $tick === 50 ? 'rgba(120,160,220,0.3)' : 'rgba(120,160,220,0.14)';
        $svg .= sprintf('<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" stroke="%s" stroke-width="1"%s/>', $padL, $vw - $padR, $ty, $ty, $stroke, $dash);
        $svg .= sprintf('<text x="%d" y="%.1f" text-anchor="end" dominant-baseline="middle" fill="#7C90B4" font-size="11" font-family="\'IBM Plex Mono\', monospace">%d%%</text>', $padL - 8, $ty, $tick);
    }

    foreach ($quarterMarks as $mark) {
        $mx = $x($mark['index']);
        $svg .= sprintf('<text x="%.1f" y="%d" text-anchor="middle" fill="#7C90B4" font-size="11" font-family="\'IBM Plex Mono\', monospace">%s</text>', $mx, $vh - 6, htmlspecialchars($mark['label']));
    }

    $svg .= '<path d="' . $areaD . '" fill="url(#wpgrad)"/>';
    $svg .= '<polyline points="' . implode(' ', $points) . '" fill="none" stroke="#E84C5E" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>';
    $last = $values[$n - 1];
    $svg .= sprintf('<circle cx="%.1f" cy="%.1f" r="4" fill="#E84C5E"/>', $x($n - 1), $y($last));
    $svg .= '</svg>';

    return $svg;
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
    <?php if ($game === null): ?>
        <div class="error">Game not found.</div>
    <?php elseif (empty($plays)): ?>
        <div class="no-results">No play-by-play data available for this game.</div>
    <?php else: ?>
        <?php
        $homeTeam = $game['home_team'];
        $awayTeam = $game['away_team'];

        // Group consecutive plays by drive number.
        $driveGroups = [];
        foreach ($plays as $p) {
            $driveNum = $p['drive'] ?? null;
            $last = count($driveGroups) - 1;
            if ($last < 0 || $driveGroups[$last]['drive'] !== $driveNum) {
                $driveGroups[] = ['drive' => $driveNum, 'team' => $p['posteam'] ?? '', 'plays' => []];
                $last++;
            }
            $driveGroups[$last]['plays'][] = $p;
        }

        // Win-probability chart data and quarter tick marks.
        $wpValues = [];
        $quarterMarks = [];
        $seenQuarters = [];
        foreach ($plays as $i => $p) {
            if (($p['wp'] ?? null) === null) {
                continue;
            }
            $wpValues[] = (float) $p['wp'];
            $q = $p['quarter'] ?? null;
            if ($q !== null && !isset($seenQuarters[$q])) {
                $seenQuarters[$q] = true;
                $quarterMarks[] = ['index' => count($wpValues) - 1, 'label' => 'Q' . $q];
            }
        }

        $ticker_items = [
            strtoupper($awayTeam) . ' ' . $game['away_score'] . ', ' . strtoupper($homeTeam) . ' ' . $game['home_score'] . ' &mdash; ' . ($game['game_type'] === 'REG' ? 'WEEK ' . $game['week'] : $game['game_type']),
            count($plays) . ' PLAYS &middot; ' . count($driveGroups) . ' DRIVES CHARTED',
            'EPA &middot; WP &middot; TAGS PRE-COMPUTED ON EVERY PLAY',
            'GET /v1/plays?game_id=' . htmlspecialchars($gameId),
        ];
        ?>

        <div class="section-header red">
            <h2><?= htmlspecialchars($awayTeam) ?> @ <?= htmlspecialchars($homeTeam) ?></h2>
            <span class="endpoint-label">Week <?= htmlspecialchars((string) $game['week']) ?> &middot; <?= htmlspecialchars($game['game_type']) ?> &middot; <?= htmlspecialchars($game['gameday'] ?? '') ?></span>
        </div>
        <div class="page-pinstripe"></div>
        <div class="section-body">
            <div class="game-scoreboard">
                <div class="game-team">
                    <span class="shield"><?= htmlspecialchars($awayTeam) ?></span>
                    <span class="game-score"><?= htmlspecialchars((string) $game['away_score']) ?></span>
                </div>
                <span class="game-at">AT</span>
                <div class="game-team">
                    <span class="game-score"><?= htmlspecialchars((string) $game['home_score']) ?></span>
                    <span class="shield"><?= htmlspecialchars($homeTeam) ?></span>
                </div>
                <span class="game-status">Final</span>
            </div>

            <?php if (!empty($wpValues)): ?>
                <div class="wp-chart-box">
                    <div class="wp-chart-head">
                        <h3>Win Probability</h3>
                        <span class="endpoint-label">Possession-team WP &middot; GET /v1/plays?game_id=<?= htmlspecialchars($gameId) ?></span>
                    </div>
                    <?= wp_chart_svg($wpValues, $quarterMarks) ?>
                </div>
            <?php endif; ?>

            <div class="filter-bar">
                <div class="filter-group" data-filter-key="team">
                    <span class="filter-label">Team</span>
                    <div class="filter-buttons">
                        <button type="button" class="filter-btn active" data-filter-value="ALL">Both</button>
                        <button type="button" class="filter-btn" data-filter-value="<?= htmlspecialchars($homeTeam) ?>"><?= htmlspecialchars($homeTeam) ?></button>
                        <button type="button" class="filter-btn" data-filter-value="<?= htmlspecialchars($awayTeam) ?>"><?= htmlspecialchars($awayTeam) ?></button>
                    </div>
                </div>
                <div class="filter-group" data-filter-key="play">
                    <span class="filter-label">Play</span>
                    <div class="filter-buttons">
                        <button type="button" class="filter-btn active" data-filter-value="ALL">All</button>
                        <button type="button" class="filter-btn" data-filter-value="pass">Pass</button>
                        <button type="button" class="filter-btn" data-filter-value="run">Run</button>
                    </div>
                </div>
                <span class="drive-count-label">
                    <?php if ($driveGroups[0]['drive'] !== null): ?>
                        <?= count($driveGroups) ?> drives shown
                    <?php else: ?>
                        <?= count($plays) ?> plays shown
                    <?php endif; ?>
                </span>
            </div>

            <div class="pbp-container">
                <div class="play-header-row">
                    <span>Qtr</span>
                    <span>Down &amp; Dist</span>
                    <span>Play</span>
                    <span class="text-right">Yds</span>
                    <span class="text-right">EPA</span>
                    <span class="text-right">WP&Delta;</span>
                </div>
                <?php foreach ($driveGroups as $drive): ?>
                    <?php
                    [$resultLabel, $resultClass] = drive_result($drive['plays']);
                    $totalYards = array_sum(array_map(fn($p) => $p['yards_gained'] ?? 0, $drive['plays']));
                    ?>
                    <div class="drive-group">
                        <?php if ($drive['drive'] !== null): ?>
                            <div class="drive-header">
                                <span class="shield small"><?= htmlspecialchars($drive['team']) ?></span>
                                <span class="drive-title">Drive <?= htmlspecialchars((string) $drive['drive']) ?></span>
                                <span class="drive-summary"><?= count($drive['plays']) ?> plays &middot; <?= $totalYards >= 0 ? '+' : '' ?><?= $totalYards ?> yds</span>
                                <span class="drive-result <?= $resultClass ?>"><?= $resultLabel ?></span>
                            </div>
                        <?php endif; ?>
                        <?php foreach ($drive['plays'] as $p): ?>
                            <?php
                            $tags = charting_tags($chartingByPlay[$p['play_id']] ?? null);
                            $epa = $p['epa'] ?? null;
                            $wpa = $p['wpa'] ?? null;
                            $epaClass = $epa === null ? '' : ($epa >= 0 ? 'pos' : 'neg');
                            $wpaClass = $wpa === null ? '' : ($wpa >= 0 ? 'pos' : 'neg');
                            $ddText = ($p['down'] !== null && $p['ydstogo'] !== null) ? fmt($p['down']) . ' &amp; ' . fmt($p['ydstogo']) : '-';
                            ?>
                            <div class="play-row" data-play-type="<?= htmlspecialchars($p['play_type'] ?? '') ?>" data-team="<?= htmlspecialchars($p['posteam'] ?? '') ?>">
                                <span class="play-qtr">Q<?= fmt($p['quarter']) ?></span>
                                <span class="play-dd"><?= $ddText ?></span>
                                <div class="play-desc-wrap">
                                    <div class="play-desc"><?= play_desc($p) ?></div>
                                    <?php if (!empty($tags)): ?>
                                        <div class="play-tags">
                                            <?php foreach ($tags as $tag): ?>
                                                <span class="play-tag"><?= htmlspecialchars($tag) ?></span>
                                            <?php endforeach; ?>
                                        </div>
                                    <?php endif; ?>
                                </div>
                                <span class="play-yds text-right"><?= fmt($p['yards_gained']) ?></span>
                                <span class="play-epa text-right <?= $epaClass ?>"><?= $epa === null ? '-' : (($epa >= 0 ? '+' : '') . number_format($epa, 2)) ?></span>
                                <span class="play-wpa text-right <?= $wpaClass ?>"><?= $wpa === null ? '-' : (($wpa >= 0 ? '+' : '') . number_format($wpa * 100, 1) . '%') ?></span>
                            </div>
                        <?php endforeach; ?>
                    </div>
                <?php endforeach; ?>
            </div>
        </div>

        <script>
            (function () {
                var container = document.querySelector('.pbp-container');
                if (!container) return;
                var filters = { team: 'ALL', play: 'ALL' };

                function applyFilters() {
                    container.querySelectorAll('.play-row').forEach(function (row) {
                        var teamVisible = filters.team === 'ALL' || row.getAttribute('data-team') === filters.team;
                        var playVisible = filters.play === 'ALL' || row.getAttribute('data-play-type') === filters.play;
                        row.classList.toggle('filter-hidden', !(teamVisible && playVisible));
                    });
                }

                document.querySelectorAll('.filter-group').forEach(function (group) {
                    var key = group.getAttribute('data-filter-key');
                    group.querySelectorAll('.filter-btn').forEach(function (btn) {
                        btn.addEventListener('click', function () {
                            group.querySelectorAll('.filter-btn').forEach(function (b) { b.classList.remove('active'); });
                            btn.classList.add('active');
                            filters[key] = btn.getAttribute('data-filter-value');
                            applyFilters();
                        });
                    });
                });
            })();
        </script>
    <?php endif; ?>
<?php endif; ?>

<?php require __DIR__ . '/includes/footer.php'; ?>
