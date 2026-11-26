"""Checks for the Stage B1 values (OCE-369): CSI nodeplugin limits, MetalLB and Traefik Guaranteed.

Asserts, for every key B1 changes:
  - it renders the B1 value;
  - the sizing rule holds against the peaks already recorded in b0_memory_peaks.yml:
    Burstable request = P rounded up to 8Mi and limit = 1.25 x request (CSI plugin
    containers 1.5x); Guaranteed request = limit = 1.25 x P rounded up to 8Mi;
  - no request is below P and no limit is above the pre-B0 limit;
  - every MetalLB container and the Traefik HelmChartConfig have request == limit,
    memory and CPU.
B1 adds no measured value to core: P is read from the B0 fixture that is already
published, and Traefik is held to the Guaranteed 256Mi floor the spec sets for it.
The helm render checks need `helm` and the pinned charts, and are skipped without them.

Run from the core checkout:  python3 -m unittest discover -s ansible/tests -v
Needs PyYAML.
"""
import math
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

CORE = Path(__file__).resolve().parents[2]
B0 = {r["name"]: r for r in yaml.safe_load(Path(__file__).with_name("b0_memory_peaks.yml").read_text())["containers"]}
OPERATOR_VALUES = CORE / "deployments/rook-ceph/rook-ceph-operator-values.yaml"
METALLB_VALUES = CORE / "ansible/vars/metallb_helm_values.yml"
TRAEFIK_VALUES = CORE / "ansible/vars/traefik_helmchartconfig_values.yml"
VARS = CORE / "ansible/vars"


def to_mi(value):
    value = str(value)
    if value.endswith("Gi"):
        return float(value[:-2]) * 1024
    if value.endswith("Mi"):
        return float(value[:-2])
    raise ValueError(f"unsupported memory quantity {value!r}")


def to_milli(value):
    value = str(value)
    return float(value[:-1]) if value.endswith("m") else float(value) * 1000


def up8(x):
    return int(math.ceil(x / 8.0) * 8)


def csi_entries(key):
    """name -> {requests, limits} for one csi*Resource string of the operator values."""
    values = yaml.safe_load(OPERATOR_VALUES.read_text())
    return {e["name"].strip(): e["resource"] for e in yaml.safe_load(values["csi"][key])}


# Rook 1.18.1 with ROOK_USE_CSI_OPERATOR builds the Driver CR's spec.nodePlugin.resources from
# the *ProvisionerResource keys (pkg/operator/ceph/csi/operator_driver.go,
# createDriverNodePluginResouces, matching "registrar", "plugin", "liveness") and its
# spec.controllerPlugin.resources from the *PluginResource keys. B1 therefore edits the former.
NODEPLUGIN = {
    # key: (container, B0 row, request, limit, limit factor)
    "csiRBDProvisionerResource": [
        ("csi-rbdplugin", "csi-rbdplugin", 104, 160, 1.5),
        ("driver-registrar", "csi-rbdplugin driver-registrar", 32, 40, 1.25),
        ("liveness-prometheus", "csi-rbdplugin liveness-prometheus", 40, 56, 1.25),
    ],
    "csiCephFSProvisionerResource": [
        ("csi-cephfsplugin", "csi-cephfsplugin", 112, 168, 1.5),
        ("driver-registrar", "csi-cephfsplugin driver-registrar", 32, 40, 1.25),
        ("liveness-prometheus", "csi-cephfsplugin liveness-prometheus", 40, 56, 1.25),
    ],
}

METALLB = [
    # path in metallb_helm_values, B0 row, memory Mi, cpu m
    (("speaker", "resources"), "metallb speaker", 88, 100),
    (("speaker", "frr", "resources"), "metallb frr", 64, 125),
    (("speaker", "reloader", "resources"), "metallb reloader", 64, 125),
    (("speaker", "frrMetrics", "resources"), "metallb frr-metrics", 48, 275),
    (("controller", "resources"), "metallb controller", 152, 50),
]


