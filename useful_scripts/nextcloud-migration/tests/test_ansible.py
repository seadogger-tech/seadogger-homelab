"""Execute real Ansible entry points against a recording Kubernetes boundary."""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

CORE = Path(__file__).resolve().parents[3]
FAKE_MODULE = r'''from ansible.module_utils.basic import AnsibleModule
import json
import os
from pathlib import Path
module = AnsibleModule(argument_spec={
    "kubeconfig": {}, "api_version": {}, "kind": {}, "name": {}, "namespace": {},
    "state": {}, "definition": {"type": "dict"}, "src": {},
    "label_selectors": {"type": "list", "elements": "str"},
}, supports_check_mode=True)
params = module.params
with open(os.environ["NC_TEST_CALLS"], "a") as stream:
    stream.write(json.dumps(params) + "\n")
fixtures = json.loads(Path(os.environ["NC_TEST_FIXTURES"]).read_text())
key = params.get("kind", "") + "/" + (params.get("name") or "") if params.get("kind") else ""
if params.get("definition"):
    module.exit_json(changed=not module.check_mode, result=params["definition"])
module.exit_json(changed=False, resources=fixtures.get(key, []))
'''


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.playbooks = self.root / "ansible"
        self.playbooks.mkdir()
        for name in ("main.yml", "nextcloud_postgresql.yml"):
            shutil.copy(CORE / "ansible" / name, self.playbooks / name)
        (self.playbooks / "tasks").symlink_to(CORE / "ansible/tasks", target_is_directory=True)
        (self.playbooks / "config.yml").write_text((CORE / "ansible/example.config.yml").read_text())
        self.collection = self.root / "collections/ansible_collections/kubernetes/core/plugins/modules"
        self.collection.mkdir(parents=True)
        for name in ("k8s", "k8s_info", "helm", "helm_repository", "k8s_json_patch"):
            (self.collection / (name + ".py")).write_text(FAKE_MODULE)
        self.fixtures = {
            "StorageClass/ceph-block-data": [{"reclaimPolicy": "Retain", "allowVolumeExpansion": True}],
            "Prometheus/k8s": [{"spec": {"ruleSelector": {}, "ruleNamespaceSelector": {}}}],
            "StatefulSet/nextcloud-db": [{"status": {"readyReplicas": 1}}],
        }
        self.variables = {
            "ansible_connection": "local", "ansible_become": False,
            "ansible_python_interpreter": sys.executable,
            "cold_start_stage_3_install_applications": True,
            "manual_install_nextcloud_postgresql": True,
            "nextcloud_postgresql_revision": "a" * 40,
            "nextcloud_postgresql_admin_password": "example-admin-password-24-characters",
            "nextcloud_postgresql_password": "example-app-password-24-characters",
        }

    def run_playbook(self, name="main.yml", tags="nextcloud_postgresql", check=False):
        (self.root / "fixtures.json").write_text(json.dumps(self.fixtures))
        (self.root / "vars.json").write_text(json.dumps(self.variables))
        (self.root / "inventory").write_text("[control_plane]\nlocalhost\n")
        calls = self.root / "calls.jsonl"
        calls.write_text("")
        (self.root / "ansible.cfg").write_text("[defaults]\n")
        env = dict(os.environ, ANSIBLE_CONFIG=str(self.root / "ansible.cfg"), ANSIBLE_NOCOLOR="1",
                   ANSIBLE_LOCAL_TEMP=str(self.root / "tmp"),
                   ANSIBLE_COLLECTIONS_PATH=str(self.root / "collections"),
                   NC_TEST_CALLS=str(calls), NC_TEST_FIXTURES=str(self.root / "fixtures.json"))
        command = ["ansible-playbook", str(self.playbooks / name), "-i", str(self.root / "inventory"),
                   "-e", "@" + str(self.root / "vars.json"), "--skip-tags", "always", "--tags", tags]
        if check:
            command.append("--check")
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=90)
        self.calls = [json.loads(line) for line in calls.read_text().splitlines()]
        self.writes = [c["definition"] for c in self.calls if c.get("definition")]
        return result

    def test_main_stages_database_through_argo_without_selecting_it_for_nextcloud(self):
        result = self.run_playbook()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([(r["kind"], r["metadata"]["name"]) for r in self.writes],
                         [("Secret", "nextcloud-db-auth"), ("Application", "nextcloud-db")])
        app = self.writes[-1]
        self.assertEqual(app["spec"]["source"]["path"], "deployments/nextcloud/postgresql")
        self.assertEqual(app["spec"]["source"]["targetRevision"], "a" * 40)

    def test_missing_marker_refuses_to_remove_live_postgresql_configuration(self):
        self.fixtures["Application/nextcloud"] = [{
            "spec": {"source": {"helm": {"valuesObject": {"externalDatabase": {"type": "postgresql"}}}},
                     "syncPolicy": {"automated": {"prune": True, "selfHeal": True}}}}]
        result = self.run_playbook(tags="nextcloud_configuration")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.writes)
        self.assertIn("private migration", result.stdout)

    def test_missing_credentials_on_retained_storage_stop_before_any_write(self):
        self.fixtures["PersistentVolumeClaim/nextcloud-db-data"] = [{"status": {"phase": "Bound"}}]
        result = self.run_playbook()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.writes)

    def test_disabled_stage_or_manual_switch_produces_no_database_calls(self):
        for stage, manual in [(False, False), (False, True), (True, False)]:
            with self.subTest(stage=stage, manual=manual):
                self.variables.update(cold_start_stage_3_install_applications=stage,
                                      manual_install_nextcloud_postgresql=manual)
                result = self.run_playbook()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertFalse(self.calls)

    def test_explicit_staging_and_main_preserve_credentials_and_active_backups(self):
        self.fixtures["Secret/nextcloud-db-auth"] = [{"data": {
            "db-password": base64.b64encode(self.variables["nextcloud_postgresql_password"].encode()).decode(),
            "postgres-password": base64.b64encode(self.variables["nextcloud_postgresql_admin_password"].encode()).decode()}}]
        patches = [{"target": {"kind": "CronJob", "name": "nextcloud-db-backup"},
                    "patch": "- op: replace\n  path: /spec/suspend\n  value: false\n"}]
        self.fixtures["Application/nextcloud-db"] = [{"spec": {"source": {"kustomize": {"patches": patches}}}}]
        result = self.run_playbook()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        normal = self.writes
        self.variables["nextcloud_postgresql_apply"] = True
        result = self.run_playbook("nextcloud_postgresql.yml", tags="all")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(normal, self.writes)
        self.assertEqual(self.writes[-1]["spec"]["source"]["kustomize"]["patches"], patches)
        self.variables["nextcloud_postgresql_password"] = "an-unapproved-credential-change"
        result = self.run_playbook()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.writes)
        self.assertNotIn("an-unapproved-credential-change", result.stdout)

    def install_marker(self, active):
        values = {"image": {"registry": "docker.io", "repository": "library/nextcloud",
                            "tag": "32.0.6-apache@sha256:" + "b" * 64}}
        if active:
            values["externalDatabase"] = {"type": "postgresql"}
        marker = {"nextcloud_migration_run": "test-run", "nextcloud_postgresql_active": active,
                  "nextcloud_postgresql_revision": "a" * 40, "nextcloud_migration_helm_values": values}
        path = self.playbooks / "nextcloud-database.local.json"
        path.write_text(json.dumps(marker))
        path.chmod(0o600)
        self.fixtures["Application/nextcloud"] = [{"spec": {
            "source": {"helm": {"valuesObject": values}},
            "syncPolicy": {"automated": {"prune": True, "selfHeal": True}}}}]
        return marker

    def test_rerun_preserves_database_and_image_after_either_reopening(self):
        for active in (True, False):
            with self.subTest(postgresql=active):
                marker = self.install_marker(active)
                result = self.run_playbook(tags="nextcloud_postgresql,nextcloud_configuration")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual([r["metadata"]["name"] for r in self.writes],
                                 ["nextcloud-db-auth", "nextcloud-db", "nextcloud"])
                helm = self.writes[-1]["spec"]["source"]["helm"]
                self.assertEqual(helm["valuesObject"], marker["nextcloud_migration_helm_values"])
                self.assertEqual(any("nextcloud-postgresql-values" in path for path in helm["valueFiles"]), active)

    def test_paused_application_and_stale_marker_refuse_nextcloud_writes(self):
        self.install_marker(True)
        app = self.fixtures["Application/nextcloud"][0]
        app["spec"]["syncPolicy"] = {}
        result = self.run_playbook(tags="nextcloud_configuration")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.writes)
        app["spec"]["syncPolicy"] = {"automated": {}}
        app["spec"]["source"]["helm"]["valuesObject"]["externalDatabase"]["type"] = "mysql"
        result = self.run_playbook(tags="nextcloud_configuration")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.writes)

    def test_check_mode_and_staging_authorization(self):
        result = self.run_playbook(check=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(any(c.get("kind") == "StatefulSet" for c in self.calls))
        result = self.run_playbook("nextcloud_postgresql.yml", tags="all")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.calls)


if __name__ == "__main__":
    unittest.main()
