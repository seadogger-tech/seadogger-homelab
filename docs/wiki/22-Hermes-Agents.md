![wiki-banner.svg](images/wiki-banner.svg)
![accent-divider](images/accent-divider.svg)

# Hermes Agents (Pro)

Per-user AI agents running on the cluster, reachable over Signal (and
other messengers later). Each family member gets their own isolated
agent: own pod, own PVC, own credentials, own session memory, own
Anthropic billing.

A shared `signal-cli` daemon handles the Signal transport; N
`hermes-<user>` deployments fan out behind it.

![accent-divider](images/accent-divider.svg)

## Architecture

```
namespace: signal-cli            namespace: hermes-jason          namespace: hermes-<user>
┌──────────────────────┐         ┌──────────────────────┐         ┌──────────────────────┐
│ signal-cli daemon    │◄────────┤ hermes (gateway)     │   ...   │ hermes (gateway)     │
│ AsamK upstream       │ JSON-RPC│ docker.io/nous/      │         │ same image, own PVC  │
│ multi-account, --http│  8080   │   hermes-agent:vYYYY │         │                      │
│ PVC 5Gi RBD          │         │ PVC 50Gi RBD         │         │ PVC 50Gi RBD         │
│ ClusterIP :8080      │         │ Dashboard :9119      │         │ Dashboard :9119      │
│ NO ingress           │         │ IngressRoute         │         │ IngressRoute         │
│                      │         │ jason.seadogger-     │         │ <user>.seadogger-    │
│                      │         │   homelab            │         │   homelab            │
└──────────────────────┘         └──────────────────────┘         └──────────────────────┘
```

- **One** `signal-cli` pod, multi-account capable. Serves every `hermes-<user>` over in-cluster DNS.
- **N** `hermes-<user>` pods, one per family member, fully isolated state.
- All storage on `ceph-block-data` (3× replicated RBD).
- Dashboards exposed via Traefik IngressRoute with cert-manager TLS from `internal-local-issuer`.

![accent-divider](images/accent-divider.svg)

## Image Build Pipeline (Bedrock Pattern)

The `signal-cli` image is built from `deployments/signal-cli/Dockerfile`
in the Pro repo by a GitHub Action that mirrors the bedrock-gateway
upstream-tracking workflow:

```
.github/workflows/upstream-rebuild-signal-cli.yaml   - every 6h
.github/upstream_tag_signal_cli                      - last-built tag
deployments/signal-cli/Dockerfile                    - VERSION=<tag>
deployments/signal-cli/deployment.yaml               - image: ghcr.io/seadogger-tech/signal-cli:<tag>
```

Flow:
1. Workflow polls `AsamK/signal-cli` releases every 6 hours
2. If `releases/latest` tag != `.github/upstream_tag_signal_cli`, rebuild
3. `docker buildx` multi-arch (amd64 + arm64) build from the Dockerfile
4. Push to `ghcr.io/seadogger-tech/signal-cli:<version>` + `:latest`
5. Update tag file + bump `image:` line in deployment.yaml
6. Commit + push - ArgoCD sees the manifest change and rolls the pod

Hermes image follows the same "track upstream release" rule but no rebuild
is needed because NousResearch publishes their own multi-arch image to
Docker Hub. We just pin `docker.io/nousresearch/hermes-agent:<release>`
directly and bump deliberately.

![accent-divider](images/accent-divider.svg)

## Repository Layout

```
deployments/signal-cli/             # shared daemon
  Dockerfile                        # AsamK upstream tarball, eclipse-temurin base
  argocd-application.yaml
  deployment.yaml                   # image: ghcr.io/seadogger-tech/signal-cli:<tag>
  service.yaml                      # ClusterIP only
  pvc.yaml                          # 5Gi
  kustomization.yaml

deployments/hermes/
  base/                             # kustomize template - never deployed alone
    deployment.yaml                 # image pinned to a Hermes release tag
    service.yaml
    pvc.yaml                        # 50Gi
    ingressroutes.yml
    certificate.yml
    kustomization.yaml
  overlays/
    jason/                          # one overlay per user
      kustomization.yaml            # patches namespace + hostname + cert dnsNames
      argocd-application.yaml

ansible/tasks/
  signal_cli_deploy.yml             # namespace + ArgoCD app for shared signal-cli
  hermes_deploy.yml                 # loops hermes_users -> ns + ArgoCD app per user

.github/
  upstream_tag_signal_cli           # last-built upstream tag (committed by CI)
  workflows/
    upstream-rebuild-signal-cli.yaml
```

