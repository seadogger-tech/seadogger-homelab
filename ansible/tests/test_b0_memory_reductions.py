"""Checks for the Stage B0 immediate memory reductions (OCE-369 / OCE-598).

Loads every file B0 changes and asserts, per container in b0_memory_peaks.yml:
  - limit  <= today's live limit            (a cut, never a raise)
  - request <= today's live request         (no request goes up)
  - limit  >= 1.25 x the recorded peak      (the cut stays above the high-water mark)
  - peak_mi == max(oce550_peak_mi, live_peak_mi), every row has a live_peak_mi, and
    memory.events max and oom_kill are 0 (the live re-read is recorded, not skipped)
and that cmd-reporter is set explicitly at 64Mi / 512Mi. The helm render checks
need `helm` and the pinned charts, and are skipped when either is missing.

Run from the core checkout:  python3 -m unittest discover -s ansible/tests -v
Needs PyYAML.
"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

CORE = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).with_name("b0_memory_peaks.yml")
WIKI = CORE / "docs" / "wiki" / "30-Cluster-Resource-Monitor.md"
CLUSTER_VALUES = CORE / "deployments/rook-ceph/rook-ceph-cluster-values.yaml"

# Chart pins, equal to the ones in the deploy tasks.
CHARTS = {
    "metallb": ("metallb", "https://metallb.github.io/metallb", "metallb", "0.15.2"),
    "argocd": ("argo-cd", "https://argoproj.github.io/argo-helm", "argo-cd", "8.5.8"),
    "rook-cluster": ("rook-ceph-cluster", "https://charts.rook.io/release", "rook-ceph-cluster", "1.18.1"),
}


def to_mi(value):
    value = str(value)
    if value.endswith("Gi"):
        return float(value[:-2]) * 1024
    if value.endswith("Mi"):
        return float(value[:-2])
    raise ValueError(f"unsupported memory quantity {value!r}")


def load_yaml(rel):
    return yaml.safe_load((CORE / rel).read_text())


def resources_for(spec):
    """Return the {requests, limits} memory in Mi for one fixture entry."""
    data = load_yaml(spec["file"])
    path, _, container = spec["path"].partition("#")
    node = data
    for part in path.split("."):
        if isinstance(node, str):  # csi*PluginResource is a YAML string
            node = yaml.safe_load(node)
        node = node[part]
    if isinstance(node, str):
        node = yaml.safe_load(node)
    if container:
        node = next(c for c in node if c["name"].strip() == container)
        node = node.get("resource", node.get("resources", node))
    return {
        "request": to_mi(node["requests"]["memory"]),
        "limit": to_mi(node["limits"]["memory"]),
    }


class TestB0MemoryReductions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = yaml.safe_load(FIXTURE.read_text())["containers"]

    def test_every_container_is_cut_and_above_1_25x_peak(self):
        for spec in self.rows:
            with self.subTest(spec["name"]):
                got = resources_for(spec)
                self.assertLess(got["limit"], spec["old_limit_mi"], "limit must come down")
                self.assertLessEqual(got["request"], spec["old_request_mi"], "no request may go up")
                self.assertGreaterEqual(got["limit"], 1.25 * spec["peak_mi"], "limit must stay >= 1.25 x peak")
                self.assertGreaterEqual(got["request"], 32, "32Mi request floor")
                self.assertGreaterEqual(got["limit"], 40, "40Mi limit floor")
                self.assertLessEqual(got["request"], got["limit"])

    def test_peak_is_max_of_oce550_and_live_read(self):
        for spec in self.rows:
            with self.subTest(spec["name"]):
                self.assertIn("live_peak_mi", spec, "every row needs the live memory.peak re-read")
                self.assertIn("oce550_peak_mi", spec)
                self.assertEqual(spec["peak_mi"], max(spec["oce550_peak_mi"], spec["live_peak_mi"]))
                self.assertIn("live_window_days", spec)

    def test_no_oom_events_at_live_read(self):
        for spec in self.rows:
            with self.subTest(spec["name"]):
                self.assertEqual(spec.get("events_max"), 0)
                self.assertEqual(spec.get("oom_kill"), 0)

    def test_cmd_reporter_is_explicit_at_todays_effective_values(self):
        values = yaml.safe_load(CLUSTER_VALUES.read_text())
        res = values["cephClusterSpec"]["resources"].get("cmd-reporter")
        self.assertIsNotNone(res, "cmd-reporter key must be set so a LimitRange cut cannot reach it")
        self.assertEqual(to_mi(res["requests"]["memory"]), 64)
        self.assertEqual(to_mi(res["limits"]["memory"]), 512)

    def test_wiki_section_lists_every_container(self):
        text = WIKI.read_text()
        self.assertIn("Stage B0 immediate reductions", text)
        self.assertIn("rollback", text.lower())
        for spec in self.rows:
            with self.subTest(spec["name"]):
                self.assertIn(f"| {spec['name']} |", text)


@unittest.skipUnless(shutil.which("helm"), "helm not installed")
class TestB0HelmRender(unittest.TestCase):
    def render(self, key, values):
        name, repo, release, version = CHARTS[key]
        with tempfile.TemporaryDirectory() as tmp:
            vfile = Path(tmp) / "values.yaml"
            vfile.write_text(yaml.safe_dump(values))
            proc = subprocess.run(
                ["helm", "template", release, name, "--repo", repo, "--version", version, "-f", str(vfile)],
                capture_output=True, text=True)
        if proc.returncode:
            self.skipTest(f"chart {name} {version} not fetchable: {proc.stderr[:200]}")
        return [d for d in yaml.safe_load_all(proc.stdout) if d]

    @staticmethod
    def containers(docs, kinds=("Deployment", "DaemonSet", "StatefulSet")):
        for d in docs:
            if d["kind"] in kinds:
                for c in d["spec"]["template"]["spec"].get("containers", []):
                    yield c["name"], c.get("resources", {})

    def check(self, docs, expected):
        seen = dict(self.containers(docs))
        for cname, (req, lim) in expected.items():
            with self.subTest(cname):
                self.assertIn(cname, seen)
                self.assertEqual(to_mi(seen[cname]["requests"]["memory"]), req)
                self.assertEqual(to_mi(seen[cname]["limits"]["memory"]), lim)

    def test_metallb_renders_new_limits(self):
        values = load_yaml("ansible/vars/metallb_helm_values.yml")["metallb_helm_values"]
        by = {s["name"]: s for s in yaml.safe_load(FIXTURE.read_text())["containers"]}
        docs = self.render("metallb", values)
        seen = dict(self.containers(docs))
        for cname, row in (("speaker", "metallb speaker"), ("frr", "metallb frr"),
                           ("reloader", "metallb reloader"), ("frr-metrics", "metallb frr-metrics"),
                           ("controller", "metallb controller")):
            with self.subTest(cname):
                self.assertIn(cname, seen)
                self.assertLess(to_mi(seen[cname]["limits"]["memory"]), by[row]["old_limit_mi"])
                self.assertLessEqual(to_mi(seen[cname]["requests"]["memory"]), by[row]["old_request_mi"])

    def test_argocd_renders_new_limits(self):
        values = load_yaml("ansible/vars/argocd_helm_values.yml")["argocd_helm_values"]
        by = {s["name"]: s for s in yaml.safe_load(FIXTURE.read_text())["containers"]}
        seen = dict(self.containers(self.render("argocd", values), ("Deployment", "StatefulSet")))
        for cname, row in (("application-controller", "argocd application-controller"),
                           ("repo-server", "argocd repo-server"), ("server", "argocd server"),
                           ("dex-server", "argocd dex-server"),
                           ("notifications-controller", "argocd notifications-controller"),
                           ("applicationset-controller", "argocd applicationset-controller"),
                           ("redis", "argocd redis")):
            with self.subTest(cname):
                self.assertIn(cname, seen)
                self.assertLess(to_mi(seen[cname]["limits"]["memory"]), by[row]["old_limit_mi"])
                self.assertLessEqual(to_mi(seen[cname]["requests"]["memory"]), by[row]["old_request_mi"])

    def test_cephcluster_cr_carries_cmd_reporter_logcollector_exporter(self):
        values = yaml.safe_load(CLUSTER_VALUES.read_text())
        docs = self.render("rook-cluster", values)
        cr = next(d for d in docs if d["kind"] == "CephCluster")
        res = cr["spec"]["resources"]
        self.assertEqual(to_mi(res["cmd-reporter"]["requests"]["memory"]), 64)
        self.assertEqual(to_mi(res["cmd-reporter"]["limits"]["memory"]), 512)
        self.assertEqual(to_mi(res["logcollector"]["limits"]["memory"]), 40)
        self.assertEqual(to_mi(res["exporter"]["limits"]["memory"]), 64)
        for k in ("logcollector", "exporter"):  # CPU is kept from the chart defaults
            self.assertIn("cpu", res[k]["requests"])


if __name__ == "__main__":
    unittest.main()
