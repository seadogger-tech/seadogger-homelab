<?php
// Simulate the upstream command/database boundary; exercise the production
// command through run(), with real SQLite review checks supplied by the caller.
namespace Symfony\Component\Console\Input { interface InputInterface {} }
namespace Symfony\Component\Console\Output { interface OutputInterface { public function writeln($line); } }
namespace OC\DB {
    class Column implements \JsonSerializable {
        public function __construct(private array $data) {}
        public function hasPlatformOption($key) { return isset($this->data[$key]); }
        public function getPlatformOption($key) {
            if (!$this->hasPlatformOption($key)) { throw new \RuntimeException('Absent platform option'); }
            return $this->data[$key];
        }
        public function getType() {
            return new class($this->data['type']) {
                public function __construct(private string $name) {}
                public function getName() { return $this->name; }
            };
        }
        public function setPlatformOption($key, $value) { $this->data[$key] = $value; }
        public function jsonSerialize(): mixed { return $this->data; }
    }
    class Table implements \JsonSerializable {
        private array $columns;
        public function __construct(private array $data) {
            $this->columns = array_map(fn ($column) => new Column($column), $data['columns'] ?? []);
        }
        public function __clone() { $this->columns = array_map(fn ($column) => clone $column, $this->columns); }
        public function getName() { return $this->data['name']; }
        public function getColumns() { return $this->columns; }
        public function jsonSerialize(): mixed { return array_replace($this->data, ['columns' => $this->columns]); }
    }
    class Connection {
        public function __construct(public array $tables) {}
        public function createSchema() {
            return new class($this->tables) {
                public function __construct(private array $tables) {}
                public function getTable($name) { return new Table($this->tables[$name]); }
            };
        }
        public function createSchemaManager() {
            return new class($this) {
                public function __construct(private Connection $connection) {}
                public function createTable($table) {
                    if (isset($this->connection->tables[$table->getName()])) { throw new \RuntimeException('Overwrite attempted'); }
                    $this->connection->tables[$table->getName()] = $table;
                }
            };
        }
    }
}
namespace OC\Core\Command\Db {
    class ConvertType {
        public function __construct(protected object $config) {}
        protected function getTables(\OC\DB\Connection $db) { return array_keys($db->tables); }
        protected function createSchema(\OC\DB\Connection $fromDB, \OC\DB\Connection $toDB,
            \Symfony\Component\Console\Input\InputInterface $input,
            \Symfony\Component\Console\Output\OutputInterface $output) {
            $toDB->tables['oc_current'] = ['name' => 'oc_current'];
        }
        public function run($source, $target) {
            $input = new class implements \Symfony\Component\Console\Input\InputInterface {};
            $output = new class implements \Symfony\Component\Console\Output\OutputInterface {
                public function writeln($line) {}
            };
            $this->createSchema($source, $target, $input, $output);
        }
    }
}
namespace {
    require $argv[1];
    $config = new class($argv[2]) {
        public function __construct(private string $directory) {}
        public function getSystemValue($key) { return $this->directory; }
    };
    $source = new \OC\DB\Connection(json_decode(file_get_contents($argv[3]), true, flags: JSON_THROW_ON_ERROR));
    $target = new \OC\DB\Connection([]);
    $code = 0;
    try { (new \PreservingConvertType($config))->run($source, $target); }
    catch (\Throwable $error) { fwrite(STDERR, $error->getMessage()); $code = 1; }
    echo json_encode($target->tables, JSON_THROW_ON_ERROR), "\n";
    exit($code);
}
