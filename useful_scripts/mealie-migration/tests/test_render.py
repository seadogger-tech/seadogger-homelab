"""S2: inspect the actual local Kustomize output; never apply it."""
import copy
import os
from pathlib import Path
import subprocess
import unittest

import yaml

CORE = Path(__file__).resolve().parents[3]
IMAGE = ("ghcr.io/mealie-recipes/mealie:v3.30.0@sha256:"
         "90f83da6f3ab0a421efc827118a556168573930105f13fa3321768f42163d784")


class CandidateContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(
            ["kubectl", "kustomize", str(CORE / "useful_scripts/mealie-migration/candidate")],
            env=dict(os.environ, KUBECONFIG=os.devnull), capture_output=True, text=True,
            check=True, timeout=30,
        )
        cls.rendered = list(yaml.safe_load_all(result.stdout))

    def assert_contract(self, documents):
        # Literal expected requirements, not a snapshot generated from the render.
        self.assertEqual(len(documents), 8, "resource count")
        resources = {}
        for doc in documents:
            self.assertEqual(doc["metadata"].get("namespace"), "mealie", "namespace")
            key = (doc["kind"], doc["metadata"]["name"])
            self.assertNotIn(key, resources, "duplicate resource")
            resources[key] = doc

        deployment = resources[("Deployment", "mealie")]
        spec = deployment["spec"]
        self.assertEqual(spec["replicas"], 1, "single SQLite writer")
        self.assertEqual(spec["strategy"], {"type": "Recreate"}, "writer replacement")
        self.assertEqual(spec["selector"]["matchLabels"], {"app": "mealie"})
        pod = spec["template"]["spec"]
        self.assertEqual(spec["template"]["metadata"]["labels"], {"app": "mealie"})
        self.assertEqual(pod["nodeSelector"], {"kubernetes.io/arch": "arm64"}, "ARM64")
        self.assertEqual(len(pod["containers"]), 1, "one application container")
        self.assertFalse(pod.get("initContainers"), "no additional writer")
        container = pod["containers"][0]
        self.assertEqual(container["name"], "mealie")
        self.assertEqual(container["image"], IMAGE, "candidate image")
        self.assertEqual(container["imagePullPolicy"], "Always")
        self.assertEqual(container["env"], [
            {"name": "BASE_URL", "value": "https://mealie.seadogger-homelab"},
            {"name": "TZ", "value": "America/New_York"},
            {"name": "PUID", "value": "911"},
            {"name": "PGID", "value": "911"},
            {"name": "OPENAI_CUSTOM_PROMPT_DIR", "value": "/app/custom-prompts"},
        ], "ownership and retained prompt environment")
        self.assertFalse(container.get("envFrom"), "no unreviewed configuration source")
        self.assertEqual(container["ports"], [{"name": "http", "containerPort": 9000}])
        self.assertEqual(container["volumeMounts"], [
            {"name": "data", "mountPath": "/app/data"},
            {"name": "custom-prompts", "mountPath": "/app/custom-prompts/recipes"},
        ], "original data and prompt mounts")
        self.assertEqual(container["resources"], {
            "requests": {"cpu": "50m", "memory": "320Mi"},
            "limits": {"cpu": "1000m", "memory": "1Gi"},
        }, "resource contract")
        self.assertEqual(container["readinessProbe"], {
            "httpGet": {"path": "/api/app/about", "port": 9000},
            "initialDelaySeconds": 20, "periodSeconds": 10,
        }, "readiness probe")
        self.assertEqual(container["livenessProbe"], {
            "httpGet": {"path": "/api/app/about", "port": 9000},
            "initialDelaySeconds": 60, "periodSeconds": 30,
        }, "liveness probe")
        self.assertEqual(resources[("PersistentVolumeClaim", "mealie-data")]["spec"], {
            "accessModes": ["ReadWriteOnce"], "storageClassName": "ceph-block-data",
            "resources": {"requests": {"storage": "10Gi"}},
        }, "original RWO claim")

        prompt_maps = [d for d in documents if d["kind"] == "ConfigMap"]
        self.assertEqual(len(prompt_maps), 1)
        prompt_map = prompt_maps[0]
        self.assertTrue(prompt_map["metadata"]["name"].startswith("mealie-custom-prompts-"))
        self.assertEqual(pod["volumes"], [
            {"name": "data", "persistentVolumeClaim": {"claimName": "mealie-data"}},
            {"name": "custom-prompts", "configMap": {"name": prompt_map["metadata"]["name"]}},
        ], "original volume references")
        prompt_names = ["parse-recipe-ingredients.txt", "parse-recipe-image.txt",
                        "parse-recipe-video.txt", "scrape-recipe.txt"]
        self.assertEqual(set(prompt_map["data"]), set(prompt_names), "retained prompt inputs")
        for name in prompt_names:
            # Preservation of source bytes, not approval of the legacy prompt semantics.
            self.assertEqual(prompt_map["data"][name],
                             (CORE / "deployments/mealie/prompts/recipes" / name).read_text())
        self.assertEqual(resources[("Service", "mealie")]["spec"], {
            "selector": {"app": "mealie"}, "ports": [{"port": 9000, "targetPort": 9000}],
        }, "Service routing")
        self.assertEqual(resources[("Certificate", "mealie-certificate")]["spec"], {
            "secretName": "mealie-local-tls", "duration": "2160h", "renewBefore": "360h",
            "subject": {"organizations": ["SeaDogger Homelab"]}, "isCA": False,
            "privateKey": {"algorithm": "RSA", "encoding": "PKCS1", "size": 2048},
            "dnsNames": ["mealie.seadogger-homelab"],
            "issuerRef": {"name": "internal-local-issuer", "kind": "ClusterIssuer"},
        }, "certificate contract")
        self.assertEqual(resources[("Middleware", "mealie-redirect-https")]["spec"], {
            "redirectScheme": {"scheme": "https", "permanent": True, "port": "443"},
        }, "HTTPS redirect")
        route = {"match": "Host(`mealie.seadogger-homelab`)", "kind": "Rule",
                 "services": [{"name": "mealie", "port": 9000}]}
        self.assertEqual(resources[("IngressRoute", "mealie-http")]["spec"], {
            "entryPoints": ["web"],
            "routes": [dict(route, middlewares=[{"name": "mealie-redirect-https"}])],
        }, "HTTP route")
        self.assertEqual(resources[("IngressRoute", "mealie-https")]["spec"], {
            "entryPoints": ["websecure"], "routes": [route],
            "tls": {"secretName": "mealie-local-tls"},
        }, "TLS route")

    def test_candidate_preserves_the_reviewed_deployment_contract(self):
        self.assert_contract(self.rendered)

    def test_contract_rejects_focused_regressions(self):
        # Each mutation alters actual renderer output at S2. A rejected mutant is
        # sensitivity evidence, not a failed application run or runtime assurance.
        cases = [
            ("Deployment", "mealie", ("spec", "replicas"), 2),
            ("Deployment", "mealie", ("spec", "strategy"), {"type": "RollingUpdate"}),
            ("Deployment", "mealie", ("spec", "template", "spec", "nodeSelector"),
             {"kubernetes.io/arch": "amd64"}),
            ("Deployment", "mealie", ("spec", "template", "spec", "containers", 0, "image"),
             "ghcr.io/mealie-recipes/mealie:v3.30.0"),
            ("Deployment", "mealie", ("spec", "template", "spec", "containers", 0, "env", 2, "value"), "0"),
            ("Deployment", "mealie", ("spec", "template", "spec", "containers", 0,
                                    "volumeMounts", 0, "mountPath"), "/wrong"),
            ("Deployment", "mealie", ("spec", "template", "spec", "volumes", 0,
                                    "persistentVolumeClaim", "claimName"), "replacement-data"),
            ("Deployment", "mealie", ("spec", "template", "spec", "containers", 0,
                                    "resources", "requests", "memory"), "256Mi"),
            ("Deployment", "mealie", ("spec", "template", "spec", "containers", 0,
                                    "readinessProbe", "httpGet", "path"), "/"),
            ("Deployment", "mealie", ("spec", "template", "spec", "containers", 0,
                                    "livenessProbe", "httpGet", "port"), 80),
            ("PersistentVolumeClaim", "mealie-data", ("spec", "accessModes"), ["ReadWriteMany"]),
            ("Service", "mealie", ("spec", "ports", 0, "targetPort"), 80),
            ("Certificate", "mealie-certificate", ("spec", "dnsNames"), ["wrong.test"]),
            ("IngressRoute", "mealie-https", ("spec", "tls", "secretName"), "wrong-tls"),
            ("Middleware", "mealie-redirect-https", ("spec", "redirectScheme", "scheme"), "http"),
        ]
        for kind, name, path, value in cases:
            with self.subTest(resource=name, path=path):
                documents = copy.deepcopy(self.rendered)
                target = next(d for d in documents if (d["kind"], d["metadata"]["name"]) == (kind, name))
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                with self.assertRaises(AssertionError):
                    self.assert_contract(documents)
        documents = copy.deepcopy(self.rendered)
        prompt_map = next(d for d in documents if d["kind"] == "ConfigMap")
        del prompt_map["data"]["scrape-recipe.txt"]
        with self.assertRaises(AssertionError):
            self.assert_contract(documents)


if __name__ == "__main__":
    unittest.main()
