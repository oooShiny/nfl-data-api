<?php
// Expects $page_title and optional $page_subtitle to be set before include.
$page_title = $page_title ?? 'NFL Data Tools and Visualizations';
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><?= htmlspecialchars($page_title) ?> - nfldata.org</title>
    <link rel="stylesheet" href="/assets/style.css">
</head>
<body>
    <div class="container">
        <nav class="site-nav">
            <a href="/">Home</a>
            <a href="/team_wins_finder.php">Team Wins Finder</a>
            <a href="/head_to_head.php">Head-to-Head</a>
            <a href="/team_situation_finder.php">Team Situation Finder</a>
            <a href="/player_explorer.php">Player Explorer</a>
            <a href="/qb_comparator.php">QB Comparator</a>
            <a href="/play_explorer.php">Play Explorer</a>
            <a href="/era_dashboard.php">Era Dashboard</a>
            <a href="/draft_value.php">Draft Value</a>
            <a href="/team_snapshot.php">Team Snapshot</a>
            <a href="/trade_browser.php">Trade History</a>
            <a href="/combine_explorer.php">Combine vs Production</a>
        </nav>
        <h1><?= htmlspecialchars($page_title) ?></h1>
        <?php if (!empty($page_subtitle)): ?>
            <p class="subtitle"><?= $page_subtitle ?></p>
        <?php endif; ?>
