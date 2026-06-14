<?php
require_once __DIR__ . '/includes/api.php';

$page_title = 'NFL Data Tools and Visualizations';
$plain_layout = true;

$meta = nfl_api_get_cached('/meta', [], 86400);
$seasonCount = count($meta['seasons'] ?? []);
$teamCount = count($meta['teams'] ?? []);

$ticker_items = [
    'PASS YDS: T.BRADY 89,216 (1999-PRESENT)',
    'NORMALIZED: ONE SCHEMA, 1999-PRESENT',
    'NO API KEY REQUIRED — JUST GET',
    'PLAYS: 1,279,000+ SINCE 1999',
    'FREE &amp; OPEN — API.NFLDATA.ORG/DOCS',
    'GAMES: 19,900+ WITH BOX SCORES',
    'STABLE IDS &middot; ISO DATES &middot; TYPED NUMBERS',
];

require __DIR__ . '/includes/header.php';
?>

<!-- ===== HERO ===== -->
<section class="hero">
    <div class="hero-panel">
        <div class="hero-tag">
            <span class="dot"></span>
            <span>REST + JSON &middot; No API Key</span>
        </div>
        <h1>A Century of<br>NFL Data,<br><span class="gold">One Clean API.</span></h1>
        <p>A century of football data, compiled over decades by the people who love it most &mdash; then cleaned, normalized, and reshaped into one predictable format. Games, players, teams, play-by-play. Free, no signup.</p>
        <div class="hero-cta">
            <a href="https://api.nfldata.org/docs" class="btn-gold">Read the Docs &rarr;</a>
            <a href="#quickstart" class="btn-ghost">Quickstart</a>
        </div>
    </div>
    <div class="tape-panel">
        <div class="tape-header">
            <span class="tape-label">&#9679; The Tape</span>
            <span class="tape-file">request.sh</span>
            <button class="copy-btn" type="button" data-copy="curl https://api.nfldata.org/v1/players/00-0033873/stats?season=2023&amp;week=1">COPY</button>
        </div>
        <div class="code-block">
            <div class="dim"># no key, no headers</div>
            <div><span class="verb">curl</span> https://api.nfldata.org/v1/players/00-0033873/stats
                <br>?season=<span class="num">2023</span>
                <br>&amp;week=<span class="num">1</span></div>
        </div>
        <div class="code-divider"></div>
        <div class="code-block">
            <div class="brace">{</div>
            <div>&nbsp;&nbsp;<span class="key">"player_name"</span>: <span class="str">"Patrick Mahomes"</span>,</div>
            <div>&nbsp;&nbsp;<span class="key">"recent_team"</span>: <span class="str">"KC"</span>,</div>
            <div>&nbsp;&nbsp;<span class="key">"season"</span>: <span class="num">2023</span>,</div>
            <div>&nbsp;&nbsp;<span class="key">"week"</span>: <span class="num">1</span>,</div>
            <div>&nbsp;&nbsp;<span class="key">"passing_yards"</span>: <span class="num">226</span>,</div>
            <div>&nbsp;&nbsp;<span class="key">"passing_tds"</span>: <span class="num">2</span></div>
            <div class="brace">}</div>
        </div>
    </div>
</section>

<!-- ===== COVERAGE CHIPS ===== -->
<section class="coverage-chips">
    <div class="chip">
        <div class="chip-value"><?= htmlspecialchars((string) $seasonCount) ?></div>
        <div class="chip-label">Seasons 1999&ndash;Present</div>
    </div>
    <div class="chip">
        <div class="chip-value">20K</div>
        <div class="chip-label">Games &amp; box scores</div>
    </div>
    <div class="chip">
        <div class="chip-value">25K</div>
        <div class="chip-label">Players all-time</div>
    </div>
    <div class="chip">
        <div class="chip-value">1.3M</div>
        <div class="chip-label">Plays since 1999</div>
    </div>
    <div class="chip">
        <div class="chip-value"><?= htmlspecialchars((string) $teamCount) ?></div>
        <div class="chip-label">Teams + defunct</div>
    </div>
