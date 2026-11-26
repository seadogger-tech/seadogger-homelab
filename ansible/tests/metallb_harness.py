"""Shared fixtures for the MetalLB speaker-replacement tests (OCE-369 Stage B1).

A stub `kubectl` (metallb_kubectl_stub.py) serves canned JSON from a state file and
logs every call; a local HTTP server stands in for Traefik's LoadBalancer IP.
"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

STUB = Path(__file__).with_name("metallb_kubectl_stub.py")
NODES = ["n1", "n2", "n3", "n4"]
OLD, NEW = "6b8d5c9f4", "7c5f8b6d9"


class _Ok(BaseHTTPRequestHandler):
    def do_GET(self):  # any status counts; 404 proves the answer is not a 200 requirement
        self.send_response(404)
        self.end_headers()

    def log_message(self, *args):
        pass


def start_http():
    server = HTTPServer(("127.0.0.1", 0), _Ok)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def default_state(stale_nodes=("n1", "n2", "n3", "n4"), new_qos="Guaranteed"):
    """Four speakers; pod names sort differently from node names on purpose."""
    names = {"n1": "metallb-speaker-zz1", "n2": "metallb-speaker-yy2",
             "n3": "metallb-speaker-xx3", "n4": "metallb-speaker-ww4"}
    pods = [{"name": names[n], "uid": f"uid-{n}", "node": n, "hash": OLD if n in stale_nodes else NEW,
             "qos": "Burstable", "ready": True} for n in NODES]
    return {
        "nodes": NODES, "pods": pods, "pending": [], "deletions": [], "seq": 0,
        "services": [
            {"namespace": "kube-system", "name": "traefik", "type": "LoadBalancer", "ip": "127.0.0.1"},
            {"namespace": "pihole", "name": "pihole-dns", "type": "LoadBalancer", "ip": "127.0.0.2"},
            {"namespace": "default", "name": "plain", "type": "ClusterIP", "ip": ""},
        ],
        # listed out of order: the target is the highest revision, not the last listed
        "controller_revisions": [{"revision": 2, "hash": NEW}, {"revision": 1, "hash": OLD}],
        "new_hash": NEW, "new_qos": new_qos,
        "fail_n_after_deletions": None, "ready_after_polls": 0,
    }


def write_state(path, state):
    Path(path).write_text(json.dumps(state))


def read_state(path):
    return json.loads(Path(path).read_text())


def install_stub(bindir):
    """Put a `kubectl` on PATH that runs the python stub."""
    target = Path(bindir) / "kubectl"
    target.write_text(f'#!/bin/sh\nexec {sys.executable} {STUB} "$@"\n')
    target.chmod(0o755)
