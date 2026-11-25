"""Regression checks for the Stage B0 rollout instructions in the core wiki."""
import re
import unittest
from pathlib import Path

CORE = Path(__file__).resolve().parents[2]
ROLLOUT_SECTIONS = {
    CORE / "docs/wiki/05-GitOps-and-IaC.md": (
        "For the Pro B0 rollout",
        "The `cmd-reporter` key",
    ),
    CORE / "docs/wiki/30-Cluster-Resource-Monitor.md": (
        "### Rollout, verification and rollback",
        None,
    ),
}
RESTART_ACTION = re.compile(r"\b(?:recreat\w*|restart\w*)\b", re.IGNORECASE)


class TestB0RolloutDocs(unittest.TestCase):
    def test_only_rook_ceph_pods_are_recreated_or_restarted(self):
        for page, (start_marker, end_marker) in ROLLOUT_SECTIONS.items():
            with self.subTest(page=page.name):
                text = page.read_text()
                rollout = text.split(start_marker, 1)[1]
                if end_marker:
                    rollout = rollout.split(end_marker, 1)[0]
                action_lines = [line for line in rollout.splitlines() if RESTART_ACTION.search(line)]
                self.assertTrue(
                    any("rook-ceph" in line.lower() for line in action_lines),
                    "the B0 rook-ceph Pod recreation step must remain documented",
                )
                for line in action_lines:
                    self.assertNotIn(
                        "cert-manager",
                        line.lower(),
                        "B0 rollout instructions must not restart cert-manager Pods",
                    )
