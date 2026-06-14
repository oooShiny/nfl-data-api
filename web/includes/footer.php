        <?php if (empty($plain_layout)): ?>
        </div>
        <?php endif; ?>
    </div>
    <footer class="site-footer">
        <div class="footer-top">
            <div class="wordmark">NFL<span class="gold">DATA</span>.ORG</div>
            <div class="copyright">&copy; <?= date('Y') ?> nfldata.org &mdash; Built on public NFL play-by-play data.</div>
        </div>
    </footer>
    <?php
    $ticker_items = $ticker_items ?? [
        'NFL DATA — 100+ SEASONS OF HISTORY',
        'TEAM, PLAYER, AND PLAY-LEVEL STATS',
        'HEAD-TO-HEAD MATCHUP EXPLORER',
        'ERA-ADJUSTED COMPARISONS',
        'FREE PUBLIC API AT API.NFLDATA.ORG',
    ];
    $ticker_string = implode('  &#9670;  ', $ticker_items);
    ?>
    <div class="ticker">
        <div class="ticker-slug">
            <span class="slug-label">LIVE</span>
            <span class="dots"><span></span><span></span><span></span></span>
        </div>
        <div class="ticker-track-wrap">
            <div class="ticker-track">
                <span><?= $ticker_string ?>&nbsp;&nbsp;&#9670;&nbsp;&nbsp;</span>
                <span><?= $ticker_string ?>&nbsp;&nbsp;&#9670;&nbsp;&nbsp;</span>
            </div>
        </div>
    </div>
    <script src="/assets/sorttable.js"></script>
    <script>
        document.querySelectorAll('[data-tab]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var group = btn.closest('[data-tab-group]') || document;
                var target = btn.getAttribute('data-tab');

                group.querySelectorAll('[data-tab]').forEach(function (b) {
                    b.classList.remove('active');
                });
                group.querySelectorAll('[data-tabpanel]').forEach(function (p) {
                    p.classList.remove('active');
                });

                btn.classList.add('active');
                var panel = group.querySelector('[data-tabpanel="' + target + '"]');
                if (panel) {
                    panel.classList.add('active');
                }
            });
        });
    </script>
</body>
</html>