</section>

<!-- ===== REPLAY (MESSY VS CLEAN) ===== -->
<section class="replay-section">
    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 14px;">
        <span class="gold-pill">Replay</span>
        <h2 style="font-family: 'Oswald', sans-serif; font-weight: 600; font-size: 27px; text-transform: uppercase; color: #fff; margin: 0; letter-spacing: 0.01em;">The messy part is already done</h2>
    </div>
    <p style="font-family: 'Barlow Semi Condensed', sans-serif; font-size: 15.5px; color: var(--text-muted); line-height: 1.5; margin: 0 0 16px; max-width: 720px;">The data's all there, thanks to years of community work &mdash; it just doesn't agree with itself. The same player, team, and date show up a dozen different ways across sources. Every spelling, code, and format gets reconciled into one canonical record.</p>
    <div class="replay-grid">
        <div class="replay-messy">
            <div class="replay-title">What's Out There</div>
            <div class="messy-field">
                <div>
                    <div class="messy-field-name">PLAYER NAME</div>
                    <div class="messy-values">
                        <span>"P.Mahomes"</span>
                        <span>"Mahomes, Patrick"</span>
                        <span>"mahomes_pat_01"</span>
                    </div>
                </div>
                <div>
                    <div class="messy-field-name">TEAM</div>
                    <div class="messy-values">
                        <span>"KC"</span>
                        <span>"KAN"</span>
                        <span>"Kansas City"</span>
                    </div>
                </div>
                <div>
                    <div class="messy-field-name">GAME DATE</div>
                    <div class="messy-values">
                        <span>"9/7/23"</span>
                        <span>"Sep 7 2023"</span>
                        <span>"2023-09-07"</span>
                    </div>
                </div>
                <div>
                    <div class="messy-field-name">PASSING YARDS</div>
                    <div class="messy-values">
                        <span>"4,183"</span>
                        <span>4183.0</span>
                        <span>null</span>
                    </div>
                </div>
            </div>
        </div>
        <div class="replay-arrow">&rarr;</div>
        <div class="replay-clean">
            <div class="replay-title">What You Get</div>
            <div class="code-block" style="padding: 0;">
                <div class="brace">{</div>
                <div>&nbsp;&nbsp;<span class="key">"player_id"</span>: <span class="str">"00-0033873"</span>,</div>
                <div>&nbsp;&nbsp;<span class="key">"name"</span>:&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<span class="str">"Patrick Mahomes"</span>,</div>
                <div>&nbsp;&nbsp;<span class="key">"team"</span>:&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<span class="str">"KC"</span>,</div>
                <div>&nbsp;&nbsp;<span class="key">"game_date"</span>: <span class="str">"2023-09-07"</span>,</div>
                <div>&nbsp;&nbsp;<span class="key">"pass_yds"</span>:&nbsp;&nbsp;<span class="num">4183</span></div>
                <div class="brace">}</div>
            </div>
            <div class="clean-footnote">STABLE IDs &middot; ISO DATES &middot; TYPED NUMBERS &middot; ONE TEAM CODE</div>
        </div>
    </div>
</section>

<!-- ===== THE ASSIST (CREDIT) ===== -->
<section>
    <div class="credit-panel">
        <div class="credit-badge">
            <span class="label-sm">The</span>
            <span class="label-lg">Assist</span>
        </div>
        <div class="credit-body">
            <p>None of this exists without the people who compiled it &mdash; the statisticians, archivists, and open-source communities who spent years digging up box scores, charting plays, and keeping the record straight. nfldata.org doesn't replace their work. It just takes what they built and irons out the formatting wrinkles so it's easier to query.</p>
        </div>
    </div>
</section>

