"""Stage B3 core-app sizing and Jellyfin placement (OCE-369, ticket core-apps).

Asserts, per row of the B3 spec 3.2 table:
  - the manifest or values file carries the B3 request and limit;
  - limit <= ceil8(1.25 x request), except the listed exceptions (Jellyfin 1.5x, containers under 64Mi);
  - request >= the app's own memory budget where it has one (PHP memory_limit, Redis maxmemory,
    Postgres args);
and that the Nextcloud cron sidecar is sized through the chart's real key and Jellyfin is held to
anakin or obiwan. The helm render checks need `helm` and network access to the chart repos, and
skip without them. Run from the core checkout:  python3 -m unittest discover -s ansible/tests -v
"""
import math
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

CORE = Path(__file__).resolve().parents[2]
D = CORE / "deployments"
WIKI = CORE / "docs/wiki/05-GitOps-and-IaC.md"

PHP_MEMORY_LIMIT_MI = 512  # image env PHP_MEMORY_LIMIT, read from the live pod (512M)
POSTGRES_BASELINE_MI = 20  # postmaster, per-backend overhead and catalog caches beyond the settings

# name: (file, expected request, expected limit, allowed ratio)
ROWS = {
    "nextcloud": ("nextcloud/nextcloud-values.yaml", 512, 640, 1.25),
    "nextcloud-cron": ("nextcloud/nextcloud-values.yaml", 72, 96, 1.25),
    "nextcloud-db": ("nextcloud/postgresql/statefulset.yaml", 192, 240, 1.25),
    "nextcloud-redis": ("nextcloud/redis/deployment.yaml", 64, 80, 1.25),
    "s3-sync": ("nextcloud/s3-backup-cronjob.yaml", 80, 104, 1.25),
    "jellyfin": ("jellyfin/jellyfin-values.yaml", 968, 1456, 1.5),
    "xmltv-proxy": ("jellyfin/xmltv-proxy.yaml", 24, 32, 1.5),
    "pihole": ("pihole/pihole-values.yaml", 96, 120, 1.25),
    "home-assistant": ("home-assistant/home-assistant-values.yaml", 1144, 1432, 1.25),
    "mealie": ("mealie/deployment.yaml", 312, 392, 1.25),
}

PUBLIC_P_FILES = (
    CORE / "ansible/tests/test_b3_core_apps_sizing.py",
    CORE / "ansible/tests/test_b3_runner_chart_sizing.py",
    CORE / "ansible/vars/argocd_helm_values.yml",
    CORE / "deployments/home-assistant/home-assistant-values.yaml",
    CORE / "deployments/jellyfin/jellyfin-values.yaml",
    CORE / "deployments/mealie/deployment.yaml",
    CORE / "deployments/nextcloud/nextcloud-values.yaml",
    CORE / "deployments/nextcloud/postgresql/statefulset.yaml",
    CORE / "deployments/pihole/pihole-values.yaml",
    CORE / "deployments/rook-ceph/rook-ceph-cluster-values.yaml",
)


class TestMeasuredPeaksStayPrivate(unittest.TestCase):
    def test_public_b3_files_do_not_contain_measured_p(self):
        measured_p_patterns = (
            re.compile(r"live " + "P"),
            re.compile(r"\b" + "P" + r"\s*[0-9]"),
            re.compile("Measured " + "P is"),
        )
        for path in PUBLIC_P_FILES:
            if ".previous" in path.name:
                continue
            with self.subTest(path=path.relative_to(CORE)):
                contents = path.read_text()
                for pattern in measured_p_patterns:
                    self.assertIsNone(pattern.search(contents), f"{pattern.pattern} found in {path.relative_to(CORE)}")

    def test_b3_rows_do_not_have_a_measured_p_column(self):
        self.assertTrue(all(len(row) == 4 for row in ROWS.values()),
                        "ROWS must contain only file, request, limit and ratio")


