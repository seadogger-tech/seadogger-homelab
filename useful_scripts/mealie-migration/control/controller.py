"""Single-run controller. Operations supplies the enforcing broker and ingress.

The controller never connects to Mealie itself. A forward is a single revocable
capability consumed by the broker, serialized there with closure of the same run.
"""

from __future__ import annotations

import re
import threading
import uuid

from adapter import SocketAdapter, boot_id, boottime_ns, verified
from contract import (BODY, BODY_LIMIT, END_NS, SLUG, STOP_NS, Binding, Denied, canonical_target,
                      decode, digest, encode, exact_keys, opaque, require, unbase64)
from ledger import Ledger, TERMINAL


READINESS = (
    "authorityCurrent", "rearmAuthorized", "priorStateReconciled", "retentionHeld", "capacityReserved",
    "custodyBound", "imageEvidenceVerified", "preloadedImageMatched", "configurationMatched",
    "componentsMatched", "targetMatched", "noUplink", "networkBeforeExec", "packetQuotaEnforced",
    "offloadBypassExcluded", "allWritePathsBounded", "singleWriterEnforced", "startFenceClosed",
    "ledgerDurabilityVerified", "hostTombstoneCurrent", "watchdogIndependent", "watchdogArmed",
    "suspendResumeFenced", "allHelpersCovered", "providerOff", "zeroProviderAttempts",
    "observerSessionValid", "uiInventoryReviewed", "parserAgreementVerified", "edgeLimitsEnforced",
)
LIVE = ("targetMatched", "configurationMatched", "imageRuntimeMatched", "hostTombstoneCurrent", "watchdogArmed",
        "networkGenerationMatched", "packetBudgetAvailable", "capacityReserved", "singleWriterEnforced",
        "allHelpersCovered", "zeroProviderAttempts", "observerSessionValid", "leaseCurrent")
QUIESCENCE = ("processesEmpty", "runtimeTasksAbsent", "helpersStopped", "networkClosed",
              "restartFenceClosed", "backendIoSettled", "coverageComplete", "noReplacementWriter")


