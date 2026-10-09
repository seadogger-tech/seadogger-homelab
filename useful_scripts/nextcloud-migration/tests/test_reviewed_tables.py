"""Operator-facing review check against a real, temporary SQLite database."""
import hashlib
import json
from pathlib import Path
import sqlite3
import shutil
import subprocess
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]


class ReviewedTableTests(unittest.TestCase):
    def test_converter_preserves_reviewed_schema_and_refuses_unreviewed_missing_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sql = 'CREATE TABLE oc_legacy (id INTEGER PRIMARY KEY, value TEXT NOT NULL)'
            with sqlite3.connect(root / 'nextcloud.db') as db:
                db.execute(sql)
            (root / 'reviewed-empty-tables.json').write_text(json.dumps([
                {'name': 'oc_legacy', 'schema_sha256': hashlib.sha256(sql.encode()).hexdigest()}]))
            for name in ('preserving-converter.php', 'reviewed-empty-tables.php'):
                path = SCRIPTS / name
                if path.exists():
                    shutil.copy(path, root / name)
            table = {'name': 'oc_legacy', 'columns': [{'type': 'integer'}, {'type': 'string', 'collation': 'BINARY'},
                                                    {'type': 'json', 'collation': 'BINARY'}], 'primary_key': ['id'],
                     'unique_indexes': [['value']], 'defaults': {'value': ''}}
            source = {'oc_current': {'name': 'oc_current'}, 'oc_legacy': table}
            payload = root / 'source.json'

            def convert():
                payload.write_text(json.dumps(source))
                return subprocess.run(['php', str(SCRIPTS / 'tests/fixtures/preserving-converter.php'),
                                       str(root / 'preserving-converter.php'), str(root), str(payload)],
                                      capture_output=True, text=True)

            result = convert()
            self.assertEqual(result.returncode, 0, result.stderr)
            expected = dict(table, columns=[{'type': 'integer'}, {'type': 'string', 'collation': 'C'},
                                            {'type': 'json', 'collation': None}])
            self.assertEqual(json.loads(result.stdout), {'oc_current': {'name': 'oc_current'}, 'oc_legacy': expected})
            source['oc_unreviewed'] = {'name': 'oc_unreviewed'}
            result = convert()
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout), {'oc_current': {'name': 'oc_current'}})

    def test_only_unchanged_empty_reviewed_tables_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / 'source.db'
            plan = root / 'review.json'
            sql = 'CREATE TABLE oc_legacy (id INTEGER PRIMARY KEY, value TEXT NOT NULL)'
            with sqlite3.connect(database) as db:
                db.execute(sql)
            plan.write_text(json.dumps([{'name': 'oc_legacy',
                                        'schema_sha256': hashlib.sha256(sql.encode()).hexdigest()}]))

            def check():
                return subprocess.run(['php', str(SCRIPTS / 'reviewed-empty-tables.php'), str(plan), str(database)],
                                      capture_output=True, text=True)

            result = check()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), ['oc_legacy'])
            # Kubernetes ConfigMap keys are symlinks to an atomic data directory.
            saved = root / 'configmap-data'
            plan.rename(saved)
            plan.symlink_to(saved)
            self.assertEqual(check().returncode, 0)
            with sqlite3.connect(database) as db:
                db.execute("INSERT INTO oc_legacy VALUES (1, 'must not be silently omitted')")
            self.assertNotEqual(check().returncode, 0)
            with sqlite3.connect(database) as db:
                self.assertEqual(db.execute('SELECT value FROM oc_legacy').fetchone()[0],
                                 'must not be silently omitted')
                db.execute('DELETE FROM oc_legacy')
                db.execute('CREATE INDEX unexpected_index ON oc_legacy(value)')
            self.assertNotEqual(check().returncode, 0)

