#!/usr/bin/env python3
"""
Home Assistant Lovelace dashboard editor — via the real WebSocket API.

WHAT THIS IS
------------
A safe way to add/modify cards on a HA dashboard without hand-editing the
live /config/.storage/lovelace.dashboard_<name> file. That file is owned by
HA's own storage manager and can be read/written at any time (autosave,
UI edits), so direct file edits risk a race: HA silently overwriting the
change, or catching the file mid-write. This script instead calls the same
`lovelace/config` (read) and `lovelace/config/save` (write) WebSocket
commands the frontend itself uses, so it's exactly as safe as an ordinary
UI edit.

HOW TO RUN IT
-------------
This must run *inside* the home-assistant pod (it connects to
localhost:8123, HA's actual listen port — NOT the Service's port 8080,
which only exists for the k8s Service/Ingress and doesn't accept
connections from inside the pod itself):

    kubectl cp ha_dashboard_edit.py home-assistant/home-assistant-0:/tmp/ha_dashboard_edit.py -c home-assistant
    kubectl exec -n home-assistant home-assistant-0 -c home-assistant -- \\
      env HA_TOKEN="<long-lived-access-token>" \\
          HA_DASHBOARD_URL_PATH="dashboard-family" \\
          python3 /tmp/ha_dashboard_edit.py

Requires a Long-Lived Access Token (Settings -> profile -> Security ->
Long-Lived Access Tokens in the HA UI), passed via the HA_TOKEN
environment variable — never hardcode it in this file or commit it
anywhere. It's a real credential; the user may want it revoked from
that same screen once done with it.

FINDING THE RIGHT DASHBOARD URL PATH
-------------------------------------
The url_path is NOT necessarily the dashboard's title. Check the real
value first:

    kubectl exec -n home-assistant home-assistant-0 -c home-assistant -- \\
      cat /config/.storage/lovelace_dashboards

Look for the "url_path" field of the dashboard you want (e.g. a dashboard
titled "Family" had url_path "dashboard-family", not "family").

WHAT CARDS ARE VALID
---------------------
Any card type HA/HACS supports — built-in (`weather-forecast`, `calendar`,
`entities`, etc.) or custom (`custom:mushroom-climate-card`,
`custom:daylight-calendar-card`, `custom:weather-radar-card`, etc.), as
long as the underlying integration/HACS card is already installed. This
script doesn't install anything — it only edits dashboard *config*. Edit
NEW_CARDS below for whatever you're adding; leave it empty to just print
the current config without changing anything.

VERIFYING THE RESULT
---------------------
    kubectl exec -n home-assistant home-assistant-0 -c home-assistant -- \\
      cat /config/.storage/lovelace.dashboard_<name>

(the storage filename is lovelace.dashboard_<id>, where <id> is the "id"
field from lovelace_dashboards, e.g. "dashboard_family" -> file
"lovelace.dashboard_family")
"""

import asyncio
import json
import os
import sys

import websockets

TOKEN = os.environ.get("HA_TOKEN")
URL = os.environ.get("HA_WEBSOCKET_URL", "ws://localhost:8123/api/websocket")
DASHBOARD_URL_PATH = os.environ.get("HA_DASHBOARD_URL_PATH", "")

# Cards to append to the dashboard's first view. Edit this list for
# whatever cards you're adding next; leave empty ([]) to just print the
# current config without changing anything.
NEW_CARDS = []


async def main():
    if not TOKEN:
        sys.exit("HA_TOKEN environment variable is required (see module docstring)")
    if not DASHBOARD_URL_PATH:
        sys.exit("HA_DASHBOARD_URL_PATH environment variable is required (see module docstring)")

    async with websockets.connect(URL) as ws:
        msg = json.loads(await ws.recv())
        assert msg["type"] == "auth_required", msg
        await ws.send(json.dumps({"type": "auth", "access_token": TOKEN}))
        msg = json.loads(await ws.recv())
        assert msg["type"] == "auth_ok", msg
        print("authenticated")

        msg_id = 1

        async def call(payload):
            nonlocal msg_id
            payload["id"] = msg_id
            msg_id += 1
            await ws.send(json.dumps(payload))
            while True:
                resp = json.loads(await ws.recv())
                if resp.get("id") == payload["id"]:
                    return resp

        resp = await call({"type": "lovelace/config", "url_path": DASHBOARD_URL_PATH})
        if not resp["success"]:
            print("FETCH FAILED:", resp)
            return
        config = resp["result"]
        print("current cards:", [c.get("type") for c in config["views"][0]["cards"]])

        if not NEW_CARDS:
            return

        config["views"][0]["cards"].extend(NEW_CARDS)

        resp = await call(
            {"type": "lovelace/config/save", "url_path": DASHBOARD_URL_PATH, "config": config}
        )
        print("save result:", resp["success"], resp.get("error"))


asyncio.run(main())