![accent-divider](images/accent-divider.svg)

## Secrets Model - Important

**Personal credentials never enter Git, ansible, or a Kubernetes Secret.**

Deliberate split from the bedrock / velero / argo-repo pattern, where
operator-owned infrastructure secrets are provisioned via ansible vars
in `config.yml`. Hermes' credentials are **user-owned**:

- `ANTHROPIC_API_KEY` - billed to the user
- `SIGNAL_ACCOUNT` - the user's Signal phone number (E.164)
- `SIGNAL_ALLOWED_USERS` - allowlist for inbound messages
- Gateway tokens (Telegram bot, Discord bot, etc.)
- Skill OAuth tokens (Google, GitHub, Spotify, ...)
- Peer cards, memory entries, session DB

Storing these in `config.yml` would force every family member to share
them with the operator. Storing them in a k8s Secret would mean anyone
with `kubectl get secret` to the namespace can read them.

Instead: Hermes' canonical config store is `~/.hermes/.env`, which inside
the pod is `/opt/data/.env` - a file on the 50Gi RBD PVC. The user edits
it directly inside the pod. Survives pod restarts, node moves, and image
upgrades. Never replicated to any other namespace.

### Provisioning a new agent (per user)

After `ansible-playbook ansible/main.yml --tags signal_cli,hermes` has
created the pod:

```bash
# 1. Register the user's number with the shared signal-cli daemon
#    (one-time per Signal account; not per Hermes user)
kubectl -n signal-cli exec -it deploy/signal-cli -- \
    signal-cli --config /data link -n "Hermes <user>"
# Scan the QR code with Signal on your phone (Settings -> Linked Devices)

# 2. Shell into the user's hermes pod and run the wizard
kubectl -n hermes-<user> exec -it deploy/hermes -- /bin/bash
hermes gateway setup
#    - paste ANTHROPIC_API_KEY
#    - SIGNAL_HTTP_URL is already set (env var) - just confirm
#    - SIGNAL_ACCOUNT = your E.164 number
#    - SIGNAL_ALLOWED_USERS = your E.164 number
#    - SIGNAL_HOME_CHANNEL = your E.164 number
exit

# 3. Restart so the gateway picks up the new env
kubectl -n hermes-<user> rollout restart deploy/hermes

# 4. Tail logs and confirm the platform connected
kubectl -n hermes-<user> logs deploy/hermes -f
# Look for: "[Signal] SSE connected" / health checks every ~30s
```

The wizard writes `/opt/data/.env` on the PVC. No other party sees these
values.

![accent-divider](images/accent-divider.svg)

## Adding a New Family Member

```bash
# 1. Add the user to ansible/config.yml hermes_users list
#    (file is .gitignored - edits stay local)
- name: kim

# 2. Create the kustomize overlay
cd /Users/jason/Desktop/Development/seadogger-homelab-pro/deployments/hermes/overlays
cp -r jason kim
sed -i '' 's/jason/kim/g' kim/kustomization.yaml kim/argocd-application.yaml

# 3. Commit & push (Pro repo)
cd /Users/jason/Desktop/Development/seadogger-homelab-pro
git add deployments/hermes/overlays/kim
git commit -m "feat(pro): add hermes-kim overlay"
git push

# 4. Apply
ansible-playbook -i ansible/hosts.ini ansible/main.yml --tags hermes

# 5. Link kim's Signal number to the shared daemon + run her hermes setup
#    (see "Provisioning a new agent" above)
```

![accent-divider](images/accent-divider.svg)

## Upgrading

### signal-cli (automatic, every 6h)

CI checks `AsamK/signal-cli` releases. New tag -> automatic rebuild and
`image:` bump in deployment.yaml. ArgoCD rolls the pod.

To force an immediate check: Actions tab -> "Rebuild from AsamK/signal-cli
on new release" -> "Run workflow".

### hermes (manual)