class TestNodepluginValues(unittest.TestCase):
    def test_every_nodeplugin_entry_renders_the_b1_value(self):
        for key, rows in NODEPLUGIN.items():
            entries = csi_entries(key)
            for cname, _, req, lim, _ in rows:
                with self.subTest(f"{key}/{cname}"):
                    res = entries[cname]
                    self.assertEqual(to_mi(res["requests"]["memory"]), req)
                    self.assertEqual(to_mi(res["limits"]["memory"]), lim)

    def test_sizing_rule_holds_against_the_recorded_peaks(self):
        for key, rows in NODEPLUGIN.items():
            entries = csi_entries(key)
            for cname, row, _, _, factor in rows:
                with self.subTest(f"{key}/{cname}"):
                    p, old_limit = B0[row]["peak_mi"], B0[row]["old_limit_mi"]
                    res = entries[cname]
                    request, limit = to_mi(res["requests"]["memory"]), to_mi(res["limits"]["memory"])
                    self.assertEqual(request, up8(p), "Burstable request = P rounded up to 8Mi")
                    self.assertEqual(limit, up8(factor * request), f"limit = {factor} x request")
                    self.assertGreaterEqual(request, p, "no request below P")
                    self.assertLessEqual(limit, old_limit, "no limit above today's")

    def test_only_the_two_plugin_containers_use_the_1_5x_exception(self):
        for key, rows in NODEPLUGIN.items():
            for cname, _, _, _, factor in rows:
                self.assertEqual(factor == 1.5, cname.endswith("plugin") and cname.startswith("csi-"), cname)

    def test_controller_plugin_keys_are_left_as_b0_set_them(self):
        for key, plugin in (("csiRBDPluginResource", "csi-rbdplugin"), ("csiCephFSPluginResource", "csi-cephfsplugin")):
            res = csi_entries(key)[plugin]
            self.assertEqual(to_mi(res["requests"]["memory"]), 64)
            self.assertIn(to_mi(res["limits"]["memory"]), (128, 144))

    def test_registrar_is_sized_through_the_nodeplugin_keys(self):
        for key in NODEPLUGIN:
            self.assertIn("driver-registrar", csi_entries(key))


class TestMetalLBGuaranteed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.values = yaml.safe_load(METALLB_VALUES.read_text())["metallb_helm_values"]

    @staticmethod
    def dig(values, path):
        for part in path:
            values = values[part]
        return values

    def test_every_container_renders_the_b1_value_with_request_equal_limit(self):
        for path, row, mem, cpu in METALLB:
            with self.subTest(row):
                res = self.dig(self.values, path)
                for kind in ("memory", "cpu"):
                    self.assertEqual(res["requests"][kind], res["limits"][kind], f"{kind} request == limit")
                self.assertEqual(to_mi(res["requests"]["memory"]), mem)
                self.assertEqual(to_milli(res["requests"]["cpu"]), cpu)

    def test_cpu_request_and_limit_meet_the_measured_spec_floors(self):
        floors = {"speaker": 100, "frr": 125, "reloader": 125, "frrMetrics": 275, "controller": 50}
        for name, floor in floors.items():
            path = (("controller", "resources") if name == "controller"
                    else ("speaker", "resources") if name == "speaker"
                    else ("speaker", name, "resources"))
            with self.subTest(name):
                res = self.dig(self.values, path)
                request = to_milli(res["requests"]["cpu"])
                limit = to_milli(res["limits"]["cpu"])
                self.assertEqual(request, limit)
                self.assertGreaterEqual(request, floor)

    def test_sizing_rule_holds_against_the_recorded_peaks(self):
        for path, row, _, _ in METALLB:
            with self.subTest(row):
                p, old_limit = B0[row]["peak_mi"], B0[row]["old_limit_mi"]
                got = to_mi(self.dig(self.values, path)["limits"]["memory"])
                self.assertEqual(got, up8(1.25 * p), "Guaranteed = 1.25 x P rounded up to 8Mi")
                self.assertGreaterEqual(to_mi(self.dig(self.values, path)["requests"]["memory"]), p)
                self.assertLessEqual(got, old_limit)

    def test_speaker_daemonset_is_ondelete(self):
        self.assertEqual(self.values["speaker"]["updateStrategy"], {"type": "OnDelete"})


