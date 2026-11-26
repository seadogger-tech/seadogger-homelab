"""Checks for the gated MetalLB speaker replacement (OCE-369 Stage B1).

tasks/metallb_speaker_replace.yml runs for real on localhost against a stub `kubectl`
on PATH (metallb_kubectl_stub.py) that serves canned JSON and logs deletions, and a
local HTTP server standing in for Traefik's LoadBalancer IP. No cluster is needed.

Run from the core checkout:  python3 -m unittest discover -s ansible/tests -v
Needs ansible (ansible-playbook) and PyYAML.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

import metallb_harness as h

CORE = Path(__file__).resolve().parents[2]
TASKS = CORE / "ansible" / "tasks"
VARS = CORE / "ansible" / "vars"

# What Core 6097389 (Stage B0) held in ansible/vars/metallb_helm_values.yml, written out
# as explicit expectations rather than a snapshot file.
CORE_6097389_METALLB_VALUES = {
    "controller": {"resources": {"requests": {"cpu": "25m", "memory": "96Mi"}, "limits": {"memory": "152Mi"}}},
    "speaker": {
        "resources": {"requests": {"cpu": "25m", "memory": "80Mi"}, "limits": {"memory": "104Mi"}},
        "frr": {"resources": {"requests": {"memory": "32Mi"}, "limits": {"memory": "64Mi"}}},
        "reloader": {"resources": {"requests": {"memory": "32Mi"}, "limits": {"memory": "64Mi"}}},
        "frrMetrics": {"resources": {"requests": {"memory": "32Mi"}, "limits": {"memory": "48Mi"}}},
    },
}


def ansible_playbook():
    path = shutil.which("ansible-playbook")
    if not path:
        raise unittest.SkipTest("ansible-playbook not installed")
    return path


class MetalLBValuesFiles(unittest.TestCase):
    def load(self, name):
        return yaml.safe_load((VARS / name).read_text())["metallb_helm_values"]

    def test_both_values_files_use_ondelete(self):
        for name in ("metallb_helm_values.yml", "metallb_helm_values.previous.yml"):
            with self.subTest(name):
                self.assertEqual(self.load(name)["speaker"]["updateStrategy"], {"type": "OnDelete"})

    def test_previous_is_core_6097389_plus_ondelete_only(self):
        previous = self.load("metallb_helm_values.previous.yml")
        del previous["speaker"]["updateStrategy"]
        self.assertEqual(previous, CORE_6097389_METALLB_VALUES)

    def test_previous_matches_the_commit_when_history_is_available(self):
        shown = subprocess.run(
            ["git", "show", "6097389:ansible/vars/metallb_helm_values.yml"],
            cwd=CORE, capture_output=True, text=True)
        if shown.returncode:
            self.skipTest("commit 6097389 is not in this checkout (shallow clone)")
        previous = self.load("metallb_helm_values.previous.yml")
        del previous["speaker"]["updateStrategy"]
        self.assertEqual(previous, yaml.safe_load(shown.stdout)["metallb_helm_values"])


class LoopRun(unittest.TestCase):
    def setUp(self):
        self.ansible = ansible_playbook()
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.server, self.port = h.start_http()
        self.addCleanup(self.server.shutdown)
        bindir = self.tmp / "bin"
        bindir.mkdir()
        h.install_stub(bindir)
        self.state = self.tmp / "state.json"
        self.log = self.tmp / "calls.log"
        self.play = self.tmp / "play.yml"
        self.play.write_text(yaml.safe_dump([{
            "hosts": "localhost", "gather_facts": False,
            "tasks": [
                {"ansible.builtin.set_fact": {"KUBECONFIG": "/nonexistent/k3s.yaml"}},
                {"ansible.builtin.include_tasks": str(TASKS / "metallb_speaker_replace.yml")},
            ]}]))
        self.env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", STUB_LOG=str(self.log),
                        METALLB_STUB_STATE=str(self.state), ANSIBLE_LOCALHOST_WARNING="False",
                        ANSIBLE_INVENTORY_UNPARSED_WARNING="False")
        self.set_state(h.default_state())

    def set_state(self, state):
        h.write_state(self.state, state)

    def run_loop(self, **extra):
        cmd = [self.ansible, "-i", "localhost,", "-c", "local", str(self.play),
               "-e", f"metallb_check_http_port={self.port}", "-e", "metallb_check_retries=2",
               "-e", "metallb_check_delay=1", "-e", "metallb_replace_wait_retries=3",
               "-e", "metallb_replace_wait_delay=1", "-e", "ansible_python_interpreter=" + shutil.which("python3")]
        for key, value in extra.items():
            cmd += ["-e", f"{key}={value}"]
        result = subprocess.run(cmd, capture_output=True, text=True, env=self.env)
        out = result.stdout + result.stderr
        return result, out, h.read_state(self.state)["deletions"]

    def test_all_checks_pass_one_deletion_per_stale_pod_in_node_order(self):
        result, out, deletions = self.run_loop()
        self.assertEqual(result.returncode, 0, out)
        self.assertEqual(deletions, ["metallb-speaker-zz1", "metallb-speaker-yy2",
                                     "metallb-speaker-xx3", "metallb-speaker-ww4"])

    def test_only_pods_off_the_target_revision_are_replaced_by_default(self):
        self.set_state(h.default_state(stale_nodes=("n2", "n4")))
        result, out, deletions = self.run_loop()
        self.assertEqual(result.returncode, 0, out)
        self.assertEqual(deletions, ["metallb-speaker-yy2", "metallb-speaker-ww4"])

    def test_replace_all_replaces_current_pods_too(self):
        self.set_state(h.default_state(stale_nodes=("n2",)))
        result, out, deletions = self.run_loop(metallb_speaker_replace="all")
        self.assertEqual(result.returncode, 0, out)
        self.assertEqual(len(deletions), 4, deletions)

    def test_nothing_stale_deletes_nothing_and_passes(self):
        self.set_state(h.default_state(stale_nodes=()))
        result, out, deletions = self.run_loop()
        self.assertEqual(result.returncode, 0, out)
        self.assertEqual(deletions, [])

    def test_network_check_fails_after_first_replacement_stops_the_play(self):
        state = h.default_state()
        state["fail_n_after_deletions"] = 1
        self.set_state(state)
        result, out, deletions = self.run_loop()
        self.assertNotEqual(result.returncode, 0, out)
        self.assertEqual(deletions, ["metallb-speaker-zz1"])
        self.assertIn("metallb-speaker-zz1", out, "the failure must name the pod")

    def test_failed_precheck_deletes_nothing(self):
        state = h.default_state()
        state["fail_n_after_deletions"] = 0
        self.set_state(state)
        result, out, deletions = self.run_loop()
        self.assertNotEqual(result.returncode, 0, out)
        self.assertEqual(deletions, [])

    def test_wrong_qos_class_stops_before_a_second_deletion(self):
        self.set_state(h.default_state(new_qos="Burstable"))
        result, out, deletions = self.run_loop()
        self.assertNotEqual(result.returncode, 0, out)
        self.assertEqual(deletions, ["metallb-speaker-zz1"])
        self.assertIn("Burstable", out)
        self.assertIn("metallb-speaker-zz1", out)

    def test_expect_qos_burstable_accepts_burstable_replacements(self):
        self.set_state(h.default_state(new_qos="Burstable"))
        result, out, deletions = self.run_loop(metallb_speaker_expect_qos="Burstable")
        self.assertEqual(result.returncode, 0, out)
        self.assertEqual(len(deletions), 4)

    def test_slow_replacement_is_waited_for(self):
        state = h.default_state(stale_nodes=("n1",))
        state["ready_after_polls"] = 2
        self.set_state(state)
        result, out, deletions = self.run_loop()
        self.assertEqual(result.returncode, 0, out)
        self.assertEqual(deletions, ["metallb-speaker-zz1"])

    def test_replacement_that_never_becomes_ready_stops_the_play(self):
        state = h.default_state()
        state["ready_after_polls"] = 1000
        self.set_state(state)
        result, out, deletions = self.run_loop()
        self.assertNotEqual(result.returncode, 0, out)
        self.assertEqual(deletions, ["metallb-speaker-zz1"])
        self.assertIn("not Ready at revision", out)
        self.assertIn("after 3 s", out)

    def test_replacement_with_a_restarted_container_names_it_and_stops_before_next_delete(self):
        state = h.default_state()
        state["new_restart_container"] = "frr"
        self.set_state(state)
        result, out, deletions = self.run_loop()
        self.assertNotEqual(result.returncode, 0, out)
        self.assertEqual(deletions, ["metallb-speaker-zz1"])
        self.assertIn("container frr restarted 1 times", out)

    def test_init_container_resources_are_printed(self):
        result, out, _ = self.run_loop()
        self.assertEqual(result.returncode, 0, out)
        self.assertIn("cp-frr-files", out)

    def test_unreachable_traefik_ip_fails_the_check(self):
        result, out, deletions = self.run_loop(metallb_check_http_port=1)
        self.assertNotEqual(result.returncode, 0, out)
        self.assertEqual(deletions, [])

    def test_unknown_replace_or_qos_value_fails_before_any_kubectl_call(self):
        for key, value in (("metallb_speaker_replace", "everything"), ("metallb_speaker_expect_qos", "BestEffort")):
            with self.subTest(key):
                self.log.unlink(missing_ok=True)
                result, out, deletions = self.run_loop(**{key: value})
                self.assertNotEqual(result.returncode, 0, out)
                self.assertEqual(deletions, [])
                self.assertFalse(self.log.exists() and self.log.read_text(), "kubectl must not be called")

    def test_task_file_uses_only_kubectl_and_uri(self):
        for name in ("metallb_speaker_replace.yml", "metallb_speaker_replace_pod.yml", "metallb_network_check.yml"):
            text = "\n".join(l for l in (TASKS / name).read_text().splitlines() if not l.lstrip().startswith("#"))
            for banned in ("ansible.builtin.shell", "ansible.builtin.raw", "curl", "kubernetes.core", "helm "):
                self.assertNotIn(banned, text, f"{name} uses {banned}")


if __name__ == "__main__":
    unittest.main()
