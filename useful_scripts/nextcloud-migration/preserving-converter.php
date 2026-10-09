<?php
declare(strict_types=1);

require_once __DIR__ . '/reviewed-empty-tables.php';

// Keep the pinned upstream conversion/data-copy implementation. Only add the
// explicitly reviewed empty schemas that its current app migrations omit.
class PreservingConvertType extends \OC\Core\Command\Db\ConvertType {
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
