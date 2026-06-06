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

![accent-divider](images/accent-divider.svg)

## ArgoCD Apps Created

| Application      | Source path                                   | Namespace      |
|------------------|-----------------------------------------------|----------------|
| `signal-cli`     | `deployments/signal-cli`                      | `signal-cli`   |
| `hermes-jason`   | `deployments/hermes/overlays/jason`           | `hermes-jason` |
| `hermes-<user>`  | `deployments/hermes/overlays/<user>`          | `hermes-<user>`|

All sync automatically with prune + selfHeal.
