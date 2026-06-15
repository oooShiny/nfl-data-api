<?php
require_once __DIR__ . '/includes/api.php';

$page_title = 'Stuff Built with this Data';
$page_subtitle = 'Tools, dashboards, and projects built on the nfldata.org API &mdash; including the ones above.';

const SUBMISSION_TO_EMAIL = 'arbrown83@gmail.com';

$status = null;
$old = ['name' => '', 'url' => '', 'description' => '', 'contact' => ''];

if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['project_name'])) {
    $old['name'] = trim($_POST['project_name'] ?? '');
    $old['url'] = trim($_POST['project_url'] ?? '');
    $old['description'] = trim($_POST['project_description'] ?? '');
    $old['contact'] = trim($_POST['contact'] ?? '');
    $honeypot = trim($_POST['website'] ?? '');

    if ($honeypot !== '') {
        // Bot caught by honeypot field; pretend it worked.
        $status = 'success';
        $old = ['name' => '', 'url' => '', 'description' => '', 'contact' => ''];
    } elseif ($old['name'] === '' || $old['url'] === '' || $old['description'] === '') {
        $status = 'error';
    } else {
        $body = "New \"Built with nfldata.org\" submission:\n\n"
            . "Name: {$old['name']}\n"
            . "URL: {$old['url']}\n"
            . "Contact: {$old['contact']}\n\n"
            . "Description:\n{$old['description']}\n";

        $headers = "From: nfldata.org <noreply@nfldata.org>\r\n";
        if ($old['contact'] !== '' && filter_var($old['contact'], FILTER_VALIDATE_EMAIL)) {
            $headers .= 'Reply-To: ' . $old['contact'] . "\r\n";
        }

        $sent = @mail(SUBMISSION_TO_EMAIL, 'New showcase submission: ' . $old['name'], $body, $headers);

        if ($sent) {
            $status = 'success';
            $old = ['name' => '', 'url' => '', 'description' => '', 'contact' => ''];
        } else {
            $status = 'mail_error';
        }
    }
}

require __DIR__ . '/includes/header.php';
?>

<?php require __DIR__ . '/includes/showcase_grid.php'; ?>

<!-- ===== SUBMISSION FORM ===== -->
<section style="margin-top: 38px; margin-bottom: 38px;">
    <div class="section-header blue">
        <h2>Submit Your Project</h2>
        <span class="endpoint-label">Built something with the data?</span>
    </div>
    <div class="page-pinstripe"></div>
    <div class="section-body" style="padding: 16px 20px;">
        <p style="font-family: 'Barlow Semi Condensed', sans-serif; font-size: 14.5px; color: var(--text-muted); margin: 0 0 14px;">Built a tool, dashboard, model, or app on top of the nfldata.org API? Tell us about it and we may feature it above.</p>

        <?php if ($status === 'success'): ?>
            <div class="info">Thanks! Your submission has been sent &mdash; we'll take a look.</div>
        <?php elseif ($status === 'error'): ?>
            <div class="error">Please fill in the project name, URL, and a short description.</div>
        <?php elseif ($status === 'mail_error'): ?>
            <div class="error">Sorry, something went wrong sending your submission. Please try again later.</div>
        <?php endif; ?>

        <form method="POST" class="form-section">
            <div class="form-row" style="grid-column: 1 / -1; position: absolute; left: -9999px;" aria-hidden="true">
                <label for="website">Leave this field empty</label>
                <input type="text" id="website" name="website" tabindex="-1" autocomplete="off">
            </div>
            <div class="form-row">
                <label for="project_name">Project Name</label>
                <input type="text" id="project_name" name="project_name" value="<?= htmlspecialchars($old['name']) ?>" required>
            </div>
            <div class="form-row">
                <label for="project_url">Project URL</label>
                <input type="text" id="project_url" name="project_url" value="<?= htmlspecialchars($old['url']) ?>" placeholder="https://" required>
            </div>
            <div class="form-row">
                <label for="contact">Your Contact (optional)</label>
                <input type="text" id="contact" name="contact" value="<?= htmlspecialchars($old['contact']) ?>" placeholder="email or @handle">
            </div>
            <div class="form-row" style="grid-column: 1 / -1;">
                <label for="project_description">Description</label>
                <input type="text" id="project_description" name="project_description" value="<?= htmlspecialchars($old['description']) ?>" placeholder="What does it do, and what nfldata.org endpoints does it use?" required>
            </div>
            <div class="form-row">
                <button type="submit" class="submit-btn">Submit</button>
            </div>
        </form>
    </div>
</section>

<?php require __DIR__ . '/includes/footer.php'; ?>
