"""Local integration and fault tests; never contact a cluster or AWS."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('migration', SCRIPTS / 'migrate.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class FilesystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.config = self.root / 'config'
        self.config.mkdir()
        (self.config / 'config.php').write_text('original config')
        self.env = dict(os.environ, NC_MIGRATION_DATA=str(self.root), NC_MIGRATION_CONFIG=str(self.config),
                        NC_MIGRATION_SOURCE=str(self.root))

    def php(self, script, *args):
        return subprocess.run(['php', str(SCRIPTS / script), *args], env=self.env, capture_output=True)

    def checkpoint(self):
        db = sqlite3.connect(self.root / 'nextcloud.db')
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA wal_autocheckpoint=0')
        db.execute('CREATE TABLE oc_items (id INTEGER PRIMARY KEY, value TEXT)')
        db.execute('CREATE TABLE oc_users (uid TEXT, displayname TEXT)')
        db.execute('CREATE TABLE oc_share (id INTEGER, share_type INTEGER, share_with TEXT, uid_owner TEXT, file_source INTEGER, file_target TEXT, permissions INTEGER)')
        db.execute('CREATE TABLE oc_filecache (fileid INTEGER, storage INTEGER, path TEXT, parent INTEGER, name TEXT, size INTEGER, mimetype INTEGER)')
        db.execute('CREATE TABLE oc_storages (numeric_id INTEGER, id TEXT)')
        db.executemany('INSERT INTO oc_items(value) VALUES (?)', [('committed in WAL',), ('second',)])
        db.commit()
        self.addCleanup(db.close)
        self.assertGreater((self.root / 'nextcloud.db-wal').stat().st_size, 0)
        result = self.php('database.php', 'checkpoint', 'test-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        return db, self.root / '.postgresql-migration/test-run'

    def test_checkpoint_reads_committed_wal_and_refuses_overwrite(self):
        _, checkpoint = self.checkpoint()
        with contextlib.closing(sqlite3.connect(checkpoint / 'nextcloud.db')) as copy:
            self.assertEqual(copy.execute('SELECT value FROM oc_items ORDER BY id').fetchall(),
                             [('committed in WAL',), ('second',)])
        before = (checkpoint / 'nextcloud.db').read_bytes()
        self.assertNotEqual(self.php('database.php', 'checkpoint', 'test-run').returncode, 0)
        self.assertEqual((checkpoint / 'nextcloud.db').read_bytes(), before)

    def test_corrupt_checkpoint_cannot_replace_original(self):
        db, checkpoint = self.checkpoint()
        db.close()
        original = (self.root / 'nextcloud.db').read_bytes()
        (checkpoint / 'nextcloud.db').write_bytes(b'corrupt')
        self.assertNotEqual(self.php('database.php', 'rollback', 'test-run').returncode, 0)
        self.assertEqual((self.root / 'nextcloud.db').read_bytes(), original)
        self.assertEqual((self.config / 'config.php').read_text(), 'original config')

    def test_rollback_preserves_current_database_sidecars_and_config(self):
        db, checkpoint = self.checkpoint()
        db.execute("INSERT INTO oc_items(value) VALUES ('later')")
        db.commit()
        db.close()  # Caller must stop every database process before rollback.
        (self.root / 'nextcloud.db-wal').write_bytes(b'old sidecar')
        (checkpoint / 'config.tar').write_bytes(b'archive verified by phase runner')
        (checkpoint / 'complete').write_text('complete')
        result = self.php('database.php', 'rollback', 'test-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        preserved = checkpoint / 'preserved-before-rollback'
        self.assertEqual((preserved / 'nextcloud.db-wal').read_bytes(), b'old sidecar')
        self.assertEqual((preserved / 'config/config.php').read_text(), 'original config')
        self.assertFalse((self.root / 'nextcloud.db-wal').exists())
        with contextlib.closing(sqlite3.connect(self.root / 'nextcloud.db')) as restored:
            self.assertEqual(restored.execute('SELECT COUNT(*) FROM oc_items').fetchone()[0], 2)
        self.assertNotEqual(self.php('database.php', 'rollback', 'test-run').returncode, 0)

    def test_reference_hashes_are_independent_of_uid_collation(self):
        db, checkpoint = self.checkpoint()
        for uid in ['a', 'Z', 'A', 'é']:
            db.execute('INSERT INTO oc_users VALUES (?, ?)', (uid, uid))
        db.commit()
        result = self.php('database.php', 'checkpoint', 'collation-one')
        self.assertEqual(result.returncode, 0, result.stderr)
        db.execute('ALTER TABLE oc_users RENAME TO old_users')
        db.execute('CREATE TABLE oc_users (uid TEXT COLLATE NOCASE, displayname TEXT)')
        db.execute('INSERT INTO oc_users SELECT * FROM old_users')
        db.execute('DROP TABLE old_users')
        db.commit()
        result = self.php('database.php', 'checkpoint', 'collation-two')
        self.assertEqual(result.returncode, 0, result.stderr)
        base = self.root / '.postgresql-migration'
        self.assertEqual((base / 'collation-one/references.json').read_bytes(),
                         (base / 'collation-two/references.json').read_bytes())

    def test_manifest_special_names_exclusions_and_internal_links(self):
        (self.root / 'space and\nnewline').write_bytes(b'abc')
        (self.root / 'alias').symlink_to('space and\nnewline')
        cache = self.root / 'user/cache'
        cache.mkdir(parents=True)
        (cache / 'excluded').write_text('no')
        result = self.php('manifest.php')
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = {r['key']: r['size'] for r in json.loads(result.stdout)}
        self.assertEqual(rows['nextcloud-data/space and\nnewline'], 3)
        self.assertEqual(rows['nextcloud-data/alias'], 3)
        self.assertNotIn('nextcloud-data/user/cache/excluded', rows)

    def test_manifest_rejects_escaping_and_cyclic_links_without_partial_output(self):
        link = self.root / 'escape'
        link.symlink_to('/etc/hosts')
        result = self.php('manifest.php')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(result.stdout)
        link.unlink()
        (self.root / 'cycle').symlink_to(self.root, target_is_directory=True)
        result = self.php('manifest.php')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(result.stdout)


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.migration = m.Migration(self.temp.name, True)
        self.migration.state = {'run': 'test-run', 'pod': 'maintenance', 'fenced': True,
                                'checkpoint': True, 'refreshed': True, 'context': 'test'}

    def test_metadata_compare_detects_all_missing_sizes_and_duplicates(self):
        source = [{'key': 'a', 'size': 1}, {'key': 'b', 'size': 2}]
        actual = [{'Key': 'a', 'Size': 0}, {'Key': 'extra', 'Size': 3}]
        self.assertEqual(m.compare_manifest(source, actual),
                         {'missing': ['b'], 'size_mismatch': ['a'], 'remote_only': 1, 'matched': 0})
        with self.assertRaises(m.Stopped):
            m.compare_manifest(source + source, actual)
        with self.assertRaises(m.Stopped):
            m.compare_manifest(source, actual + actual)

    def test_fence_stops_for_web_replicas_pods_endpoints_and_argo(self):
        cases = [('deployment', {'spec': {'replicas': 1}}),
                 ('selected-pods', {'items': [{'metadata': {'name': 'web'}}]}),
                 ('endpoints', {'subsets': [{'notReadyAddresses': [{}]}]}),
                 ('applications.argoproj.io', {'metadata': {}, 'spec': {'syncPolicy': {'automated': {'selfHeal': True}}}}),
                 ('applications.argoproj.io', {'metadata': {}, 'spec': {'syncPolicy': {'automated': {}}}})]
        baseline = {'deployment': {'spec': {'replicas': 0}}, 'selected-pods': {'items': []},
                    'endpoints': {'subsets': []}, 'applications.argoproj.io': {'metadata': {}, 'spec': {}},
                    'horizontalpodautoscalers': {'items': []},
                    'cronjob': {'spec': {'suspend': True}}, 'jobs': {'items': []}, 'pods': {'items': []}}
        for kind, bad in cases:
            with self.subTest(kind=kind):
                values = dict(baseline, **{kind: bad})
                with patch.object(self.migration, 'get', side_effect=lambda k, *a: values[k]), \
                     patch.object(self.migration, 'kube', return_value=json.dumps(values['selected-pods']).encode()):
                    with self.assertRaises(m.Stopped):
                        self.migration.assert_fenced()

    def test_partial_conversion_is_never_retried(self):
        self.migration.state['conversion_started'] = True
        with patch.object(self.migration, 'assert_fenced'), patch.object(self.migration, 'db') as db:
            with self.assertRaises(m.Stopped):
                self.migration.convert()
            db.assert_not_called()

    def test_post_reopening_rejects_rollback_before_any_cluster_call(self):
        self.migration.state['reopening_started'] = True
        with patch.object(self.migration, 'get') as get, patch.object(self.migration, 'db') as db:
            with self.assertRaises(m.Stopped):
                self.migration.rollback()
            get.assert_not_called()
            db.assert_not_called()

    def test_uncertain_canary_prevents_database_rollback(self):
        self.migration.state['canary_writes_uncertain'] = True
        with patch.object(self.migration, 'assert_fenced'), patch.object(self.migration, 'db') as db:
            with self.assertRaises(m.Stopped):
                self.migration.rollback()
            db.assert_not_called()

    def test_cleanup_refuses_foreign_file_or_collection(self):
        self.migration.state['canary_path'] = '/expected'
        for reply in [(200, b'foreign content'), (404, b'')]:
            calls = []
            def request(port, method, path, **kwargs):
                calls.append(method)
                if method == 'GET':
                    return reply
                return 207, b'<d:multistatus xmlns:d="DAV:"><d:response><d:href>/foreign/</d:href></d:response></d:multistatus>'
            with self.subTest(reply=reply), patch.object(self.migration, 'request', side_effect=request):
                with self.assertRaises(m.Stopped):
                    self.migration.clean_canary(1234, {})
                self.assertNotIn('DELETE', calls)

    def test_main_pauses_instead_of_rollback_after_reopening(self):
        self.migration.state['reopening_started'] = True
        self.migration.save()
        args = ['migrate.py', 'reopen', '--state-dir', self.temp.name, '--execute']
        with patch('sys.argv', args), patch.object(m.Migration, 'reopen', side_effect=m.Stopped('failure')), \
             patch.object(m.Migration, 'pause_after_reopening') as pause, patch.object(m.Migration, 'rollback') as rollback, \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(m.main(), 1)
            pause.assert_called_once()
            rollback.assert_not_called()

    def test_failed_rollback_reopening_is_paused_without_another_rollback(self):
        self.migration.state['rollback_reopening_started'] = True
        self.migration.save()
        args = ['migrate.py', 'rollback', '--state-dir', self.temp.name, '--execute']
        with patch('sys.argv', args), patch.object(m.Migration, 'rollback', side_effect=m.Stopped('startup failed')) as rollback, \
             patch.object(m.Migration, 'pause_after_reopening') as pause, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(m.main(), 1)
            rollback.assert_called_once()
            pause.assert_called_once()

    def test_automatic_rollback_startup_failure_pauses_current_database(self):
        self.migration.save()
        args = ['migrate.py', 'convert', '--state-dir', self.temp.name, '--execute']
        def failed_rollback(controller):
            controller.record('rollback_reopening_started')
            raise m.Stopped('SQLite startup failed')
        with patch('sys.argv', args), patch.object(m.Migration, 'convert', side_effect=m.Stopped('conversion failed')), \
             patch.object(m.Migration, 'rollback', new=failed_rollback), \
             patch.object(m.Migration, 'pause_after_reopening') as pause, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(m.main(), 1)
            pause.assert_called_once()

    def test_main_rolls_back_failure_before_reopening(self):
        self.migration.save()
        args = ['migrate.py', 'convert', '--state-dir', self.temp.name, '--execute']
        with patch('sys.argv', args), patch.object(m.Migration, 'convert', side_effect=m.Stopped('failure')), \
             patch.object(m.Migration, 'pause_after_reopening') as pause, patch.object(m.Migration, 'rollback') as rollback, \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(m.main(), 1)
            rollback.assert_called_once()
            pause.assert_not_called()


if __name__ == '__main__':
    unittest.main()
