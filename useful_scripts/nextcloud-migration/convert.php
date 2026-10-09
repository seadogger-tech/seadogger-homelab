<?php
declare(strict_types=1);
// Invoke the pinned upstream command, but never allow an omission prompt to
// default to yes. The password exists only in process memory, never argv.
define('OC_CONSOLE', 1);
chdir('/var/www/html');
if (hash_file('sha256', '/var/www/html/core/Command/Db/ConvertType.php') !==
    'cb4643788cde0914e8a3194b70ce950648695570343ba1b23b6782914eed2b2d') {
    fwrite(STDERR, "Unreviewed converter source; stop before loading the application.\n");
    exit(1);
}
require_once '/var/www/html/lib/base.php';
try {
    if (posix_getuid() !== 33 || fileowner('/var/www/html/config/config.php') !== 33) {
        throw new RuntimeException('Wrong service identity');
    }
    $config = \OCP\Server::get(\OCP\IConfig::class);
    if ($config->getSystemValue('dbtype') !== 'sqlite3') { throw new RuntimeException('Source is not SQLite'); }
    $command = new \OC\Core\Command\Db\ConvertType(
        $config, \OCP\Server::get(\OC\DB\ConnectionFactory::class), \OCP\Server::get(\OCP\App\IAppManager::class));
    $helper = new class extends \Symfony\Component\Console\Helper\QuestionHelper {
        public function ask(\Symfony\Component\Console\Input\InputInterface $input,
            \Symfony\Component\Console\Output\OutputInterface $output,
            \Symfony\Component\Console\Question\Question $question): mixed {
            throw new RuntimeException('Conversion stopped: omitted tables or unexpected prompt require review');
        }
    };
    $command->setHelperSet(new \Symfony\Component\Console\Helper\HelperSet([$helper]));
    $input = new \Symfony\Component\Console\Input\ArrayInput([
        'type' => 'pgsql', 'username' => 'nextcloud', 'hostname' => 'nextcloud-db.nextcloud.svc.cluster.local',
        'database' => 'nextcloud', '--port' => '5432', '--all-apps' => true,
        '--password' => file_get_contents('/migration-secrets/db-password'),
    ]);
    $input->setInteractive(true);
    $output = new \Symfony\Component\Console\Output\ConsoleOutput();
    exit($command->run($input, $output));
} catch (Throwable $e) {
    fwrite(STDERR, "Conversion stopped; preserve the destination and inspect the private transcript.\n");
    exit(1);
}
