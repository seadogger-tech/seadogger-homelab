"""Checks for the helm-upgrade-only apply flags (OCE-369 / OCE-560).

enable_rook_ceph_resources, enable_metallb_resources and enable_argocd_resources
may only `helm upgrade` an existing release, with values from the checked-out
repo. No cluster is needed: helm and kubectl are stubs on PATH that log their
calls, and the tasks are run through the real main.yml with --tags.

Run from the core checkout:  python3 -m unittest discover -s ansible/tests -v
Needs ansible (ansible-playbook with kubernetes.core) and PyYAML.
"""
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

CORE = Path(__file__).resolve().parents[2]
ANSIBLE = CORE / "ansible"
TASKS = ANSIBLE / "tasks"
GUARD_DIR = CORE / "deployments" / "ansible-runner"

FLAGS = {
    "rook": ("enable_rook_ceph_resources", "rook_ceph_resources.yml"),
    "metallb": ("enable_metallb_resources", "metallb_resources.yml"),
    "argocd": ("enable_argocd_resources", "argocd_resources.yml"),
}
RELEASES = {
    "rook": ["rook-ceph", "rook-ceph-cluster"],
    "metallb": ["metallb"],
    "argocd": ["argocd"],
}

HELM_STUB = """#!/bin/sh
echo "helm $*" >> "$STUB_LOG"
case "$1" in
  status)
    if [ "$HELM_RELEASES_PRESENT" = "1" ]; then echo "STATUS: deployed"; exit 0; fi
    echo "Error: release: not found" >&2; exit 1 ;;
esac
echo "STATUS: deployed"
"""

KUBECTL_STUB = """#!/bin/sh
echo "kubectl $*" >> "$STUB_LOG"
case "$*" in
  *"ceph health"*) echo "$CEPH_HEALTH" ;;
  *"ceph status"*|*"ceph -s"*|*"ceph pg stat"*) cat "$PG_JSON" ;;
esac
exit 0
"""

PG_CLEAN = {"pgmap": {"num_pgs": 3, "pgs_by_state": [{"state_name": "active+clean", "count": 3}]}}


def real_ansible():
    path = shutil.which("ansible-playbook")
    if not path:
        raise unittest.SkipTest("ansible-playbook not installed")
    return path


def code_lines(path):
    return [l for l in path.read_text().splitlines() if not l.lstrip().startswith("#")]


