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

import metallb_harness

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
  version) echo "${HELM_VERSION:-v3.17.3+gabcdef}"; exit 0 ;;
  status)
    if [ "$HELM_RELEASES_PRESENT" = "1" ]; then echo "STATUS: deployed"; exit 0; fi
    echo "Error: release: not found" >&2; exit 1 ;;
esac
echo "STATUS: deployed"
"""

KUBECTL_STUB = """#!/bin/sh
# The MetalLB runs serve the speaker-replacement canned state; the stub there logs its own calls.
case "$*" in *ceph*) ;; *) [ -n "$METALLB_STUB_STATE" ] && exec python3 "$METALLB_STUB" "$@" ;; esac
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

    def test_helm_values_files_are_copied_to_the_host_first(self):
        # helm runs on the control-plane host, not in the runner pod, so a -f path
        # must be the dest of an earlier copy task and never a controller path.
        for _, name in FLAGS.values():
            copied = set()
            for task in yaml.safe_load((TASKS / name).read_text()):
                copy = task.get("ansible.builtin.copy")
                if copy:
                    copied.add(copy["dest"])
                argv = (task.get("ansible.builtin.command") or {})
                argv = argv.get("argv") if isinstance(argv, dict) else None
                if not argv or "helm" not in argv:
                    continue
                for i, arg in enumerate(argv[:-1]):
                    if arg == "-f":
                        path = argv[i + 1]
                        self.assertNotIn("playbook_dir", path, name)
                        self.assertIn(path, copied, f"{name}: -f {path} is not copied to the host first")

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
        # MetalLB's gated loop: speakers all current by default (nothing to replace), Traefik
        # answering on a local port.
        self.http, self.http_port = metallb_harness.start_http()
        self.addCleanup(self.http.shutdown)
        self.metallb_state = self.tmp / "metallb-state.json"
        metallb_harness.write_state(self.metallb_state, metallb_harness.default_state(stale_nodes=()))
        self.env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", STUB_LOG=str(self.log),
                        PG_JSON=str(self.pg), CEPH_HEALTH="HEALTH_OK", HELM_RELEASES_PRESENT="1",
                        ANSIBLE_COLLECTIONS_PATH=os.environ.get("ANSIBLE_COLLECTIONS_PATH", ""))

    def run_flag(self, key, check=False, extra=(), **env):
        flag = FLAGS[key][0]
        cmd = [self.ansible, "-i", str(self.tmp / "hosts.ini"), "main.yml", "--tags", flag,
               "-e", f"{flag}=true", "-e", "ansible_become=false",
               "-e", "ansible_python_interpreter=" + shutil.which("python3")]
        env = dict(self.env, **env)
        if key == "metallb":
            env.update(METALLB_STUB_STATE=str(self.metallb_state), METALLB_STUB=str(metallb_harness.STUB))
            extra = ("metallb_check_http_port=%d" % self.http_port, "metallb_check_retries=1",
                     "metallb_check_delay=1", "metallb_replace_wait_retries=2", "metallb_replace_wait_delay=1") + tuple(extra)
        for pair in extra:
            cmd += ["-e", pair]
        if check:
            cmd.append("--check")
        result = subprocess.run(cmd, cwd=self.checkout / "ansible", capture_output=True, text=True, env=env)
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
                    self.assertNotIn(str(self.checkout), call)
                    if key == "rook":
                        self.assertRegex(call, r"-f /tmp/rook-ceph-(operator|cluster)-values\.yaml")
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

    def test_metallb_unknown_values_file_or_mode_fails_before_helm_or_kubectl(self):
        for pair in ("metallb_values_file=argocd_helm_values.yml", "metallb_values_file=../vars/metallb_helm_values.yml",
                     "metallb_speaker_replace=everything", "metallb_speaker_expect_qos=BestEffort"):
            with self.subTest(pair):
                self.log.unlink(missing_ok=True)
                result, calls = self.run_flag("metallb", extra=(pair,))
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertFalse(calls, calls)

    def test_metallb_previous_values_file_is_what_helm_gets(self):
        for name, memory in (("metallb_helm_values.previous.yml", "80Mi"), ("metallb_helm_values.yml", "88Mi")):
            with self.subTest(name):
                result, _ = self.run_flag("metallb", extra=(f"metallb_values_file={name}",))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                sent = yaml.safe_load(Path("/tmp/metallb-helm-values.yml").read_text())
                self.assertEqual(sent["speaker"]["updateStrategy"], {"type": "OnDelete"})
                self.assertEqual(sent["speaker"]["resources"]["requests"]["memory"], memory)

    def test_metallb_helm_wait_follows_the_helm_major_version(self):
        for version, wanted, banned in (("v3.17.3+gabc", ["--atomic", "--wait"], ["--wait=legacy", "--rollback-on-failure"]),
                                        ("v4.0.1+gabc", ["--rollback-on-failure", "--wait=legacy"], ["--atomic"])):
            with self.subTest(version):
                self.log.unlink(missing_ok=True)
                result, calls = self.run_flag("metallb", HELM_VERSION=version)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                upgrade = next(c for c in calls if c.startswith("helm upgrade")).split()
                for flag in wanted:
                    self.assertIn(flag, upgrade)
                for flag in banned:
                    self.assertNotIn(flag, upgrade)
                self.assertIn(version.split("+")[0], result.stdout, "the Helm version is recorded in the run output")

    def test_metallb_stale_speakers_are_replaced_after_the_upgrade_under_the_tag(self):
        metallb_harness.write_state(self.metallb_state, metallb_harness.default_state(stale_nodes=("n2", "n3")))
        result, calls = self.run_flag("metallb")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        upgrade = next(i for i, c in enumerate(calls) if c.startswith("helm upgrade"))
        deletes = [i for i, c in enumerate(calls) if "delete pod" in c]
        self.assertEqual(len(deletes), 2, calls)
        self.assertTrue(all(i > upgrade for i in deletes), calls)
        self.assertEqual(metallb_harness.read_state(self.metallb_state)["deletions"],
                         ["metallb-speaker-yy2", "metallb-speaker-xx3"])

    def test_metallb_check_mode_deletes_nothing(self):
        metallb_harness.write_state(self.metallb_state, metallb_harness.default_state())
        result, calls = self.run_flag("metallb", check=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse([c for c in calls if "delete pod" in c], calls)

    def test_metallb_failed_upgrade_replaces_no_speaker(self):
        # a helm failure ends the play before the loop is reached
        metallb_harness.write_state(self.metallb_state, metallb_harness.default_state())
        result, calls = self.run_flag("metallb", HELM_RELEASES_PRESENT="0")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse([c for c in calls if "delete pod" in c], calls)


class TraefikResourcesFlag(unittest.TestCase):
    """enable_traefik_resources writes only the Traefik HelmChartConfig, on the apply-flag pattern."""

    def test_flag_is_wired_tagged_and_default_false(self):
        main = (ANSIBLE / "main.yml").read_text()
        self.assertIn("tasks/traefik_resources.yml", main)
        self.assertIn("enable_traefik_resources | default(false)", main)
        self.assertIn("tags: [enable_traefik_resources]", main)
        example = yaml.safe_load((ANSIBLE / "example.config.yml").read_text())
        self.assertIs(example.get("enable_traefik_resources"), False)

    def test_task_writes_one_helmchartconfig_and_nothing_else(self):
        text = "\n".join(code_lines(TASKS / "traefik_resources.yml"))
        for pattern in (r"get_url", r"raw\.githubusercontent\.com", r"helm\s+(install|upgrade)", r"ansible\.builtin\.(command|shell|raw)",
                        r"systemctl", r"state:\s*(absent|restarted)", r"IngressRoute"):
            self.assertIsNone(re.search(pattern, text), pattern)
        writes = [t["kubernetes.core.k8s"] for t in yaml.safe_load((TASKS / "traefik_resources.yml").read_text())
                  if "kubernetes.core.k8s" in t]
        self.assertEqual([(w["definition"]["kind"], w["definition"]["metadata"]["name"], w["state"]) for w in writes],
                         [("HelmChartConfig", "traefik", "present")])

    def test_dashboard_task_writes_only_the_dashboard_objects_and_the_helmchartconfig(self):
        tasks = yaml.safe_load((TASKS / "traefik_dashboard_deploy.yml").read_text())
        writes = []
        for t in tasks:
            k8s = t.get("kubernetes.core.k8s")
            if k8s:
                writes.append(k8s["definition"]["kind"] if "definition" in k8s else k8s["src"])
            for module in ("ansible.builtin.command", "ansible.builtin.shell", "ansible.builtin.raw"):
                self.assertNotIn(module, t)
        self.assertEqual(writes, ["HelmChartConfig", "/tmp/traefik-dashboard-ingress.yml"])

    def test_guard_does_not_list_the_dashboard_or_the_resources_flag(self):
        guard = yaml.safe_load((GUARD_DIR / "guard.yml").read_text())[0]["vars"]
        listed = set(guard["destructive_flags"]) | set(guard["derived_flags"])
        self.assertFalse({"enable_traefik_dashboard", "enable_traefik_resources"} & listed)


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

    def run_guard(self, *extra_args, **overrides):
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
        return subprocess.run(["python3", str(GUARD_DIR / "guard.py"), " ".join(("main.yml -i hosts.ini",) + extra_args)],
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

    def test_b1_variables_and_flags_are_evaluated_and_none_is_refused(self):
        result = self.run_guard(
            "-e metallb_values_file=metallb_helm_values.previous.yml", "-e metallb_speaker_replace=all",
            "-e metallb_speaker_expect_qos=Burstable", "-e enable_traefik_resources=true",
            "-e enable_traefik_dashboard=true", enable_metallb_resources=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("REAL_RUN_REACHED", result.stdout)

    def test_destructive_flag_is_still_refused_next_to_the_b1_variables(self):
        result = self.run_guard("-e metallb_speaker_replace=all", "-e enable_wipe_k3s_cluster=true")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("REAL_RUN_REACHED", result.stdout)

    def test_guard_lists_do_not_mention_the_apply_flags(self):
        text = (GUARD_DIR / "guard.yml").read_text()
        self.assertNotIn("_resources", text)


if __name__ == "__main__":
    unittest.main()
