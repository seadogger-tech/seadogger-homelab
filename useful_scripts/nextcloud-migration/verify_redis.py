#!/usr/bin/env python3
"""Verify live Nextcloud Redis locking with a temporary, authenticated WebDAV file."""

import argparse
import base64
import http.client
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.parse
import uuid
import xml.etree.ElementTree as ET


PHP_CONFIG = r'''
$directory = '/var/www/html/config/';
$files = ['config.php', 'apcu.config.php', 'redis.config.php'];
$merged = [];
foreach (glob($directory . '*.config.php') as $path) {
    if (!in_array(basename($path), $files, true) &&
        preg_match('/memcache\.(local|locking|distributed)/', file_get_contents($path))) {
        fwrite(STDERR, 'Another config fragment sets a cache key');
        exit(2);
    }
}
foreach ($files as $file) {
    unset($CONFIG);
    include $directory . $file;
    if (isset($CONFIG) && is_array($CONFIG)) {
        $merged = array_replace_recursive($merged, $CONFIG);
    }
}
echo json_encode([
    'local' => $merged['memcache.local'] ?? null,
    'locking' => $merged['memcache.locking'] ?? null,
    'distributed' => $merged['memcache.distributed'] ?? null,
    'redis_host' => $merged['redis']['host'] ?? null,
    'session_handler' => ini_get('session.save_handler'),
]);
'''


class ValidationError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def credentials(path):
    require(path.is_file() and not path.is_symlink(), 'Protected WebDAV credential file is required')
    require(path.stat().st_mode & 0o077 == 0, 'WebDAV credential file must be mode 0600')
    value = json.loads(path.read_text())
    require(isinstance(value, dict) and value.get('username') and value.get('password'),
            'WebDAV username and password are required')
    return value


def kube(context, namespace, *args):
    result = subprocess.run(['kubectl', '--context', context, '-n', namespace, *args],
                            capture_output=True, text=True, timeout=30)
    require(result.returncode == 0, f'kubectl {args[0]} failed: {result.stderr.strip()}')
    return result.stdout


def check_config(context):
    application = json.loads(kube(context, 'argocd', 'get', 'application', 'nextcloud', '-o', 'json'))
    status = application.get('status', {})
    require(status.get('sync', {}).get('status') == 'Synced' and
            status.get('health', {}).get('status') == 'Healthy', 'Nextcloud GitOps Application is not Synced/Healthy')
    value_files = application.get('spec', {}).get('source', {}).get('helm', {}).get('valueFiles', [])
    require(any('nextcloud-redis-values.yaml' in value for value in value_files),
            'Nextcloud Application does not select the Redis overlay')
    deployment = json.loads(kube(context, 'nextcloud', 'get', 'deployment', 'nextcloud', '-o', 'json'))
    require(deployment.get('status', {}).get('readyReplicas', 0) >= 1, 'Nextcloud has no Ready Pod')
    selected = json.loads(kube(context, 'nextcloud', 'exec', 'deployment/nextcloud', '--',
                               'php', '-r', PHP_CONFIG))
    require(selected == {
        'local': '\\OC\\Memcache\\APCu',
        'locking': '\\OC\\Memcache\\Redis',
        'distributed': None,
        'redis_host': 'tcp://nextcloud-redis.nextcloud.svc.cluster.local',
        'session_handler': 'files',
    }, 'Effective cache or PHP session selection differs from the lock-only design')
    print('PASS GitOps health, Ready Pod, APCu local cache, Redis locking, no distributed cache, file-backed sessions',
          flush=True)


def request(port, auth, method, path, body=None, headers=None):
    header = {'Host': 'nextcloud.seadogger-homelab', 'Authorization': auth, **(headers or {})}
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=120)
    try:
        print(f'{method}: started', flush=True)
        connection.request(method, path, body=body, headers=header)
        response = connection.getresponse()
        result = response.status, response.read()
        print(f'{method}: {response.status}', flush=True)
        return result
    finally:
        connection.close()


def cleanup(probe, folder, file, content):
    status, actual = probe('GET', file)
    if status == 200:
        require(actual == content, 'Probe path contains unexpected data; preserved for inspection')
        status, _ = probe('DELETE', file)
        require(status == 204, 'Could not delete probe file; preserved for inspection')
    else:
        require(status == 404, 'Could not inspect probe file; preserved for inspection')
    status, body = probe('PROPFIND', folder + '/', headers={'Depth': '1'})
    require(status == 207, 'Could not list probe folder; preserved for inspection')
    responses = ET.fromstring(body).findall('{DAV:}response')
    require(len(responses) == 1, 'Probe folder contains other files; preserved for inspection')
    href = responses[0].findtext('{DAV:}href') or ''
    require(urllib.parse.unquote(urllib.parse.urlsplit(href).path).rstrip('/') ==
            urllib.parse.unquote(folder).rstrip('/'), 'Probe folder listing differs; preserved for inspection')
    status, _ = probe('DELETE', folder)
    require(status == 204, 'Could not delete probe folder; preserved for inspection')


def canary(probe, username, token=None):
    token = token or uuid.uuid4().hex
    folder = '/remote.php/dav/files/' + urllib.parse.quote(username, safe='') + '/redis-validation-' + token
    file = folder + '/probe.txt'
    content = ('redis-lock-validation-' + token).encode()
    status, body = probe('GET', '/status.php')
    require(status == 200 and not json.loads(body).get('maintenance'), 'Nextcloud status check failed')
    attempted = False
    try:
        attempted = True
        status, _ = probe('MKCOL', folder)
        require(status == 201, f'Probe folder was not newly created; inspect {folder}')
        status, _ = probe('PUT', file, body=content, headers={'If-None-Match': '*'})
        require(status == 201, 'Probe file was not newly created')
        status, actual = probe('GET', file)
        require(status == 200 and actual == content, 'Probe readback differs')
    except BaseException:
        if attempted:
            print('Probe data needs inspection:', folder, flush=True)
        raise
    try:
        cleanup(probe, folder, file, content)
    except Exception:
        print('Probe data needs inspection:', folder, flush=True)
        raise
    print('PASS authenticated WebDAV create, exact readback, and verified cleanup', flush=True)


def validate(context, credential_file):
    secret = credentials(credential_file)
    check_config(context)
    auth = 'Basic ' + base64.b64encode((secret['username'] + ':' + secret['password']).encode()).decode()
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen(['kubectl', '--context', context, '-n', 'nextcloud', 'port-forward',
                                    '--address=127.0.0.1', 'deployment/nextcloud', f'{port}:80'],
                                   stdout=log, stderr=log)
        try:
            for _ in range(100):
                require(process.poll() is None, 'Nextcloud Pod port forward exited')
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                raise ValidationError('Nextcloud Pod port forward did not open')
            canary(lambda method, path, body=None, headers=None:
                   request(port, auth, method, path, body, headers), secret['username'])
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context', required=True, help='Explicit kubectl context for the target cluster')
    parser.add_argument('--credentials', required=True, type=Path, help='Mode-0600 JSON WebDAV credential file')
    args = parser.parse_args()
    try:
        validate(args.context, args.credentials)
    except (ValidationError, OSError, subprocess.TimeoutExpired, ValueError, ET.ParseError) as error:
        parser.exit(1, f'FAIL {error}\n')


if __name__ == '__main__':
    main()