class StaticChecks(unittest.TestCase):
    def test_task_files_never_install_wipe_or_restart_k3s(self):
        banned = [r"helm\s+install", r"--install", r"wipe", r"k3s[\w.-]*\s*(restart|stop)",
                  r"systemctl", r"state:\s*restarted", r"raw\.githubusercontent\.com"]
        for _, name in FLAGS.values():
            text = "\n".join(code_lines(TASKS / name))
            self.assertIn("helm upgrade", text, name)
            for pattern in banned:
                self.assertIsNone(re.search(pattern, text), f"{name} matches {pattern}")

    def test_values_come_from_the_checked_out_repo(self):
        for key, (_, name) in FLAGS.items():
            text = "\n".join(code_lines(TASKS / name))
            self.assertNotIn("raw.githubusercontent.com", text, name)
            self.assertIn("{{ playbook_dir }}", text, name)
        rook = (TASKS / FLAGS["rook"][1]).read_text()
        self.assertIn("{{ playbook_dir }}/../deployments/rook-ceph/rook-ceph-operator-values.yaml", rook)
        self.assertIn("{{ playbook_dir }}/../deployments/rook-ceph/rook-ceph-cluster-values.yaml", rook)

    def test_metallb_chart_version_is_pinned_in_both_tasks(self):
        for name in ("metallb_native_deploy.yml", "metallb_resources.yml"):
            text = "\n".join(code_lines(TASKS / name))
            self.assertRegex(text, r"""(chart_version:\s*["']?|--version\s+-\s*["']?)0\.15\.2\b""", name)

    def test_deploy_and_apply_tasks_share_one_values_file(self):
        for app, deploy, apply_, vars_file in (
            ("metallb", "metallb_native_deploy.yml", "metallb_resources.yml", "metallb_helm_values.yml"),
            ("argocd", "argocd_native_deploy.yml", "argocd_resources.yml", "argocd_helm_values.yml"),
        ):
            self.assertTrue((ANSIBLE / "vars" / vars_file).is_file(), vars_file)
            for name in (deploy, apply_):
                text = (TASKS / name).read_text()
                self.assertIn(f"vars/{vars_file}", text, name)
                tasks = yaml.safe_load(text)
                inline = [t for t in tasks if "values" in (t.get("kubernetes.core.helm") or {})]
                for t in inline:
                    self.assertIn("_helm_values", str(t["kubernetes.core.helm"]["values"]), name)

    def test_rook_versions_match_the_cold_start_pins(self):
        part1 = (TASKS / "rook_ceph_deploy_part1.yml").read_text()
        resources = (TASKS / FLAGS["rook"][1]).read_text()
        for version in re.findall(r"--version\s+(\S+)", part1):
            self.assertRegex(resources, rf"""--version\s+-\s*["']?{re.escape(version)}["']?\s""")

    def test_flags_are_wired_in_main_and_example_config_default_false(self):
        main = (ANSIBLE / "main.yml").read_text()
        example = yaml.safe_load((ANSIBLE / "example.config.yml").read_text())
        for flag, name in FLAGS.values():
            self.assertIn(f"tasks/{name}", main)
            self.assertIn(f"{flag} | default(false)", main)
            self.assertIs(example.get(flag), False, flag)

    def test_syntax_check(self):
        ansible = real_ansible()
        result = subprocess.run([ansible, "-i", "localhost,", "--syntax-check", "main.yml"],
                                cwd=ANSIBLE, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class RunWithStubs(unittest.TestCase):
    def setUp(self):
        self.ansible = real_ansible()
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        # A copy of the checkout so playbook_dir/../deployments resolves like on the runner.
        self.checkout = self.tmp / "core"
        shutil.copytree(CORE / "deployments", self.checkout / "deployments", symlinks=True)
        shutil.copytree(ANSIBLE, self.checkout / "ansible", ignore=shutil.ignore_patterns("tests"))
        (self.checkout / "ansible" / "config.yml").write_text("---\nplaceholder: true\n")
        bindir = self.tmp / "bin"
        bindir.mkdir()
        for name, body in (("helm", HELM_STUB), ("kubectl", KUBECTL_STUB)):
            (bindir / name).write_text(body)
            (bindir / name).chmod(0o755)
        self.log = self.tmp / "calls.log"
        self.pg = self.tmp / "pg.json"
        self.pg.write_text(json.dumps(PG_CLEAN))
        (self.tmp / "hosts.ini").write_text("[control_plane]\nlocalhost ansible_connection=local\n")
        self.env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", STUB_LOG=str(self.log),
                        PG_JSON=str(self.pg), CEPH_HEALTH="HEALTH_OK", HELM_RELEASES_PRESENT="1",
                        ANSIBLE_COLLECTIONS_PATH=os.environ.get("ANSIBLE_COLLECTIONS_PATH", ""))

    def run_flag(self, key, check=False, extra=(), **env):
        flag = FLAGS[key][0]
        cmd = [self.ansible, "-i", str(self.tmp / "hosts.ini"), "main.yml", "--tags", flag,
               "-e", f"{flag}=true", "-e", "ansible_become=false",
               "-e", "ansible_python_interpreter=" + shutil.which("python3")]
        for pair in extra:
            cmd += ["-e", pair]
        if check:
            cmd.append("--check")
        result = subprocess.run(cmd, cwd=self.checkout / "ansible", capture_output=True, text=True,
                                env=dict(self.env, **env))
        calls = self.log.read_text().splitlines() if self.log.exists() else []
        return result, calls

    def test_absent_release_fails_before_any_change(self):
        for key in FLAGS:
            with self.subTest(key):
                self.log.unlink(missing_ok=True)
                result, calls = self.run_flag(key, HELM_RELEASES_PRESENT="0")
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("not installed", result.stdout + result.stderr)
                self.assertFalse([c for c in calls if c.startswith("helm upgrade")], calls)
                self.assertFalse([c for c in calls if c.startswith("kubectl")], calls)

    def test_absent_release_fails_in_check_mode_too(self):
        for key in FLAGS:
            with self.subTest(key):
                result, _ = self.run_flag(key, check=True, HELM_RELEASES_PRESENT="0")
                self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_upgrade_uses_checkout_values_and_never_installs(self):
        for key in FLAGS:
            with self.subTest(key):
                self.log.unlink(missing_ok=True)
                result, calls = self.run_flag(key)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                upgrades = [c for c in calls if c.startswith("helm upgrade")]
                self.assertEqual(len(upgrades), len(RELEASES[key]), calls)
                self.assertFalse([c for c in calls if "install" in c], calls)
                self.assertFalse([c for c in calls if "--install" in c], calls)
                for call in upgrades:
                    if key == "rook":
                        self.assertIn(f"{self.checkout}/ansible/../deployments/rook-ceph/", call)
                    self.assertNotIn("raw.githubusercontent.com", call)
                    self.assertIn("-f ", call)
                if key == "metallb":
                    self.assertIn("--version 0.15.2", upgrades[0])
                if key == "argocd":
                    self.assertIn("--version 8.5.8", upgrades[0])

    def test_check_mode_makes_no_change(self):
        for key in FLAGS:
            with self.subTest(key):
                self.log.unlink(missing_ok=True)
                result, calls = self.run_flag(key, check=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertFalse([c for c in calls if c.startswith("helm upgrade")], calls)

    def test_rook_refuses_when_ceph_is_not_health_ok(self):
        result, calls = self.run_flag("rook", CEPH_HEALTH="HEALTH_WARN 1 pgs degraded")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse([c for c in calls if c.startswith("helm upgrade")], calls)

    def test_rook_checks_health_before_and_pgs_after_the_upgrade(self):
        result, calls = self.run_flag("rook")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        first_upgrade = next(i for i, c in enumerate(calls) if c.startswith("helm upgrade"))
        last_upgrade = max(i for i, c in enumerate(calls) if c.startswith("helm upgrade"))
        health = [i for i, c in enumerate(calls) if "ceph health" in c]
        pgs = [i for i, c in enumerate(calls) if "ceph status" in c or "ceph pg" in c]
        self.assertTrue(health and health[0] < first_upgrade, calls)
        self.assertTrue(pgs and pgs[-1] > last_upgrade, calls)
        self.assertTrue(any("deploy/rook-ceph-tools" in c for c in calls), calls)

    def test_rook_fails_loudly_when_pgs_never_go_clean(self):
        dirty = {"pgmap": {"num_pgs": 3, "pgs_by_state": [
            {"state_name": "active+clean", "count": 2}, {"state_name": "active+remapped+backfilling", "count": 1}]}}
        self.pg.write_text(json.dumps(dirty))
        # Shrink the poll so the test is quick; the defaults are 180 x 10s = 30 minutes.
        result, _ = self.run_flag("rook", extra=("rook_pg_clean_retries=2", "rook_pg_clean_delay=1"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("active+clean", result.stdout + result.stderr)


class GuardUnchanged(unittest.TestCase):
    """guard.py still refuses the destructive Rook flag and accepts the apply flags."""

    BASE = {
        "cold_start_stage_1_wipe_cluster": False, "enable_wipe_k3s_cluster": False,
        "perform_physical_disk_wipe": False, "cold_start_stage_2_install_infrastructure": False,
        "run_pod_cleanup": False, "run_infrastructure_cleanup": False,
        "enable_k3s_control_plane": False, "enable_k3s_workers": False,
        "enable_rook_ceph_part1": False, "enable_metallb_native": False,
        "enable_argocd_native": False, "enable_raspberry_pi_config": False,
    }

    def run_guard(self, **overrides):
        real = real_ansible()
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "config.yml").write_text(yaml.safe_dump(dict(self.BASE, **overrides)))
        wrapper = tmp / "bin" / "ansible-playbook"
        wrapper.parent.mkdir()
        # The guard's own evaluation runs for real; the run it would launch afterwards is a marker.
        wrapper.write_text(f'#!/bin/sh\ncase "$*" in *guard.yml*) exec {real} "$@";; esac\necho REAL_RUN_REACHED\n')
        wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
        env = dict(os.environ, PATH=f"{wrapper.parent}:{os.environ['PATH']}")
        return subprocess.run(["python3", str(GUARD_DIR / "guard.py"), "main.yml -i hosts.ini"],
                              cwd=tmp, capture_output=True, text=True, env=env)

    def test_destructive_part1_flag_is_still_refused(self):
        result = self.run_guard(enable_rook_ceph_part1=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("REAL_RUN_REACHED", result.stdout)

    def test_k3s_flag_is_still_refused(self):
        result = self.run_guard(enable_k3s_control_plane=True)
        self.assertNotEqual(result.returncode, 0)

    def test_apply_flags_are_accepted(self):
        result = self.run_guard(enable_rook_ceph_resources=True, enable_metallb_resources=True,
                                enable_argocd_resources=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("REAL_RUN_REACHED", result.stdout)

    def test_guard_lists_do_not_mention_the_apply_flags(self):
        text = (GUARD_DIR / "guard.yml").read_text()
        self.assertNotIn("_resources", text)


if __name__ == "__main__":
    unittest.main()
