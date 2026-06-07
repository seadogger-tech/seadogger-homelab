![wiki-banner.svg](images/wiki-banner.svg)
![accent-divider](images/accent-divider.svg)

# Hermes Dev Environment — Setup & Operations

This page covers everything needed to deploy, configure, and use the Hermes +
VS Code dev environment end-to-end. For the architectural design rationale see
[24-Hermes-Container-Architecture](24-Hermes-Container-Architecture.md).

![accent-divider](images/accent-divider.svg)

## What You Get

| URL | What it is |
|-----|-----------|
| `hermes-<user>.seadogger-homelab` | Hermes AI agent dashboard |
| `code-<user>.seadogger-homelab` | VS Code (code-server) browser IDE |

Both pods share a single 50Gi CephFS PVC (`hermes-data`) mounted at `/opt/data`.
The PVC is the source of truth for all persistent state — credentials, config,
repos, memories. Container image updates never touch it.

![accent-divider](images/accent-divider.svg)

## Deployment

Everything is driven by the pro repo ansible playbook. User configuration lives
in `ansible/config.yml` (gitignored — never committed).

### User configuration (`ansible/config.yml`)

```yaml
hermes_users:
  - name: jason
    cluster_admin: true    # binds cluster-admin ClusterRoleBinding
    dev_pod: true          # deploys code-server pod + portal tile
  - name: kelly
    cluster_admin: false   # read-only cluster access only
    dev_pod: false         # no code-server pod
```

### What the playbook does (hermes section)

1. Generates an ed25519 SSH keypair per user on localhost (`/tmp/hermes-ssh-<user>`)
2. Creates `hermes-ssh-keys` Secret in `hermes-<user>` namespace (authorized_keys + private key)
3. Creates namespaces (`hermes-<user>`)
4. Generates kustomize overlays (`deployments/hermes/overlays/<user>/`) with patched hostnames
5. Generates dev overlays (`deployments/hermes/overlays/<user>-dev/`) if `dev_pod: true`
6. Creates ArgoCD Applications for hermes and dev pods
7. Applies RBAC — cluster-admin if flagged, read-only otherwise
8. Updates Pi-hole DNS with `hermes-<user>` and `code-<user>` entries
9. Injects portal tiles (Hermes + Code) into `deployments/portal/portal.html`

### Running the playbook

```bash
ansible-playbook -i ansible/hosts.ini ansible/main.yml
```

To re-run only the hermes tasks (faster):

```bash
ansible-playbook -i ansible/hosts.ini ansible/main.yml --tags hermes
```

### Forcing ArgoCD to sync immediately after a push

Always hard-refresh rather than waiting for the polling interval:

```bash
kubectl -n argocd annotate application hermes-jason argocd.argoproj.io/refresh=hard --overwrite
kubectl -n argocd annotate application dev-jason argocd.argoproj.io/refresh=hard --overwrite
kubectl -n argocd annotate application portal argocd.argoproj.io/refresh=hard --overwrite
```

![accent-divider](images/accent-divider.svg)

## CephFS Permissions — The Root Cause

**This is the most important thing to understand about this deployment.**

The Rook-Ceph CSI driver mounts CephFS volumes using the `admin` client key.
All file I/O on the PVC goes through this mount, which means:

- Files are written with the UID/GID of the process inside the container
- The hermes pod process runs as UID 10000 (the `hermes` user defined in the image)
- The dev pod (code-server) runs as **root (UID 0)** — this is required

### Why the dev pod must run as root

When the dev pod tried to run as UID 1000 (the code-server image default), it
could not read or write files owned by UID 10000 (hermes) on the CephFS mount.
CephFS preserves UIDs faithfully — there is no squash configured — so a process
running as UID 1000 simply cannot access files owned by 10000.

Root (UID 0) can read any file regardless of ownership, which is why both
`securityContext.runAsUser: 0` is set on the init container and the code-server
container in `deployments/hermes/dev/deployment.yaml`.