```bash
# Edit deployments/hermes/base/deployment.yaml
image: docker.io/nousresearch/hermes-agent:vYYYY.M.D

# Commit & push - ArgoCD rolls every hermes-<user> pod
git add deployments/hermes/base/deployment.yaml
git commit -m "chore(pro): bump hermes-agent to vYYYY.M.D"
git push
```

Per AGENTS.md policy the image is **always pinned to a release tag, never
`:latest`**.

![accent-divider](images/accent-divider.svg)

## Multi-Profile Routing (Kanban Orchestrator)

A single `hermes-<user>` pod can host several **profiles**
(`/opt/data/profiles/<name>/`, each with its own `config.yaml`, `.env`,
sessions and skills). One profile acts as the router; the others are
specialist workers. Established 2026-08-03 on `hermes-jason`
(`default` + `homelab-it-engineer` + `gmail-email-assistant`).

### Rule 1 — exactly one profile owns each messaging account

**Profiles must never share a Signal account.** Upstream docs require
unique credentials per platform per profile; newer Hermes hard-refuses
to start the second gateway. Our version instead fought over the account
via `--replace` handoffs roughly every 20s indefinitely — a respawn
storm that silently degraded Signal for every profile involved
(observed for hours before it was diagnosed).

Only the router profile gets `SIGNAL_*` vars in its `.env`. Specialists
have them commented out and correctly log
`No messaging platforms enabled`. Their gateways still run, for cron and
kanban work.

### Rule 2 — one dispatcher, enforced by a lock

`kanban.dispatch_in_gateway: true` embeds the task dispatcher in the
gateway (60s tick). With several profile gateways running, a
machine-global advisory lock at `/opt/data/kanban/.dispatcher.lock`
serialises them — the winner logs `holding singleton dispatcher lock`,
the rest log `this gateway will NOT dispatch`. Concurrent dispatchers
would double reclaim frequency and can corrupt WAL index pages, hence
the backstop.

**The lock is won by whichever gateway starts first**, so keep
`kanban.*` settings consistent across profiles, or the effective
behaviour depends on a startup race.

### Rule 3 — the router needs the `kanban` toolset

This is the non-obvious one. `tools/kanban_tools.py::_check_kanban_mode`
enables kanban tools when **either**:

1. `HERMES_KANBAN_TASK` is set (dispatcher-spawned worker), **or**
2. the profile lists `kanban` in its `toolsets:` config.

A router profile is neither a worker nor a `kanban`-toolset profile by
default, so it gets **zero kanban tools** and cannot open a task. The
symptom is subtle: instead of erroring, the agent just does all the work
itself and never routes. Fix:

```yaml
# /opt/data/config.yaml  (router profile)
toolsets:
  - hermes-cli
  - kanban
```

Because the router has no `HERMES_KANBAN_TASK`, this grants the
**orchestrator** surface (`kanban_create`, `kanban_list`, `kanban_link`,
`kanban_unblock`) rather than the worker lifecycle surface.

> ⚠️ `hermes doctor` prints `kanban (runtime-gated; loaded only for
> dispatcher-spawned workers)` **unconditionally** — `doctor.py` only
> tests the env var and ignores the profile-toolset path. Do not trust
> it here. Verify with:
> ```bash
> /opt/hermes/.venv/bin/python3 -c "import sys; sys.path.insert(0,'/opt/hermes'); \
>   from tools import kanban_tools as kt; print(kt._check_kanban_mode())"
> ```

### Rule 4 — routing is task dispatch, not live chat handoff

Messaging the router does **not** transparently switch you into a
specialist mid-conversation (that is upstream feature request #24913,
unshipped). Work reaches specialists as dispatched kanban tasks and
results return through the router. `kanban_create` also requires an
explicit `assignee`, and `kanban.auto_decompose` only fans out tasks
**already in `triage`** — it never converts an inbound chat message into
a task.

### Working configuration

```yaml
# router profile — /opt/data/config.yaml
toolsets: [hermes-cli, kanban]
kanban:
  dispatch_in_gateway: true
  orchestrator_profile: default   # set explicitly; '' resolves via the
                                  # active profile, which `hermes profile
                                  # use` mutates
  auto_decompose: true
```

Specialists are routed to by **role description**, not name —
`hermes profile describe <name>` text is fed to
`auxiliary.kanban_decomposer` by `_build_roster()`. A profile with no
description is a poor routing target.

### Verified end-to-end flow

```
Signal msg → default → kanban_create(assignee=homelab-it-engineer)
          → dispatcher tick (≤60s) → spawns:
             hermes -p homelab-it-engineer ... chat -q work kanban task t_xxxx
          → task done → result back through default's Signal connection
