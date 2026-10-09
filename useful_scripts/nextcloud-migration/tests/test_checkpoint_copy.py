"""Keep native schema hooks from changing the data selected for conversion."""
import contextlib
import hashlib
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]


class CheckpointCopyTests(unittest.TestCase):
    def test_copy_uses_checkpoint_and_preserves_historical_migrations(self):
        for failure in (None, 'digest', 'columns'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                checkpoint = root / 'checkpoint'
                checkpoint.mkdir()
                for path in (checkpoint / 'nextcloud.db', root / 'live.db', root / 'target.db'):
                    with contextlib.closing(sqlite3.connect(path)) as db, db:
                        db.executescript('CREATE TABLE oc_appconfig (appid TEXT, configkey TEXT, configvalue TEXT);'
                                         'CREATE TABLE oc_mounts (id INTEGER PRIMARY KEY, value TEXT);'
                                         'CREATE TABLE oc_migrations (app TEXT, version TEXT, PRIMARY KEY(app,version));')
                        if path.parent == checkpoint:
                            db.execute("INSERT INTO oc_appconfig VALUES ('files','enabled','yes')")
                            db.execute("INSERT INTO oc_mounts VALUES (7,'original mount')")
                            db.executemany('INSERT INTO oc_migrations VALUES (?,?)', [('core', 'current'), ('app', 'historical')])
                        elif path.name == 'live.db':
                            db.execute("INSERT INTO oc_appconfig VALUES ('hook','unexpected','new default')")
                        else:
                            db.executemany('INSERT INTO oc_migrations VALUES (?,?)', [('core', 'current'), ('core', 'generated')])
                            if failure == 'columns':
                                db.execute('ALTER TABLE oc_mounts ADD COLUMN incompatible TEXT')
                original = (checkpoint / 'nextcloud.db').read_bytes()
                (checkpoint / 'database.sha256').write_text(hashlib.sha256(original).hexdigest() if failure != 'digest' else '0' * 64)
                (checkpoint / 'complete').write_text('complete\n')
                result = subprocess.run(['php', str(SCRIPTS / 'tests/fixtures/checkpoint-copy.php'),
                                         str(SCRIPTS / 'preserving-converter.php'), str(checkpoint),
                                         str(root / 'live.db'), str(root / 'target.db')], capture_output=True, text=True)
                self.assertEqual((checkpoint / 'nextcloud.db').read_bytes(), original)
                with contextlib.closing(sqlite3.connect(root / 'target.db')) as db:
                    if failure:
                        self.assertNotEqual(result.returncode, 0)
                        self.assertEqual(db.execute('SELECT COUNT(*) FROM oc_appconfig').fetchone()[0], 0)
                    else:
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(db.execute('SELECT * FROM oc_appconfig').fetchall(), [('files', 'enabled', 'yes')])
                        self.assertEqual(db.execute('SELECT * FROM oc_mounts').fetchall(), [(7, 'original mount')])
                        self.assertEqual(set(db.execute('SELECT * FROM oc_migrations')), {('core', 'current'), ('core', 'generated'), ('app', 'historical')})