def mi(value):
    value = str(value)
    if value.endswith("Gi"):
        return float(value[:-2]) * 1024
    if value.endswith("Mi"):
        return float(value[:-2])
    raise ValueError(value)


def up8(value):
    return int(math.ceil(value / 8) * 8)


def docs(path):
    return [d for d in yaml.safe_load_all((D / path).read_text()) if d]


def pod_spec(doc):
    spec = doc["spec"]
    if doc["kind"] == "CronJob":
        return spec["jobTemplate"]["spec"]["template"]["spec"]
    return spec["template"]["spec"]


def manifest_container(path, name):
    for doc in docs(path):
        if doc.get("kind") in ("Deployment", "StatefulSet", "CronJob"):
            for c in pod_spec(doc)["containers"]:
                if c["name"] == name:
                    return c
    raise KeyError(name)


def resources_of(name):
    """(request Mi, limit Mi) as the file sets them."""
    path = ROWS[name][0]
    if name == "nextcloud":
        res = docs(path)[0]["resources"]
    elif name == "nextcloud-cron":
        res = docs(path)[0]["cronjob"]["sidecar"]["resources"]
    elif name == "jellyfin":
        res = docs(path)[0]["controllers"]["main"]["containers"]["app"]["resources"]
    elif name in ("pihole", "home-assistant"):
        res = docs(path)[0]["resources"]
    else:
        container = {"nextcloud-db": "postgres", "nextcloud-redis": "redis", "s3-sync": "s3-sync",
                     "xmltv-proxy": "proxy", "mealie": "mealie"}[name]
        res = manifest_container(path, container)["resources"]
    return mi(res["requests"]["memory"]), mi(res["limits"]["memory"])


class TestRows(unittest.TestCase):
    def test_each_row_has_the_b3_request_and_limit(self):
        for name, (_, req, lim, _) in ROWS.items():
            with self.subTest(name):
                self.assertEqual(resources_of(name), (req, lim))

    def test_each_row_follows_the_sizing_rule(self):
        for name, (_, req, _, ratio) in ROWS.items():
            request, limit = resources_of(name)
            with self.subTest(name):
                self.assertEqual(request % 8, 0)
                self.assertLessEqual(limit, up8(ratio * request))
                if ratio == 1.25 and request >= 64:
                    self.assertLessEqual(limit, up8(1.25 * request))

    def test_app_budgets_are_inside_the_request(self):
        self.assertGreaterEqual(resources_of("nextcloud")[0], PHP_MEMORY_LIMIT_MI)
        redis_cmd = " ".join(manifest_container("nextcloud/redis/deployment.yaml", "redis")["command"])
        maxmemory = int(re.search(r"maxmemory (\d+)mb", redis_cmd).group(1))
        self.assertGreaterEqual(resources_of("nextcloud-redis")[0], maxmemory)

    def test_postgres_request_is_the_args_budget(self):
        args = manifest_container("nextcloud/postgresql/statefulset.yaml", "postgres")["args"]
        setting = {k: v for k, v in (a.split("=", 1) for a in args if "=" in a)}
        size = lambda key: mi(setting[key].replace("MB", "Mi"))
        budget = (size("shared_buffers") + int(setting["max_connections"]) * size("work_mem")
                  + size("maintenance_work_mem") + size("autovacuum_work_mem") + POSTGRES_BASELINE_MI)
        request, limit = resources_of("nextcloud-db")
        self.assertGreaterEqual(request, budget)
        self.assertEqual(up8(1.25 * request), limit)

    def test_cron_sidecar_uses_the_chart_key_and_the_dead_key_is_gone(self):
        cronjob = docs("nextcloud/nextcloud-values.yaml")[0]["cronjob"]
        self.assertNotIn("resources", cronjob)
        self.assertIn("resources", cronjob["sidecar"])

    def test_jellyfin_is_held_to_anakin_or_obiwan_preferring_anakin(self):
        affinity = docs("jellyfin/jellyfin-values.yaml")[0]["controllers"]["main"]["pod"]["affinity"]["nodeAffinity"]
        required = affinity["requiredDuringSchedulingIgnoredDuringExecution"]["nodeSelectorTerms"]
        self.assertEqual(len(required), 1)
        exprs = required[0]["matchExpressions"]
        host = next(e for e in exprs if e["key"] == "kubernetes.io/hostname")
        # The node labels are the full node names (anakin.local), as the other core apps use.
        self.assertEqual((host["operator"], sorted(host["values"])), ("In", ["anakin.local", "obiwan.local"]))
        self.assertTrue(any(e["key"] == "node-role.kubernetes.io/control-plane" and e["operator"] == "DoesNotExist"
                            for e in exprs))
        preferred = affinity["preferredDuringSchedulingIgnoredDuringExecution"]
        self.assertEqual(len(preferred), 1)
        self.assertEqual(preferred[0]["preference"]["matchExpressions"],
                         [{"key": "kubernetes.io/hostname", "operator": "In", "values": ["anakin.local"]}])


