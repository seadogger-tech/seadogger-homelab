"""Controller-side paths in apply tasks, the cert-manager definition, and the s3-backup schedule (OCE-832).

The runner executes tasks on the control-plane host (yoda), so a kubernetes.core module
argument that names a file under the runner's checkout (playbook_dir, role_path, /work/)
reads a path that does not exist there. Such a file must be read with lookup('file') on the
controller or copied to the host first.

Run from the core checkout:  python3 -m unittest discover -s ansible/tests -v
"""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

CORE = Path(__file__).resolve().parents[2]
ANSIBLE = CORE / "ansible"
TASKS = ANSIBLE / "tasks"
CONTROLLER_PATH = re.compile(r"playbook_dir|role_path|/work/")
ARGS = {"kubernetes.core.k8s": ("src",), "kubernetes.core.helm": ("values_files", "chart_ref")}
CERT_FILES = ("cert-manager-application.yml", "cert-manager-application.previous.yml")


def controller_path_args(path):
    """Yield (task name, module, arg) for module args naming a controller path with no earlier copy."""
    copied = set()
    for task in yaml.safe_load(path.read_text()) or []:
        copy = task.get("ansible.builtin.copy")
        if copy:
            copied.add(str(copy.get("dest")))
        for module, names in ARGS.items():
            args = task.get(module)
            for name in names if args else ():
                value = args.get(name)
                for item in value if isinstance(value, list) else [value]:
                    if item and CONTROLLER_PATH.search(str(item)) and str(item) not in copied:
                        yield task.get("name"), module, name


class ControllerPaths(unittest.TestCase):
    def test_no_resources_task_passes_a_controller_path_to_a_module(self):
        files = sorted(TASKS.glob("*_resources.yml"))
        self.assertGreaterEqual(len(files), 5)
        for path in files:
            with self.subTest(path.name):
                self.assertEqual(list(controller_path_args(path)), [])


class CertManagerApply(unittest.TestCase):
    def apply_task(self):
        tasks = yaml.safe_load((TASKS / "cert_manager_resources.yml").read_text())
        return next(t for t in tasks if "kubernetes.core.k8s" in t)["kubernetes.core.k8s"]

    def test_application_is_a_definition_built_from_the_file_on_the_controller(self):
        k8s = self.apply_task()
        self.assertNotIn("src", k8s)
        self.assertRegex(k8s["definition"], r"lookup\(.file.[\s\S]*playbook_dir")
        self.assertIn("from_yaml", k8s["definition"])

    def test_definition_renders_to_the_selected_application_without_a_file_on_the_module_side(self):
        if not shutil.which("ansible-playbook"):
            self.skipTest("ansible-playbook not installed")
        expression = self.apply_task()["definition"]
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        # The module never sees the checkout: only the rendered mapping reaches it.
        checkout = tmp / "core"
        shutil.copytree(CORE / "certificates", checkout / "certificates")
        (checkout / "ansible").mkdir()
        play = checkout / "ansible" / "render.yml"
        play.write_text(yaml.safe_dump([{"hosts": "localhost", "gather_facts": False, "connection": "local", "tasks": [
            {"ansible.builtin.set_fact": {"rendered": expression}},
            {"ansible.builtin.copy": {"dest": str(tmp / "out.json"), "content": "{{ rendered | to_json }}"}}]}]))
        for name in CERT_FILES:
            with self.subTest(name):
                result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(play), "-e",
                                         f"cert_manager_application_file={name}"],
                                        cwd=checkout / "ansible", capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                rendered = json.loads((tmp / "out.json").read_text())
                self.assertIsInstance(rendered, dict)
                self.assertEqual(rendered, yaml.safe_load((CORE / "certificates" / name).read_text()))

    def test_unknown_file_still_fails_the_assert(self):
        tasks = yaml.safe_load((TASKS / "cert_manager_resources.yml").read_text())
        assertion = tasks[0]["ansible.builtin.assert"]
        self.assertEqual(len(assertion["that"]), 1)
        self.assertIn("['cert-manager-application.yml', 'cert-manager-application.previous.yml']", " ".join(assertion["that"][0].split()))
        if not shutil.which("ansible-playbook"):
            self.skipTest("ansible-playbook not installed")
        result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(TASKS / "cert_manager_resources.yml"),
                                 "-e", "cert_manager_application_file=../x.yml"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)


class S3BackupSchedule(unittest.TestCase):
    def test_runs_at_03_00_new_york(self):
        spec = yaml.safe_load((CORE / "deployments/nextcloud/s3-backup-cronjob.yaml").read_text())["spec"]
        self.assertEqual(spec["schedule"], "0 3 * * *")
        self.assertEqual(spec["timeZone"], "America/New_York")


if __name__ == "__main__":
    unittest.main()