<!-- ===== PASSING LEADERS ===== -->
<section id="leaders" style="margin-top: 38px;">
    <div class="section-header red">
        <h2>Passing Leaders (1999&ndash;Present)</h2>
        <span class="endpoint-label">GET /v1/stats/season</span>
    </div>
    <div class="page-pinstripe"></div>
    <div class="section-body">
        <div class="leaders-row leaders-header">
            <span></span>
            <span>Player</span>
            <span class="text-right">Years</span>
            <span class="text-right">Pass Yds</span>
        </div>
        <?php
        $leaders = [
            ['Tom Brady', 23, 89216],
            ['Drew Brees', 20, 80428],
            ['Peyton Manning', 16, 68201],
            ['Aaron Rodgers', 21, 66267],
            ['Matthew Stafford', 17, 64578],
            ['Ben Roethlisberger', 18, 64128],
            ['Philip Rivers', 18, 63978],
        ];
        foreach ($leaders as $i => $p): ?>
        <div class="leaders-row">
            <span class="leaders-rank"><?= $i + 1 ?></span>
            <span class="leaders-name"><?= htmlspecialchars($p[0]) ?></span>
            <span class="leaders-years"><?= $p[1] ?></span>
            <span class="leaders-yards"><?= number_format($p[2]) ?></span>
        </div>
        <?php endforeach; ?>
        <div class="leaders-footer">
            <span class="shield">ND</span>
            <span class="note">One query &middot; instant leaderboard &middot; any stat, any span</span>
        </div>
    </div>
</section>

<!-- ===== QUICKSTART ===== -->
<section id="quickstart" style="margin-top: 38px;" data-tab-group>
    <div class="quickstart-grid">
        <div>
            <div class="gold-pill" style="margin-bottom: 13px;">The Playbook</div>
            <h2 style="font-family: 'Oswald', sans-serif; font-weight: 600; font-size: 27px; text-transform: uppercase; color: #fff; margin: 0 0 12px; line-height: 1.05;">Zero to first query in under a minute</h2>
            <p style="font-family: 'Barlow Semi Condensed', sans-serif; font-size: 15.5px; color: var(--text-muted); line-height: 1.5; margin: 0;">Pick an endpoint, send a plain GET, read the JSON. No key, no signup, no SDK.</p>
            <div class="quickstart-steps">
                <div class="step">
                    <span class="step-num">1</span>
                    <span>Pick an endpoint from the reference.</span>
                </div>
                <div class="step">
                    <span class="step-num">2</span>
                    <span>Send a plain GET &mdash; no keys, no auth headers.</span>
                </div>
                <div class="step">
                    <span class="step-num">3</span>
                    <span>Parse the JSON &mdash; same shape every time.</span>
                </div>
            </div>
        </div>
        <div class="tape-panel">
            <div class="tab-bar" style="padding: 7px 8px; background: linear-gradient(180deg, rgba(30,60,118,0.7), rgba(12,28,62,0.7)); border-bottom: 2px solid var(--border-primary);">
                <button type="button" class="tab-btn active" data-tab="curl">cURL</button>
                <button type="button" class="tab-btn" data-tab="python">Python</button>
                <button type="button" class="tab-btn" data-tab="js">JavaScript</button>
            </div>
            <div class="code-block tab-panel active" data-tabpanel="curl">
                <div class="dim"># no key, no headers &mdash; just GET</div>
                <div><span class="verb">curl</span> https://api.nfldata.org/v1/players/00-0033873/stats?season=<span class="num">2023</span>&amp;week=<span class="num">1</span></div>
            </div>
            <div class="code-block tab-panel" data-tabpanel="python">
                <div><span class="key">import</span> requests</div>
                <div>&nbsp;</div>
                <div>r = requests.<span class="str">get</span>(</div>
                <div>&nbsp;&nbsp;&nbsp;&nbsp;<span class="str">"https://api.nfldata.org/v1/players/00-0033873/stats?season=2023&amp;week=1"</span></div>
                <div>)</div>
                <div><span class="str">print</span>(r.json()[<span class="str">"data"</span>][<span class="num">0</span>][<span class="str">"passing_yards"</span>])&nbsp;&nbsp;<span class="dim"># 226</span></div>
            </div>
            <div class="code-block tab-panel" data-tabpanel="js">
                <div><span class="key">const</span> res = <span class="key">await</span> <span class="str">fetch</span>(</div>
                <div>&nbsp;&nbsp;<span class="str">"https://api.nfldata.org/v1/players/00-0033873/stats?season=2023&amp;week=1"</span></div>
                <div>);</div>
                <div><span class="key">const</span> data = <span class="key">await</span> res.<span class="str">json</span>();</div>
                <div>console.<span class="str">log</span>(data.data[0].passing_yards); <span class="dim">// 226</span></div>
            </div>
        </div>
    </div>
