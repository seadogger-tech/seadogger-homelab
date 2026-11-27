"""Required placement away from rey and the OCE-832 rollback contract."""
import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

CORE = Path(__file__).resolve().parents[2]
ROOK = CORE / "deployments/rook-ceph"
MAP_BASE = "f883ee2"
WORKERS = {"anakin.local", "obiwan.local"}
CORE_WORKERS = WORKERS | {"yoda"}
REFERENCE_SHA256 = {
    "deployments/rook-ceph/rook-ceph-operator-values.yaml":
        "ff8fb80b7b16a0b691abfe39f6455ba38a6dffc1670355e1fceccc7c7cdfd934",
    "deployments/rook-ceph/rook-ceph-cluster-values.yaml":
        "d940cc3778713fc28b38356361f3226f2e1e7e9269447959f2a6e2061ded665b",
    "ansible/tasks/rook_ceph_resources.yml":
        "cbdd9e60a456f7d26ca883ddea3f224bdd15abb0813946a8c71f5b40baa4eb9a",
    "ansible/scripts/rook_recovery_gate.py":
        "2cb22fc14640c89fdb2b659adfc9bf5b0fdafac0cb5bd25d02f0bafeccc90365",
}


def read_yaml(path):
    return yaml.safe_load(path.read_text())


def helm_docs(chart, repo, version, values_file):
    result = subprocess.run(
        ["helm", "template", "rey-check", chart, "--repo", repo, "--version", version,
         "-f", str(values_file)], capture_output=True, text=True,
    )
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return [item for item in yaml.safe_load_all(result.stdout) if item]


def render_values(chart, repo, version, values):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "values.yaml"
        path.write_text(yaml.safe_dump(values, sort_keys=False))
        return helm_docs(chart, repo, version, path)


def assert_required_hosts(test, affinity, allowed_hosts):
    node = affinity["nodeAffinity"]
    terms = node["requiredDuringSchedulingIgnoredDuringExecution"]["nodeSelectorTerms"]
    host_expressions = [expression for term in terms for expression in term.get("matchExpressions", [])
                        if expression.get("key") == "kubernetes.io/hostname"]
    test.assertTrue(host_expressions, "required hostname affinity is missing")
    # Each OR term must exclude rey; a matching In expression narrows hosts,
    # while NotIn is the explicit exclusion used for movable workloads.
    for term in terms:
        expressions = [expression for expression in term.get("matchExpressions", [])
                       if expression.get("key") == "kubernetes.io/hostname"]
        test.assertTrue(expressions)
        test.assertTrue(any(
            (expression.get("operator") == "NotIn" and "rey.local" in expression.get("values", []))
            or (expression.get("operator") == "In" and "rey.local" not in expression.get("values", []))
            for expression in expressions
        ), f"term permits rey.local: {term}")
    if allowed_hosts:
        in_values = [set(expression.get("values", [])) for expression in host_expressions
                     if expression.get("operator") == "In"]
        if in_values:
            test.assertTrue(any("rey.local" not in hosts and hosts <= allowed_hosts for hosts in in_values))


def pod_spec(document):
    spec = document["spec"]
    if document["kind"] == "CronJob":
        return spec["jobTemplate"]["spec"]["template"]["spec"]
    return spec["template"]["spec"]


def rendered_file_at(commit, relative):
    result = subprocess.run(["git", "show", f"{commit}:{relative}"], cwd=CORE,
                            capture_output=True)
    if result.returncode == 0:
        return result.stdout
    expected_hash = REFERENCE_SHA256.get(relative)
    if expected_hash is None:
        raise AssertionError(f"reference blob unavailable and no committed SHA-256 for {relative}")
    return expected_hash.encode("ascii")


