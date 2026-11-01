"""Closed evaluation packet parsing. Validation establishes shape, never authority."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any


SOURCE = "9552df62118224a377d9c9b0a62706a62220ab86"
INDEX = "sha256:90f83da6f3ab0a421efc827118a556168573930105f13fa3321768f42163d784"
ARM64 = "sha256:8dbe3fd73896e77c797f7029201823fa8b1ddbc725059f496cf884f06c9916da"
BODY_LIMIT = 2_097_152
PACKET_LIMIT = 67_108_864
STOP_NS = 295_000_000_000
END_NS = 300_000_000_000
BODY = {"url": "https://recipes.test/ordinary-web.html", "includeTags": False, "includeCategories": False}
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*", re.ASCII)
DIGEST = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)


class Denied(ValueError):
    """A fixed, non-sensitive reason code suitable for a sanitized receipt."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise Denied(code)


def digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def encode(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def decode(raw: bytes, limit: int = BODY_LIMIT) -> Any:
    require(len(raw) <= limit, "BODY_LIMIT")

    def pairs(entries):
        result = {}
        for key, value in entries:
            require(key not in result, "DUPLICATE_KEY")
            result[key] = value
        return result

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(Denied("INVALID_JSON")))
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, Denied):
            raise
        raise Denied("INVALID_JSON") from None


def unbase64(value: str) -> bytes:
    require(isinstance(value, str) and len(value) <= (BODY_LIMIT + 2) // 3 * 4, "BODY_LIMIT")
    try:
        raw = base64.b64decode(value, validate=True)
    except ValueError:
        raise Denied("INVALID_ENCODING") from None
    require(len(raw) <= BODY_LIMIT, "BODY_LIMIT")
    return raw


def exact_keys(value: Any, expected: set[str]) -> None:
    require(isinstance(value, dict) and value.keys() == expected, "INVALID_FIELDS")


def opaque(value: Any) -> None:
    require(isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value)), "INVALID_REFERENCE")


def sha(value: Any) -> None:
    require(isinstance(value, str) and bool(DIGEST.fullmatch(value)), "INVALID_DIGEST")


def canonical_target(value: Any) -> None:
    require(isinstance(value, str) and value.startswith("/") and len(value) <= 2048, "INVALID_TARGET")
    # Query strings are separately reviewed literals. Never decode or normalize paths.
    path = value.split("?", 1)[0]
    require(not any(c in value for c in "%\\#\x00") and all(32 < ord(c) < 127 for c in value), "INVALID_TARGET")
    require("//" not in path and not any(p in (".", "..") for p in path.split("/")), "INVALID_TARGET")
    require(value.count("?") <= 1 and not value.endswith("?"), "INVALID_TARGET")