```yaml
# deployments/hermes/dev/deployment.yaml
securityContext:
  runAsUser: 0   # Required — CephFS UID mismatch with hermes pod (UID 10000)
```

This is a known trade-off. The dev pod is on the cluster internal network,
protected by internal CA TLS, with no cluster API permissions. The blast
radius of running code-server as root is limited to the PVC contents.

![accent-divider](images/accent-divider.svg)

## SSH Keypair — VS Code Remote SSH

The SSH keypair allows the VS Code integrated terminal to SSH directly into
the hermes pod, giving you a shell with the full hermes dev toolchain on PATH.

### How keypairs are provisioned

```
ansible (localhost)
  └── community.crypto.openssh_keypair
        generates /tmp/hermes-ssh-<user> (private)
                  /tmp/hermes-ssh-<user>.pub (public)
        → k8s Secret hermes-ssh-keys in hermes-<user> namespace
              authorized_keys: <public key>   ← mounted into hermes pod
              id_ed25519: <private key>        ← mounted into dev pod
```

The init container in the hermes pod copies `authorized_keys` to
`/opt/data/home/.ssh/authorized_keys` on the PVC at startup.

The init container in the dev pod copies `id_ed25519` to
`/opt/data/.ssh/id_ed25519` and writes the SSH config:

```
Host hermes
    HostName hermes.<namespace>.svc.cluster.local
    Port 22
    User hermes
    IdentityFile /opt/data/.ssh/id_ed25519
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
```

### Connecting from VS Code terminal

```bash
ssh hermes
```

This connects from the dev pod to the hermes pod over the cluster internal
network. You land in `/opt/data` as the `hermes` user with all dev tools
(kubectl, gh, helm, swift, etc.) on PATH.

### sshd configuration in the hermes image

- `PasswordAuthentication no` — pubkey only
- `PermitRootLogin prohibit-password` — root blocked from password auth
- `AuthorizedKeysFile /opt/data/home/.ssh/authorized_keys` — key on PVC
- Started as an s6-overlay longrun service alongside the hermes gateway

![accent-divider](images/accent-divider.svg)

## VS Code (code-server) Configuration

### Workspace

code-server opens `/opt/data` as the workspace root. This is the hermes
persistent home directory containing all agent config, memories, and repos.

The workspace is pinned via `coder.json` — written by the init container
on every pod start so it survives restarts:

```json
{"query":{"folder":"/opt/data"},"update":{"checked":1780872063183,"version":"4.123.0"}}
```

### Dotfiles visibility

All hermes state files are dotfiles (`.env`, `.hermes`, `.kube`, `.ssh`, etc.).
VS Code shows them by default — the `files.exclude` setting does **not** contain
a `**/.*` pattern in the default code-server configuration.

If dotfiles are not visible, open Settings (`Ctrl+,`) and verify `files.exclude`
does not contain `**/*.*` or similar catch-all patterns.

### Terminal

The integrated terminal runs inside the dev pod (root, Debian). To get a shell
in the hermes pod with all dev tools, use `ssh hermes` from the terminal.

Terminal settings are persisted to the PVC at:
`/opt/data/home/.local/share/code-server/User/settings.json`

A minimal `.bashrc` lives at `/opt/data/.bashrc` so the terminal starts
immediately without sourcing slow or missing profile files.

### Extensions

Extensions are installed to the PVC at:
`/opt/data/home/.local/share/code-server/extensions/`

They persist across pod restarts and image updates. Install extensions
normally via the Extensions sidebar.

### User settings persistence

All VS Code settings, keybindings, and extensions are stored on the PVC at
`/opt/data/home/.local/share/code-server/`. They survive pod restarts, image
updates, and cluster restores from Velero.

![accent-divider](images/accent-divider.svg)

## Claude Code Authentication

The Claude Code extension (`anthropic.claude-code`) is pre-installed from the
GHCR image and persists on the PVC. Authentication uses your Claude subscription
(not API key billing).

### First-time auth

Claude Code uses an OAuth PKCE flow with a localhost callback. Because the
callback lands on a random port inside the pod — not your Mac — you need a
one-time port-forward to bridge the OAuth redirect.