class TestRequiredPlacement(unittest.TestCase):
    def test_rook_ctrlplugin_operator_config_requires_the_three_core_hosts(self):
        values = read_yaml(ROOK / "rook-ceph-operator-values.yaml")
        self.assertEqual(values["csi"]["provisionerNodeAffinity"],
                         "kubernetes.io/hostname=anakin.local,obiwan.local,yoda")

    def test_argocd_component_values_require_notin_rey(self):
        values = read_yaml(CORE / "ansible/vars/argocd_helm_values.yml")["argocd_helm_values"]
        components = ("controller", "repoServer", "dex", "server", "notifications", "applicationSet", "redis")
        for name in components:
            with self.subTest(component=name):
                assert_required_hosts(self, values[name]["affinity"], None)

    def test_cert_manager_components_keep_yoda_preference_and_exclude_rey(self):
        app = read_yaml(CORE / "certificates/cert-manager-application.yml")
        values = yaml.safe_load(app["spec"]["source"]["helm"]["values"])
        for name, component in (("controller", values), ("cainjector", values["cainjector"]),
                                ("webhook", values["webhook"])):
            with self.subTest(component=name):
                affinity = component["affinity"]
                assert_required_hosts(self, affinity, None)
                preferred = affinity["nodeAffinity"]["preferredDuringSchedulingIgnoredDuringExecution"]
                self.assertIn("yoda", preferred[0]["preference"]["matchExpressions"][0]["values"])

    def test_named_core_workload_pod_specs_exclude_rey(self):
        values = read_yaml(CORE / "deployments/pihole/pihole-values.yaml")
        assert_required_hosts(self, values["affinity"], None)

        nextcloud = read_yaml(CORE / "deployments/nextcloud/nextcloud-values.yaml")
        assert_required_hosts(self, nextcloud["affinity"], WORKERS)

        for relative, kinds in (
            ("deployments/jellyfin/xmltv-proxy.yaml", {"Deployment"}),
            ("deployments/nextcloud/s3-backup-cronjob.yaml", {"CronJob"}),
            ("deployments/nextcloud/postgresql/backup-cronjob.yaml", {"CronJob"}),
            ("deployments/nextcloud/postgresql/statefulset.yaml", {"StatefulSet"}),
            ("deployments/nextcloud/redis/deployment.yaml", {"Deployment"}),
        ):
            documents = [doc for doc in yaml.safe_load_all((CORE / relative).read_text()) if doc]
            workloads = [doc for doc in documents if doc.get("kind") in kinds]
            self.assertTrue(workloads, relative)
            for workload in workloads:
                with self.subTest(file=relative, kind=workload["kind"]):
                    assert_required_hosts(self, pod_spec(workload)["affinity"],
                                          WORKERS if relative.endswith(("nextcloud-values.yaml", "statefulset.yaml", "deployment.yaml")) else None)

        db = read_yaml(CORE / "deployments/nextcloud/postgresql/statefulset.yaml")["spec"]["template"]["spec"]["affinity"]["nodeAffinity"]
        preferred = db["preferredDuringSchedulingIgnoredDuringExecution"]
        self.assertEqual(preferred[0]["preference"]["matchExpressions"][0]["values"], ["obiwan.local"])
        redis = read_yaml(CORE / "deployments/nextcloud/redis/deployment.yaml")["spec"]["template"]["spec"]["affinity"]["nodeAffinity"]
        self.assertEqual(redis["preferredDuringSchedulingIgnoredDuringExecution"][0]["preference"]["matchExpressions"][0]["values"], ["anakin.local"])

    def test_metallb_controller_excludes_rey_and_speaker_values_are_unchanged(self):
        current = read_yaml(CORE / "ansible/vars/metallb_helm_values.yml")["metallb_helm_values"]
        previous = read_yaml(CORE / "ansible/vars/metallb_helm_values.previous.yml")["metallb_helm_values"]
        assert_required_hosts(self, current["controller"]["affinity"], None)
        self.assertEqual(current, previous)

    def test_rook_previous_pair_is_the_b3_snapshot_and_only_current_operator_has_rule(self):
        pairs = (
            ("deployments/rook-ceph/rook-ceph-operator-values.yaml",
             "deployments/rook-ceph/rook-ceph-operator-values.previous.yaml"),
            ("deployments/rook-ceph/rook-ceph-cluster-values.yaml",
             "deployments/rook-ceph/rook-ceph-cluster-values.previous.yaml"),
        )
        for current, previous in pairs:
            with self.subTest(previous=previous):
                self.assertEqual((CORE / previous).read_bytes(), rendered_file_at(MAP_BASE, current))
        current_operator = read_yaml(CORE / pairs[0][0])
        previous_operator = read_yaml(CORE / pairs[0][1])
        current_operator["csi"].pop("provisionerNodeAffinity", None)
        previous_operator["csi"].pop("provisionerNodeAffinity", None)
        self.assertEqual(current_operator, previous_operator)
        self.assertEqual(read_yaml(CORE / pairs[1][0]), read_yaml(CORE / pairs[1][1]))

        previous_cluster = read_yaml(CORE / pairs[1][1])
        resources = previous_cluster["cephClusterSpec"]["resources"]
        self.assertEqual(resources["osd"]["requests"]["memory"], "1280Mi")
        mds = previous_cluster["cephFileSystems"][0]["spec"]["metadataServer"]["resources"]
        self.assertEqual(mds["limits"]["memory"], "1280Mi")

    def test_rook_recovery_implementation_and_gate_are_the_reference_blobs(self):
        for relative in ("ansible/tasks/rook_ceph_resources.yml", "ansible/scripts/rook_recovery_gate.py"):
            with self.subTest(file=relative):
                content = (CORE / relative).read_bytes()
                reference = rendered_file_at(MAP_BASE, relative)
                if len(reference) == 64 and reference.decode("ascii") in REFERENCE_SHA256.values():
                    self.assertEqual(hashlib.sha256(content).hexdigest(), reference.decode("ascii"))
                else:
                    self.assertEqual(content, reference)

    @unittest.skipUnless(shutil.which("helm"), "helm not installed")
    def test_metallb_render_does_not_change_the_speaker_daemonset(self):
        current_values = read_yaml(CORE / "ansible/vars/metallb_helm_values.yml")["metallb_helm_values"]
        baseline_values = yaml.safe_load(rendered_file_at(MAP_BASE, "ansible/vars/metallb_helm_values.yml"))["metallb_helm_values"]
        current = render_values("metallb", "https://metallb.github.io/metallb", "0.15.2", current_values)
        baseline = render_values("metallb", "https://metallb.github.io/metallb", "0.15.2", baseline_values)
        speaker = lambda docs: next(doc for doc in docs if doc.get("kind") == "DaemonSet"
                                    and "speaker" in doc["metadata"]["name"])
        self.assertEqual(speaker(current), speaker(baseline))

        controller = next(doc for doc in current if doc.get("kind") == "Deployment"
                          and "controller" in doc["metadata"]["name"])
        assert_required_hosts(self, controller["spec"]["template"]["spec"]["affinity"], None)

    @unittest.skipUnless(shutil.which("helm"), "helm not installed")
    def test_argocd_render_applies_required_placement_to_each_component_pod(self):
        values = read_yaml(CORE / "ansible/vars/argocd_helm_values.yml")["argocd_helm_values"]
        docs = render_values("argo-cd", "https://argoproj.github.io/argo-helm", "8.5.8", values)
        workloads = [doc for doc in docs if doc.get("kind") in ("Deployment", "StatefulSet")
                     and "argocd" in doc.get("metadata", {}).get("name", "")]
        self.assertGreaterEqual(len(workloads), 7)
        for workload in workloads:
            with self.subTest(workload=workload["metadata"]["name"]):
                assert_required_hosts(self, pod_spec(workload)["affinity"], None)

    @unittest.skipUnless(shutil.which("helm"), "helm not installed")
    def test_cert_manager_render_applies_required_placement_to_all_three_deployments(self):
        app = read_yaml(CORE / "certificates/cert-manager-application.yml")
        values = yaml.safe_load(app["spec"]["source"]["helm"]["values"])
        docs = render_values("cert-manager", "https://charts.jetstack.io", "1.14.4", values)
        deployments = [doc for doc in docs if doc.get("kind") == "Deployment"
                       and doc.get("metadata", {}).get("name", "").endswith(
                           ("cert-manager", "cert-manager-cainjector", "cert-manager-webhook"))]
        self.assertEqual(len(deployments), 3)
        for deployment in deployments:
            with self.subTest(workload=deployment["metadata"]["name"]):
                spec = pod_spec(deployment)
                assert_required_hosts(self, spec["affinity"], None)
                node = spec["affinity"]["nodeAffinity"]
                preferred = node["preferredDuringSchedulingIgnoredDuringExecution"]
                self.assertIn("yoda", preferred[0]["preference"]["matchExpressions"][0]["values"])

    @unittest.skipUnless(shutil.which("helm"), "helm not installed")
    def test_pihole_render_applies_required_placement(self):
        docs = helm_docs("pihole", "https://mojo2600.github.io/pihole-kubernetes/", "2.35.0",
                         CORE / "deployments/pihole/pihole-values.yaml")
        workloads = [doc for doc in docs if doc.get("kind") in ("Deployment", "StatefulSet")]
        self.assertTrue(workloads)
        for workload in workloads:
            with self.subTest(workload=workload["metadata"]["name"]):
                assert_required_hosts(self, pod_spec(workload)["affinity"], None)

    @unittest.skipUnless(shutil.which("helm"), "helm not installed")
    def test_nextcloud_render_applies_required_placement(self):
        docs = helm_docs("nextcloud", "https://nextcloud.github.io/helm/", "8.9.1",
                         CORE / "deployments/nextcloud/nextcloud-values.yaml")
        deployment = next(doc for doc in docs if doc.get("kind") == "Deployment"
                          and doc["metadata"]["name"].endswith("nextcloud"))
        assert_required_hosts(self, pod_spec(deployment)["affinity"], WORKERS)

    @unittest.skipUnless(shutil.which("helm"), "helm not installed")
    def test_rook_render_contains_controller_plugin_affinity_in_operator_config(self):
        docs = helm_docs("rook-ceph", "https://charts.rook.io/release", "1.19.2",
                         CORE / "deployments/rook-ceph/rook-ceph-operator-values.yaml")
        config = next(doc for doc in docs if doc.get("kind") == "ConfigMap"
                      and doc["metadata"]["name"] == "rook-ceph-operator-config")
        self.assertEqual(config["data"]["CSI_PROVISIONER_NODE_AFFINITY"],
                         "kubernetes.io/hostname=anakin.local,obiwan.local,yoda")


