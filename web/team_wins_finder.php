<?php
require_once __DIR__ . '/includes/api.php';

$meta = nfl_api_get_cached('/meta', [], 86400);
$teams = $meta['teams'] ?? [];
$seasons = $meta['seasons'] ?? [];
usort($teams, fn($a, $b) => strcmp($a['abbr'], $b['abbr']));
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NFL Team Wins Finder</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            text-align: center;
            margin-bottom: 30px;
        }
        .form-section {
            margin-bottom: 30px;
            padding: 20px;
            background-color: #f8f9fa;
            border-radius: 5px;
        }
        .team-selection {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
            gap: 10px;
            margin-top: 15px;
        }
        .team-checkbox {
            display: flex;
            align-items: center;
        }
        .team-checkbox input {
            margin-right: 8px;
        }
        .team-checkbox label {
            cursor: pointer;
        }
        .submit-btn {
            background-color: #2c3e50;
            color: white;
            padding: 12px 30px;
            border: none;
            border-radius: 5px;
            font-size: 16px;
            cursor: pointer;
            margin-top: 20px;
        }
        .submit-btn:hover {
            background-color: #34495e;
        }
        .results-section {
            margin-top: 30px;
        }
        .result-item {
            margin-bottom: 30px;
            border: 1px solid #ddd;
            border-radius: 5px;
            overflow: hidden;
        }
        .result-header {
            background-color: #2c3e50;
            color: white;
            padding: 15px;
            font-size: 18px;
            font-weight: bold;
        }
        .games-table {
            width: 100%;
            border-collapse: collapse;
        }
        .games-table th {
            background-color: #ecf0f1;
            padding: 10px;
            text-align: left;
            border-bottom: 2px solid #bdc3c7;
            font-weight: bold;
        }
        .games-table td {
            padding: 10px;
            border-bottom: 1px solid #ecf0f1;
        }
        .games-table tr:hover {
            background-color: #f8f9fa;
        }
        .win {
            background-color: #d4edda;
            font-weight: bold;
        }
        .no-results {
            padding: 20px;
            text-align: center;
            color: #666;
            font-size: 16px;
        }
        .error {
            background-color: #f8d7da;
            color: #721c24;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .info {
            background-color: #d1ecf1;
            color: #0c5460;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>NFL Team Wins Finder</h1>
        <p style="text-align: center; color: #666; margin-bottom: 20px;">
            Select teams to find    weeks where all selected teams won their games
        </p>

        <form method="POST" class="form-section">
            <h3>Select Teams:</h3>
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
    </div>
    <script src="/assets/sorttable.js"></script>
</body>
</html>