@dataclass(frozen=True)
class Binding:
    """Immutable canonical bytes; callers receive copies, never mutable shared state."""

    raw: bytes

    @classmethod
    def parse(cls, raw: bytes) -> Binding:
        value = decode(raw)
        exact_keys(value, {"version", "runId", "epoch", "hostBootId", "targetBootId", "configDigest",
                           "bundleDigest", "source", "index", "arm64", "imageConfig", "coreRevision",
                           "components", "identities", "references", "authority", "requestBodyDigest",
                           "groupSlug", "groupId", "runnerId", "observerId", "observerValidUntilNs",
                           "t0Ns", "uiManifest", "limits"})
        require(value["version"] == "OCE63-CONTROL-1", "CONTRACT_VERSION")
        for key in ("runId", "epoch", "hostBootId", "targetBootId", "groupId", "runnerId", "observerId"):
            opaque(value[key])
        require(value["runnerId"] != value["observerId"], "IDENTITY_MISMATCH")
        require(isinstance(value["groupSlug"], str) and bool(SLUG.fullmatch(value["groupSlug"])), "INVALID_SLUG")
        require(value["source"] == SOURCE and value["index"] == INDEX and value["arm64"] == ARM64, "IMAGE_MISMATCH")
        require(bool(re.fullmatch(r"[0-9a-f]{40}", value["coreRevision"])), "SOURCE_MISMATCH")
        for key in ("configDigest", "bundleDigest", "imageConfig", "requestBodyDigest"):
            sha(value[key])
        exact_keys(value["components"], {"controller", "admission", "adapter", "fixture", "oracle", "dns",
                                          "stub", "ui", "ingress", "browser", "network"})
        for item in value["components"].values():
            sha(item)
        exact_keys(value["identities"], {"cluster", "apiCa", "namespace", "node", "workload", "netns",
                                          "processSet", "runtimeSet", "backendSet", "volume", "filesystem",
                                          "writerEpoch", "networkGeneration", "hostVm", "guestNode"})
        for item in value["identities"].values():
            opaque(item)
        exact_keys(value["references"], {"authority", "imageEvidence", "capacity", "custody", "retention",
                                          "rearm", "observerSession", "runnerCredential", "fallbackAuthority"})
        for item in value["references"].values():
            opaque(item)
        require(bool(re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", value["authority"])), "INVALID_AUTHORITY")
        require(type(value["t0Ns"]) is int and value["t0Ns"] >= 0, "INVALID_CLOCK")
        require(type(value["observerValidUntilNs"]) is int
                and value["observerValidUntilNs"] >= value["t0Ns"] + END_NS, "SESSION_WINDOW")
        require(value["limits"] == {
            "requestBytes": BODY_LIMIT, "responseBytes": BODY_LIMIT, "packetBytes": PACKET_LIMIT,
            "stopSeconds": 295, "endSeconds": 300, "intakePerMinute": 6, "intakeBurst": 1,
            "generalPerMinute": 60, "generalBurst": 10, "intakeInFlight": 1, "generalInFlight": 4,
            "appTempBytes": 268435456, "ingressTempBytes": 16777216, "dataBytes": 10737418240,
            "totalDiskBytes": 21474836480, "appCpuMilli": 1000, "appMemoryBytes": 1073741824,
            "appRequestCpuMilli": 50, "appRequestMemoryBytes": 335544320,
            "vmCpu": 4, "vmMemoryBytes": 4294967296, "providerAttempts": 0,
            "stubCalls": 20, "stubRequestBytes": 65536, "stubResponseBytes": 4096,
        }, "LIMIT_MISMATCH")
        validate_manifest(value["uiManifest"], value["components"]["ui"])
        return cls(encode(value))

    @property
    def value(self) -> dict:
        return decode(self.raw)

    @property
    def hash(self) -> str:
        return digest(self.raw)


def validate_manifest(manifest: Any, expected_digest: str) -> None:
    exact_keys(manifest, {"version", "candidate", "packageInventoryDigest", "reviewRef", "complete", "routes"})
    require(manifest["version"] == "OCE63-UI-1" and manifest["candidate"] == ARM64, "MANIFEST_IDENTITY")
    require(manifest["complete"] is True, "UI_INVENTORY_MISSING")
    sha(manifest["packageInventoryDigest"])
    opaque(manifest["reviewRef"])
    require(digest(encode(manifest)) == expected_digest, "MANIFEST_DIGEST")
    routes = manifest["routes"]
    require(isinstance(routes, list) and 4 <= len(routes) <= 1024, "MANIFEST_ROUTES")
    seen = set()
    for route in routes:
        exact_keys(route, {"actor", "method", "target", "purpose", "sourceRef", "maxBytes", "assetDigest"})
        require(route["actor"] in ("observer", "probe") and route["method"] in ("GET", "HEAD"), "MANIFEST_METHOD")
        target = route["target"]
        canonical_target(target)
        require("*" not in target and "[" not in target and "]" not in target, "MANIFEST_WILDCARD")
        stripped = target.replace("{groupSlug}", "group").replace("{returnedSlug}", "recipe")
        require("{" not in stripped and "}" not in stripped, "MANIFEST_PLACEHOLDER")
        require(not any(p in stripped.split("/api/", 1)[-1].split("/")
                        for p in ("auth", "admin", "ai-providers", "explore", "debug", "backups", "webhooks")), "FORBIDDEN_ROUTE")
        require(type(route["maxBytes"]) is int and 0 < route["maxBytes"] <= BODY_LIMIT, "RESPONSE_LIMIT")
        require(isinstance(route["purpose"], str) and 1 <= len(route["purpose"]) <= 200, "MANIFEST_PURPOSE")
        require(isinstance(route["sourceRef"], str) and 1 <= len(route["sourceRef"]) <= 256, "MANIFEST_SOURCE")
        if route["assetDigest"] is not None:
            sha(route["assetDigest"])
            require("{" not in target and not target.startswith("/api/"), "MANIFEST_ASSET")
        key = route["actor"], route["method"], target
        require(key not in seen, "MANIFEST_DUPLICATE")
        seen.add(key)
    require({("observer", "GET", "/api/users/self"),
             ("observer", "GET", "/g/{groupSlug}/r/{returnedSlug}"),
             ("observer", "GET", "/api/recipes/{returnedSlug}"),
             ("probe", "GET", "/api/app/about")} <= seen, "MANIFEST_SEEDS")
    require(any(r["assetDigest"] is not None for r in routes), "UI_INVENTORY_MISSING")


def verify_image_bytes(index_raw: bytes, manifest_raw: bytes, config_raw: bytes, expected_config: str) -> dict:
    """E1 byte linkage only; does not approve provenance, layers, scans or runtime."""
    require(digest(index_raw) == INDEX and digest(manifest_raw) == ARM64, "IMAGE_MISMATCH")
    sha(expected_config)
    require(digest(config_raw) == expected_config, "IMAGE_CONFIG_MISMATCH")
    index, manifest, config = (decode(raw) for raw in (index_raw, manifest_raw, config_raw))
    require(index.get("schemaVersion") == 2 and manifest.get("schemaVersion") == 2, "IMAGE_SCHEMA")
    matches = [d for d in index.get("manifests", []) if d.get("digest") == ARM64]
    require(len(matches) == 1, "IMAGE_MEMBERSHIP")
    child = matches[0]
    require(child.get("size") == len(manifest_raw) and child.get("platform", {}).get("os") == "linux"
            and child.get("platform", {}).get("architecture") == "arm64", "IMAGE_PLATFORM")
    require(manifest.get("config", {}).get("digest") == expected_config
            and manifest["config"].get("size") == len(config_raw), "IMAGE_CONFIG_DESCRIPTOR")
    require(config.get("os") == "linux" and config.get("architecture") == "arm64", "IMAGE_PLATFORM")
    require(isinstance(manifest.get("layers"), list) and isinstance(config.get("rootfs"), dict), "IMAGE_LAYERS")
    require(config["rootfs"].get("type") == "layers"
            and len(config["rootfs"].get("diff_ids", [])) == len(manifest["layers"]), "IMAGE_LAYER_COUNT")
    for layer in manifest["layers"]:
        sha(layer.get("digest"))
        require(type(layer.get("size")) is int and layer["size"] >= 0, "IMAGE_LAYER_DESCRIPTOR")
    for diff_id in config["rootfs"]["diff_ids"]:
        sha(diff_id)
    return {"identity": "BYTES_LINKED", "layersVerified": False, "sourceEquivalence": "UNPROVEN",
            "provenance": "UNASSESSED", "scan": "UNASSESSED", "runtime": "UNOBSERVED"}
