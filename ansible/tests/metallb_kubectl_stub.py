#!/usr/bin/env python3
"""Stub kubectl for the MetalLB speaker-replacement tests (OCE-369 Stage B1).

Serves canned JSON from the state file named by $METALLB_STUB_STATE and appends
every call to $STUB_LOG. `delete pod` removes the pod, logs the deletion and
creates the replacement, so the loop's checks see a cluster that changes as it
is driven. Nothing here talks to a cluster.

State keys (see metallb_harness.default_state):
  nodes, pods[{name,uid,node,hash,qos,ready}], services[{namespace,name,type,ip}],
  controller_revisions[{revision,hash}], new_hash, new_qos,
  fail_n_after_deletions (None, or N fails once that many pods are deleted),
  ready_after_polls (a replacement is not Ready for this many pod listings),
  deletions[], pending[], seq
"""
import json
import os
import sys

DS = "metallb-speaker"
NS = "metallb-system"


def load(path):
    with open(path) as fh:
        return json.load(fh)


def save(path, state):
    with open(path, "w") as fh:
        json.dump(state, fh)


def pod_json(p, state):
    ready = p.get("ready", True)
    return {
        "metadata": {
            "name": p["name"], "namespace": NS, "uid": p["uid"],
            "labels": {"app.kubernetes.io/component": "speaker", "controller-revision-hash": p["hash"]},
        },
        "spec": {
            "nodeName": p["node"],
            "initContainers": [
                {"name": n, "resources": {"requests": {"cpu": "10m", "memory": "64Mi"},
                                          "limits": {"cpu": "10m", "memory": "64Mi"}}}
                for n in ("cp-frr-files", "cp-reloader", "cp-metrics")
            ],
            "containers": [{"name": "speaker", "resources": {}}],
        },
        "status": {
            "qosClass": p["qos"],
            "conditions": [{"type": "Ready", "status": "True" if ready else "False"}],
        },
    }


def ready_speaker_nodes(state):
    return {p["node"] for p in state["pods"] if p.get("ready", True)}


def l2_statuses(state):
    ok_nodes = sorted(ready_speaker_nodes(state))
    out = []
    lbs = [s for s in state["services"] if s["type"] == "LoadBalancer"]
    limit = state.get("fail_n_after_deletions")
    for i, s in enumerate(lbs):
        if limit is not None and len(state["deletions"]) >= limit and i == 0:
            continue  # the announcement for the first Service is gone
        out.append({"metadata": {"name": f"l2-{s['name']}"},
                    "status": {"node": ok_nodes[i % len(ok_nodes)] if ok_nodes else "none",
                               "serviceName": s["name"], "serviceNamespace": s["namespace"]}})
    return out


def main(argv):
    path = os.environ["METALLB_STUB_STATE"]
    with open(os.environ["STUB_LOG"], "a") as log:
        log.write("kubectl " + " ".join(argv) + "\n")
    state = load(path)
    if "get" in argv:
        res = argv[argv.index("get") + 1]
    elif "delete" in argv:
        res = "delete"
    else:
        return 0

    if res == "delete":
        name = argv[argv.index("pod") + 1]
        old = next(p for p in state["pods"] if p["name"] == name)
        state["pods"].remove(old)
        state["deletions"].append(name)
        state["seq"] += 1
        state["pending"].append({
            "name": f"{DS}-new{state['seq']}", "uid": f"uid-new{state['seq']}", "node": old["node"],
            "hash": state["new_hash"], "qos": state["new_qos"], "ready": False,
            "polls_left": state["ready_after_polls"]})
        state["pods"].append(state["pending"].pop())
        save(path, state)
        print(f'pod "{name}" deleted')
        return 0

    if res.startswith("daemonset") or res == "ds":
        pods = state["pods"]
        n = len(pods)
        doc = {"metadata": {"name": DS},
               "status": {"desiredNumberScheduled": n,
                          "updatedNumberScheduled": sum(p["hash"] == state["new_hash"] for p in pods),
                          "numberReady": sum(p.get("ready", True) for p in pods)}}
    elif res.startswith("controllerrevisions"):
        doc = {"items": [{"metadata": {"name": f"{DS}-{r['hash']}",
                                       "ownerReferences": [{"kind": "DaemonSet", "name": DS}]},
                          "revision": r["revision"]} for r in state["controller_revisions"]]
               + [{"metadata": {"name": "other-ds-zzz", "ownerReferences": [{"kind": "DaemonSet", "name": "other"}]},
                   "revision": 99}]}
    elif res.startswith("pods"):
        for p in state["pods"]:
            if not p.get("ready", True):
                if p.get("polls_left", 0) > 0:
                    p["polls_left"] -= 1
                else:
                    p["ready"] = True
        save(path, state)
        doc = {"items": [pod_json(p, state) for p in state["pods"]]}
    elif res.startswith("services"):
        doc = {"items": [
            {"metadata": {"name": s["name"], "namespace": s["namespace"]},
             "spec": {"type": s["type"]},
             "status": {"loadBalancer": {"ingress": [{"ip": s["ip"]}] if s.get("ip") else []}}}
            for s in state["services"]]}
    elif res.startswith("servicel2statuses"):
        doc = {"items": l2_statuses(state)}
    else:
        return 0  # anything else is a no-op, like the apply-flag tests' own stub
    print(json.dumps(doc))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
