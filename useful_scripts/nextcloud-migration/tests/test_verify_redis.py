"""Exercise the Redis WebDAV probe and its conservative cleanup without a cluster."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('verify_redis', SCRIPTS / 'verify_redis.py')
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


class FakeDAV:
    def __init__(self, fail_put=False, existing=False):
        self.folder = existing
        self.file = None
        self.fail_put = fail_put
        self.deleted = []

    def request(self, method, path, body=None, headers=None):
        if path == '/status.php':
            return 200, json.dumps({'maintenance': False}).encode()
        if method == 'MKCOL':
            if self.folder:
                return 405, b''
            self.folder = True
            return 201, b''
        if method == 'PUT':
            self.file = body
            if self.fail_put:
                raise TimeoutError('Response lost after PUT')
            return 201, b''
        if method == 'GET':
            return (200, self.file) if self.file is not None else (404, b'')
        if method == 'PROPFIND':
            responses = '<d:response><d:href>' + path + '</d:href></d:response>'
            if self.file is not None:
                responses += '<d:response><d:href>' + path + 'probe.txt</d:href></d:response>'
            return 207, ('<d:multistatus xmlns:d="DAV:">' + responses + '</d:multistatus>').encode()
        if method == 'DELETE':
            self.deleted.append(path)
            if path.endswith('/probe.txt'):
                self.file = None
            else:
                self.folder = False
            return 204, b''
        raise AssertionError((method, path))


class RedisValidationTests(unittest.TestCase):
    def run_canary(self, dav):
        with contextlib.redirect_stdout(io.StringIO()):
            verify.canary(dav.request, 'test user', token='known')

    def test_success_cleans_only_its_probe(self):
        dav = FakeDAV()
        self.run_canary(dav)
        self.assertFalse(dav.folder)
        self.assertIsNone(dav.file)
        self.assertEqual(len(dav.deleted), 2)

    def test_lost_put_response_preserves_uncertain_write(self):
        dav = FakeDAV(fail_put=True)
        with self.assertRaisesRegex(TimeoutError, 'Response lost'):
            self.run_canary(dav)
        self.assertTrue(dav.folder)
        self.assertIsNotNone(dav.file)
        self.assertEqual(dav.deleted, [])

    def test_unknown_data_is_preserved(self):
        dav = FakeDAV()
        def request(method, path, body=None, headers=None):
            if method == 'GET' and path.endswith('/probe.txt'):
                return 200, b'someone else\'s content'
            return dav.request(method, path, body, headers)
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaisesRegex(verify.ValidationError, 'readback differs'):
            verify.canary(request, 'test user', token='known')
        self.assertIn('Probe data needs inspection:', output.getvalue())
        self.assertTrue(dav.folder)
        self.assertEqual(dav.deleted, [])

    def test_existing_folder_is_never_deleted(self):
        dav = FakeDAV(existing=True)
        with self.assertRaisesRegex(verify.ValidationError, 'not newly created'):
            self.run_canary(dav)
        self.assertTrue(dav.folder)
        self.assertEqual(dav.deleted, [])

    def test_credentials_require_private_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'credentials.json'
            path.write_text(json.dumps({'username': 'test', 'password': 'secret'}))
            os.chmod(path, 0o644)
            with self.assertRaisesRegex(verify.ValidationError, '0600'):
                verify.credentials(path)
            os.chmod(path, 0o600)
            self.assertEqual(verify.credentials(path)['username'], 'test')


if __name__ == '__main__':
    unittest.main()
