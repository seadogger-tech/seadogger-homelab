<?php
declare(strict_types=1);

require_once __DIR__ . '/reviewed-empty-tables.php';

// Keep the pinned upstream conversion/data-copy implementation. Only add the
// explicitly reviewed empty schemas that its current app migrations omit.
class PreservingConvertType extends \OC\Core\Command\Db\ConvertType {
    protected function configure() {
        parent::configure();
        $this->addOption('checkpoint', null, \Symfony\Component\Console\Input\InputOption::VALUE_REQUIRED,
            'Verified immutable checkpoint directory used as the data-copy source');
    }

    protected function convertDB(\OC\DB\Connection $fromDB, \OC\DB\Connection $toDB, array $tables,
        \Symfony\Component\Console\Input\InputInterface $input,
        \Symfony\Component\Console\Output\OutputInterface $output) {
        $directory = $input->getOption('checkpoint');
        if (!is_string($directory) || !str_starts_with($directory, '/') || is_link($directory) ||
            is_link(dirname($directory))) { throw new RuntimeException('Invalid checkpoint directory'); }
        $path = $directory . '/nextcloud.db';
        foreach (['nextcloud.db', 'database.sha256', 'complete'] as $file) {
            if (!is_file($directory . '/' . $file) || is_link($directory . '/' . $file)) {
                throw new RuntimeException('Incomplete or symlinked checkpoint');
            }
        }
        $digest = trim(file_get_contents($directory . '/database.sha256'));
        if (!preg_match('/^[a-f0-9]{64}$/D', $digest) || hash_file('sha256', $path) !== $digest) {
            throw new RuntimeException('Checkpoint digest mismatch');
        }
        // Native schema hooks use the live source connection. Copy the original
        // checkpoint instead, so their config/cache mutations cannot lose rows.
        $checkpoint = $this->connectionFactory->getConnection('sqlite3', [
            'path' => 'file:' . $path . '?immutable=1',
            'driverOptions' => [PDO::SQLITE_ATTR_OPEN_FLAGS => PDO::SQLITE_OPEN_READONLY],
        ]);
        try {
            $checkpoint->executeStatement('PRAGMA query_only=ON');
            if ($checkpoint->fetchFirstColumn('PRAGMA integrity_check') !== ['ok']) {
                throw new RuntimeException('Checkpoint integrity failed');
            }
            $sourceSchema = $checkpoint->createSchema();
            $targetSchema = $toDB->createSchema();
            foreach ($tables as $name) {
                $sourceColumns = array_keys($sourceSchema->getTable($name)->getColumns());
                $targetColumns = array_keys($targetSchema->getTable($name)->getColumns());
                sort($sourceColumns); sort($targetColumns);
                if ($sourceColumns !== $targetColumns) {
                    throw new RuntimeException('Checkpoint/target columns differ: ' . $name);
                }
            }
            // Upstream skips copying migrations. Retain historical records that
            // are absent from today's migration files without executing them.
            foreach ($checkpoint->fetchAllAssociative('SELECT app,version FROM oc_migrations') as $row) {
                if (!$toDB->fetchOne('SELECT COUNT(*) FROM oc_migrations WHERE app=? AND version=?',
                    [$row['app'], $row['version']])) {
                    $toDB->insert('oc_migrations', $row);
                }
            }
            parent::convertDB($checkpoint, $toDB, $tables, $input, $output);
        } finally {
            $checkpoint->close();
            if (hash_file('sha256', $path) !== $digest) { throw new RuntimeException('Checkpoint changed during copy'); }
        }
    }

    protected function createSchema(\OC\DB\Connection $fromDB, \OC\DB\Connection $toDB,
        \Symfony\Component\Console\Input\InputInterface $input,
        \Symfony\Component\Console\Output\OutputInterface $output) {
        $plan = __DIR__ . '/reviewed-empty-tables.json';
        $database = $this->config->getSystemValue('datadirectory') . '/nextcloud.db';
        $reviewed = reviewedEmptyTables($plan, $database);
        parent::createSchema($fromDB, $toDB, $input, $output);
        // Upstream migrations can run hooks against the source connection.
        if (reviewedEmptyTables($plan, $database) !== $reviewed) {
            throw new RuntimeException('Legacy-table review changed during schema creation');
        }
        $missing = array_values(array_diff($this->getTables($fromDB), $this->getTables($toDB)));
        sort($missing, SORT_STRING);
        if ($missing !== $reviewed) {
            throw new RuntimeException('Missing tables differ from the reviewed empty-table set; preserve target and inspect');
        }
        $schema = $fromDB->createSchema();
        $manager = $toDB->createSchemaManager();
        foreach ($reviewed as $name) {
            $table = clone $schema->getTable($name);
            foreach ($table->getColumns() as $column) {
                if (!$column->hasPlatformOption('collation')) { continue; }
                $collation = $column->getPlatformOption('collation');
                if ($collation !== 'BINARY') { throw new RuntimeException('Unreviewed SQLite collation'); }
                // SQLite introspection attaches BINARY even to JSON. PostgreSQL
                // accepts collations only on character types; C retains binary
                // comparison semantics for the reviewed string/text columns.
                $character = in_array($column->getType()->getName(), ['string', 'text'], true);
                $column->setPlatformOption('collation', $character ? 'C' : null);
            }
            $manager->createTable($table);
            $output->writeln('Preserved reviewed empty table: ' . $name);
        }
    }
}
