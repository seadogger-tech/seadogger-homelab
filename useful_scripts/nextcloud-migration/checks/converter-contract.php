<?php
// Execute only upstream saveDBInfo, with inert interfaces and an in-memory config.
// The caller verifies the upstream file hash before this script loads it.
namespace Symfony\Component\Console\Command { class Command {} }
namespace Symfony\Component\Console\Input { interface InputInterface {} }
namespace Stecman\Component\Symfony\Console\BashCompletion\Completion {
    interface CompletionAwareInterface {}
}
namespace OCP { interface IConfig {} }
namespace {
    require $argv[1];
    $fixture = json_decode(file_get_contents($argv[2]), true, flags: JSON_THROW_ON_ERROR);
    $config = new class implements \OCP\IConfig {
        public array $values = [];
        public function setSystemValues(array $values): void { $this->values = $values; }
    };
    $input = new class($fixture) implements \Symfony\Component\Console\Input\InputInterface {
        public function __construct(private array $fixture) {}
        public function getArgument(string $key): mixed { return $this->fixture['arguments'][$key]; }
        public function getOption(string $key): mixed { return $this->fixture['options'][$key]; }
    };
    $class = new \ReflectionClass(\OC\Core\Command\Db\ConvertType::class);
    $command = $class->newInstanceWithoutConstructor();
    $class->getProperty('config')->setValue($command, $config);
    $class->getMethod('saveDBInfo')->invoke($command, $input);
    if ($config->values['dbhost'] !== $fixture['saved_dbhost']) {
        fwrite(STDERR, "Upstream saved dbhost disagrees with the reviewed contract.\n");
        exit(1);
    }
    echo "Pinned upstream saveDBInfo contract passed.\n";
}