**Step 1** — In the VS Code terminal, run:

```bash
/opt/data/home/.local/share/code-server/extensions/anthropic.claude-code-*/resources/native-binary/claude setup-token
```

The command prints an authorization URL like:
```
https://claude.ai/oauth/authorize?...&redirect_uri=http%3A%2F%2Flocalhost%3A<PORT>%2Fcallback&...
```

**Step 2** — Note the `<PORT>` from the redirect_uri. On your Mac in a separate terminal:

```bash
kubectl port-forward -n hermes-jason deploy/dev <PORT>:<PORT>
```

**Step 3** — Open the authorization URL in your browser, approve access on claude.ai.
The browser will redirect to `localhost:<PORT>/callback` — which the port-forward
tunnels into the pod. Authentication completes and the token is stored on the PVC.

**Step 4** — Kill the port-forward. It is not needed again.

### Why this works

`kubectl port-forward` runs on your Mac and creates a TCP tunnel from
`localhost:<PORT>` on your Mac through the Kubernetes API server into the pod.
The OAuth callback hits your Mac's localhost, gets forwarded into the pod,
and the `setup-token` process receives it — no cluster-level networking change needed.

### Token persistence

The auth token is stored in `/opt/data/home/.local/share/code-server/` on the
PVC. It persists across pod restarts and image updates. Re-authentication is only
needed if the token expires or is revoked.

### Subsequent use

After first-time auth, Claude Code works normally in the VS Code panel. No
port-forward or special steps needed.

![accent-divider](images/accent-divider.svg)

## PVC Layout

```
/opt/data/                              ← CephFS RWM PVC root (hermes home)
  .env                                  ← ANTHROPIC_API_KEY, Signal, gateway tokens
  .bashrc                               ← Minimal shell config for VS Code terminal
  .ssh/                                 ← SSH keys for dev pod → hermes pod connection
    authorized_keys                     ← Written by hermes init container
    id_ed25519                          ← Written by dev init container
    config                              ← SSH host alias "hermes"
  .hermes/                              ← Hermes agent internal state
  .kube/                                ← kubectl config (cluster-admin if opted in)
  .gitconfig                            ← Git identity
  .git-credentials                      ← Git auth tokens
  auth.json                             ← Platform auth sessions
  config.yaml                           ← Full agent configuration
  state.db                              ← Conversation history, kanban, cron
  memories/                             ← Long-term agent memory
  skills/                               ← Installed skill definitions
  repos/                                ← Development repositories (clone here)
  home/                                 ← Dev pod home (code-server config)
    .local/share/code-server/           ← VS Code extensions, settings, state
      User/settings.json                ← VS Code user settings
      extensions/                       ← Installed extensions (persisted)
      coder.json                        ← Workspace folder (pinned to /opt/data)
```

![accent-divider](images/accent-divider.svg)

## Day-to-Day Workflow

### Clone a repo and work on it

```bash
# In VS Code terminal (dev pod, root)
cd /opt/data/repos
git clone https://github.com/your-org/your-repo
```

Open the folder in VS Code: **File → Open Folder** → `/opt/data/repos/your-repo`

Hermes can see and modify the same files at `/opt/data/repos/your-repo`.

### Get a full dev shell (hermes toolchain)

```bash
# In VS Code terminal
ssh hermes
# Now you are in /opt/data as the hermes user with all dev tools on PATH
kubectl get nodes
gh pr list
swift build
```

### Check hermes agent logs

```bash
kubectl logs -n hermes-jason deploy/hermes -f
```

Or from the hermes dashboard at `hermes-jason.seadogger-homelab`.

![accent-divider](images/accent-divider.svg)

## Troubleshooting

### Pod not starting — `ImagePullBackOff`

The GHCR images are public — no imagePullSecret needed. If pulling fails:

```bash
kubectl describe pod -n hermes-jason -l app=hermes | grep -A 5 Events
```

Check if the GHA build workflow completed successfully in the core repo.