</section>

<!-- ===== THE LINEUP (ENDPOINTS) ===== -->
<section id="endpoints" style="margin-top: 38px;">
    <div class="section-header blue">
        <h2>The Lineup</h2>
        <a href="https://api.nfldata.org/docs" style="font-family: 'Oswald', sans-serif; font-weight: 600; font-size: 13px; letter-spacing: 0.06em; text-transform: uppercase;">Full Reference &rarr;</a>
    </div>
    <div class="page-pinstripe"></div>
    <div class="section-body">
        <?php
        $endpoints = [
            ['/v1/games', 'Results, scores &amp; box scores'],
            ['/v1/players/{gsis_id}', 'Bios &amp; career info for a player'],
            ['/v1/players/{gsis_id}/stats', 'Season-by-season stat lines for a player'],
            ['/v1/games/head-to-head', 'Series history between two teams'],
            ['/v1/stats/season', 'League-wide season stat leaders'],
            ['/v1/plays', 'Play-by-play, 1999 to present'],
        ];
        foreach ($endpoints as $ep): ?>
        <div class="endpoint-row">
            <span class="method-badge">GET</span>
            <div class="endpoint-meta">
                <code class="endpoint-path"><?= $ep[0] ?></code>
                <span class="endpoint-desc"><?= $ep[1] ?></span>
            </div>
        </div>
        <?php endforeach; ?>
    </div>
</section>

<!-- ===== SHOWCASE ===== -->
<section id="showcase" style="margin-top: 38px;">
    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px;">
        <span class="gold-pill">Highlights</span>
        <h2 style="font-family: 'Oswald', sans-serif; font-weight: 600; font-size: 27px; text-transform: uppercase; color: #fff; margin: 0;">Stuff built with the data</h2>
    </div>
    <div class="grid">
        <div class="card">
            <a href="team_wins_finder.php">
                <div class="card-content">
                    <h3 class="card-title">Team Wins Finder</h3>
                    <p>Find any week(s) when selected teams all won their games.</p>
                </div>
            </a>
        </div>
        <div class="card">
            <a href="head_to_head.php">
                <div class="card-content">
                    <h3 class="card-title">Head-to-Head Matchup Explorer</h3>
                    <p>See how two teams have fared against each other &mdash; results, biggest wins, and top performances.</p>
                </div>
            </a>
        </div>
        <div class="card">
            <a href="player_explorer.php">
                <div class="card-content">
                    <h3 class="card-title">Player Career Explorer</h3>
                    <p>Look up a player's bio, season-by-season stats, and Next Gen Stats.</p>
                </div>
            </a>
        </div>
        <div class="card">
            <a href="qb_comparator.php">
                <div class="card-content">
                    <h3 class="card-title">QB Efficiency Comparator</h3>
                    <p>Compare quarterbacks side by side for a given season.</p>
                </div>
            </a>
        </div>
        <div class="card">
            <a href="play_explorer.php">
                <div class="card-content">
                    <h3 class="card-title">Drive/Play Explorer</h3>
                    <p>Browse every play of a game with EPA, WPA, and charting tags.</p>
                </div>
            </a>
        </div>
        <div class="card">
            <a href="team_situation_finder.php">
                <div class="card-content">
                    <h3 class="card-title">Team Situation Finder</h3>
                    <p>Find games matching specific situations &mdash; blowouts, comebacks, shootouts, and more.</p>
                </div>
            </a>
        </div>
        <div class="card">
            <a href="era_dashboard.php">
                <div class="card-content">
                    <h3 class="card-title">Era Comparison Dashboard</h3>
                    <p>League-wide trends by season since 1999: scoring, pass rate, and efficiency.</p>
                </div>
            </a>
        </div>
        <div class="card">
            <a href="draft_value.php">
                <div class="card-content">
                    <h3 class="card-title">Draft Pick Value Tracker</h3>
                    <p>See how a draft class turned out &mdash; career games and fantasy production by pick.</p>
                </div>
            </a>
        </div>
        <div class="card">
            <a href="team_snapshot.php">
                <div class="card-content">
                    <h3 class="card-title">Team Cap &amp; Roster Snapshot</h3>
                    <p>Biggest contracts and roster makeup for a team, by season.</p>
                </div>
            </a>
        </div>
        <div class="card">
            <a href="trade_browser.php">
                <div class="card-content">
                    <h3 class="card-title">Trade History Browser</h3>
                    <p>Browse player and draft pick trades by team and season.</p>
                </div>
            </a>
        </div>
        <div class="card">
            <a href="combine_explorer.php">
                <div class="card-content">
                    <h3 class="card-title">Combine vs. Production</h3>
                    <p>See how combine measurables compare to career NFL production.</p>
                </div>
            </a>
        </div>
    </div>