```

### Known limitation — file attachments

Report files produced by an agent **cannot be delivered over Signal**:
Hermes passes attachments to `signal-cli` by local path, but `signal-cli`
runs in its own pod mounting only `/data` and cannot see `/opt/data`.
Every attachment fails with `AttachmentInvalidException` while the text
reply still arrives, so it fails invisibly. Tracked as
[pro#13](https://github.com/seadogger-tech/seadogger-homelab-pro/issues/13).

### Kanban DB on CephFS

`/opt/data` is CephFS. SQLite WAL on a network filesystem intermittently
surfaces
`kanban.db is not writable: ... kanban.db-wal is read-only for this user`,
which then succeeds on retry — the filesystem is fine (verify with a
plain `touch`). If it becomes frequent, Hermes supports
`database.journal_mode: DELETE` for exactly this case (its config
comment names NFS/SMB/virtiofs).

> Run `hermes kanban *` commands **as the `hermes` user**
> (`su hermes -c '...'`). Running them as root via `kubectl exec` can
> produce spurious not-writable errors.

![accent-divider](images/accent-divider.svg)

## Troubleshooting

### Pod is `CrashLoopBackOff` with "Goodbye!" in logs
Missing `args: ["gateway"]` in `base/deployment.yaml`. Without it the
container runs the interactive CLI which exits without a TTY.

### Pod is `ImagePullBackOff` with 401 from ghcr.io for hermes
The GHCR mirror of hermes-agent isn't anonymous-pullable. Use
`docker.io/nousresearch/hermes-agent:<tag>` instead.

### Hermes warns "No messaging platforms enabled"
`/opt/data/.env` is empty. Exec in and run `hermes gateway setup`.

### Signal: "Unauthorized user: +1XXX (Name) on signal"
Your number isn't in `SIGNAL_ALLOWED_USERS`. Edit `/opt/data/.env`,
restart the pod.

### Signal: nothing logged at all
Daemon isn't reachable. Check from inside the hermes pod:
```bash
kubectl -n hermes-<user> exec -it deploy/hermes -- \
    curl -sf http://signal-cli.signal-cli.svc.cluster.local:8080/api/v1/check
```

### Signal: incoming messages silently dropped, sends work fine
signal-cli `< 0.14.5` hits [AsamK/signal-cli#2059](https://github.com/AsamK/signal-cli/issues/2059)
— Signal changed sealed-sender envelopes ~2026-06-10 and older clients
NPE on **every** inbound message:
```
Exception: getServerGuid(...) must not be null (NullPointerException)
```
Messages never reach Hermes. Fix is a version bump (≥ 0.14.5). Note the
rebuild workflow only pushes the image + updates core's tag tracker — it
deliberately does **not** touch pro's `deployment.yaml`, so bump the
`image:` tag there manually.

### The router agent does the work itself instead of routing
The router profile is missing the `kanban` toolset, so it has no
`kanban_create` tool and no way to open a task. See
[Rule 3](#rule-3--the-router-needs-the-kanban-toolset). `hermes doctor`
is misleading here — verify with `_check_kanban_mode()` directly.

### Two profiles fight over Signal (`--replace` handoff loop)
More than one profile has `SIGNAL_*` in its `.env`. Symptoms:
`Signal account already in use (PID ...)`, alternating
`explicit --replace handoff completed`, and
`Gateway (re)started 6 times in 120s — backing off`. Comment the
`SIGNAL_*` block out of every profile except the router. See
[Rule 1](#rule-1--exactly-one-profile-owns-each-messaging-account).

![accent-divider](images/accent-divider.svg)

## ArgoCD Apps Created

| Application      | Source path                                   | Namespace      |
|------------------|-----------------------------------------------|----------------|
| `signal-cli`     | `deployments/signal-cli`                      | `signal-cli`   |
| `hermes-jason`   | `deployments/hermes/overlays/jason`           | `hermes-jason` |
| `hermes-<user>`  | `deployments/hermes/overlays/<user>`          | `hermes-<user>`|

All sync automatically with prune + selfHeal.