### ArgoCD shows `Unknown` sync status

The GitHub PAT in `ansible/config.yml` may have expired. Test it:

```bash
TOKEN=$(kubectl get secret repo-credentials -n argocd -o jsonpath='{.data.password}' | base64 -d)
curl -s -o /dev/null -w "%{http_code}" -H "Authorization: token $TOKEN" \
  https://api.github.com/repos/seadogger-tech/seadogger-homelab-pro
```

If `401`, generate a new PAT and patch the secret:

```bash
NEW_TOKEN="github_pat_..."
kubectl patch secret repo-credentials -n argocd --type='json' \
  -p="[{\"op\":\"replace\",\"path\":\"/data/password\",\"value\":\"$(echo -n $NEW_TOKEN | base64)\"}]"
kubectl -n argocd annotate application hermes-jason argocd.argoproj.io/refresh=hard --overwrite
```

Update `argo_repo_token` in `ansible/config.yml` so the next playbook run
doesn't overwrite your new token.

### VS Code terminal hangs on open

The terminal shell is sourcing `/opt/data/.bashrc`. If that file is missing
or corrupt, recreate it:

```bash
kubectl exec -n hermes-jason deploy/dev -- sh -c \
  'printf "export PS1=\"\u@hermes:\w\\$ \"\nexport PATH=\"/usr/local/bin:/usr/bin:/bin:/opt/data/bin\"\n" > /opt/data/.bashrc'
```

Then reload the VS Code window: `Ctrl+Shift+P` → **Developer: Reload Window**.

### VS Code opens wrong folder

`coder.json` controls the default workspace. The init container writes it on
every pod start. To fix immediately without restarting the pod:

```bash
kubectl exec -n hermes-jason deploy/dev -- sh -c \
  'printf "{\"query\":{\"folder\":\"/opt/data\"},\"update\":{\"checked\":1780872063183,\"version\":\"4.123.0\"}}" \
  > /opt/data/home/.local/share/code-server/coder.json'
```

Then reload the VS Code window.

### SSH to hermes fails — `Connection refused`

sshd is running as an s6-overlay longrun service. Check if it is listening:

```bash
kubectl exec -n hermes-jason deploy/hermes -- grep -c "0016" /proc/net/tcp
```

Should return `1`. If `0`, the s6 sshd service failed to start:

```bash
kubectl exec -n hermes-jason deploy/hermes -- cat /etc/s6-overlay/s6-rc.d/sshd/run
kubectl exec -n hermes-jason deploy/hermes -- /usr/sbin/sshd -t  # test config
```

Check that `authorized_keys` is on the PVC:

```bash
kubectl exec -n hermes-jason deploy/hermes -- cat /opt/data/home/.ssh/authorized_keys
```

If missing, re-run the ansible playbook — the init container will re-copy
the key from the `hermes-ssh-keys` Secret.

### Claude Code auth — localhost callback fails

See [Claude Code Authentication](#claude-code-authentication) above.
The port-forward approach is required for first-time auth. Subsequent
sessions use the stored token and need no port-forward.

![accent-divider](images/accent-divider.svg)

## Portal Tiles

The ansible playbook automatically injects portal tiles into
`deployments/portal/portal.html` on every run. Markers in the HTML
define the injection zones:

```html
// ANSIBLE_HERMES_AGENT_TILES_START
// ... one tile per user in hermes_users
// ANSIBLE_HERMES_AGENT_TILES_END

// ANSIBLE_HERMES_DEV_TILES_START
// ... one tile per user with dev_pod: true
// ANSIBLE_HERMES_DEV_TILES_END
```

After the playbook runs, commit and push `portal.html`, then hard-refresh
the portal ArgoCD application:

```bash
git add deployments/portal/portal.html
git commit -m "chore: Update portal tiles"
git push
kubectl -n argocd annotate application portal argocd.argoproj.io/refresh=hard --overwrite
```

The portal ConfigMap is updated by ArgoCD and the Caddy pod hot-reloads
the file within ~60 seconds — no pod restart needed.