class TestRookRollbackBytes(unittest.TestCase):
    def test_previous_files_match_the_reference_blobs_byte_for_byte(self):
        for name in ("rook-ceph-operator-values.yaml", "rook-ceph-cluster-values.yaml"):
            relative = f"deployments/rook-ceph/{name}"
            expected = rendered_file_at(MAP_BASE, relative)
            previous = (ROOK / name.replace(".yaml", ".previous.yaml")).read_bytes()
            if len(expected) == 64 and expected.decode("ascii") in REFERENCE_SHA256.values():
                self.assertEqual(hashlib.sha256(previous).hexdigest(), expected.decode("ascii"))
            else:
                self.assertEqual(previous, expected)
            self.assertEqual(hashlib.sha256(previous).hexdigest(), REFERENCE_SHA256[relative])


class TestRunbookUpdates(unittest.TestCase):
    def test_wiki_documents_rey_rule_exceptions_capacity_cost_and_rollback_gates(self):
        monitor = (CORE / "docs/wiki/30-Cluster-Resource-Monitor.md").read_text()
        for required in ("Rey reserved for Paperclip", "N−1 capacity", "No measured P",
                         "Rook toolbox", "Rook operator", "ceph-csi-controller-manager",
                         "R1 — Rook", "R2 — cert-manager", "R3 — remaining workloads",
                         "Do not override a Rook"):
            with self.subTest(text=required):
                self.assertIn(required, monitor)

    def test_wiki_documents_exact_rollback_revision_selectors(self):
        runner = (CORE / "docs/wiki/28-Ansible-Runner.md").read_text()
        self.assertIn("**Rollback revisions.**", runner)
        self.assertIn("`f883ee2`'s B3 current values", runner)
        self.assertIn('"rook_values_set": "previous"', runner)
        self.assertIn('"rook_recovery": true', runner)
        self.assertIn('"cert_manager_application_file": "cert-manager-application.previous.yml"', runner)
        self.assertIn('"enable_metallb_resources": true', runner)
        self.assertIn('"enable_argocd_resources": true', runner)


if __name__ == "__main__":
    unittest.main()
