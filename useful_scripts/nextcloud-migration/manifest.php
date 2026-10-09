<?php
declare(strict_types=1);
// Match the existing mirror exclusions, but reject unsafe traversal before sync.
function walk(string $directory, string $root, array $ancestors = []): Generator {
    $real = realpath($directory);
    if ($real === false || ($real !== $root && !str_starts_with($real, $root . '/')) || isset($ancestors[$real])) {
        throw new RuntimeException('Escaping or cyclic directory link');
    }
    $ancestors[$real] = true;
    $names = scandir($directory);
    if ($names === false) { throw new RuntimeException('Unreadable directory'); }
    foreach ($names as $name) {
        if ($name === '.' || $name === '..') { continue; }
        $path = $directory . '/' . $name;
        $target = realpath($path);
        if ($target === false || !str_starts_with($target, $root . '/') || !is_readable($path)) {
            throw new RuntimeException('Unreadable or escaping source path');
        }
        if (is_dir($path)) { yield from walk($path, $root, $ancestors); }
        elseif (is_file($path)) { yield $path; }
        else { throw new RuntimeException('Unsupported source file type'); }
    }
}
try {
    $root = realpath(getenv('NC_MIGRATION_SOURCE') ?: '/source');
    if ($root === false) { throw new RuntimeException('Missing source root'); }
    $patterns = ['*/cache/*', '*/tmp/*', '*/appdata_*/*', '*/files_trashbin/*', '*/files_versions/*', 'nextcloud.log*'];
    $rows = [];
    foreach (walk($root, $root) as $path) {
        $relative = substr($path, strlen($root) + 1);
        $excluded = false;
        foreach ($patterns as $pattern) { if (fnmatch($pattern, $relative)) { $excluded = true; break; } }
        if (!$excluded) { $rows[] = ['key' => 'nextcloud-data/' . $relative, 'size' => filesize($path)]; }
    }
    echo json_encode($rows, JSON_THROW_ON_ERROR), "\n";
} catch (Throwable $e) {
    fwrite(STDERR, "Source traversal failed; no complete manifest produced.\n");
    exit(1);
}