class TestTraefikGuaranteed(unittest.TestCase):
    def test_helmchartconfig_resources_are_equal_and_at_the_floor(self):
        res = yaml.safe_load(TRAEFIK_VALUES.read_text())["traefik_helmchartconfig_values"]["resources"]
        for kind in ("memory", "cpu"):
            self.assertEqual(res["requests"][kind], res["limits"][kind], f"{kind} request == limit")
        self.assertEqual(to_mi(res["limits"]["memory"]), 256)
        self.assertEqual(to_milli(res["limits"]["cpu"]), 500)

    def test_dashboard_task_and_resources_task_render_the_same_values_file(self):
        for name in ("traefik_dashboard_deploy.yml", "traefik_resources.yml"):
            text = (CORE / "ansible/tasks" / name).read_text()
            self.assertIn("traefik_helmchartconfig_values", text, name)
            self.assertNotIn("memory: 512Mi", text, name)

    def test_previous_values_deep_equal_core_6097389_inline_values(self):
        shown = subprocess.run(
            ["git", "show", "6097389:ansible/tasks/traefik_dashboard_deploy.yml"],
            cwd=CORE, capture_output=True, text=True)
        if shown.returncode:
            self.skipTest("commit 6097389 is not in this checkout")
        task = next(t["kubernetes.core.k8s"] for t in yaml.safe_load(shown.stdout)
                    if "kubernetes.core.k8s" in t and
                    t["kubernetes.core.k8s"].get("definition", {}).get("kind") == "HelmChartConfig")
        expected = yaml.safe_load(task["definition"]["spec"]["valuesContent"])
        previous = yaml.safe_load((VARS / "traefik_helmchartconfig_values.previous.yml").read_text())
        self.assertEqual(previous["traefik_helmchartconfig_values"], expected)

    def test_unknown_traefik_values_file_fails_before_any_cluster_write(self):
        ansible = shutil.which("ansible-playbook")
        if not ansible:
            self.skipTest("ansible-playbook not installed")
        with tempfile.TemporaryDirectory() as tmp:
            play = Path(tmp) / "play.yml"
            play.write_text(yaml.safe_dump([{
                "hosts": "localhost", "gather_facts": False,
                "tasks": [{"ansible.builtin.include_tasks": str(CORE / "ansible/tasks/traefik_resources.yml")}],
            }]))
            proc = subprocess.run(
                [ansible, "-i", "localhost,", "-c", "local", str(play),
                 "-e", "ansible_python_interpreter=" + shutil.which("python3"),
                 "-e", "traefik_values_file=unknown.yml"],
                capture_output=True, text=True)
        output = proc.stdout + proc.stderr
        self.assertNotEqual(proc.returncode, 0, output)
        self.assertIn("traefik_values_file", output)


@unittest.skipUnless(shutil.which("helm"), "helm not installed")
class TestHelmRender(unittest.TestCase):
    def render(self, name, repo, release, version, values):
        with tempfile.TemporaryDirectory() as tmp:
            vfile = Path(tmp) / "values.yaml"
            vfile.write_text(yaml.safe_dump(values))
            proc = subprocess.run(["helm", "template", release, name, "--repo", repo, "--version", version,
                                   "-f", str(vfile)], capture_output=True, text=True)
        if proc.returncode:
            self.skipTest(f"chart {name} {version} not fetchable: {proc.stderr[:200]}")
        return [d for d in yaml.safe_load_all(proc.stdout) if d]

    def test_operator_configmap_carries_the_nodeplugin_keys(self):
        values = yaml.safe_load(OPERATOR_VALUES.read_text())
        docs = self.render("rook-ceph", "https://charts.rook.io/release", "rook-ceph", "1.18.1", values)
        data = next(d for d in docs if d["kind"] == "ConfigMap" and "CSI_RBD_PROVISIONER_RESOURCE" in d.get("data", {}))["data"]
        for env, rows in (("CSI_RBD_PROVISIONER_RESOURCE", NODEPLUGIN["csiRBDProvisionerResource"]),
                          ("CSI_CEPHFS_PROVISIONER_RESOURCE", NODEPLUGIN["csiCephFSProvisionerResource"])):
            got = {e["name"].strip(): e["resource"] for e in yaml.safe_load(data[env])}
            for cname, _, req, lim, _ in rows:
                with self.subTest(f"{env}/{cname}"):
                    self.assertEqual(to_mi(got[cname]["requests"]["memory"]), req)
                    self.assertEqual(to_mi(got[cname]["limits"]["memory"]), lim)

    def test_metallb_renders_guaranteed_containers_and_ondelete(self):
        values = yaml.safe_load(METALLB_VALUES.read_text())["metallb_helm_values"]
        docs = self.render("metallb", "https://metallb.github.io/metallb", "metallb", "0.15.2", values)
        seen = {}
        for d in docs:
            if d["kind"] in ("Deployment", "DaemonSet"):
                for c in d["spec"]["template"]["spec"]["containers"]:
                    seen[c["name"]] = c["resources"]
                if d["kind"] == "DaemonSet":
                    self.assertEqual(d["spec"]["updateStrategy"]["type"], "OnDelete")
        for cname in ("speaker", "frr", "reloader", "frr-metrics", "controller"):
            with self.subTest(cname):
                res = seen[cname]
                for kind in ("memory", "cpu"):
                    self.assertEqual(res["requests"][kind], res["limits"][kind])


if __name__ == "__main__":
    unittest.main()
