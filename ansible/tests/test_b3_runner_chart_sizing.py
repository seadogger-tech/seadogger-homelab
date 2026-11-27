"""Stage B3 sizing and runner apply contracts (OCE-369)."""
import json
import math
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

CORE = Path(__file__).resolve().parents[2]
ANSIBLE = CORE / "ansible"
TASKS = ANSIBLE / "tasks"
ROOK_CLUSTER = CORE / "deployments/rook-ceph/rook-ceph-cluster-values.yaml"
ROOK_OPERATOR = CORE / "deployments/rook-ceph/rook-ceph-operator-values.yaml"
ROOK_GATE = ANSIBLE / "scripts/rook_recovery_gate.py"


def memory_mi(value):
    value = str(value)
    if value.endswith("Gi"):
        return float(value[:-2]) * 1024
    if value.endswith("Mi"):
        return float(value[:-2])
    raise ValueError(value)


def up8(value):
    return int(math.ceil(value / 8) * 8)


def csi_values(path, key):
    values = yaml.safe_load(path.read_text())
    return {row["name"].strip(): row["resource"] for row in yaml.safe_load(values["csi"][key])}


def base_yaml(path):
    relative = path.relative_to(CORE).as_posix()
    result = subprocess.run(["git", "show", f"origin/map/OCE-369-b3-fit:{relative}"],
                            cwd=CORE, capture_output=True, text=True, check=True)
    return yaml.safe_load(result.stdout)


