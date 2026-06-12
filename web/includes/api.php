<?php
// Shared helper for calling api.nfldata.org from frontend pages.

const NFL_API_BASE = 'https://api.nfldata.org/v1';

/**
 * GET a path from the nfldata API and decode the JSON response.
 * Returns null on any transport/decode error so callers can show
 * a friendly message instead of a fatal.
 */
function nfl_api_get(string $path, array $params = []): ?array {
    $url = NFL_API_BASE . $path;
    $params = array_filter($params, fn($v) => $v !== null && $v !== '');
    if (!empty($params)) {
        $url .= '?' . http_build_query($params);
    }

    $context = stream_context_create([
        'http' => [
            'method' => 'GET',
            'timeout' => 15,
            'header' => "User-Agent: nfldata.org-frontend\r\n",
            'ignore_errors' => true,
        ],
    ]);

    $response = @file_get_contents($url, false, $context);
    if ($response === false) {
        return null;
    }

    $decoded = json_decode($response, true);
    return is_array($decoded) ? $decoded : null;
}

/**
 * Like nfl_api_get(), but caches the response to a local file for $ttl
 * seconds. Useful for pages that aggregate data across many seasons.
 */
function nfl_api_get_cached(string $path, array $params = [], int $ttl = 43200): ?array {
    $cacheDir = __DIR__ . '/../cache';
    if (!is_dir($cacheDir)) {
        mkdir($cacheDir, 0775, true);
    }

    $key = md5($path . '?' . http_build_query($params));
    $file = $cacheDir . '/' . $key . '.json';

    if (is_file($file) && (time() - filemtime($file)) < $ttl) {
        $cached = json_decode(file_get_contents($file), true);
        if (is_array($cached)) {
            return $cached;
        }
    }

    $result = nfl_api_get($path, $params);
    if ($result !== null) {
        file_put_contents($file, json_encode($result));
    }
    return $result;
}
