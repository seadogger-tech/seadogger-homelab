<?php
declare(strict_types=1);

// Deliberately independent of Nextcloud bootstrap: checkpoint/rollback must not
// open a second application connection to the database being replaced.
umask(0077);
function fail(string $message): never { throw new RuntimeException($message); }
function ident(string $name): string { return '"' . str_replace('"', '""', $name) . '"'; }
function counts(PDO $db, string $engine): array {
    $sql = $engine === 'sqlite'
        ? "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        : "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename";
    $result = [];
    foreach ($db->query($sql)->fetchAll(PDO::FETCH_COLUMN) as $name) {
        $result[$name] = (int)$db->query('SELECT COUNT(*) FROM ' . ident($name))->fetchColumn();
    }
    return $result;
}
function sqlite(string $path): PDO {
    $db = new PDO('sqlite:' . $path, null, null, [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
    $db->exec('PRAGMA query_only=ON');
    return $db;
}
function references(PDO $db): array {
    // Compare IDs and reference-bearing metadata, without publishing identities,
    // names, paths or share recipients in evidence files.
    $queries = [
        'users' => 'SELECT uid,displayname FROM oc_users ORDER BY uid',
        'shares' => 'SELECT id,share_type,share_with,uid_owner,file_source,file_target,permissions FROM oc_share ORDER BY id',
        'files' => 'SELECT fileid,storage,path,parent,name,size,mimetype FROM oc_filecache ORDER BY fileid',
        'storages' => 'SELECT numeric_id,id FROM oc_storages ORDER BY numeric_id',
    ];
    $result = [];
    foreach ($queries as $key => $sql) {
        $rows = [];
        foreach ($db->query($sql) as $row) {
            $values = [];
            foreach ($row as $column => $value) {
                if (is_int($column)) { $values[] = $value === null ? null : (string)$value; }
            }
            $rows[] = hash('sha256', json_encode($values, JSON_THROW_ON_ERROR));
        }
        // SQLite and PostgreSQL can use different string collations.
        sort($rows, SORT_STRING);
        $result[$key] = hash('sha256', implode("\n", $rows));
    }
    return $result;
}
function postgres(): PDO {
    return new PDO('pgsql:host=nextcloud-db.nextcloud.svc.cluster.local;port=5432;dbname=nextcloud',
        'nextcloud', file_get_contents('/migration-secrets/db-password'),
        [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
}
function checkIntegrity(string $path): void {
    if (!is_file($path)) { fail('Checkpoint database is missing'); }
    $checks = sqlite($path)->query('PRAGMA integrity_check')->fetchAll(PDO::FETCH_COLUMN);
    if ($checks !== ['ok']) { fail('SQLite integrity_check failed'); }
}
try {
    $action = $argv[1] ?? '';
    $root = getenv('NC_MIGRATION_DATA') ?: '/var/www/html/data';
    $config = getenv('NC_MIGRATION_CONFIG') ?: '/var/www/html/config';
    $run = $argv[2] ?? '';
    if (!preg_match('/^[a-z0-9][a-z0-9-]{5,39}$/D', $run)) { fail('Invalid run identifier'); }
    $base = $root . '/.postgresql-migration';
    $checkpoint = $base . '/' . $run;
    $source = $root . '/nextcloud.db';
    if (is_link($base) || is_link($checkpoint) || is_link($source)) { fail('Refusing symlinked checkpoint/database path'); }

    if ($action === 'checkpoint') {
        if (!is_file($source)) { fail('Expected SQLite source does not exist'); }
        if (!is_dir($base) && !mkdir($base, 0700)) { fail('Cannot create checkpoint root'); }
        if (file_exists($checkpoint) || !mkdir($checkpoint, 0700)) { fail('Checkpoint already exists; never overwrite'); }
        $from = new SQLite3($source, SQLITE3_OPEN_READONLY);
        $to = new SQLite3($checkpoint . '/nextcloud.db', SQLITE3_OPEN_READWRITE | SQLITE3_OPEN_CREATE);
        if (!$from->backup($to)) { fail('Native SQLite backup failed'); }
        $to->close();
        $from->close();
        checkIntegrity($checkpoint . '/nextcloud.db');
        $baseline = counts(sqlite($checkpoint . '/nextcloud.db'), 'sqlite');
        if ($baseline !== counts(sqlite($source), 'sqlite')) { fail('Source changed while checkpointing'); }
        file_put_contents($checkpoint . '/baseline.json', json_encode($baseline, JSON_THROW_ON_ERROR));
        file_put_contents($checkpoint . '/references.json', json_encode(references(sqlite($checkpoint . '/nextcloud.db')), JSON_THROW_ON_ERROR));
        file_put_contents($checkpoint . '/database.sha256', hash_file('sha256', $checkpoint . '/nextcloud.db'));
        echo json_encode(['tables' => count($baseline), 'bytes' => filesize($checkpoint . '/nextcloud.db')]);
    } elseif ($action === 'target') {
        $db = postgres();
        if (counts($db, 'postgres') !== []) { fail('Destination has tables; never clear or retry a partial target'); }
        if ($db->query("SELECT rolsuper OR rolcreatedb OR rolcreaterole FROM pg_roles WHERE rolname=current_user")->fetchColumn()) {
            fail('Application role has administrative privileges');
        }
        // Transactional public-schema write proves the application can create
        // and write tables while leaving the migration destination empty.
        $db->beginTransaction();
        $db->exec('CREATE TABLE nc_migration_write_probe (value integer NOT NULL)');
        $db->exec('INSERT INTO nc_migration_write_probe VALUES (42)');
        if ((int)$db->query('SELECT value FROM nc_migration_write_probe')->fetchColumn() !== 42) { fail('Target write failed'); }
        $db->rollBack();
        echo json_encode(['empty' => true, 'authenticated' => true, 'write_verified' => true]);
    } elseif ($action === 'validate') {
        checkIntegrity($checkpoint . '/nextcloud.db');
        $baseline = json_decode(file_get_contents($checkpoint . '/baseline.json'), true, 512, JSON_THROW_ON_ERROR);
        $db = postgres();
        if (references($db) !== json_decode(file_get_contents($checkpoint . '/references.json'), true, 512, JSON_THROW_ON_ERROR)) {
            fail('Users, shares or file-cache references changed during conversion');
        }
        $actual = counts($db, 'postgres');
        foreach ($baseline as $table => $count) {
            if ($table === 'oc_migrations') { continue; }
            if (!array_key_exists($table, $actual) || $actual[$table] !== $count) { fail('Converted table count mismatch: ' . $table); }
        }
        $versions = 'SELECT app, version FROM oc_migrations ORDER BY app, version';
        $old = sqlite($checkpoint . '/nextcloud.db')->query($versions)->fetchAll(PDO::FETCH_NUM);
        $new = $db->query($versions)->fetchAll(PDO::FETCH_NUM);
        foreach ($old as $version) {
            if (!in_array($version, $new, true)) { fail('Missing application migration version'); }
        }
        $columns = $db->query("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='public' " .
            "AND (column_default LIKE 'nextval(%' OR is_identity='YES')")->fetchAll(PDO::FETCH_ASSOC);
        foreach ($columns as $column) {
            $table = $column['table_name']; $name = $column['column_name'];
            $q = $db->prepare("SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace " .
                "WHERE c.oid=pg_get_serial_sequence(:tbl,:col)::regclass");
            $q->execute(['tbl' => ident($table), 'col' => $name]);
            $seq = $q->fetch(PDO::FETCH_ASSOC);
            if (!$seq) { fail('Missing sequence'); }
            $state = $db->query('SELECT last_value,is_called FROM ' . ident($seq['nspname']) . '.' . ident($seq['relname']))->fetch(PDO::FETCH_ASSOC);
            $max = $db->query('SELECT MAX(' . ident($name) . ') FROM ' . ident($table))->fetchColumn();
            if ($max !== null && $max !== false && ((int)$state['last_value'] < (int)$max ||
                ((int)$state['last_value'] === (int)$max && !$state['is_called']))) { fail('Sequence would reuse an existing ID'); }
        }
        echo json_encode(['matched_tables' => count($baseline) - 1, 'sequences' => count($columns)]);
    } elseif ($action === 'rollback') {
        checkIntegrity($checkpoint . '/nextcloud.db');
        if (hash_file('sha256', $checkpoint . '/nextcloud.db') !== file_get_contents($checkpoint . '/database.sha256')) {
            fail('Checkpoint digest changed');
        }
        if (!is_file($checkpoint . '/config.tar') || !is_file($checkpoint . '/complete')) { fail('Checkpoint is incomplete'); }
        $failed = $checkpoint . '/preserved-before-rollback';
        if (file_exists($failed) || !mkdir($failed, 0700)) { fail('Rollback already attempted; inspect retained state'); }
        mkdir($failed . '/config', 0700);
        // Caller must stop all application/validation processes first. Preserve,
        // rather than delete, the entire previous DB/WAL/SHM and configuration.
        foreach (['', '-wal', '-shm', '-journal'] as $suffix) {
            if (file_exists($source . $suffix) && !rename($source . $suffix, $failed . '/nextcloud.db' . $suffix)) {
                fail('Cannot preserve previous SQLite state');
            }
        }
        foreach (scandir($config) as $name) {
            if ($name === '.' || $name === '..') { continue; }
            if (!rename($config . '/' . $name, $failed . '/config/' . $name)) { fail('Cannot preserve configuration'); }
        }
        if (!copy($checkpoint . '/nextcloud.db', $source . '.migration-new') || !rename($source . '.migration-new', $source)) {
            fail('Cannot install SQLite checkpoint');
        }
        echo json_encode(['database_restored' => true, 'config_archive' => $checkpoint . '/config.tar']);
    } else { fail('Unknown database action'); }
    echo "\n";
} catch (Throwable $e) {
    // PDO connection exceptions can include connection details; keep output bounded.
    fwrite(STDERR, $e instanceof PDOException ? "Database operation failed; inspect privately\n" : $e->getMessage() . "\n");
    exit(1);
}