class TestB3SizingValues(unittest.TestCase):
    def test_rook_rows_use_the_spec_values_and_1_25_limits_except_osd_and_mon(self):
        cluster = yaml.safe_load(ROOK_CLUSTER.read_text())
        resources = cluster["cephClusterSpec"]["resources"]
        expected = {
            "mgr": (544, 680),
            "mgr-sidecar": (64, 80),
            "exporter": (32, 40),
        }
        for key, pair in expected.items():
            with self.subTest(key):
                request = memory_mi(resources[key]["requests"]["memory"])
                limit = memory_mi(resources[key]["limits"]["memory"])
                self.assertEqual((request, limit), pair)
                self.assertLessEqual(limit, up8(1.25 * request))
        self.assertEqual(memory_mi(resources["osd"]["requests"]["memory"]), 1280)
        self.assertEqual(memory_mi(resources["osd"]["limits"]["memory"]), 2928)
        self.assertEqual(memory_mi(resources["mon"]["requests"]["memory"]), 560)
        self.assertEqual(memory_mi(resources["mon"]["limits"]["memory"]), 1280)
        mds = cluster["cephFileSystems"][0]["spec"]["metadataServer"]["resources"]
        self.assertEqual(memory_mi(mds["limits"]["memory"]), 1280)
        self.assertEqual(memory_mi(mds["requests"]["memory"]), 1024)

    def test_rook_toolbox_operator_ctrlplugins_and_csi_manager_values(self):
        cluster = yaml.safe_load(ROOK_CLUSTER.read_text())
        toolbox = cluster["toolbox"]["resources"]
        self.assertEqual((memory_mi(toolbox["requests"]["memory"]), memory_mi(toolbox["limits"]["memory"])), (40, 56))
        self.assertEqual(cluster["toolbox"]["affinity"]["nodeAffinity"]["preferredDuringSchedulingIgnoredDuringExecution"][0]["preference"]["matchExpressions"][0]["values"], ["yoda"])
        operator = yaml.safe_load(ROOK_OPERATOR.read_text())
        operator_res = operator["resources"]
        self.assertEqual((memory_mi(operator_res["requests"]["memory"]), memory_mi(operator_res["limits"]["memory"])), (168, 216))
        # Rook operator chart v1.19.2 exposes nodeSelector/tolerations but no
        # affinity value; do not add a chart key that the template ignores.
        self.assertNotIn("affinity", operator)
        self.assertEqual(memory_mi(operator["ceph-csi-operator"]["controllerManager"]["manager"]["resources"]["requests"]["memory"]), 48)
        self.assertEqual(memory_mi(operator["ceph-csi-operator"]["controllerManager"]["manager"]["resources"]["limits"]["memory"]), 64)
        for key, expected in (("csiRBDPluginResource", {"csi-rbdplugin": (64, 80), "liveness-prometheus": (24, 32)}),
                              ("csiCephFSPluginResource", {"csi-cephfsplugin": (40, 56), "liveness-prometheus": (24, 32)})):
            entries = csi_values(ROOK_OPERATOR, key)
            for name, (request, limit) in expected.items():
                with self.subTest(key=key, name=name):
                    self.assertEqual(memory_mi(entries[name]["requests"]["memory"]), request)
                    self.assertEqual(memory_mi(entries[name]["limits"]["memory"]), limit)
        base_operator = base_yaml(ROOK_OPERATOR)
        for key in ("csiRBDProvisionerResource", "csiCephFSProvisionerResource"):
            with self.subTest(unchanged_nodeplugin_key=key):
                self.assertEqual(operator["csi"][key], base_operator["csi"][key])

    def test_argocd_values_include_copyutil_for_repo_server_and_dex(self):
        values = yaml.safe_load((ANSIBLE / "vars/argocd_helm_values.yml").read_text())["argocd_helm_values"]
        expected = {"controller": (512, 640), "repoServer": (152, 192), "dex": (128, 160),
                    "server": (64, 80), "notifications": (40, 56)}
        for key, (request, limit) in expected.items():
            resources = values[key]["resources"]
            with self.subTest(key):
                self.assertEqual(memory_mi(resources["requests"]["memory"]), request)
                self.assertEqual(memory_mi(resources["limits"]["memory"]), limit)
        self.assertEqual(values["repoServer"]["copyutil"]["resources"], values["repoServer"]["resources"])
        self.assertEqual(values["dex"]["initImage"]["resources"], values["dex"]["resources"])

    def test_cert_manager_values_and_narrow_apply_scope(self):
        app = yaml.safe_load((CORE / "certificates/cert-manager-application.yml").read_text())
        values = yaml.safe_load(app["spec"]["source"]["helm"]["values"])
        self.assertEqual(values["resources"]["requests"]["memory"], "32Mi")
        self.assertEqual(values["resources"]["limits"]["memory"], "40Mi")
        self.assertEqual(values["cainjector"]["resources"]["requests"]["memory"], "72Mi")
        self.assertEqual(values["cainjector"]["resources"]["limits"]["memory"], "96Mi")
        self.assertEqual(values["webhook"]["resources"]["requests"]["memory"], "32Mi")
        self.assertEqual(values["webhook"]["resources"]["limits"]["memory"], "40Mi")
        for component in (values, values["cainjector"], values["webhook"]):
            affinity = component["affinity"]["nodeAffinity"]["preferredDuringSchedulingIgnoredDuringExecution"]
            self.assertEqual(affinity[0]["preference"]["matchExpressions"][0]["values"], ["yoda"])
        self.assertTrue((CORE / "certificates/cert-manager-application.previous.yml").is_file())
        task = (TASKS / "cert_manager_resources.yml").read_text()
        self.assertEqual(task.count("kubernetes.core.k8s:"), 1)
        self.assertIn("cert_manager_application_file", task)
        self.assertNotIn("/root/pki", task)
        self.assertNotIn("Patch cert-manager webhook", task)

    def test_traefik_previous_is_base_current_values_and_current_prefers_yoda(self):
        current = yaml.safe_load((ANSIBLE / "vars/traefik_helmchartconfig_values.yml").read_text())
        previous = yaml.safe_load((ANSIBLE / "vars/traefik_helmchartconfig_values.previous.yml").read_text())
        self.assertEqual(previous, base_yaml(ANSIBLE / "vars/traefik_helmchartconfig_values.yml"))
        self.assertIn("yoda", str(current["traefik_helmchartconfig_values"].get("affinity")))

    def test_rook_and_cert_manager_previous_files_equal_the_base_branch(self):
        pairs = (
            (ROOK_CLUSTER, CORE / "deployments/rook-ceph/rook-ceph-cluster-values.previous.yaml"),
            (ROOK_OPERATOR, CORE / "deployments/rook-ceph/rook-ceph-operator-values.previous.yaml"),
            (CORE / "ansible/vars/traefik_helmchartconfig_values.yml",
             CORE / "ansible/vars/traefik_helmchartconfig_values.previous.yml"),
            (CORE / "certificates/cert-manager-application.yml",
             CORE / "certificates/cert-manager-application.previous.yml"),
        )
        for source, previous in pairs:
            with self.subTest(previous=previous.name):
                self.assertEqual(yaml.safe_load(previous.read_text()), base_yaml(source))

    def test_runner_job_container_and_checkout_init_resources(self):
        job = yaml.safe_load((CORE / "deployments/ansible-runner/job.template.yaml").read_text())
        pod = job["spec"]["template"]["spec"]
        for res in (pod["containers"][0]["resources"], pod["initContainers"][0]["resources"]):
            self.assertEqual(res["requests"]["memory"], "208Mi")
            self.assertEqual(res["limits"]["memory"], "264Mi")

    def test_each_b3_limit_is_at_most_1_25_times_its_request_except_osd_and_mon(self):
        cluster = yaml.safe_load(ROOK_CLUSTER.read_text())
        rook = cluster["cephClusterSpec"]["resources"]
        ordinary = [rook[key] for key in ("mgr", "mgr-sidecar", "exporter")]
        ordinary.append(cluster["toolbox"]["resources"])
        ordinary.extend((cluster["cephFileSystems"][0]["spec"]["metadataServer"]["resources"],))
        operator = yaml.safe_load(ROOK_OPERATOR.read_text())
        ordinary.append(operator["resources"])
        ordinary.append(operator["ceph-csi-operator"]["controllerManager"]["manager"]["resources"])
        for key in ("csiRBDPluginResource", "csiCephFSPluginResource"):
            ordinary.extend(row["resource"] for row in yaml.safe_load(operator["csi"][key]))
        argo = yaml.safe_load((ANSIBLE / "vars/argocd_helm_values.yml").read_text())["argocd_helm_values"]
        ordinary.extend(argo[key]["resources"] for key in ("controller", "repoServer", "dex", "server", "notifications"))
        cert = yaml.safe_load((CORE / "certificates/cert-manager-application.yml").read_text())
        cert_values = yaml.safe_load(cert["spec"]["source"]["helm"]["values"])
        ordinary.extend((cert_values["resources"], cert_values["cainjector"]["resources"], cert_values["webhook"]["resources"]))
        job = yaml.safe_load((CORE / "deployments/ansible-runner/job.template.yaml").read_text())
        pod = job["spec"]["template"]["spec"]
        ordinary.extend(item["resources"] for item in (pod["containers"][0], pod["initContainers"][0]))
        for index, resources in enumerate(ordinary):
            request = memory_mi(resources["requests"]["memory"])
            limit = memory_mi(resources["limits"]["memory"])
            with self.subTest(index=index):
                self.assertLessEqual(limit, up8(1.25 * request))


