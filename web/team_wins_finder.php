<?php
require_once __DIR__ . '/includes/api.php';

$page_title = 'Team Wins Finder';
$page_subtitle = 'Select teams to find weeks where all selected teams won their games.';

$meta = nfl_api_get_cached('/meta', [], 86400);
$teams = $meta['teams'] ?? [];
$seasons = $meta['seasons'] ?? [];
usort($teams, fn($a, $b) => strcmp($a['abbr'], $b['abbr']));

require __DIR__ . '/includes/header.php';
?>
        <form method="POST" class="form-section">
            <h3 style="grid-column: 1 / -1; margin: 0;">Select Teams</h3>
            <div class="team-selection">
<?php
// Output checkboxes for each team
foreach ($teams as $t) {
    $team = $t['abbr'];
    $checked = (isset($_POST['teams']) && in_array($team, $_POST['teams'])) ? 'checked' : '';
    echo '<div class="team-checkbox">';
    echo '<input type="checkbox" id="team_' . htmlspecialchars($team) . '" name="teams[]" value="' . htmlspecialchars($team) . '" ' . $checked . '>';
    echo '<label for="team_' . htmlspecialchars($team) . '">' . htmlspecialchars($t['name']) . '</label>';
    echo '</div>';
}
?>
            </div>
            <button type="submit" class="submit-btn">Find Winning Weeks</button>
        </form>

<?php
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['teams'])) {
    $selectedTeams = $_POST['teams'];

    if (count($selectedTeams) === 0) {
        echo '<div class="error">Please select at least one team.</div>';
    } else {
        echo '<div class="info">Searching for weeks where <strong>' . implode(', ', $selectedTeams) . '</strong> all won their games...</div>';

        // Fetch regular-season games for every season and organize by season/week
        $gamesByWeek = [];
        foreach ($seasons as $season) {
            $result = nfl_api_get_cached('/games', [
                'season' => $season,
                'game_type' => 'REG',
                'limit' => 500,
            ], 43200);

            foreach ($result['data'] ?? [] as $row) {
                if ($row['home_score'] === null || $row['away_score'] === null) {
                    continue; // game not yet played
                }
                $key = $row['season'] . '_' . $row['week'];
                if (!isset($gamesByWeek[$key])) {
                    $gamesByWeek[$key] = [
                        'season' => $row['season'],
                        'week' => $row['week'],
                        'games' => []
                    ];
                }
                $gamesByWeek[$key]['games'][] = $row;
            }
        }

        // Find weeks where all selected teams won
        $winningWeeks = [];
        foreach ($gamesByWeek as $key => $weekData) {
            $teamWins = [];

            // Check each game to see if any selected team won
            foreach ($weekData['games'] as $game) {
                $awayTeam = $game['away_team'];
                $homeTeam = $game['home_team'];
                $awayScore = (int)$game['away_score'];
                $homeScore = (int)$game['home_score'];

                // Determine winner
                if ($awayScore > $homeScore) {
                    $winner = $awayTeam;
                } elseif ($homeScore > $awayScore) {
                    $winner = $homeTeam;
                } else {
                    // Tie game
                    continue;
                }

                // Check if winner is in selected teams
                if (in_array($winner, $selectedTeams)) {
                    $teamWins[$winner] = $game;
                }
            }

            // Check if all selected teams won this week
            if (count($teamWins) === count($selectedTeams)) {
                $winningWeeks[] = [
                    'season' => $weekData['season'],
                    'week' => $weekData['week'],
                    'wins' => $teamWins
                ];
            }
        }

        // Display results
        echo '<div class="results-section">';
        if (count($winningWeeks) === 0) {
            echo '<div class="no-results">No weeks found where all selected teams won their games.</div>';
        } else {
            echo '<h2>Found ' . count($winningWeeks) . ' week(s) where all selected teams won:</h2>';

            foreach ($winningWeeks as $week) {
                echo '<div class="result-item">';
                echo '<div class="result-header">Season ' . htmlspecialchars($week['season']) . ', Week ' . htmlspecialchars($week['week']) . '</div>';
                echo '<table class="games-table sortable">';
                echo '<thead><tr>';
                echo '<th>Team</th>';
                echo '<th>Opponent</th>';
                echo '<th>Location</th>';
                echo '<th>Score</th>';
                echo '<th>Date</th>';
                echo '<th>Plays</th>';
                echo '</tr></thead>';
                echo '<tbody>';

                foreach ($selectedTeams as $team) {
                    if (isset($week['wins'][$team])) {
                        $game = $week['wins'][$team];
                        $awayTeam = $game['away_team'];
                        $homeTeam = $game['home_team'];
                        $awayScore = $game['away_score'];
                        $homeScore = $game['home_score'];

                        if ($awayTeam === $team) {
                            $opponent = $homeTeam;
                            $location = '@ ' . $opponent;
                            $score = $awayScore . ' - ' . $homeScore;
                        } else {
                            $opponent = $awayTeam;
                            $location = 'vs ' . $opponent;
                            $score = $homeScore . ' - ' . $awayScore;
                        }

                        echo '<tr class="win">';
                        echo '<td><strong>' . htmlspecialchars($team) . '</strong></td>';
                        echo '<td>' . htmlspecialchars($opponent) . '</td>';
                        echo '<td>' . htmlspecialchars($location) . '</td>';
                        echo '<td>' . htmlspecialchars($score) . '</td>';
                        echo '<td>' . htmlspecialchars($game['gameday']) . '</td>';
                        echo '<td><a href="play_explorer.php?season=' . urlencode($game['season']) . '&game_id=' . urlencode($game['game_id']) . '">View plays</a></td>';
                        echo '</tr>';
                    }
                }

                echo '</tbody></table>';
                echo '</div>';
            }
        }
        echo '</div>';
    }
}
?>
<?php require __DIR__ . '/includes/footer.php'; ?>