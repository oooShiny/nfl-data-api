<?php
// Expects $page_title and optional $page_subtitle to be set before include.
$page_title = $page_title ?? 'NFL Data Tools and Visualizations';

$nav_links = [
    '/' => 'Home',
    '/built_with.php' => 'Built with This Data',
    '/data_coverage.php' => 'Data Coverage',
    'https://nfldata-api.br0wn.net/docs' => 'API Docs',
];

$current_page = basename($_SERVER['PHP_SELF']);
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><?= htmlspecialchars($page_title) ?> - nfldata.br0wn.net</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Oswald:wght@500;600;700&family=Barlow+Semi+Condensed:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/assets/theme.css">
    <link rel="icon" type="image/png" href="/favicon-96x96.png" sizes="96x96" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <link rel="shortcut icon" href="/favicon.ico" />
    <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png" />
    <meta name="apple-mobile-web-app-title" content="NFL Data" />
    <link rel="manifest" href="/site.webmanifest" />
</head>
<body>
<header class="broadcast-header">
    <div class="header-bar">
        <div class="header-row">
            <a href="#" class="logo">
<pre>
▗▖  ▗▖▗▄▄▄▖▗▖       ▗▄▄▄  ▗▄▖▗▄▄▄▖▗▄▖
▐▛▚▖▐▌▐▌   ▐▌       ▐▌  █▐▌ ▐▌ █ ▐▌ ▐▌
▐▌ ▝▜▌▐▛▀▀▘▐▌       ▐▌  █▐▛▀▜▌ █ ▐▛▀▜▌
▐▌  ▐▌▐▌   ▐▙▄▄▖    ▐▙▄▄▀▐▌ ▐▌ █ ▐▌ ▐▌
</pre>
            </a>
        </div>
    </div>
    <div class="silver-bar">
        <nav class="site-nav" aria-label="Main">
            <?php foreach ($nav_links as $href => $label):
                $is_external = str_starts_with($href, 'http');
                $is_active = !$is_external && (
                                ($href === '/' && $current_page === 'index.php')
                                || ($href !== '/' && basename($href) === $current_page)
                        );
                ?>
                <a href="<?= $href ?>" class="<?= $is_active ? 'active' : '' ?>"<?= $is_external ? ' target="_blank" rel="noopener"' : '' ?>><?= htmlspecialchars($label) ?></a>
            <?php endforeach; ?>
        </nav>
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
