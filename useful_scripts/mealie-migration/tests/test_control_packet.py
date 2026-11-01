"""S2 artifact checks through the public offline CLI; no controller execution."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "control" / "control.py"
FIXTURE = ROOT / "control" / "fixtures" / "packet.synthetic.json"


class ControlPacketTests(unittest.TestCase):
    def validate(self, packet):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "packet.json"
            path.write_text(json.dumps(packet), encoding="utf-8")
            return subprocess.run([sys.executable, str(CLI), "validate", str(path)],
                                  capture_output=True, text=True, timeout=5, check=False)

    def test_boolean_cannot_stand_in_for_numeric_import_burst(self):
        packet = json.loads(FIXTURE.read_text(encoding="utf-8"))
        packet["limits"]["intakeBurst"] = True
        result = self.validate(packet)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(json.loads(result.stdout)["outcome"], "CLOSED")

    def test_valid_synthetic_shape_does_not_grant_execution_authority(self):
        packet = json.loads(FIXTURE.read_text(encoding="utf-8"))
        result = self.validate(packet)
        self.assertEqual(result.returncode, 0, result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["shape"], "VALID")
        self.assertEqual(report["authority"], "NOT_VERIFIED")
        self.assertIs(report["ready"], False)

    def test_runner_cannot_be_the_observer_principal(self):
        packet = json.loads(FIXTURE.read_text(encoding="utf-8"))
        packet["observerId"] = packet["runnerId"]
        result = self.validate(packet)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(json.loads(result.stdout)["outcome"], "CLOSED")


if __name__ == "__main__":
    unittest.main()
