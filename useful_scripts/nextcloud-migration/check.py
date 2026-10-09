#!/usr/bin/env python3
"""Credential-free migration checks. Run from any working directory; see --help."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import venv

HERE = Path(__file__).resolve().parent
CORE = HERE.parents[1]
CHECKS = HERE / 'checks'


def run(*args, **kwargs):
    print('+ ' + ' '.join(str(arg) for arg in args), flush=True)
    return subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact(cache, name, url, checksum, offline):
    path = cache / name
    if path.exists():
        if digest(path) != checksum:
            raise RuntimeError(f'Cached artifact checksum mismatch: {path}; inspect and remove it before retrying')
        return path
    if offline:
        raise RuntimeError(f'Offline artifact missing: {path}; run once online to populate the cache')
    print(f'Downloading pinned artifact: {url}', flush=True)
    with urllib.request.urlopen(url, timeout=60) as response:
        content = response.read()
    if hashlib.sha256(content).hexdigest() != checksum:
        raise RuntimeError(f'Download checksum mismatch: {url}')
    path.write_bytes(content)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true', help='Require already prepared dependencies and cached artifacts')
    parser.add_argument('--cache-dir', type=Path, default=CORE / '.cache/nextcloud-check')
    args = parser.parse_args()
    if not __debug__:
        raise RuntimeError('Run checks without Python optimization; render assertions must remain enabled')
    if sys.version_info < (3, 12):
        raise RuntimeError('Python 3.12 or newer is required')
    for tool in ('php', 'helm', 'kubectl', 'bash'):
        if not shutil.which(tool):
            raise RuntimeError(f'Missing {tool}; install the prerequisites in docs/wiki/27-Deployment-and-Validation.md')
    cache = args.cache_dir.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    environment = (cache / 'venv').resolve()
    python = environment / 'bin/python'
    requirements = CHECKS / 'requirements.txt'
    stamp = cache / 'requirements.sha256'
    if Path(sys.prefix).resolve() != environment:
        if not python.exists() or not stamp.exists() or stamp.read_text() != digest(requirements):
            if args.offline:
                raise RuntimeError('Offline Python environment missing or stale; run once online')
            venv.create(environment, with_pip=True)
            run(python, '-m', 'pip', 'install', '--disable-pip-version-check', '-r', requirements)
            stamp.write_text(digest(requirements))
        os.execv(str(python), [str(python), str(Path(__file__).resolve()), *sys.argv[1:]])
    # Prefer the declared toolchain over globally installed Ansible/lint commands.
    os.environ['PATH'] = str(environment / 'bin') + os.pathsep + os.environ['PATH']
    import yaml
    fixture_path = HERE / 'tests/fixtures/converter-contract.json'
    fixture = json.loads(fixture_path.read_text())
    upstream = artifact(cache, 'ConvertType-' + fixture['version'] + '.php', fixture['source_url'],
                        fixture['source_sha256'], args.offline)
    if fixture['source_sha256'] not in (HERE / 'convert.php').read_text():
        raise RuntimeError('Production converter pin differs from the reviewed contract; review and update both')
    artifact_spec = json.loads((CHECKS / 'artifacts.json').read_text())
    charts = {name: artifact(cache, name, spec['url'], spec['sha256'], args.offline)
              for name, spec in artifact_spec.items()}
    run('php', '-r', 'exit(extension_loaded("sqlite3") && extension_loaded("pdo_sqlite") ? 0 : 1);')
    run('php', CHECKS / 'converter-contract.php', upstream, fixture_path)
    with tempfile.TemporaryDirectory(prefix='nextcloud-check-') as directory:
        temp = Path(directory)
        # Syntax checks read only public example config, never operator credentials.
        ansible = temp / 'ansible'
        ansible.mkdir()
        for name in ('main.yml', 'nextcloud_postgresql.yml', 'nextcloud_migration.yml'):
            shutil.copy(CORE / 'ansible' / name, ansible / name)
        shutil.copy(CORE / 'ansible/example.config.yml', ansible / 'config.yml')
        (ansible / 'tasks').symlink_to(CORE / 'ansible/tasks', target_is_directory=True)
        config = temp / 'ansible.cfg'
        config.write_text('[defaults]\n')
        inventory = temp / 'inventory'
        inventory.write_text('[control_plane]\nlocalhost ansible_connection=local\n[cluster]\nlocalhost\n[nodes]\n')
        # Discard operator Ansible overrides before invoking isolated validation.
        for key in list(os.environ):
            if key.startswith('ANSIBLE_'):
                del os.environ[key]
        os.environ.update(ANSIBLE_CONFIG=str(config), ANSIBLE_LOCAL_TEMP=str(temp / 'ansible-tmp'),
                          ANSIBLE_NOCOLOR='1', PYTHONDONTWRITEBYTECODE='1',
                          KUBECONFIG=str(temp / 'no-kubeconfig'))
        for name in ('main.yml', 'nextcloud_postgresql.yml', 'nextcloud_migration.yml'):
            run('ansible-playbook', '--syntax-check', '-i', inventory, ansible / name)
        lint_paths = ['ansible/example.config.yml', 'ansible/main.yml', 'ansible/nextcloud_postgresql.yml',
                      'ansible/nextcloud_migration.yml', 'ansible/tasks/nextcloud_deploy.yml',
                      'ansible/tasks/nextcloud_postgresql_deploy.yml', 'deployments/nextcloud/postgresql',
                      'deployments/nextcloud/nextcloud-postgresql-values.yaml', '.github/workflows/nextcloud-checks.yml']
        run('yamllint', '-c', CORE / '.yamllint', *(CORE / p for p in lint_paths))
        for path in HERE.glob('*.py'):
            compile(path.read_text(), str(path), 'exec')
        for path in [*HERE.glob('*.php'), CHECKS / 'converter-contract.php']:
            run('php', '-l', path)
        for name in ('init.sh', 'backup.sh'):
            run('bash', '-n', CORE / 'deployments/nextcloud/postgresql' / name)
        run(sys.executable, '-m', 'unittest', 'discover', '-s', HERE / 'tests', '-v')
        rendered = run('kubectl', 'kustomize', CORE / 'deployments/nextcloud/postgresql', capture_output=True, text=True).stdout
        resources = list(yaml.safe_load_all(rendered))
        assert len(resources) == 7 and all(r['metadata']['namespace'] == 'nextcloud' for r in resources)
        pvc = next(r for r in resources if r['kind'] == 'PersistentVolumeClaim')
        assert pvc['spec']['storageClassName'] == 'ceph-block-data'
        assert pvc['spec']['resources']['requests']['storage'] == '10Gi'
        assert pvc['spec']['accessModes'] == ['ReadWriteOnce']
        assert 'Prune=false,Delete=false' in pvc['metadata']['annotations']['argocd.argoproj.io/sync-options']
        cron = next(r for r in resources if r['kind'] == 'CronJob')['spec']
        assert cron['suspend'] is True and cron['schedule'] == '15 3 * * *'
        assert cron['timeZone'] == 'America/New_York'
        values = temp / 'values.yaml'
        tag = '32.0.6-apache@sha256:' + 'b' * 64
        values.write_text(yaml.safe_dump({'replicaCount': 0, 'hpa': {'enabled': False},
            'image': {'registry': 'docker.io', 'repository': 'library/nextcloud', 'tag': tag},
            'global': {'image': {'registry': 'docker.io'}}}))
        rendered = run('helm', 'template', 'nextcloud', charts['nextcloud-8.9.1.tgz'], '--namespace', 'nextcloud',
                       '-f', CORE / 'deployments/nextcloud/nextcloud-values.yaml',
                       '-f', CORE / 'deployments/nextcloud/nextcloud-postgresql-values.yaml',
                       '-f', values, capture_output=True, text=True).stdout
        resources = [r for r in yaml.safe_load_all(rendered) if r]
        deployment = next(r for r in resources if r['kind'] == 'Deployment' and r['metadata']['name'] == 'nextcloud')
        assert deployment['spec']['replicas'] == 0
        pod = deployment['spec']['template']['spec']
        container = next(c for c in pod['containers'] if c['name'] == 'nextcloud')
        assert container['image'] == 'docker.io/library/nextcloud:' + tag
        env = {e['name']: e for e in container['env']}
        assert 'SQLITE_DATABASE' not in env
        assert env['POSTGRES_HOST']['value'] == fixture['arguments']['hostname']
        for name, key in [('POSTGRES_USER', 'db-username'), ('POSTGRES_PASSWORD', 'db-password')]:
            assert env[name]['valueFrom']['secretKeyRef'] == {'name': 'nextcloud-db-auth', 'key': key}
        assert not any(r['kind'] == 'StatefulSet' and 'postgresql' in r['metadata']['name'] for r in resources)
        assert not any('postgres' in c['name'] for c in pod.get('initContainers', []))
    print('All migration checks passed. No cluster or AWS operations were performed.')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
