![wiki-banner.svg](images/wiki-banner.svg)
![accent-divider](images/accent-divider.svg)

# Hermes Agents (Pro)

Per-user AI agents running on the cluster, reachable over messaging
platforms (Signal first, Telegram / Discord planned). Each family
member gets their own isolated agent: own pod, own PVC, own credentials,
own session memory, own Anthropic billing.

The shared `signal-cli-rest-api` instance handles the Signal transport;
N `hermes-<user>` deployments fan out behind it.

![accent-divider](images/accent-divider.svg)

## Architecture

```
namespace: signal-api          namespace: hermes-jason         namespace: hermes-<user>
┌──────────────────────┐       ┌──────────────────────┐        ┌──────────────────────┐
│ signal-cli-rest-api  │◄──────┤ hermes (gateway)     │   ...  │ hermes (gateway)     │
│ json-rpc mode        │  HTTP │ docker.io/nous/      │        │ same image, own PVC  │
│ multi-account        │  8080 │   hermes-agent:vYYYY │        │                      │
│ PVC 5Gi RBD          │       │ PVC 50Gi RBD         │        │ PVC 50Gi RBD         │
│ ClusterIP :8080      │       │ Dashboard :9119      │        │ Dashboard :9119      │
│ NO ingress           │       │ IngressRoute         │        │ IngressRoute         │
│                      │       │ jason.seadogger-     │        │ <user>.seadogger-    │
│                      │       │   homelab            │        │   homelab            │
└──────────────────────┘       └──────────────────────┘        └──────────────────────┘
```

- **One** `signal-api` pod, multi-account capable. Serves every `hermes-<user>` over in-cluster DNS.
- **N** `hermes-<user>` pods, one per family member, fully isolated state.
- All storage on `ceph-block-data` (3× replicated RBD).
- Dashboards exposed via Traefik IngressRoute with cert-manager TLS from `internal-local-issuer`.

![accent-divider](images/accent-divider.svg)

## Repository Layout

```
deployments/signal-api/             # shared, single deployment
  argocd-application.yaml
  deployment.yaml                   # bbernhard/signal-cli-rest-api:0.99
  service.yaml                      # ClusterIP only
  pvc.yaml                          # 5Gi
  kustomization.yaml

deployments/hermes/
  base/                             # kustomize template - never deployed alone
    deployment.yaml                 # image pinned to a Hermes release tag
    service.yaml
    pvc.yaml                        # 50Gi
    ingressroutes.yml               # host patched by overlay
    certificate.yml
    kustomization.yaml
  overlays/
    jason/                          # one overlay per user
      kustomization.yaml            # patches namespace + hostname + cert dnsNames
      argocd-application.yaml

ansible/tasks/
  signal_api_deploy.yml             # namespace + ArgoCD app for shared signal-api
  hermes_deploy.yml                 # loops hermes_users -> ns + ArgoCD app per user
```

![accent-divider](images/accent-divider.svg)

## Secrets Model — Important

**Personal credentials never enter Git, ansible, or a Kubernetes Secret.**

This is the deliberate split from the Bedrock / Velero / Argo-repo pattern,
where operator-owned infrastructure secrets are provisioned via ansible vars
in `config.yml`. Hermes' credentials are **user-owned**:

- `ANTHROPIC_API_KEY` — billed to the user
- `SIGNAL_ACCOUNT` — the user's Signal phone number
- Gateway tokens (Telegram bot, Discord bot, etc.) — owned by the user
- Skill OAuth tokens (Google, GitHub, Spotify, …) — written by skill setup flows
- Peer cards, memory entries, session DB — personal conversation state

Storing those in `config.yml` would force every family member to share
them with the operator. Storing them in a k8s Secret would mean anyone
with `kubectl get secret` access to the cluster could read all of them.

Instead: Hermes' canonical config store is `~/.hermes/.env`, which inside
the pod is `/opt/data/.env` — a file on the 50Gi RBD PVC. The user edits
it directly inside the pod. The file survives pod restarts, node moves,
and image upgrades. It is never replicated to any other namespace.

### Provisioning a new agent (per user)

After `ansible-playbook ansible/main.yml --tags signal_api,hermes`
has created the pod:

```bash
# 1. Shell into the user's pod
kubectl -n hermes-<user> exec -it deploy/hermes -- /bin/bash

# 2. Run the interactive setup wizard
hermes gateway setup
#    - paste ANTHROPIC_API_KEY
#    - configure Signal: SIGNAL_HTTP_URL=http://signal-api.signal-api.svc.cluster.local:8080
#    - configure Signal: SIGNAL_ACCOUNT=<your E.164 number>
#    - configure SIGNAL_ALLOWED_USERS=<your E.164 number>
#    - configure SIGNAL_HOME_CHANNEL=<your E.164 number>
#    - (optional) Telegram, Discord, etc.
exit

# 3. Restart so the gateway picks up the new env
kubectl -n hermes-<user> rollout restart deploy/hermes

# 4. Tail the logs and confirm the platform connected
kubectl -n hermes-<user> logs deploy/hermes -f
```

The wizard writes `/opt/data/.env` on the PVC. No other party sees these
values — not the operator, not ansible, not ArgoCD, not Git, not the model.

### Rotating a credential

Same workflow: exec in, edit `/opt/data/.env`, `rollout restart deploy/hermes`.

![accent-divider](images/accent-divider.svg)

## Signal — Daemon Choice

There are two HTTP-daemon shapes for signal-cli:

| | bbernhard signal-cli-rest-api | AsamK native signal-cli daemon |
|---|---|---|
| Endpoint prefix | `/v1/*` | `/api/v1/*` |
| Transport       | REST polling             | SSE push + JSON-RPC |
| Hermes env      | not natively supported    | `SIGNAL_HTTP_URL`, `SIGNAL_ACCOUNT` |
| Multi-account   | yes (json-rpc mode)       | yes |
| Image published | yes (Docker Hub, multi-arch) | no canonical image |

Hermes' built-in Signal adapter targets AsamK's daemon shape. The current
`deployments/signal-api/` ships the bbernhard image because it's
multi-arch, well-published, and already what most signal-cli-on-k8s
guides use. **Path forward**: either ship an AsamK-based image to GHCR
under `seadogger-tech/`, or write a small Hermes adapter for bbernhard.
The repo currently expects you to bring your own daemon if you want
Hermes to actually deliver Signal messages — see the open issue in the
project board.

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

# 5. Provision the user's credentials (see "Secrets Model" above)
kubectl -n hermes-kim exec -it deploy/hermes -- /bin/bash
hermes gateway setup
exit
kubectl -n hermes-kim rollout restart deploy/hermes
```

![accent-divider](images/accent-divider.svg)

## Upgrading the Hermes Image

Hermes ships semver release tags (e.g. `v2026.6.5`). Per AGENTS.md policy,
the image is **always pinned to a release tag, never `:latest`**.

```bash
# 1. Edit deployments/hermes/base/deployment.yaml
#    image: docker.io/nousresearch/hermes-agent:vYYYY.M.D

# 2. Commit & push - ArgoCD picks it up and rolls every hermes-<user> pod
cd /Users/jason/Desktop/Development/seadogger-homelab-pro
git add deployments/hermes/base/deployment.yaml
git commit -m "chore(pro): bump hermes-agent to vYYYY.M.D"
git push
```

ArgoCD's automated sync pulls the new manifest, every `hermes-<user>`
Application reconciles, pods rolling-restart, PVC data preserved.

![accent-divider](images/accent-divider.svg)

## Troubleshooting

### Pod is `CrashLoopBackOff` with "Goodbye!" in logs
You probably removed `args: ["gateway"]` from `base/deployment.yaml`.
Without it the container runs the interactive CLI which exits without
a TTY. Re-add it.

### Pod is `ImagePullBackOff` with 401 from ghcr.io
You switched the image back to `ghcr.io/nousresearch/...`. The GHCR
mirror exists but isn't anonymous-pullable. Use
`docker.io/nousresearch/hermes-agent:<tag>` instead.

### `signal-api` pod crashing with "AUTO_RECEIVE_SCHEDULE can't be used with mode json-rpc"
Don't set `AUTO_RECEIVE_SCHEDULE` at all in the deployment env — even an
empty string trips the guard.

### Hermes warns "No messaging platforms enabled"
`/opt/data/.env` is empty or missing. Exec in and run `hermes gateway setup`.

### Hermes talks to signal-api but messages don't flow
The HTTP daemon shape mismatch. See "Signal - Daemon Choice" above.

![accent-divider](images/accent-divider.svg)

## ArgoCD Apps Created

| Application      | Source path                                   | Namespace      |
|------------------|-----------------------------------------------|----------------|
| `signal-api`     | `deployments/signal-api`                      | `signal-api`   |
| `hermes-jason`   | `deployments/hermes/overlays/jason`           | `hermes-jason` |
| `hermes-<user>`  | `deployments/hermes/overlays/<user>`          | `hermes-<user>`|

All sync automatically with prune + selfHeal.