@unittest.skipUnless(shutil.which("helm"), "helm not installed")
class TestRenders(unittest.TestCase):
    def render(self, chart, repo, version, values_file):
        proc = subprocess.run(["helm", "template", "r", chart, "--repo", repo, "--version", version,
                               "-f", str(values_file)], capture_output=True, text=True)
        if proc.returncode:
            self.skipTest(f"chart {chart} {version} not fetchable: {proc.stderr[:200]}")
        return [d for d in yaml.safe_load_all(proc.stdout) if d]

    def test_nextcloud_8_9_1_renders_app_and_cron_sidecar_resources(self):
        rendered = self.render("nextcloud", "https://nextcloud.github.io/helm/", "8.9.1",
                               D / "nextcloud/nextcloud-values.yaml")
        deployment = next(d for d in rendered if d["kind"] == "Deployment" and d["metadata"]["name"].endswith("nextcloud"))
        containers = {c["name"]: c["resources"] for c in deployment["spec"]["template"]["spec"]["containers"]}
        self.assertEqual((mi(containers["nextcloud"]["requests"]["memory"]), mi(containers["nextcloud"]["limits"]["memory"])),
                         (512, 640))
        cron = containers["nextcloud-cron"]
        self.assertEqual((mi(cron["requests"]["memory"]), mi(cron["limits"]["memory"])), (72, 96))

    def test_jellyfin_renders_required_and_preferred_affinity_and_resources(self):
        rendered = self.render("app-template", "https://bjw-s-labs.github.io/helm-charts", "4.3.0",
                               D / "jellyfin/jellyfin-values.yaml")
        deployment = next(d for d in rendered if d["kind"] == "Deployment")
        spec = deployment["spec"]["template"]["spec"]
        node = spec["affinity"]["nodeAffinity"]
        hosts = [e for t in node["requiredDuringSchedulingIgnoredDuringExecution"]["nodeSelectorTerms"]
                 for e in t["matchExpressions"] if e["key"] == "kubernetes.io/hostname"]
        self.assertEqual(hosts[0]["values"], ["anakin.local", "obiwan.local"])
        self.assertEqual(node["preferredDuringSchedulingIgnoredDuringExecution"][0]["preference"]["matchExpressions"][0]["values"],
                         ["anakin.local"])
        res = spec["containers"][0]["resources"]
        self.assertEqual((mi(res["requests"]["memory"]), mi(res["limits"]["memory"])), (968, 1456))


class TestWiki(unittest.TestCase):
    def test_wiki_documents_the_core_apps_run_and_revert_rules(self):
        text = WIKI.read_text().lower()
        for needle in ("cronjob.sidecar.resources", "git hash-object", "nextcloud_s3_backup_deploy.yml",
                       "jellyfin_xmltv_proxy_deploy.yml", "hard refresh", "request = app budget"):
            with self.subTest(needle):
                self.assertIn(needle.lower(), text)


if __name__ == "__main__":
    unittest.main()
