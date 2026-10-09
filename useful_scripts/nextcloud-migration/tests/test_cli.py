"""Exercise the phase CLI with Kubernetes/AWS simulated at subprocess.run only."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
CONVERTER_CONTRACT = json.loads((SCRIPTS / 'tests/fixtures/converter-contract.json').read_text())
spec = importlib.util.spec_from_file_location('cli_migration', SCRIPTS / 'migrate.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = {
            'run': 'test-run', 'context': 'isolated-test', 'pod': 'maintenance', 'fenced': True,
            'checkpoint': {'bytes': 4096, 'config_bytes': 512}, 'refreshed': True,
            'application': {'spec': {'source': {'helm': {}}, 'syncPolicy': {'automated': {}}}},
            'mirror': {'spec': {'suspend': False}}, 'maintenance_before': False,
            'core_revision': 'a' * 40,
            'image_values': {'registry': 'docker.io', 'repository': 'library/nextcloud',
                             'tag': '32.0.6-apache@sha256:' + 'b' * 64},
        }
        self.calls = []
        self.jobs = {}
        self.replicas = 0
        self.target_error = False
        self.source = [{'key': 'nextcloud-data/space and\nnewline', 'size': 3},
                       {'key': 'nextcloud-data/second', 'size': 5}]
        self.objects = [{'Key': row['key'], 'Size': row['size']} for row in self.source]
        self.objects.append({'Key': 'nextcloud-data/remote-only', 'Size': 99})
        self.rollback_failure = False

    def command(self, args, **kwargs):
        self.calls.append(args)
        self.assertEqual(args[:3], ['kubectl', '--context', 'isolated-test'])
        verb, *rest = args[6:]
        reply = b''
        code = 0
        if verb == 'get':
            kind = rest[0]
            if kind == 'deployment':
                reply = {'spec': {'replicas': self.replicas}}
            elif kind == 'endpoints':
                reply = {}
            elif kind == 'applications.argoproj.io':
                reply = {'metadata': {}, 'spec': {}, 'status': {'operationState': {'phase': 'Succeeded'}}}
            elif kind == 'cronjob':
                reply = {'spec': {'suspend': True}}
            elif kind == 'pods' and '-l' in rest and self.reopened():
                reply = {'items': [{'metadata': {'name': 'normal-web'}}]}
            else:
                reply = {'items': []}
        elif verb == 'exec':
            command = rest[rest.index('--') + 1:]
            if '/migration/convert.php' in command:
                code, reply = 1, b'The following tables will not be converted: oc_unknown\n'
            elif '/migration/database.php' in command:
                action = command[-2]
                code = 1 if action == 'target' and self.target_error else 0
                reply = {} if code == 0 else b'Target is not empty'
            elif '/migration/manifest.php' in command:
                reply = self.source
            elif command[0] == 'ps':
                reply = b'sleep\n'
            elif 'dbhost' in command:
                reply = CONVERTER_CONTRACT['saved_dbhost'].encode()
            elif 'app:list' in command:
                reply = {'enabled': {'files': '2.4.0'}}
            elif 'dbtype' in command:
                reply = b'sqlite3'
            elif 'status' in command:
                reply = {'installed': True, 'needsDbUpgrade': False}
        elif verb == 'apply':
            job = json.loads(kwargs['input'])
            self.jobs[job['metadata']['name']] = job['spec']['template']['spec']['containers'][0]['args']
        elif verb == 'logs':
            job_args = self.jobs[rest[0].removeprefix('job/')]
            if 'list-objects-v2' in job_args:
                prefix = job_args[job_args.index('--prefix') + 1]
                reply = self.objects if prefix == 'nextcloud-data/' else [
                    {'Key': prefix + name, 'Size': size} for name, size in
                    [('nextcloud.db', 4096), ('config.tar', 512), ('baseline.json', 2),
                     ('references.json', 2), ('database.sha256', 64), ('complete', 1)]]
        elif verb == 'rollout' and self.rollback_failure:
            code, reply = 1, b'Simulated startup failure after reopening SQLite'
        elif verb not in ('patch', 'wait', 'delete', 'rollout'):
            self.fail('Unexpected Kubernetes boundary: ' + repr(args))
        if not isinstance(reply, bytes):
            reply = json.dumps(reply).encode()
        return subprocess.CompletedProcess(args, code, reply, b'Simulated failure' if code else b'')

    def reopened(self):
        state = json.loads((self.root / 'state.json').read_text())
        return state.get('rollback_reopening_started') or state.get('reopening_started')

    def run_phase(self, phase, execute=True):
        (self.root / 'state.json').write_text(json.dumps(self.state))
        argv = ['migrate.py', phase, '--state-dir', str(self.root)] + (['--execute'] if execute else [])
        self.stderr = io.StringIO()
        with patch('sys.argv', argv), patch.object(m.subprocess, 'run', side_effect=self.command), \
             patch.object(m, 'DEPLOYMENT_STATE', self.root / 'deployment-marker.json'), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(self.stderr):
            result = m.main()
        self.state = json.loads((self.root / 'state.json').read_text())
        return result

    def database_actions(self):
        return [args[-2] for args in self.calls if '/migration/database.php' in args]

    def test_fence_mounts_source_claim_once_and_exposes_its_root(self):
        self.state.update(prepared=True, writers_reviewed=True, image='nextcloud@sha256:' + 'b' * 64,
                          deployment={'spec': {'template': {'spec': {
                              'containers': [{'name': 'nextcloud', 'volumeMounts': [
                                  {'name': 'app-data', 'mountPath': '/var/www/html/data', 'subPath': 'data'}]}],
                              'volumes': [{'name': 'app-data', 'persistentVolumeClaim': {
                                  'claimName': 'nextcloud-nextcloud'}}]}}}})
        self.replicas = 1
        original = self.command
        pods = []

        def boundary(args, **kwargs):
            if args == ['kubectl', 'config', 'current-context']:
                return subprocess.CompletedProcess(args, 0, b'isolated-test', b'')
            verb, *rest = args[6:]
            if verb == 'get' and rest[0] == 'pods' and '-l' in rest and self.replicas:
                return subprocess.CompletedProcess(args, 0, b'{"items":[{"metadata":{"name":"web"}}]}', b'')
            if verb == 'patch' and rest[0] == 'deployment':
                self.replicas = json.loads(args[-1])['spec']['replicas']
            if verb == 'apply':
                resource = json.loads(kwargs['input'])
                if resource['kind'] == 'Pod':
                    pods.append(resource)
                return subprocess.CompletedProcess(args, 0, b'', b'')
            return original(args, **kwargs)

        self.command = boundary
        self.assertEqual(self.run_phase('fence'), 0, self.stderr.getvalue())
        self.assertTrue(self.state['maintenance_pod_ready'])
        self.assertEqual(len(pods), 1)
        spec = pods[0]['spec']
        claims = [v for v in spec['volumes'] if v.get('persistentVolumeClaim', {}).get('claimName') == 'nextcloud-nextcloud']
        self.assertEqual(len(claims), 1, 'Duplicate PVC volume names leave kubelet waiting for an unmounted alias')
        mounts = spec['containers'][0]['volumeMounts']
        self.assertIn({'name': 'app-data', 'mountPath': '/source'}, mounts)
        self.assertIn({'name': 'app-data', 'mountPath': '/var/www/html/data', 'subPath': 'data'}, mounts)
        self.assertNotIn('fsGroup', spec['securityContext'])

    def test_validation_accepts_host_and_port_saved_by_pinned_converter(self):
        self.state['converted'] = True
        self.state['apps_before'] = {'enabled': {'files': '2.4.0'}}
        self.assertEqual(self.run_phase('validate'), 0, self.stderr.getvalue())
        self.assertTrue(self.state['validated'])
        self.assertEqual(self.database_actions(), ['validate'])

    def test_plan_makes_no_cluster_calls(self):
        self.assertEqual(self.run_phase('convert', execute=False), 0)
        self.assertFalse(self.calls)

    def test_open_writer_barrier_blocks_conversion_and_rollback(self):
        self.replicas = 1
        self.assertEqual(self.run_phase('convert'), 1)
        self.assertFalse(self.database_actions())
        self.assertFalse(self.state.get('conversion_started'))
        self.assertIn('Normal deployment is not scaled to zero', self.stderr.getvalue())

    def test_omission_failure_retains_transcript_and_target_while_restoring_sqlite(self):
        self.assertEqual(self.run_phase('convert'), 1)
        self.assertTrue(self.state['conversion_started'])
        self.assertTrue(self.state['rolled_back'])
        self.assertEqual(self.database_actions(), ['target', 'rollback'])
        self.assertIn('oc_unknown', (self.root / 'conversion-output.txt').read_text())
        self.assertEqual((self.root / 'conversion-output.txt').stat().st_mode & 0o777, 0o600)
        self.assertFalse(any('DROP' in str(args) or 'TRUNCATE' in str(args) for args in self.calls))
        marker = json.loads((self.root / 'deployment-marker.json').read_text())
        self.assertFalse(marker['nextcloud_postgresql_active'])
        self.assertEqual(marker['nextcloud_migration_helm_values']['image'], self.state['image_values'])

    def test_nonempty_and_previously_started_targets_are_never_converted(self):
        for started in (False, True):
            with self.subTest(conversion_started=started):
                self.state.pop('rolled_back', None)
                self.state.pop('rollback_reopening_started', None)
                self.state['conversion_started'] = started
                self.target_error = True
                self.calls.clear()
                self.assertEqual(self.run_phase('convert'), 1)
                self.assertFalse(any('/migration/convert.php' in args for args in self.calls))
                self.assertEqual(self.database_actions(), ['rollback'] if started else ['target', 'rollback'])

    def test_either_reopening_boundary_pauses_without_touching_database(self):
        for flag in ('reopening_started', 'rollback_reopening_started'):
            with self.subTest(boundary=flag):
                self.state.pop('reopening_started', None)
                self.state.pop('rollback_reopening_started', None)
                self.state[flag] = True
                self.calls.clear()
                self.assertEqual(self.run_phase('rollback'), 1)
                self.assertTrue(self.state['paused_after_reopening'])
                self.assertFalse(self.database_actions())
                self.assertFalse(any('exec' in args for args in self.calls))
                patches = [json.loads(args[-1]) for args in self.calls if 'patch' in args]
                self.assertIn({'spec': {'replicas': 0}}, patches)
                self.assertIn({'spec': {'syncPolicy': {'automated': None}}}, patches)

    def test_failed_automatic_rollback_startup_pauses_without_restoring_twice(self):
        self.rollback_failure = True
        self.assertEqual(self.run_phase('convert'), 1)
        self.assertTrue(self.state['rollback_reopening_started'])
        self.assertTrue(self.state['paused_after_reopening'])
        self.assertEqual(self.database_actions().count('rollback'), 1)

    def test_refresh_checks_every_object_and_retains_remote_only_files(self):
        self.assertEqual(self.run_phase('refresh'), 0)
        self.assertEqual(self.state['refreshed']['matched'], 2)
        self.assertEqual(self.state['refreshed']['remote_only'], 1)
        for command in self.jobs.values():
            self.assertNotIn('--delete', command)
            self.assertNotIn('--no-paginate', command)
            self.assertNotIn('--max-items', command)

    def test_incomplete_refresh_prevents_conversion_and_records_all_mismatches(self):
        self.objects = [{'Key': 'nextcloud-data/second', 'Size': 4}]
        self.state.pop('refreshed')
        self.assertEqual(self.run_phase('refresh'), 1)
        comparison = json.loads((self.root / 'comparison.json').read_text())
        self.assertEqual(comparison['missing'], ['nextcloud-data/space and\nnewline'])
        self.assertEqual(comparison['size_mismatch'], ['nextcloud-data/second'])
        self.assertFalse(self.state.get('refreshed'))
        self.assertTrue(self.state['rolled_back'])
        self.assertFalse(any('/migration/convert.php' in args for args in self.calls))


if __name__ == '__main__':
    unittest.main()