class Controller:
    """Lifecycle and admission entrypoints for the reviewed adapter integration."""

    def __init__(self, ledger: Ledger, adapter: SocketAdapter, binding: Binding):
        self.binding = Binding.parse(binding.raw)
        self.ledger = ledger
        self.adapter = adapter
        self.lock = threading.RLock()
        self.closed = True
        self.launching = False
        self.forced = False
        self.stop_event = threading.Event()
        self.timer: threading.Thread | None = None
        self.last_tick = boottime_ns()
        self.buckets = {"intake": [1.0, self.last_tick, 0], "general": [10.0, self.last_tick, 0]}

    def _call(self, operation: str, state: dict, payload: dict | None = None, timeout: float = 0.2) -> dict:
        return self.adapter.call(operation, self.binding, state["sequence"], payload, timeout)

    def _time(self, before_stop: bool = True) -> int:
        value = self.binding.value
        now = boottime_ns()
        require(boot_id() == value["hostBootId"], "BOOT_CHANGED")
        require(now >= self.last_tick and now >= value["t0Ns"], "CLOCK_CHANGED")
        self.last_tick = now
        if before_stop:
            require(now < value["t0Ns"] + STOP_NS, "DEADLINE_CLOSED")
        return now

    def prepare(self) -> None:
        """Must be invoked explicitly; never recover or rearm an existing run."""
        with self.lock:
            require(self.closed and self.timer is None, "ALREADY_PREPARED")
            interrupted = self.ledger.recover()
            for binding, state in interrupted:
                # Recovery can only close. Old config/boot mismatch still requires
                # Operations' independent tombstone/watchdog, never a fresh launch.
                try:
                    self.adapter.call("close_and_stop", binding, state["sequence"], {"reason": "CONTROLLER_RESTART"})
                finally:
                    self.closed = True
            require(not interrupted, "PRIOR_RUN_UNCERTAIN")
            self._time()
            initial = {"sequence": 0}
            verified(self._call("inspect_binding", initial, {"binding": self.binding.value}), *READINESS)
            state = self.ledger.create(self.binding)
            try:
                verified(self._call("claim_writer", state, {"expectedClosedVersion": 0}),
                         "hostWriterFence", "guestMountStartFence", "hostTombstoneCurrent")
            except BaseException:
                self.close("CLAIM_UNCERTAIN")
                raise

    def launch(self) -> None:
        with self.lock:
            state = self.ledger.read(self.binding)
            require(state["phase"] == "PREPARED" and not state["launchConsumed"], "LAUNCH_SPENT")
            self._time()
            # Independent watchdog already armed; host arm_once persists its own
            # anti-rollback tombstone and interposes before every start and mount.
            state = self.ledger.change(self.binding, state, launchConsumed=True)
            self.launching = True
            try:
                verified(self._call("arm_once", state, {"t0Ns": self.binding.value["t0Ns"],
                                                        "stopNs": self.binding.value["t0Ns"] + STOP_NS,
                                                        "deadlineNs": self.binding.value["t0Ns"] + END_NS}),
                         "launchConsumed", "networkBeforeExec", "watchdogArmed", "hostTombstoneCurrent")
                self._time()
                self.ledger.change(self.binding, state, phase="RUNNING_UNUSED")
                self.closed = False
                self.timer = threading.Thread(target=self._watch, name="mealie-run-supervisor", daemon=True)
                self.timer.start()
            except BaseException:
                self.close("LAUNCH_UNCERTAIN")
                raise
            finally:
                self.launching = False

    def _watch(self) -> None:
        # This polling loop is supplementary to the independent host watchdog.
        # OS scheduling and a dead controller cannot promise timely enforcement.
        while not self.stop_event.wait(0.05):
            try:
                self.tick()
            except BaseException:
                self.close("CONTROL_LOSS")

    def tick(self) -> None:
        with self.lock:
            now = self._time(before_stop=False)
            state = self.ledger.read(self.binding)
            value = self.binding.value
            if state["phase"] in TERMINAL:
                self.stop_event.set()
                return
            if now >= value["t0Ns"] + STOP_NS:
                self.close("DEADLINE")
                return
            verified(self._call("read_run_state", state), *LIVE)

    def _live(self) -> dict:
        require(not self.closed, "RUN_CLOSED")
        self._time()
        state = self.ledger.read(self.binding)
        require(state["phase"] in ("RUNNING_UNUSED", "SPENT"), "RUN_CLOSED")
        verified(self._call("read_run_state", state), *LIVE)
        return state

    def _envelope(self, handle: str, state: dict) -> dict:
        opaque(handle)
        receipt = self._call("capture_request", state, {"handle": handle})
        verified(receipt, "authenticated", "sameGroup", "parserAgreement", "bodyFullyBuffered", "edgeLimitsEnforced")
        request = receipt.get("request")
        exact_keys(request, {"method", "target", "authority", "headers", "body", "actor", "principalId", "groupId"})
        value = self.binding.value
        require(request["authority"] == value["authority"] and request["groupId"] == value["groupId"], "IDENTITY_MISMATCH")
        require(request["actor"] in ("runner", "observer", "probe"), "ACTOR_DENIED")
        if request["actor"] != "probe":
            require(request["principalId"] == value[request["actor"] + "Id"], "IDENTITY_MISMATCH")
        else:
            verified(receipt, "boundProbe")
        canonical_target(request["target"])
        require(isinstance(request["headers"], list) and len(request["headers"]) <= 64, "INVALID_HEADERS")
        headers = {}
        for pair in request["headers"]:
            require(isinstance(pair, list) and len(pair) == 2 and all(isinstance(x, str) for x in pair), "INVALID_HEADERS")
            name, val = pair
            require(name == name.lower() and name not in headers and len(val) <= 8192, "AMBIGUOUS_HEADERS")
            require(bool(re.fullmatch(r"[!#$%&'*+.^_`|~0-9a-z-]+", name)), "INVALID_HEADERS")
            require(all(32 <= ord(c) < 127 for c in name + val), "INVALID_HEADERS")
            require(not name.startswith(("x-forwarded-", "x-http-method", "x-method-"))
                    and name not in ("forwarded", "transfer-encoding", "content-encoding", "upgrade", "proxy-authorization"),
                    "AMBIGUOUS_HEADERS")
            headers[name] = val
        require(headers.get("connection", "close") in ("close", "keep-alive"), "AMBIGUOUS_HEADERS")
        require(headers.get("host") == value["authority"], "INVALID_AUTHORITY")
        body = unbase64(request["body"])
        require(headers.get("content-length", "0") == str(len(body)), "AMBIGUOUS_LENGTH")
        request["rawBody"] = body
        request["headerMap"] = headers
        return request

    def _route(self, request: dict, state: dict) -> tuple[str, int, str | None]:
        method, target, actor = request["method"], request["target"], request["actor"]
        value = self.binding.value
        if actor == "runner" and method == "POST" and target == "/api/recipes/create/url":
            require(request["headerMap"].get("content-type") == "application/json", "CONTENT_TYPE")
            body = decode(request["rawBody"])
            require(body == BODY and type(body.get("includeTags")) is bool
                    and type(body.get("includeCategories")) is bool, "BODY_MISMATCH")
            require(digest(request["rawBody"]) == value["requestBodyDigest"], "BODY_SERIALIZATION")
            require(state["phase"] == "RUNNING_UNUSED" and not state["importSpent"], "IMPORT_SPENT")
            return "intake", BODY_LIMIT, None
        require(method in ("GET", "HEAD") and not request["rawBody"], "ROUTE_DENIED")
        if actor == "runner":
            require(method == "GET" and state["slug"] is not None and not state["readSpent"]
                    and target == "/api/recipes/" + state["slug"], "READ_DENIED")
            return "result", BODY_LIMIT, None
        require(actor in ("observer", "probe"), "ROUTE_DENIED")
        for route in value["uiManifest"]["routes"]:
            if "{returnedSlug}" in route["target"] and state["slug"] is None:
                continue
            expected = route["target"].replace("{groupSlug}", value["groupSlug"]).replace("{returnedSlug}", state["slug"] or "")
            if (actor, method, target) == (route["actor"], route["method"], expected):
                return "general", route["maxBytes"], route["assetDigest"]
        raise Denied("ROUTE_DENIED")

    def _take_bucket(self, kind: str) -> str:
        key = "intake" if kind == "intake" else "general"
        bucket = self.buckets[key]
        now = self._time()
        cap, rate, concurrency = (1, 0.1, 1) if key == "intake" else (10, 1.0, 4)
        bucket[0] = min(cap, bucket[0] + (now - bucket[1]) / 1e9 * rate)
        bucket[1] = now
        require(bucket[0] >= 1 and bucket[2] < concurrency, "HTTP_LIMIT")
        bucket[0] -= 1
        bucket[2] += 1
        return key

    def handle(self, handle: str) -> dict:
        """Consume a request captured by the authenticated ingress broker.

        Only the broker can resolve the handle to native credentials/HTTP bytes.
        Raw responses never enter task logs. The returned object is metadata.
        """
        bucket = None
        attempted = False
        try:
            with self.lock:
                state = self._live()
                request = self._envelope(handle, state)
                kind, response_limit, asset_digest = self._route(request, state)
                bucket = self._take_bucket(kind)
                attempt = uuid.uuid4().hex
                if kind == "intake":
                    state = self.ledger.change(self.binding, state, phase="SPENT", importSpent=True, attempt=attempt)
                elif kind == "result":
                    state = self.ledger.change(self.binding, state, readSpent=True)
                # The durable commit above must complete before the broker sees
                # the revocable, one-use forward capability. There is no retry.
                self._time()
                forward = {"handle": handle, "attempt": attempt, "kind": kind,
                           "requestDigest": digest(encode({k: v for k, v in request.items()
                                                          if k not in ("rawBody", "headerMap")})),
                           "responseLimit": response_limit}
                remaining = (self.binding.value["t0Ns"] + STOP_NS - boottime_ns()) / 1e9
                require(remaining > 0, "DEADLINE_CLOSED")
                attempted = True
            response = self._call("forward_once", state, forward, timeout=min(remaining, 60))
            verified(response, "sameGeneration", "capabilityConsumed", "requestMatched", "targetMatched")
            with self.lock:
                current = self._live()
                result = response.get("response")
                exact_keys(result, {"status", "body", "groupId", "principalId", "contentType"})
                raw = unbase64(result["body"])
                require(len(raw) <= response_limit, "RESPONSE_LIMIT")
                require(result["groupId"] == self.binding.value["groupId"], "RESULT_GROUP")
                require(result["status"] == (201 if kind == "intake" else 200), "HTTP_UNCERTAIN")
                if kind == "intake":
                    require(result["contentType"] == "application/json", "RESULT_TYPE")
                    slug = decode(raw)
                    require(isinstance(slug, str) and 0 < len(slug) <= 250 and bool(SLUG.fullmatch(slug)), "RESULT_SLUG")
                    require(current["attempt"] == attempt and current["slug"] is None, "RESULT_BINDING")
                    current = self.ledger.change(self.binding, current, slug=slug)
                elif request["target"] == "/api/recipes/" + (current["slug"] or ""):
                    recipe = decode(raw)
                    require(isinstance(recipe, dict) and recipe.get("slug") == current["slug"]
                            and recipe.get("groupId") == self.binding.value["groupId"], "RESULT_BINDING")
                if asset_digest is not None and request["method"] == "GET":
                    require(digest(raw) == asset_digest, "ASSET_MISMATCH")
                if request["target"] == "/api/users/self":
                    user = decode(raw)
                    require(user.get("id") == self.binding.value["observerId"]
                            and user.get("groupId") == self.binding.value["groupId"], "OBSERVER_MISMATCH")
                verified(self._call("release_response", current, {"handle": handle, "attempt": attempt,
                                                                  "responseDigest": digest(raw)}),
                         "sameGeneration", "responseMatched", "releasedOnce")
                return {"outcome": "RELEASED", "kind": kind}
        except BaseException:
            # Invalid request does not earn a retry of an ambiguous forward.
            # Conservatively close the evaluation on any protocol/control error.
            self.close("FORWARD_UNCERTAIN" if attempted else "ADMISSION_DENIED")
            raise
        finally:
            if bucket is not None:
                with self.lock:
                    self.buckets[bucket][2] -= 1

    def close(self, reason: str) -> dict:
        with self.lock:
            self.closed = True
            self.stop_event.set()
            state = None
            try:
                state = self.ledger.read(self.binding)
                if state["phase"] in TERMINAL:
                    return state
                if state["phase"] != "STOPPING":
                    state = self.ledger.change(self.binding, state, phase="STOPPING", reason=reason)
            except BaseException:
                # Durable storage loss cannot prevent independent closure. The
                # broker must close regardless of its last sequence for this op.
                state = {"sequence": 0}
            deadline = self.binding.value["t0Ns"] + END_NS
            try:
                self._call("close_and_stop", state, {"reason": reason, "deadlineNs": deadline,
                                                    "graceNs": max(0, min(5_000_000_000, deadline - boottime_ns()))})
                # Acknowledgement is never quiescence. Escalation is the broker's
                # independent schedule (TERM295, KILL297, bound VM fallback298).
                receipt = self._call("observe_quiescence", state)
                verified(receipt, *QUIESCENCE)
                require(receipt["observedNs"] <= deadline, "DEADLINE_MISSED")
                retained = self._call("describe_retained_set", state)
                verified(retained, "retainedHeld", "coherentStoppedEpoch", "custodyBound")
                phase = "QUIESCENT_RETAINED"
            except BaseException:
                phase = "FAILED_UNCERTAIN_RETAINED"
                if not self.forced:
                    self.forced = True
                    try:
                        self._call("force_fence", state, {"authorityRef": self.binding.value["references"]["fallbackAuthority"],
                                                         "deadlineNs": deadline})
                    except BaseException:
                        pass
            try:
                current = self.ledger.read(self.binding)
                return self.ledger.change(self.binding, current, phase=phase, reason=reason)
            except BaseException:
                return {"phase": "FAILED_UNCERTAIN_RETAINED", "reason": "LEDGER_UNAVAILABLE",
                        "inspectionAllowed": False}

    def status(self) -> dict:
        with self.lock:
            return self.ledger.read(self.binding)
