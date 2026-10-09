<?php
// Simulate Nextcloud's command/connection boundary with real SQLite databases.
namespace Symfony\Component\Console\Input { interface InputInterface { public function getOption($name); } }
namespace Symfony\Component\Console\Output { interface OutputInterface {} }
namespace OC\DB {
    class Connection {
        public \PDO $pdo;
        public function __construct(string $path, array $options = []) { $this->pdo = new \PDO('sqlite:' . $path, options: $options); }
        public function executeStatement($sql, $parameters = []) {
            $s = $this->pdo->prepare($sql); $s->execute($parameters); return $s;
        }
        public function fetchFirstColumn($sql) { return $this->executeStatement($sql)->fetchAll(\PDO::FETCH_COLUMN); }
        public function fetchAllAssociative($sql) { return $this->executeStatement($sql)->fetchAll(\PDO::FETCH_ASSOC); }
        public function fetchOne($sql, $parameters = []) { return $this->executeStatement($sql, $parameters)->fetchColumn(); }
        public function insert($table, $row) {
            $this->executeStatement('INSERT INTO ' . $table . ' (' . implode(',', array_keys($row)) . ') VALUES (' .
                implode(',', array_fill(0, count($row), '?')) . ')', array_values($row));
        }
        public function createSchema() {
            return new class($this) {
                public function __construct(private Connection $db) {}
                public function getTable($name) {
                    $columns = $this->db->fetchAllAssociative('PRAGMA table_info(' . $name . ')');
                    if (!$columns) { throw new \RuntimeException('Missing table'); }
                    return new class($columns) {
                        public function __construct(private array $columns) {}
                        public function getColumns() { return array_column($this->columns, null, 'name'); }
                    };
                }
            };
        }
        public function close() { unset($this->pdo); }
    }
}
namespace OC\Core\Command\Db {
    class ConvertType {
        public function __construct(protected object $config, protected object $connectionFactory) {}
        protected function convertDB(\OC\DB\Connection $fromDB, \OC\DB\Connection $toDB, array $tables,
            \Symfony\Component\Console\Input\InputInterface $input,
            \Symfony\Component\Console\Output\OutputInterface $output) {
            foreach ($tables as $table) {
                if ($table === 'oc_migrations') { continue; }
                foreach ($fromDB->fetchAllAssociative('SELECT * FROM ' . $table) as $row) { $toDB->insert($table, $row); }
            }
        }
        public function run($from, $to, $input) {
            $this->convertDB($from, $to, ['oc_appconfig', 'oc_mounts', 'oc_migrations'], $input,
                new class implements \Symfony\Component\Console\Output\OutputInterface {});
        }
    }
}
namespace {
    require $argv[1];
    $input = new class($argv[2]) implements \Symfony\Component\Console\Input\InputInterface {
        public function __construct(private string $path) {}
        public function getOption($name) { return $this->path; }
    };
    $factory = new class {
        public function getConnection($type, $parameters) {
            if (!str_ends_with($parameters['path'], '?immutable=1') ||
                $parameters['driverOptions'][\PDO::SQLITE_ATTR_OPEN_FLAGS] !== \PDO::SQLITE_OPEN_READONLY) {
                throw new \RuntimeException('Checkpoint must be immutable and read-only');
            }
            return new \OC\DB\Connection($parameters['path'], $parameters['driverOptions']);
        }
    };
    try {
        (new \PreservingConvertType(new \stdClass(), $factory))->run(
            new \OC\DB\Connection($argv[3]), new \OC\DB\Connection($argv[4]), $input);
    } catch (\Throwable $e) { fwrite(STDERR, $e->getMessage()); exit(1); }
}