</section>

<!-- ===== RAW DATA ===== -->
<section style="margin-top: 38px;">
    <div class="section-header blue">
        <h2>Raw NFL Data</h2>
        <span class="endpoint-label">Downloadable CSVs</span>
    </div>
    <div class="page-pinstripe"></div>
    <div class="section-body" style="padding: 16px 20px;">
        <p style="font-family: 'Barlow Semi Condensed', sans-serif; font-size: 14.5px; color: var(--text-muted); margin: 0 0 14px;">Each section below has downloadable CSV files with raw NFL data collected from various tools and sources.</p>
        <div class="grid">
            <div class="card">
                <a href="game-logs">
                    <div class="card-content">
                        <h3 class="card-title">Game Logs (1970-2022)</h3>
                        <p>CSV files with data from every game in each season.</p>
                    </div>
                </a>
            </div>
            <div class="card">
                <a href="game-scoring">
                    <div class="card-content">
                        <h3 class="card-title">Game Scoring Data (1970-2007)</h3>
                        <p>Data from the "Scoring" section of the boxscore pages on Pro Football Reference.</p>
                    </div>
                </a>
            </div>
            <div class="card">
                <a href="play-by-play">
                    <div class="card-content">
                        <h3 class="card-title">Play By Play Data (2000-2023)</h3>
                        <p>Detailed play-by-play logs broken down by season.</p>
                    </div>
                </a>
            </div>
        </div>
    </div>
</section>

<!-- ===== FROM THE BOOTH ===== -->
<section style="margin-top: 38px; margin-bottom: 38px;">
    <div class="credit-panel glow">
        <div class="credit-badge">
            <span class="label-sm">From the</span>
            <span class="label-lg">Booth</span>
        </div>
        <div class="credit-body">
            <p>It's just me &mdash; and to be clear, I didn't compile any of this. Statisticians, archivists, and the open-source football community spent years digging up box scores and charting plays. I just got tired of re-cleaning their work for every side project, so I built the clean layer once and put it behind a free API. All the credit for the data goes to them. If this saves you an afternoon, that's the whole reward.</p>
            <div class="credit-sign">&mdash; The nfldata guy</div>
        </div>
    </div>
</section>

<script>
    document.querySelectorAll('.copy-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var text = btn.getAttribute('data-copy');
            if (navigator.clipboard) {
                navigator.clipboard.writeText(text);
            }
            var original = btn.textContent;
            btn.textContent = 'COPIED';
            setTimeout(function () { btn.textContent = original; }, 1600);
        });
    });
</script>

<?php require __DIR__ . '/includes/footer.php'; ?>
