<?php
declare(strict_types=1);

// Public read-only preflight: php reviewed-empty-tables.php REVIEW.json SOURCE.db
// Fingerprints cover table/index/trigger definitions in type/name order, joined
// with a newline. A reviewed table must remain empty; nothing is dropped.
function reviewedEmptyTables(string $planPath, string $databasePath): array {
    if (!is_file($planPath) || !is_file($databasePath) || is_link($databasePath)) {
        throw new RuntimeException('Expected regular review and source database files');
    }
    $plan = json_decode(file_get_contents($planPath), true, flags: JSON_THROW_ON_ERROR);
    if (!is_array($plan) || !array_is_list($plan)) { throw new RuntimeException('Review must be a list'); }
    $database = new SQLite3($databasePath, SQLITE3_OPEN_READONLY);
    $database->enableExceptions(true);
    $names = [];
    try {
        foreach ($plan as $entry) {
            if (!is_array($entry) || count($entry) !== 2 ||
                !preg_match('/^oc_[a-z0-9_]+$/D', $entry['name'] ?? '') ||
                !preg_match('/^[a-f0-9]{64}$/D', $entry['schema_sha256'] ?? '') ||
                in_array($entry['name'], $names, true)) {
                throw new RuntimeException('Invalid or duplicate reviewed table');
            }
            $name = $entry['name'];
            $statement = $database->prepare('SELECT type,sql FROM sqlite_master WHERE tbl_name=:name ORDER BY type,name');
            $statement->bindValue(':name', $name, SQLITE3_TEXT);
            $result = $statement->execute();
            $definitions = []; $hasTable = false;
            while ($row = $result->fetchArray(SQLITE3_ASSOC)) {
                if ($row['type'] === 'trigger') { throw new RuntimeException('Reviewed legacy triggers require separate conversion'); }
                $hasTable = $hasTable || $row['type'] === 'table';
                $definitions[] = $row['sql'] ?? '';
            }
            $result->finalize();
            $statement->close();
            if (!$hasTable || hash('sha256', implode("\n", $definitions)) !== $entry['schema_sha256']) {
                throw new RuntimeException('Reviewed table schema changed or is missing: ' . $name);
            }
            if ((int)$database->querySingle('SELECT COUNT(*) FROM "' . $name . '"') !== 0) {
                throw new RuntimeException('Reviewed table is no longer empty: ' . $name);
            }
            $names[] = $name;
        }
    } finally {
        $database->close();
    }
    sort($names, SORT_STRING);
    return $names;
}

if (realpath($_SERVER['SCRIPT_FILENAME'] ?? '') === __FILE__) {
    try {
        if ($argc !== 3) { throw new RuntimeException('Usage: reviewed-empty-tables.php REVIEW.json SOURCE.db'); }
        echo json_encode(reviewedEmptyTables($argv[1], $argv[2]), JSON_THROW_ON_ERROR), "\n";
    } catch (Throwable $error) {
        fwrite(STDERR, $error->getMessage() . "\n");
        exit(1);
    }
}
