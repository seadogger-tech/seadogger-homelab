#!/usr/bin/env python3
"""Bounded production migration phases. Nothing mutates unless --execute is set.

State and evidence are private local files. This is intentionally a phase runner,
not an unattended retry loop: a partial target or uncertain fence stays stopped.
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures
import contextlib
import copy
import datetime as dt
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import urllib.parse
import uuid
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
DEPLOYMENT_STATE = HERE.parent.parent / 'ansible' / 'nextcloud-database.local.json'
NAMESPACE = 'nextcloud'
SERVICE_LABELS = 'app.kubernetes.io/component=app,app.kubernetes.io/instance=nextcloud,app.kubernetes.io/name=nextcloud'
AWS_IMAGE = 'docker.io/amazon/aws-cli:2.37.10@sha256:3dacc5db57c923c4223e949795f538ecf1f2212b2b7d5a028b47b97f91564c0d'
MIRROR_BUCKET = 'homelab-nextcloud-backup-708765384784-us-east-1-an'
BACKUP_BUCKET = 'seadogger-homelab-backup'
EXCLUDES = ['*/cache/*', '*/tmp/*', '*/appdata_*/*', '*/files_trashbin/*', '*/files_versions/*', 'nextcloud.log*']
PHASES = ['prepare', 'status', 'fence', 'checkpoint', 'refresh', 'convert', 'validate', 'canary', 'backup', 'reopen', 'rollback']


class Stopped(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise Stopped(message)


def private_write(path, value):
    path = Path(path)
    require(not path.is_symlink(), 'Refusing symlinked evidence path')
    temporary = path.with_suffix(path.suffix + '.new')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(value if isinstance(value, str) else json.dumps(value, indent=2) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def merge_dict(left, right):
    result = copy.deepcopy(left)
    for key, value in right.items():
        result[key] = merge_dict(result.get(key, {}), value) if isinstance(value, dict) else copy.deepcopy(value)
    return result


def compare_manifest(source, objects):
    expected = {r['key']: int(r['size']) for r in source}
    actual = {r['Key']: int(r['Size']) for r in objects}
    require(len(expected) == len(source), 'Duplicate source keys')
    require(len(actual) == len(objects), 'Duplicate S3 keys')
    missing = sorted(expected.keys() - actual.keys())
    mismatches = sorted(k for k in expected.keys() & actual.keys() if expected[k] != actual[k])
    return {'missing': missing, 'size_mismatch': mismatches,
            'remote_only': len(actual.keys() - expected.keys()), 'matched': len(expected) - len(missing) - len(mismatches)}


class Migration:
    def __init__(self, directory, execute=False):
        self.directory = Path(directory).expanduser().absolute()
        require(not self.directory.is_symlink(), 'State directory must not be a symlink')
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        require(self.directory.stat().st_uid == os.getuid(), 'State directory has another owner')
        os.chmod(self.directory, 0o700)
        self.execute = execute
        self.path = self.directory / 'state.json'
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {}

    def save(self):
        private_write(self.path, self.state)

    def record(self, key, value=True):
        self.state[key] = value
        self.save()

    def cmd(self, args, *, data=None, timeout=180, sensitive=False):
        try:
            result = subprocess.run(args, input=data, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            private_write(self.directory / 'last-command-output.txt', (error.stdout or b'').decode(errors='replace'))
            private_write(self.directory / 'last-command-error.txt', (error.stderr or b'').decode(errors='replace'))
            raise Stopped('Command timed out; inspect private output and server-side processes') from error
        if result.returncode:
            private_write(self.directory / 'last-command-output.txt', result.stdout.decode(errors='replace'))
            private_write(self.directory / 'last-command-error.txt', result.stderr.decode(errors='replace'))
            raise Stopped('Command failed; inspect private last-command-error.txt' if sensitive else
                          f'{args[0]} failed; inspect private last-command-error.txt')
        return result.stdout

    def kube(self, *args, data=None, namespace=NAMESPACE, **kwargs):
        request_timeout = '0' if args and args[0] in ('exec', 'wait', 'rollout', 'logs') else '30s'
        context = ['--context', self.state['context']] if self.state.get('context') else []
        return self.cmd(['kubectl', *context, '--request-timeout=' + request_timeout, '-n', namespace, *args], data=data, **kwargs)

    def get(self, kind, name=None, namespace=NAMESPACE):
        return json.loads(self.kube('get', kind, *([name] if name else []), '-o', 'json', namespace=namespace))

    def apply(self, resource):
        require(self.execute, 'Mutation requires --execute')
        return self.kube('apply', '-f', '-', data=json.dumps(resource).encode())

    def patch(self, kind, name, patch, namespace=NAMESPACE):
        require(self.execute, 'Mutation requires --execute')
        return self.kube('patch', kind, name, '--type=merge', '-p', json.dumps(patch), namespace=namespace)

    def exec(self, *args, pod=None, data=None, **kwargs):
        return self.kube('exec', '-i', pod or self.state['pod'], '-c', 'nextcloud', '--', *args, data=data, **kwargs)

    def occ(self, *args, **kwargs):
        identity = ['runuser', '-u', 'www-data', '--'] if kwargs.get('pod') else []
        return self.exec(*identity, 'php', '/var/www/html/occ', *args, **kwargs).decode().strip()

    def db(self, action):
        return json.loads(self.exec('php', '/migration/database.php', action, self.state['run']))

    def require_stage(self, *flags):
        for flag in flags:
            require(self.state.get(flag), f'Missing completed prerequisite: {flag}')

    def assert_fenced(self):
        self.require_stage('fenced')
        require(not self.state.get('reopening_started') and not self.state.get('rollback_reopening_started'),
                'Reopening has started; automatic SQLite rollback is forbidden')
        deployment = self.get('deployment', 'nextcloud')
        require(deployment['spec'].get('replicas', 1) == 0, 'Normal deployment is not scaled to zero')
        pods = json.loads(self.kube('get', 'pods', '-l', SERVICE_LABELS, '-o', 'json'))['items']
        require(not pods, 'Normal web pods still exist')
        endpoints = self.get('endpoints', 'nextcloud')
        require(not any(s.get('addresses') or s.get('notReadyAddresses') for s in endpoints.get('subsets', [])),
                'Normal Service still has endpoints')
        app = self.get('applications.argoproj.io', 'nextcloud', 'argocd')
        require(not app['metadata'].get('ownerReferences'), 'A parent controller could restore Argo automation')
        automated = app['spec'].get('syncPolicy', {}).get('automated')
        require(automated is None or automated.get('enabled') is False, 'Argo automation could undo the fence')
        require(not app.get('operation') and app.get('status', {}).get('operationState', {}).get('phase') != 'Running',
                'An Argo sync is still running')
        require(not any(h['spec']['scaleTargetRef'].get('name') == 'nextcloud'
                        for h in self.get('horizontalpodautoscalers')['items']), 'An autoscaler could recreate web pods')
        require(self.get('cronjob', 'nextcloud-s3-backup')['spec'].get('suspend'), 'File mirror is not suspended')
        require(not any(j.get('status', {}).get('active', 0) for j in self.get('jobs')['items']
                        if any(o['name'] == 'nextcloud-s3-backup' for o in j['metadata'].get('ownerReferences', []))),
                'An existing file mirror job is still active')
        # Inventory again at every dangerous phase. The maintenance pod is the
        # only permitted active direct mount of the original PVC in this namespace.
        for pod in self.get('pods')['items']:
            if pod['status'].get('phase') in ('Succeeded', 'Failed') or pod['metadata']['name'] == self.state['pod']:
                continue
            if any(v.get('persistentVolumeClaim', {}).get('claimName') == 'nextcloud-nextcloud'
                   for v in pod['spec'].get('volumes', [])):
                raise Stopped('Unexpected active source-volume pod: ' + pod['metadata']['name'])

    def prepare(self):
        require(not self.state, 'State already exists; use a new private run directory')
        require(not DEPLOYMENT_STATE.exists(), 'Deployment marker already exists; inspect prior migration before preparing')
        self.credentials()
        review = self.directory / 'reviewed-empty-tables.json'
        require(not review.is_symlink(), 'Refusing symlinked legacy-table review')
        reviewed_empty_tables = json.loads(review.read_text()) if review.exists() else []
        require(isinstance(reviewed_empty_tables, list), 'Legacy-table review must be a list')
        deployment = self.get('deployment', 'nextcloud')
        pods = json.loads(self.kube('get', 'pods', '-l', SERVICE_LABELS, '-o', 'json'))['items']
        require(len(pods) == 1 and pods[0]['status']['phase'] == 'Running', 'Expected one running Nextcloud pod')
        image = next(c for c in pods[0]['status']['containerStatuses'] if c['name'] == 'nextcloud')['imageID'].removeprefix('docker-pullable://')
        require('@sha256:' in image, 'Need a pullable immutable Nextcloud imageID')
        require(image.split('@')[0] in ('docker.io/library/nextcloud', 'docker.io/nextcloud', 'library/nextcloud', 'nextcloud'),
                'Review unexpected Nextcloud image repository')
        run = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d%H%M%S') + '-' + uuid.uuid4().hex[:8]
        self.state = {'run': run, 'pod': 'nc-migrate-' + run, 'image': image,
                      'context': self.cmd(['kubectl', 'config', 'current-context']).decode().strip(),
                      'deployment': deployment,
                      'application': self.get('applications.argoproj.io', 'nextcloud', 'argocd'),
                      'mirror': self.get('cronjob', 'nextcloud-s3-backup'), 'prepared': True,
                      'reviewed_empty_tables': reviewed_empty_tables}
        source_spec = self.state['application']['spec']['source']
        require(not self.state['application']['metadata'].get('ownerReferences'), 'Review parent-owned Argo Application first')
        require(not source_spec.get('helm', {}).get('parameters'), 'Review existing Helm parameters before migration')
        db_application = self.get('applications.argoproj.io', 'nextcloud-db', 'argocd')
        revision = db_application['spec']['source']['targetRevision']
        require(re.fullmatch('[0-9a-f]{40}', revision), 'Database Application must use an immutable reviewed commit')
        self.state['core_revision'] = revision
        self.state['image_values'] = {'registry': 'docker.io', 'repository': 'library/nextcloud',
                                      'tag': '32.0.6-apache@' + image.split('@')[1]}
        source = pods[0]['metadata']['name']
        for key, wanted in [('dbtype', 'sqlite3'), ('dbname', 'nextcloud'), ('datadirectory', '/var/www/html/data')]:
            require(self.occ('config:system:get', key, pod=source) == wanted, 'Unexpected source configuration: ' + key)
        status = json.loads(self.occ('status', '--output=json', pod=source))
        require(status['versionstring'] == '32.0.6', 'Converter wrapper requires reviewed Nextcloud32.0.6')
        self.state['maintenance_before'] = bool(status.get('maintenance'))
        self.state['apps_before'] = json.loads(self.occ('app:list', '--output=json', pod=source))
        self.save()

    def fence(self):
        self.require_stage('prepared', 'writers_reviewed')
        require(not self.state.get('fence_started'), 'Fence already attempted; inspect current state before resuming')
        require(self.cmd(['kubectl', 'config', 'current-context']).decode().strip() == self.state['context'], 'Kube context changed')
        self.record('fence_started')
        self.patch('applications.argoproj.io', 'nextcloud', {'spec': {'syncPolicy': {'automated': None}}}, 'argocd')
        self.patch('cronjob', 'nextcloud-s3-backup', {'spec': {'suspend': True}})
        # Never terminate an in-flight sync or Argo operation as a shortcut.
        app = self.get('applications.argoproj.io', 'nextcloud', 'argocd')
        require(not app.get('operation') and app.get('status', {}).get('operationState', {}).get('phase') != 'Running',
                'Wait for existing Argo operation to finish')
        require(not any(j.get('status', {}).get('active', 0) for j in self.get('jobs')['items']
                        if any(o['name'] == 'nextcloud-s3-backup' for o in j['metadata'].get('ownerReferences', []))),
                'Wait for existing mirror job to finish')
        pods = json.loads(self.kube('get', 'pods', '-l', SERVICE_LABELS, '-o', 'json'))['items']
        require(len(pods) == 1, 'Source pod changed; inspect before proceeding')
        self.occ('maintenance:mode', '--on', pod=pods[0]['metadata']['name'])
        self.patch('deployment', 'nextcloud', {'spec': {'replicas': 0}})
        self.kube('wait', '--for=delete', 'pod', '-l', SERVICE_LABELS, '--timeout=180s', timeout=210)
        self.record('fenced')
        self.assert_fenced()
        scripts = {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': self.state['pod'], 'namespace': NAMESPACE},
                   'data': {p.name: p.read_text() for p in HERE.glob('*.php')}}
        scripts['data']['reviewed-empty-tables.json'] = json.dumps(self.state.get('reviewed_empty_tables', []))
        self.apply(scripts)
        pod_spec = copy.deepcopy(self.state['deployment']['spec']['template']['spec'])
        source_volumes = [v['name'] for v in pod_spec['volumes']
                          if v.get('persistentVolumeClaim', {}).get('claimName') == 'nextcloud-nextcloud']
        require(len(source_volumes) == 1, 'Expected one source PVC volume in the original deployment')
        source = next(c for c in pod_spec['containers'] if c['name'] == 'nextcloud')
        container = {k: copy.deepcopy(v) for k, v in source.items()
                     if k in ('env', 'envFrom', 'volumeMounts', 'resources', 'workingDir')}
        container.update({'name': 'nextcloud', 'image': self.state['image'], 'command': ['sleep', 'infinity'],
                          'resources': {'requests': {'cpu': '100m', 'memory': '256Mi'},
                                        'limits': {'cpu': '1', 'memory': '1Gi'}},
                          'securityContext': {'runAsUser': 33, 'runAsGroup': 33, 'runAsNonRoot': True,
                                              'allowPrivilegeEscalation': False, 'capabilities': {'drop': ['ALL']}}})
        container['volumeMounts'] += [{'name': 'migration-tools', 'mountPath': '/migration', 'readOnly': True},
                                      {'name': 'migration-secrets', 'mountPath': '/migration-secrets', 'readOnly': True},
                                      {'name': source_volumes[0], 'mountPath': '/source'}]
        pod_spec['containers'] = [container]
        for key in ['initContainers', 'serviceAccount', 'serviceAccountName', 'nodeName']:
            pod_spec.pop(key, None)
        pod_spec['automountServiceAccountToken'] = False
        pod_spec['restartPolicy'] = 'Never'
        # Do not introduce fsGroup traversal on the multi-terabyte source PVC.
        pod_spec['securityContext'] = {'runAsUser': 33, 'runAsGroup': 33, 'runAsNonRoot': True,
                                       'seccompProfile': {'type': 'RuntimeDefault'}}
        pod_spec['volumes'] += [{'name': 'migration-tools', 'configMap': {'name': self.state['pod']}},
                               {'name': 'migration-secrets', 'secret': {'secretName': 'nextcloud-db-auth', 'defaultMode': 0o444,
                                 'items': [{'key': 'db-password', 'path': 'db-password'}]}}]
        self.apply({'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': self.state['pod'], 'namespace': NAMESPACE,
                    'labels': {'app.kubernetes.io/name': 'nextcloud-migration', 'migration-run': self.state['run']}}, 'spec': pod_spec})
        self.kube('wait', '--for=condition=Ready', 'pod/' + self.state['pod'], '--timeout=180s', timeout=210)
        self.db('target')
        self.record('maintenance_pod_ready')

    def checkpoint(self):
        self.assert_fenced()
        self.require_stage('maintenance_pod_ready')
        require(not self.state.get('checkpoint_started'), 'Checkpoint already attempted; preserve artifacts and inspect')
        self.record('checkpoint_started')
        result = self.db('checkpoint')
        path = '/var/www/html/data/.postgresql-migration/' + self.state['run']
        self.exec('tar', '-cpf', path + '/config.tar', '-C', '/var/www/html/config', '.')
        result['config_bytes'] = int(self.exec('stat', '-c', '%s', path + '/config.tar'))
        self.exec('php', '-r', 'file_put_contents($argv[1], "complete\n");', path + '/complete')
        self.record('checkpoint', result)

    def aws_job(self, purpose, args, mount_source=False):
        name = 'nc-' + purpose + '-' + self.state['run'] + '-' + uuid.uuid4().hex[:6]
        container = {'name': 'aws', 'image': AWS_IMAGE, 'args': args,
                     'env': [{'name': 'AWS_DEFAULT_REGION', 'value': 'us-east-1'}, {'name': 'HOME', 'value': '/tmp'},
                             {'name': 'AWS_SHARED_CREDENTIALS_FILE', 'value': '/aws/aws-credentials'}],
                     'securityContext': {'allowPrivilegeEscalation': False, 'capabilities': {'drop': ['ALL']}},
                     'resources': {'requests': {'cpu': '100m', 'memory': '128Mi'}, 'limits': {'cpu': '1', 'memory': '512Mi'}},
                     'volumeMounts': [{'name': 'credentials', 'mountPath': '/aws', 'readOnly': True}]}
        volumes = [{'name': 'credentials', 'secret': {'secretName': 'nextcloud-s3-backup-credentials', 'defaultMode': 0o444}}]
        if mount_source:
            volumes.append({'name': 'source', 'persistentVolumeClaim': {'claimName': 'nextcloud-nextcloud'}})
            container['volumeMounts'].append({'name': 'source', 'mountPath': '/source', 'readOnly': True})
        self.apply({'apiVersion': 'batch/v1', 'kind': 'Job', 'metadata': {'name': name, 'namespace': NAMESPACE},
                    'spec': {'backoffLimit': 0, 'activeDeadlineSeconds': 7200, 'template': {'spec': {
                        'restartPolicy': 'Never', 'automountServiceAccountToken': False,
                        'securityContext': {'runAsUser': 33, 'runAsGroup': 33, 'runAsNonRoot': True},
                        'nodeSelector': {'kubernetes.io/arch': 'arm64'}, 'containers': [container], 'volumes': volumes}}}})
        self.kube('wait', '--for=condition=Complete', 'job/' + name, '--timeout=7200s', timeout=7230)
        result = self.kube('logs', 'job/' + name, '--container=aws').decode()
        private_write(self.directory / (purpose + '.log'), result)
        return result

    def refresh(self):
        self.assert_fenced()
        self.require_stage('checkpoint')
        # Reject escaping/cyclic links before AWS CLI follows any source links.
        source = json.loads(self.exec('php', '/migration/manifest.php'))
        self.aws_job('checkpoint', ['s3', 'cp', '/source/data/.postgresql-migration/' + self.state['run'] + '/',
                                    f's3://{BACKUP_BUCKET}/nextcloud-migration/{self.state["run"]}/',
                                    '--recursive', '--only-show-errors'], True)
        args = ['s3', 'sync', '/source/', f's3://{MIRROR_BUCKET}/nextcloud-data/', '--only-show-errors']
        for pattern in EXCLUDES:
            args.extend(['--exclude', pattern])
        self.aws_job('refresh', args, True)  # Deliberately NO --delete.
        require(source == json.loads(self.exec('php', '/migration/manifest.php')), 'Source changed during S3 refresh')
        # AWS CLI auto-pagination; no --max-items or --no-paginate truncation.
        listing = json.loads(self.aws_job('inventory', ['s3api', 'list-objects-v2', '--bucket', MIRROR_BUCKET,
            '--prefix', 'nextcloud-data/', '--query', 'Contents', '--output', 'json'])) or []
        private_write(self.directory / 'source-manifest.json', source)
        private_write(self.directory / 's3-manifest.json', listing)
        comparison = compare_manifest(source, listing)
        private_write(self.directory / 'comparison.json', comparison)
        require(not comparison['missing'] and not comparison['size_mismatch'], 'S3 metadata comparison failed')
        checkpoint = json.loads(self.aws_job('checkpoint-list', ['s3api', 'list-objects-v2', '--bucket', BACKUP_BUCKET,
            '--prefix', f'nextcloud-migration/{self.state["run"]}/', '--query', 'Contents', '--output', 'json'])) or []
        names = {o['Key'].split('/')[-1]: o['Size'] for o in checkpoint}
        require(names.get('nextcloud.db') == self.state['checkpoint']['bytes']
                and names.get('config.tar') == self.state['checkpoint']['config_bytes']
                and all(names.get(k, 0) > 0 for k in ('baseline.json', 'references.json', 'database.sha256', 'complete')),
                'Checkpoint upload is incomplete')
        self.record('refreshed', comparison)

    def convert(self):
        self.assert_fenced()
        self.require_stage('checkpoint', 'refreshed')
        require(not self.state.get('conversion_started'), 'Never automatically retry a partially converted target')
        self.db('target')
        self.record('conversion_started')
        try:
            transcript = self.exec('php', '/migration/convert.php', timeout=7200, sensitive=True)
        except Stopped:
            for name in ('output', 'error'):
                path = self.directory / ('last-command-' + name + '.txt')
                if path.exists():
                    private_write(self.directory / ('conversion-' + name + '.txt'), path.read_text())
            raise
        private_write(self.directory / 'conversion.log', transcript.decode(errors='replace'))
        require(self.occ('config:system:get', 'dbtype') == 'pgsql', 'Conversion did not switch effective database')
        self.record('converted')

    def validate(self):
        self.assert_fenced()
        self.require_stage('converted')
        self.record('database_validation', self.db('validate'))
        status = json.loads(self.occ('status', '--output=json'))
        require(status['installed'] and not status.get('needsDbUpgrade'), 'Nextcloud is not ready')
        apps = json.loads(self.occ('app:list', '--output=json'))
        require(apps.get('enabled') == self.state['apps_before'].get('enabled'), 'Enabled apps changed')
        # ConvertType::saveDBInfo appends the explicitly supplied --port.
        require(self.occ('config:system:get', 'dbhost') == 'nextcloud-db.nextcloud.svc.cluster.local:5432',
                'Wrong effective database host')
        self.record('validated')

    @contextlib.contextmanager
    def http(self):
        self.assert_fenced()
        # Apache is launched as UID33 in the CLI-only pod with a purpose-built
        # config. Neither the Pod IP nor normal Service can reach this listener.
        configuration = '''ServerRoot /etc/apache2
PidFile /tmp/migration-apache.pid
DefaultRuntimeDir /tmp
Listen 127.0.0.1:8081
IncludeOptional /etc/apache2/mods-enabled/*.load
IncludeOptional /etc/apache2/mods-enabled/*.conf
ServerName nextcloud.seadogger-homelab
User www-data
Group www-data
DocumentRoot /var/www/html
ErrorLog /tmp/migration-apache-error.log
<Directory /var/www/html>
Require all granted
AllowOverride All
Options FollowSymLinks
</Directory>
'''
        self.exec('php', '-r', 'file_put_contents("/tmp/migration-apache.conf", stream_get_contents(STDIN));', data=configuration.encode())
        apache = ['env', 'APACHE_RUN_DIR=/tmp', 'APACHE_LOCK_DIR=/tmp', 'APACHE_LOG_DIR=/tmp',
                  'APACHE_RUN_USER=www-data', 'APACHE_RUN_GROUP=www-data',
                  'apache2', '-f', '/tmp/migration-apache.conf']
        self.exec(*apache, '-t')
        self.exec(*apache, '-k', 'start')
        try:
            # Inspect kernel socket bindings independently of the config string.
            sockets = self.exec('cat', '/proc/net/tcp', '/proc/net/tcp6').decode()
            listeners = [line.split()[1] for line in sockets.splitlines()[1:] if len(line.split()) > 3 and line.split()[3] == '0A']
            require(listeners == ['0100007F:1F91'], 'Unexpected network listener; keep access closed')
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
            log = open(self.directory / 'port-forward.log', 'wb')
            os.chmod(self.directory / 'port-forward.log', 0o600)
            process = subprocess.Popen(['kubectl', '--context', self.state['context'], '-n', NAMESPACE, 'port-forward', '--address=127.0.0.1',
                                        'pod/' + self.state['pod'], f'{port}:8081'], stdout=log, stderr=log)
            try:
                for _ in range(50):
                    require(process.poll() is None, 'Port forward exited')
                    try:
                        connection = socket.create_connection(('127.0.0.1', port), timeout=0.2)
                        connection.close(); break
                    except OSError:
                        time.sleep(0.1)
                else:
                    raise Stopped('Port forward did not become ready')
                yield port
            finally:
                process.terminate(); process.wait(timeout=10); log.close()
        finally:
            self.exec(*apache, '-k', 'stop')

    def request(self, port, method, path, body=None, auth=None, headers=None):
        hdrs = {'Host': 'nextcloud.seadogger-homelab', **(headers or {})}
        if auth:
            hdrs['Authorization'] = 'Basic ' + base64.b64encode((auth['username'] + ':' + auth['password']).encode()).decode()
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=30)
        try:
            connection.request(method, path, body=body, headers=hdrs)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def credentials(self):
        path = self.directory / 'webdav-credentials.json'
        require(path.exists() and not path.is_symlink(), 'Private webdav-credentials.json is required for canary validation')
        require(path.stat().st_mode & 0o077 == 0, 'WebDAV credential file must be mode0600')
        value = json.loads(path.read_text())
        require(value.get('username') and value.get('password'), 'Missing WebDAV credentials')
        return value

    def clean_canary(self, port, auth):
        path = self.state['canary_path']
        for i in range(4):
            content = ('nextcloud-migration:' + self.state['run'] + ':' + str(i)).encode()
            status, actual = self.request(port, 'GET', path + f'/probe-{i}.txt', auth=auth)
            if status == 404:
                continue
            require(status == 200 and actual == content, 'Canary cleanup encountered unexpected content; preserve it')
            status, _ = self.request(port, 'DELETE', path + f'/probe-{i}.txt', auth=auth)
            require(status == 204, 'Canary file cleanup failed')
        status, body = self.request(port, 'PROPFIND', path + '/', auth=auth, headers={'Depth': '1'})
        require(status == 207, 'Cannot verify canary folder contents')
        responses = ET.fromstring(body).findall('{DAV:}response')
        require(len(responses) == 1, 'Canary folder contains untracked files; do not delete')
        href = responses[0].findtext('{DAV:}href') or ''
        require(urllib.parse.unquote(urllib.parse.urlsplit(href).path).rstrip('/') ==
                urllib.parse.unquote(path).rstrip('/'), 'Canary listing does not identify the expected collection')
        status, _ = self.request(port, 'DELETE', path, auth=auth)
        require(status == 204, 'Canary folder cleanup failed')
        self.record('canary_cleaned')

    def canary(self):
        self.require_stage('validated')
        require(not self.state.get('canary_started'), 'Canary already attempted; inspect tracked paths before retrying')
        auth = self.credentials()
        path = '/remote.php/dav/files/' + urllib.parse.quote(auth['username'], safe='') + '/migration-validation-' + self.state['run']
        self.record('canary_path', path)
        self.record('canary_started')
        with self.http() as port:
            status, body = self.request(port, 'GET', '/status.php')
            require(status == 200 and not json.loads(body).get('maintenance'), 'HTTP status check failed')
            status, _ = self.request(port, 'MKCOL', path, auth=auth)
            require(status == 201, 'Canary folder was not newly created; never reuse an existing folder')
            self.record('canary_created')
            self.record('canary_writes_uncertain')
            try:
                def upload(i):
                    content = ('nextcloud-migration:' + self.state['run'] + ':' + str(i)).encode()
                    status, _ = self.request(port, 'PUT', path + f'/probe-{i}.txt', content, auth, {'If-None-Match': '*'})
                    require(status == 201, 'Parallel canary upload failed')
                    status, readback = self.request(port, 'GET', path + f'/probe-{i}.txt', auth=auth)
                    require(status == 200 and readback == content, 'Canary readback mismatch')
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                    list(pool.map(upload, range(4)))
                self.record('canary_writes_uncertain', False)
            finally:
                if not self.state.get('canary_writes_uncertain'):
                    self.clean_canary(port, auth)
        self.record('canary_passed')

    def backup(self):
        self.assert_fenced()
        self.require_stage('canary_passed')
        cron = self.get('cronjob', 'nextcloud-db-backup')
        name = 'nextcloud-db-backup-cutover-' + self.state['run']
        job = {'apiVersion': 'batch/v1', 'kind': 'Job', 'metadata': {'name': name, 'namespace': NAMESPACE},
               'spec': copy.deepcopy(cron['spec']['jobTemplate']['spec'])}
        self.apply(job)
        self.kube('wait', '--for=condition=Complete', 'job/' + name, '--timeout=1800s', timeout=1830)
        pods = json.loads(self.kube('get', 'pods', '-l', 'job-name=' + name, '-o', 'json'))['items']
        require(len(pods) == 1, 'Unexpected backup attempt count')
        uid = pods[0]['metadata']['uid']
        items = json.loads(self.aws_job('dump-list', ['s3api', 'list-objects-v2', '--bucket', BACKUP_BUCKET,
            '--prefix', 'nextcloud-postgresql/', '--query', 'Contents', '--output', 'json'])) or []
        backup = [o for o in items if '/' + uid + '/' in o['Key'] or ('-' + uid + '/') in o['Key']]
        require({o['Key'].split('/')[-1] for o in backup} == {'nextcloud.dump', 'SHA256SUMS', 'metadata.txt'}
                and all(o['Size'] > 0 for o in backup), 'Native backup S3 objects are incomplete')
        self.record('backup_verified', backup)

    def sync_application(self, source):
        require(self.execute, 'Mutation requires --execute')
        self.kube('patch', 'applications.argoproj.io', 'nextcloud', '--type=json', '-p',
                  json.dumps([{'op': 'replace', 'path': '/spec/source', 'value': source}]), namespace='argocd')
        self.patch('applications.argoproj.io', 'nextcloud', {'operation': {'sync': {'prune': False}}}, 'argocd')
        for _ in range(90):
            app = self.get('applications.argoproj.io', 'nextcloud', 'argocd')
            phase = app.get('status', {}).get('operationState', {}).get('phase')
            if not app.get('operation') and phase == 'Succeeded':
                return
            require(app.get('operation') or phase not in ('Failed', 'Error'), 'Argo sync failed')
            time.sleep(2)
        raise Stopped('Argo sync did not finish')

    def reopen(self):
        self.assert_fenced()
        self.require_stage('validated', 'canary_passed', 'canary_cleaned', 'backup_verified', 'runtime_health_reviewed')
        source = copy.deepcopy(self.state['application']['spec']['source'])
        overlay_url = ('https://raw.githubusercontent.com/seadogger-tech/seadogger-homelab/' +
                       self.state['core_revision'] + '/deployments/nextcloud/nextcloud-postgresql-values.yaml')
        source.setdefault('helm', {}).setdefault('valueFiles', []).append(overlay_url)
        self.protect_legacy_database()
        # Disable chart precedence but retain the old resources with explicit
        # Argo prune protection until their data/consumers have been inspected.
        overlay = {'replicaCount': 0, 'hpa': {'enabled': False}, 'internalDatabase': {'enabled': False},
                   'postgresql': {'enabled': False}, 'image': self.state['image_values'],
                   'global': {'image': {'registry': 'docker.io'}},
                   'mariadb': {'enabled': False}, 'externalDatabase': {'enabled': True, 'type': 'postgresql',
                   'host': 'nextcloud-db.nextcloud.svc.cluster.local', 'database': 'nextcloud',
                   'existingSecret': {'enabled': True, 'secretName': 'nextcloud-db-auth',
                                      'usernameKey': 'db-username', 'passwordKey': 'db-password'}}}
        source.setdefault('helm', {})['valuesObject'] = merge_dict(source.get('helm', {}).get('valuesObject', {}), overlay)
        self.sync_application(source)
        deployment = self.get('deployment', 'nextcloud')
        require(deployment['spec']['replicas'] == 0, 'Rendered chart did not honor replicas0')
        container = next(c for c in deployment['spec']['template']['spec']['containers'] if c['name'] == 'nextcloud')
        require(container['image'] == 'docker.io/library/nextcloud:' + self.state['image_values']['tag'],
                'Rendered Nextcloud image differs from the reviewed source digest')
        env = {e['name']: e for e in container.get('env', [])}
        require('SQLITE_DATABASE' not in env and env.get('POSTGRES_HOST', {}).get('value') ==
                'nextcloud-db.nextcloud.svc.cluster.local', 'Rendered deployment does not select the intended PostgreSQL')
        for key, secret_key in [('POSTGRES_USER', 'db-username'), ('POSTGRES_PASSWORD', 'db-password')]:
            ref = env.get(key, {}).get('valueFrom', {}).get('secretKeyRef', {})
            require(ref.get('name') == 'nextcloud-db-auth' and ref.get('key') == secret_key, 'Wrong rendered database secret')
        self.assert_fenced()
        final_values = copy.deepcopy(source['helm']['valuesObject'])
        final_values['replicaCount'] = self.state['deployment']['spec'].get('replicas', 1)
        self.deployment_marker(True, final_values)
        self.occ('maintenance:mode', '--off')
        self.kube('delete', 'pod', self.state['pod'], '--wait=true', '--timeout=180s', timeout=210)
        # Persist BEFORE requesting any web pod; an interrupted call may already
        # have reopened access. Never use an observed absence of writes to undo it.
        self.record('reopening_started')
        source['helm']['valuesObject']['replicaCount'] = self.state['deployment']['spec'].get('replicas', 1)
        self.sync_application(source)
        self.kube('rollout', 'status', 'deployment/nextcloud', '--timeout=300s', timeout=330)
        self.normal_health()
        self.record('reopened')
        self.patch('cronjob', 'nextcloud-s3-backup', {'spec': {'suspend': self.state['mirror']['spec'].get('suspend', False)}})
        policy = self.state['application']['spec'].get('syncPolicy', {})
        self.patch('applications.argoproj.io', 'nextcloud', {'spec': {'syncPolicy': policy}}, 'argocd')
        dbapp = self.get('applications.argoproj.io', 'nextcloud-db', 'argocd')
        patches = dbapp['spec']['source'].get('kustomize', {}).get('patches', [])
        patches = [p for p in patches if p.get('target', {}).get('name') != 'nextcloud-db-backup']
        patches.append({'target': {'kind': 'CronJob', 'name': 'nextcloud-db-backup'},
                        'patch': '- op: replace\n  path: /spec/suspend\n  value: false\n'})
        self.patch('applications.argoproj.io', 'nextcloud-db', {'spec': {'source': {'kustomize': {'patches': patches}}}}, 'argocd')
        for _ in range(90):
            if self.get('cronjob', 'nextcloud-db-backup')['spec'].get('suspend') is False:
                break
            time.sleep(2)
        else:
            raise Stopped('Nightly native backup activation did not reconcile')
        self.record('schedules_restored')

    def protect_legacy_database(self):
        resources = self.state['application'].get('status', {}).get('resources', [])
        legacy = [r for r in resources if r['name'].startswith('nextcloud-postgresql')]
        require(any(r['kind'] == 'StatefulSet' for r in legacy), 'Legacy database inventory is missing')
        for resource in legacy:
            require(resource.get('namespace') == NAMESPACE, 'Unexpected legacy resource namespace')
            kind = resource['kind'] + ('.' + resource['group'] if resource.get('group') else '')
            self.patch(kind, resource['name'], {'metadata': {'annotations': {
                'argocd.argoproj.io/sync-options': 'Prune=false,Delete=false',
                'argocd.argoproj.io/compare-options': 'IgnoreExtraneous'}}})
        self.record('legacy_resources_retained', [{'kind': r['kind'], 'name': r['name']} for r in legacy])

    def normal_health(self, database='pgsql', maintenance=False):
        pods = json.loads(self.kube('get', 'pods', '-l', SERVICE_LABELS, '-o', 'json'))['items']
        require(len(pods) == 1, 'Unexpected web pod count after reopening')
        pod = pods[0]['metadata']['name']
        # Readiness probes were absent on the original deployment. Check Apache
        # through its normal Service and bootstrap the effective DB explicitly.
        code = ('$c=curl_init("http://nextcloud:8080/status.php");'
                'curl_setopt_array($c,[CURLOPT_RETURNTRANSFER=>true,CURLOPT_TIMEOUT=>10,'
                'CURLOPT_HTTPHEADER=>["Host: nextcloud.seadogger-homelab"]]);'
                '$s=json_decode(curl_exec($c),true);'
                'exit(curl_getinfo($c,CURLINFO_HTTP_CODE)===200 && ($s["installed"]??false)'
                ' && ($s["maintenance"]??null)===' + ('true' if maintenance else 'false') +
                ' && !($s["needsDbUpgrade"]??true) ? 0:1);')
        for attempt in range(30):
            try:
                self.exec('php', '-r', code, pod=pod)
                require(self.occ('config:system:get', 'dbtype', pod=pod) == database, 'Normal pod uses an unexpected database')
                status = json.loads(self.occ('status', '--output=json', pod=pod))
                require(status['installed'] and not status.get('needsDbUpgrade'), 'Normal Nextcloud bootstrap failed')
                return
            except Stopped:
                if attempt == 29:
                    raise
                time.sleep(2)

    def deployment_marker(self, active, helm_values=None):
        # This local, gitignored Ansible input survives later main.yml runs.
        # A marker from another run is never overwritten.
        if DEPLOYMENT_STATE.exists():
            marker = json.loads(DEPLOYMENT_STATE.read_text())
            require(marker.get('nextcloud_migration_run') == self.state['run'], 'Deployment marker belongs to another run')
        private_write(DEPLOYMENT_STATE, {'nextcloud_postgresql_active': active,
                                       'nextcloud_postgresql_revision': self.state['core_revision'],
                                       'nextcloud_migration_helm_values': helm_values or {},
                                       'nextcloud_migration_run': self.state['run']})

    def pause_after_reopening(self):
        # In-flight GitOps operations must finish before asserting a durable pause.
        self.patch('applications.argoproj.io', 'nextcloud', {'spec': {'syncPolicy': {'automated': None}}}, 'argocd')
        self.patch('cronjob', 'nextcloud-s3-backup', {'spec': {'suspend': True}})
        for _ in range(90):
            self.patch('deployment', 'nextcloud', {'spec': {'replicas': 0}})
            app = self.get('applications.argoproj.io', 'nextcloud', 'argocd')
            if not app.get('operation') and app.get('status', {}).get('operationState', {}).get('phase') != 'Running':
                break
            time.sleep(2)
        else:
            raise Stopped('Could not establish pause while GitOps is running; operator intervention required')
        self.patch('deployment', 'nextcloud', {'spec': {'replicas': 0}})
        self.kube('wait', '--for=delete', 'pod', '-l', SERVICE_LABELS, '--timeout=180s', timeout=210)
        endpoints = self.get('endpoints', 'nextcloud')
        require(not any(s.get('addresses') or s.get('notReadyAddresses') for s in endpoints.get('subsets', [])),
                'Service endpoints remain; pause is not established')
        self.record('paused_after_reopening')

    def rollback(self):
        self.assert_fenced()
        self.require_stage('checkpoint')
        require(not self.state.get('canary_writes_uncertain'),
                'Canary write outcome is uncertain; preserve PostgreSQL and test files for inspection')
        if self.state.get('canary_started') and not self.state.get('canary_created'):
            with self.http() as port:
                status, _ = self.request(port, 'PROPFIND', self.state['canary_path'],
                                         auth=self.credentials(), headers={'Depth': '0'})
                require(status == 404, 'Canary creation outcome is uncertain; preserve data and inspect')
        if self.state.get('canary_created') and not self.state.get('canary_cleaned'):
            with self.http() as port:
                self.clean_canary(port, self.credentials())
        # The CLI-only pod must have no lingering PHP/Apache processes. Do not
        # replace a SQLite file while a process might still hold its WAL open.
        processes = self.exec('ps', '-eo', 'comm=').decode().split()
        require(not any(p.startswith(('php', 'apache', 'cron')) for p in processes), 'Application process still active')
        self.db('rollback')
        checkpoint = '/var/www/html/data/.postgresql-migration/' + self.state['run']
        self.exec('tar', '-xpf', checkpoint + '/config.tar', '-C', '/var/www/html/config', '--no-same-owner')
        require(self.occ('config:system:get', 'dbtype') == 'sqlite3', 'Restored config is not SQLite')
        source = copy.deepcopy(self.state['application']['spec']['source'])
        original_values = source.setdefault('helm', {}).get('valuesObject', {})
        source['helm']['valuesObject'] = merge_dict(original_values, {'replicaCount': 0, 'hpa': {'enabled': False}})
        self.sync_application(source)
        self.occ('maintenance:mode', '--on' if self.state['maintenance_before'] else '--off')
        self.kube('delete', 'pod', self.state['pod'], '--wait=true', '--timeout=180s', timeout=210)
        self.record('rollback_reopening_started')
        original = copy.deepcopy(self.state['application']['spec']['source'])
        helm = original.setdefault('helm', {})
        helm['valuesObject'] = merge_dict(helm.get('valuesObject', {}), {
            'image': self.state['image_values'], 'global': {'image': {'registry': 'docker.io'}}})
        self.deployment_marker(False, helm['valuesObject'])
        self.sync_application(original)
        self.kube('rollout', 'status', 'deployment/nextcloud', '--timeout=300s', timeout=330)
        self.normal_health('sqlite3', self.state['maintenance_before'])
        self.patch('cronjob', 'nextcloud-s3-backup', {'spec': {'suspend': self.state['mirror']['spec'].get('suspend', False)}})
        self.patch('applications.argoproj.io', 'nextcloud', {'spec': {'syncPolicy': self.state['application']['spec'].get('syncPolicy', {})}}, 'argocd')
        self.record('rolled_back')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=PHASES)
    parser.add_argument('--state-dir', required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--writers-reviewed', action='store_true', help='Record completed external/host writer inventory at prepare time')
    parser.add_argument('--health-reviewed', action='store_true', help='Attest the runbook runtime health/log/alert checks before reopening')
    args = parser.parse_args()
    migration = Migration(args.state_dir, args.execute)
    lock = open(migration.directory / '.lock', 'a')
    os.chmod(migration.directory / '.lock', 0o600)
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Stopped('Another migration phase holds the state lock')
        migration.state = json.loads(migration.path.read_text()) if migration.path.exists() else {}
        if args.phase == 'status':
            print(json.dumps({k: v for k, v in migration.state.items()
                              if isinstance(v, bool) or k in ('run', 'context')}, indent=2))
            return 0
        if not args.execute:
            print(f'PLAN ONLY: {args.phase}; state={migration.directory}. Read the runbook and use --execute for the scheduled phase.')
            return 0
        require(not args.plan, 'Choose either --plan or --execute')
        require(not migration.state.get('rolled_back') and not migration.state.get('schedules_restored'),
                'This run is finished; preserve its evidence and do not repeat phases')
        try:
            if args.phase == 'reopen' and args.health_reviewed:
                migration.record('runtime_health_reviewed')
            getattr(migration, args.phase)()
            if args.phase == 'prepare' and args.writers_reviewed:
                migration.record('writers_reviewed')
            print('Completed phase: ' + args.phase)
            return 0
        except (Stopped, subprocess.TimeoutExpired, OSError, ValueError) as error:
            print('STOPPED: ' + str(error), file=sys.stderr)
            if migration.state.get('reopening_started') or migration.state.get('rollback_reopening_started'):
                # Re-fence without touching database/configuration or discarding writes.
                migration.pause_after_reopening()
                print('Access paused; the current database and files are preserved. No further rollback attempted.', file=sys.stderr)
            elif args.phase in ('refresh', 'convert', 'validate', 'canary', 'backup', 'reopen') and migration.state.get('checkpoint'):
                try:
                    migration.rollback()
                    print('Returned to the saved SQLite checkpoint before reopening.', file=sys.stderr)
                except Exception:
                    if migration.state.get('rollback_reopening_started'):
                        migration.pause_after_reopening()
                    print('Safe automatic rollback could not be established. Inspect private state and verify the barrier.', file=sys.stderr)
            return 1
    finally:
        lock.close()


if __name__ == '__main__':
    sys.exit(main())
