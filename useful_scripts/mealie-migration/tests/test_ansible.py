"""S2: run the real Mealie entrypoint with recording Kubernetes modules."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

CORE = Path(__file__).resolve().parents[3]
TAG = "mealie_contract_test"
FAKE_MODULE = r'''
from ansible.module_utils.basic import AnsibleModule
import json
import os
module = AnsibleModule(argument_spec={
    "kubeconfig": {}, "state": {}, "definition": {"type": "dict"},
    "api_version": {}, "kind": {}, "name": {}, "namespace": {},
}, supports_check_mode=True)
record = {"module": "__MODULE__", "params": module.params}
with open(os.environ["MEALIE_TEST_CALLS"], "a") as stream:
    stream.write(json.dumps(record) + "\n")
if "__MODULE__" == "k8s":
    module.exit_json(changed=False, result=module.params["definition"])
module.exit_json(changed=False, resources=[{"status": {"health": {"status": "Healthy"}}}])
'''


class ApplicationSwitchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.playbooks = self.root / "ansible"
        self.playbooks.mkdir()
        self.config = yaml.safe_load((CORE / "ansible/example.config.yml").read_text())
        main = yaml.safe_load((CORE / "ansible/main.yml").read_text())
        imports = [task for play in main for task in play.get("tasks", [])
                   if task.get("import_tasks", task.get("ansible.builtin.import_tasks"))
                   == "tasks/mealie_deploy.yml"]
        self.assertEqual(len(imports), 1, "exactly one Mealie entrypoint")
        # Add a selection tag to the copied entrypoint only. Preserve its actual
        # condition, task body and vars_files; never recreate the enable expression.
        imports[0]["tags"] = list(imports[0].get("tags", [])) + [TAG]
        (self.playbooks / "main.yml").write_text(yaml.safe_dump(main, sort_keys=False))
        (self.playbooks / "tasks").symlink_to(CORE / "ansible/tasks", target_is_directory=True)
        self.assert_recordable_tasks(yaml.safe_load((CORE / "ansible/tasks/mealie_deploy.yml").read_text()))
        modules = self.root / "collections/ansible_collections/kubernetes/core/plugins/modules"
        modules.mkdir(parents=True)
        for name in ("k8s", "k8s_info"):
            (modules / (name + ".py")).write_text(FAKE_MODULE.replace("__MODULE__", name))
        (self.root / "inventory").write_text("[control_plane]\nlocalhost ansible_connection=local\n")
        (self.root / "ansible.cfg").write_text("[defaults]\nretry_files_enabled = False\n")
        self.variables = {"ansible_connection": "local", "ansible_become": False,
                          "ansible_python_interpreter": sys.executable}
        self.calls_file = self.root / "calls.jsonl"

    def assert_recordable_tasks(self, tasks):
        # Fail before execution if the selected file gains a new action, include,
        # delegation or loop. This harness has no general-purpose command adapter.
        metadata = {"name", "vars", "when", "register", "retries", "delay", "until"}
        for task in tasks:
            keys = set(task) - metadata
            if "block" in keys:
                self.assertEqual(keys, {"block"}, "unreviewed block behavior")
                self.assert_recordable_tasks(task["block"])
            else:
                self.assertEqual(len(keys), 1, "unreviewed task behavior")
                self.assertIn(next(iter(keys)), {
                    "kubernetes.core.k8s", "kubernetes.core.k8s_info", "ansible.builtin.debug",
                }, "only inert module boundaries may execute")

    def run_main(self):
        (self.playbooks / "config.yml").write_text(yaml.safe_dump(self.config, sort_keys=False))
        (self.root / "vars.json").write_text(json.dumps(self.variables))
        self.calls_file.write_text("")
        # Do not inherit operator ANSIBLE_*, cloud, kubeconfig or credential env.
        env = {
            "PATH": os.environ["PATH"], "HOME": str(self.root), "LANG": "C.UTF-8",
            "ANSIBLE_CONFIG": str(self.root / "ansible.cfg"),
            "ANSIBLE_NOCOLOR": "1", "ANSIBLE_LOCAL_TEMP": str(self.root / "local-tmp"),
            "ANSIBLE_REMOTE_TEMP": str(self.root / "remote-tmp"),
            "ANSIBLE_COLLECTIONS_PATH": str(self.root / "collections"),
            "KUBECONFIG": os.devnull, "MEALIE_TEST_CALLS": str(self.calls_file),
        }
        # setup-python's hosted interpreter needs its shared-library search path.
        # Preserve this runtime setting without inheriting operator credentials.
        if "LD_LIBRARY_PATH" in os.environ:
            env["LD_LIBRARY_PATH"] = os.environ["LD_LIBRARY_PATH"]
        result = subprocess.run([
            shutil.which("ansible-playbook"), str(self.playbooks / "main.yml"),
            "-i", str(self.root / "inventory"), "-e", "@" + str(self.root / "vars.json"),
            "--skip-tags", "always", "--tags", TAG,
        ], env=env, capture_output=True, text=True, timeout=30, cwd=self.root)
        self.calls = [json.loads(line) for line in self.calls_file.read_text().splitlines()]
        return result

    def assert_application(self, result, enabled):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        if not enabled:
            self.assertEqual(self.calls, [], "disabled means no Kubernetes calls")
            return
        self.assertEqual([call["module"] for call in self.calls], ["k8s", "k8s_info"])
        write, read = [call["params"] for call in self.calls]
        self.assertEqual(write["state"], "present")
        self.assertEqual(write["definition"], {
            "apiVersion": "argoproj.io/v1alpha1", "kind": "Application",
            "metadata": {"name": "mealie", "namespace": "argocd"},
            "spec": {
                "project": "default",
                "source": {
                    "repoURL": "https://github.com/seadogger-tech/seadogger-homelab",
                    "path": "deployments/mealie", "targetRevision": "HEAD",
                },
                "destination": {"server": "https://kubernetes.default.svc", "namespace": "mealie"},
                "syncPolicy": {"automated": {"prune": True, "selfHeal": True},
                               "syncOptions": ["CreateNamespace=true"]},
            },
        }, "existing Application contract; not permission to reconcile it")
        self.assertEqual({key: read[key] for key in ("api_version", "kind", "name", "namespace")}, {
            "api_version": "argoproj.io/v1alpha1", "kind": "Application",
            "name": "mealie", "namespace": "argocd",
        })

    def test_public_stage_and_manual_switch_matrix(self):
        for stage, manual, enabled in [
            (False, False, False), (False, True, False),
            (True, False, False), (True, True, True),
        ]:
            with self.subTest(stage=stage, manual=manual):
                self.config.update(cold_start_stage_3_install_applications=stage, manual_install_mealie=manual)
                self.assert_application(self.run_main(), enabled)

    def test_explicit_enable_overrides_the_derived_switch(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                self.variables["enable_mealie"] = enabled
                self.config.update(cold_start_stage_3_install_applications=not enabled,
                                   manual_install_mealie=not enabled)
                self.assert_application(self.run_main(), enabled)

    def test_absent_enable_uses_the_existing_true_default(self):
        del self.config["enable_mealie"]
        self.config.update(cold_start_stage_3_install_applications=False, manual_install_mealie=False)
        self.assert_application(self.run_main(), True)

    def test_missing_manual_flag_with_stage_enabled_uses_existing_true_default(self):
        del self.config["manual_install_mealie"]
        self.config["cold_start_stage_3_install_applications"] = True
        # The outer default(true) also handles undefined derived configuration.
        # Characterize this legacy behavior; do not silently harden the policy.
        self.assert_application(self.run_main(), True)

    def test_missing_manual_flag_short_circuits_when_stage_disabled(self):
        del self.config["manual_install_mealie"]
        self.config["cold_start_stage_3_install_applications"] = False
        self.assert_application(self.run_main(), False)


if __name__ == "__main__":
    unittest.main()