class TestRookRecoveryGate(unittest.TestCase):
    def run_gate(self, status, checks, num_osds=3, num_up_osds=3):
        fixture = {"health": {"status": status, "checks": checks},
                   "osd": {"num_osds": num_osds, "num_up_osds": num_up_osds}}
        return subprocess.run([sys.executable, str(ROOK_GATE)], input=json.dumps(fixture),
                              text=True, capture_output=True)

    def test_recovery_accepts_only_the_listed_warn_conditions_with_at_most_one_osd_down(self):
        allowed = ["MDS_CACHE_OVERSIZED", "SLOW_OPS"]
        result = self.run_gate("HEALTH_WARN", {code: {"severity": "HEALTH_WARN"} for code in allowed})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = self.run_gate("HEALTH_WARN", {"OSD_DOWN": {"severity": "HEALTH_WARN"},
                                               "PG_DEGRADED": {"severity": "HEALTH_WARN"}}, 3, 2)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_recovery_refuses_unlisted_codes_health_err_and_two_osds_down(self):
        for status, checks, up in (("HEALTH_ERR", {"MDS_CACHE_OVERSIZED": {}}, 3),
                                   ("HEALTH_WARN", {"PG_AVAILABILITY": {}}, 3),
                                   ("HEALTH_WARN", {"MON_DOWN": {}}, 3),
                                   ("HEALTH_WARN", {"OSD_DOWN": {}}, 1)):
            with self.subTest(status=status, checks=list(checks), up=up):
                result = self.run_gate(status, checks, 3, up)
                self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("PG_AVAILABILITY", self.run_gate("HEALTH_WARN", {"PG_AVAILABILITY": {}}).stderr)

    def test_rook_values_selector_and_recovery_are_explicitly_validated(self):
        task = (TASKS / "rook_ceph_resources.yml").read_text()
        self.assertIn("rook_values_set", task)
        self.assertIn("rook_recovery", task)
        self.assertIn("rook-ceph-cluster-values.previous.yaml", task)
        self.assertIn("rook-ceph-operator-values.previous.yaml", task)
        self.assertIn("rook_health_before.stdout | trim == \"HEALTH_OK\"", task)
        self.assertIn("rook_recovery_gate", task)
        self.assertIn("when: not (rook_recovery | default(false) | bool)", task)

    def test_cert_manager_file_selector_has_only_the_two_allowed_names(self):
        task = (TASKS / "cert_manager_resources.yml").read_text()
        self.assertIn("cert-manager-application.yml", task)
        self.assertIn("cert-manager-application.previous.yml", task)
        self.assertIn("refused: cert_manager_application_file must be", task)

    def test_traefik_values_selector_still_refuses_unknown_names(self):
        task = (TASKS / "traefik_resources.yml").read_text()
        self.assertIn("traefik_values_file", task)
        self.assertIn("traefik_helmchartconfig_values.yml", task)
        self.assertIn("traefik_helmchartconfig_values.previous.yml", task)
        self.assertIn("refused: traefik_values_file must be", task)

    def test_guard_does_not_block_the_new_runner_flags_or_selectors(self):
        guard = (CORE / "deployments/ansible-runner/guard.py").read_text()
        guard_rules = (CORE / "deployments/ansible-runner/guard.yml").read_text()
        for name in ("enable_cert_manager_resources", "cert_manager_application_file",
                     "rook_values_set", "rook_recovery"):
            with self.subTest(name):
                self.assertNotIn(name, guard)
                self.assertNotIn(name, guard_rules)


if __name__ == "__main__":
    unittest.main()
