![wiki-banner.svg](images/wiki-banner.svg)
![accent-divider](images/accent-divider.svg)
# Runbooks

This page provides step-by-step operational procedures for common tasks.

![accent-divider](images/accent-divider.svg)
## Cold Start Cycle
1) Stage 1 — Wipe (destructive):
- Set in `ansible/config.yml`: `cold_start_stage_1_wipe_cluster: true` and optionally `perform_physical_disk_wipe: true`.
- Run: `ansible-playbook cleanup.yml`.

2) Stage 2 — Install Infrastructure:
- Set: `cold_start_stage_2_install_infrastructure: true`.
- Run: `ansible-playbook main.yml`.

3) Stage 3 — Deploy Applications:
- Set: `cold_start_stage_3_install_applications: true` and enable per-app `manual_install_*` flags.
- Run: `ansible-playbook main.yml`.

![accent-divider](images/accent-divider.svg)
## Reset an Application (keep or delete data)
1) In `ansible/config.yml` set `run_pod_cleanup: true`.
2) In `pod_cleanup_list`, keep only the target app and choose `delete_pvc: true|false`.
3) Run: `ansible-playbook cleanup.yml`.
4) Redeploy via Stage 3 if desired.

![accent-divider](images/accent-divider.svg)
## Rotate Internal CA
1) Create a new Intermediate CA signed by the offline Root CA.
2) Update cert-manager `ClusterIssuer` to reference the new Intermediate.
3) Trigger re-issuance of app certificates.
4) Distribute (or ensure trust of) the Root CA on client devices.

![accent-divider](images/accent-divider.svg)
## Add/Replace a Node
1) Image OS, set static DHCP reservation, ensure SSH.
2) Join as worker with k3s token; verify with `kubectl get nodes`.
3) Label/taint as needed and confirm workloads schedule as expected.

![accent-divider](images/accent-divider.svg)
## Upgrade k3s
1) Drain control plane node; upgrade; uncordon.
2) Sequentially drain/upgrade worker nodes; uncordon each.
3) Verify node readiness and workload recovery.

![accent-divider](images/accent-divider.svg)
## Observability Quick-Checks
- Prefer accessing UIs via Ingress + TLS at Traefik VIP.
- Verify Prometheus, Grafana, Alertmanager UIs load and show healthy targets.
- Check node-exporter and kube-state-metrics.

![accent-divider](images/accent-divider.svg)
## Secrets & Credentials
- Do not commit real credentials. Use Ansible Vault for secrets and GitHub Actions secrets for CI.
- If secrets were previously committed, rotate immediately and remove from repo history if necessary.

![accent-divider](images/accent-divider.svg)
## Edit a Home Assistant Dashboard via Code
Don't hand-edit `/config/.storage/lovelace.dashboard_<name>` directly — HA
owns that file and can overwrite an edit made while it's live. Use
`deployments/home-assistant/ha_dashboard_edit.py` (alongside the HA
deployment manifests it operates on), which calls the same
`lovelace/config` / `lovelace/config/save` WebSocket API the frontend
itself uses:
1) Create a Long-Lived Access Token: HA profile (bottom-left) → Security → Long-Lived Access Tokens.
2) Find the dashboard's real `url_path` (not necessarily its title): `kubectl exec -n home-assistant home-assistant-0 -c home-assistant -- cat /config/.storage/lovelace_dashboards`.
3) Edit `NEW_CARDS` in the script for whatever card(s) you're adding.
4) `kubectl cp deployments/home-assistant/ha_dashboard_edit.py home-assistant/home-assistant-0:/tmp/ha_dashboard_edit.py -c home-assistant`
5) `kubectl exec -n home-assistant home-assistant-0 -c home-assistant -- env HA_TOKEN="<token>" HA_DASHBOARD_URL_PATH="<url_path>" python3 /tmp/ha_dashboard_edit.py`
6) Revoke the token from the same Security screen once done, if it was only needed for this edit.

![accent-divider](images/accent-divider.svg)
## Importing a Claude.ai Export into Basic Memory
Claude.ai exports (Settings → Account → Export Data) unzip into
`conversations.json`, a `projects/` directory (or `projects.json`),
`design_chats/`, `memories.json`, and `users.json`. Basic Memory
(see [09-Apps#basic-memory](09-Apps#basic-memory-website-httpsdocsbasicmemorycom))
has built-in importers for some of these; the rest need manual handling.
The pod has no network access to your Mac, so files go in via `kubectl cp`.

1) Copy the export file(s) into the running pod:
   `kubectl cp <local-file> basic-memory/<pod>:/tmp/<file> -c basic-memory`

2) **Conversations** — built-in importer, works as-is:
   `kubectl exec -n basic-memory <pod> -c basic-memory -- basic-memory import claude conversations /tmp/conversations.json --folder claude-conversations`

3) **Projects** — the importer expects one combined `projects.json`
   array, but a real export gives a `projects/` directory of individual
   `<uuid>.json` files. Combine them first:
   `python3 -c "import json, glob; json.dump([json.load(open(f)) for f in sorted(glob.glob('projects/*.json'))], open('projects_combined.json','w'))"`,
   then `kubectl cp` the combined file in and run
   `basic-memory import claude projects /tmp/projects.json --base-folder claude-projects`.
   **Known gap:** this importer only pulls a project's attached `docs`
   and `prompt_template` — it silently writes nothing for the project's
   own `description` or for Claude's separate `memories.json →
   project_memories` summary, even when those have real content. Write
   those by hand (step 5) if you want them kept.

4) **`design_chats/`** (Projects-scoped chat exports) — schema doesn't
   match `conversations.json`: messages use `role`/`content` (a dict
   with embedded attachments) instead of `sender`/`text`. Forcing this
   through the conversations importer silently mis-parses or drops
   content. Read the file directly and hand-format a note (step 5)
   instead of trusting the importer with it.

5) **Anything the importers don't cover** (project descriptions,
   `memories.json`'s profile summary, `design_chats/`): write it
   directly with the CLI, piping content via stdin so markdown
   with quotes/newlines doesn't need shell-escaping:
   `cat note.md | kubectl exec -i -n basic-memory <pod> -c basic-memory -- basic-memory tool write-note --title "..." --folder "..." --tags "imported-from-claude"`

6) Reindex so the new content is searchable:
   `kubectl exec -n basic-memory <pod> -c basic-memory -- basic-memory reindex --search`

7) Clean up the copied export file from the pod's ephemeral storage —
   it's never written to the persistent vault, but there's no reason to
   leave tens of MB of conversation history sitting in `/tmp`:
   `kubectl exec -n basic-memory <pod> -c basic-memory -- rm -f /tmp/conversations.json`

`users.json` (just your account record) has no knowledge content — skip it.

