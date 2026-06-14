<?php
// Expects $page_title and optional $page_subtitle to be set before include.
$page_title = $page_title ?? 'NFL Data Tools and Visualizations';

$nav_links = [
    '/' => 'Home',
    '/team_wins_finder.php' => 'Team Wins Finder',
    '/head_to_head.php' => 'Head-to-Head',
    '/team_situation_finder.php' => 'Team Situation Finder',
    '/player_explorer.php' => 'Player Explorer',
    '/qb_comparator.php' => 'QB Comparator',
    '/play_explorer.php' => 'Play Explorer',
    '/era_dashboard.php' => 'Era Dashboard',
    '/draft_value.php' => 'Draft Value',
    '/team_snapshot.php' => 'Team Snapshot',
    '/trade_browser.php' => 'Trade History',
    '/combine_explorer.php' => 'Combine vs Production',
];

$current_page = basename($_SERVER['PHP_SELF']);
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><?= htmlspecialchars($page_title) ?> - nfldata.org</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Oswald:wght@500;600;700&family=Barlow+Semi+Condensed:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/assets/style.css">
</head>
<body>
    <div class="scanlines"></div>
    <header class="broadcast-header">
        <div class="header-bar">
            <div class="header-row">
                <a href="/" class="logo">
                    <span class="logo-mark">
                        <span>
                            <span></span>
                            <span></span>
                            <span></span>
                        </span>
                    </span>
                    <span class="logo-text">NFL<span class="gold">DATA</span><span class="dim">.ORG</span></span>
                </a>
                <div class="header-spacer"></div>
                <div class="header-badge"><span><span>V1 &middot; LIVE</span></span></div>
            </div>
        </div>
        <div class="pinstripe"></div>
        <div class="silver-bar">
            <div class="silver-row">
                <nav class="site-nav">
                    <?php foreach ($nav_links as $href => $label):
                        $is_active = ($href === '/' && $current_page === 'index.php')
                            || ($href !== '/' && basename($href) === $current_page);
                    ?>
                        <a href="<?= $href ?>" class="<?= $is_active ? 'active' : '' ?>"><?= htmlspecialchars($label) ?></a>
                    <?php endforeach; ?>
                </nav>
            </div>
        </div>
    </header>
    <div class="container<?= !empty($plain_layout) ? ' plain-layout' : '' ?>">
        <?php if (empty($plain_layout)): ?>
        <div class="page-title-bar">
            <h1><?= htmlspecialchars($page_title) ?></h1>
            <?php if (!empty($page_subtitle)): ?>
                <p class="subtitle"><?= $page_subtitle ?></p>
            <?php endif; ?>
        </div>
        <div class="page-pinstripe"></div>
        <div class="page-body">
        <?php endif; ?>
