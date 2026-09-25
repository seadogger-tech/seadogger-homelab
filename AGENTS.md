# AGENTS.md

Guidance for AI coding agents (Claude Code, Codex, etc.) working in this repo.
`CLAUDE.md` is a symlink to this file — edit `AGENTS.md` only.

## What this repo is

Seadogger Homelab: a K3s Kubernetes cluster on 4× Raspberry Pi 5 (ARM64),
provisioned by Ansible and run day-to-day by ArgoCD (GitOps). Storage is
Rook-Ceph on the worker NVMe drives, load balancing is MetalLB, ingress is
Traefik with an internal cert-manager PKI, and DNS comes from Pi-hole, which
runs on the cluster itself.

This is a **live production cluster** with real users and ~4TB of data
(Nextcloud, Jellyfin). Treat it that way.

## Layout

| Path | Contents |
|------|----------|
| `ansible/` | Playbooks. `main.yml` installs (stages 2 and 3), `cleanup.yml` tears down (stage 1). Tasks live in `ansible/tasks/*.yml`. |
| `ansible/example.config.yml`, `ansible/example.hosts.ini` | Templates. The real `config.yml` and `hosts.ini` are gitignored. |
| `ansible/ansible_collections/` | Vendored third-party collection. Don't edit it. |
| `deployments/<app>/` | Helm values, Kustomize manifests and Dockerfiles for each app. |
| `ingress/` | Traefik IngressRoutes. |
| `.github/workflows/` | CI that rebuilds images from upstream (hermes, mealie, signal-cli, bedrock gateway) and publishes the wiki. |
| `.github/*_upstream_*` | Digest and SHA pins that CI writes. Its `ci(...)` commits land on `master` automatically. |
| `docs/wiki/` | Source for the GitHub wiki (`Home.md`, numbered pages, `_Sidebar.md`). CODEOWNERS requires review. |
| `useful_scripts/` | NVMe partition and boot scripts for node bring-up. |

## Cluster nodes

| Host | IP | Role |
|------|----|------|
| `yoda.local` | 192.168.1.95 | K3s control plane (500GB NVMe) |
| `obiwan.local` | 192.168.1.96 | Worker + Ceph OSD (4TB NVMe) |
| `anakin.local` (a.k.a. "vader") | 192.168.1.97 | Worker + Ceph OSD (4TB NVMe) |
| `rey.local` | 192.168.1.98 | Worker + Ceph OSD (4TB NVMe) |

- Ansible's SSH user is `pi` (`[cluster:vars]` in `hosts.ini`).
- MetalLB pool: 192.168.1.240–254. Traefik VIP is 192.168.1.241 and the Pi-hole DNS VIP is 192.168.1.250.
- App hostnames are `*.seadogger-homelab` and resolve through Pi-hole.
- Deeper references: `docs/wiki/03-Hardware-and-Network.md`, `07-Networking-and-Ingress.md`, `12-Troubleshooting.md`, `17-Runbooks.md`.

## Working rules

- **Read before you act on the cluster.** `kubectl get`/`describe`/`logs`, `ceph status`,
  and `systemctl status` are fine. Anything that mutates state needs explicit confirmation
  from the user first. That includes `apply`, `delete`, `rollout restart`, drain/cordon,
  reboots, Ansible runs, and Ceph changes.
- **Never run `cleanup.yml`** or any wipe or disk task unless the user asks for it
  in this session. It destroys the cluster and can wipe the NVMe drives.
- **Ceph is fragile.** Every pool needs its OSDs up. Taking down more than one worker
  at a time, or rebooting a worker while Ceph is degraded, risks data availability.
  Check `ceph -s` is `HEALTH_OK` before any node maintenance.
- **DNS bootstrap loop:** nodes use Pi-hole, and Pi-hole runs on the cluster, so the
  `node_dns_fallback` setting in `config.yml` is what makes recovery after power loss work.
  Don't remove it.
- **GitOps first.** Change manifests in `deployments/`, commit, and let ArgoCD sync.
  Don't hand-patch live resources unless you're debugging, and if you do, backport the fix.
- **No secrets in git.** `config.yml`, `hosts.ini`, `*.pem` and the real credentials are
  gitignored. `.gitallowed` lists the placeholder names that are allowed.
- Everything is ARM64. Images and binaries must support `linux/arm64`.
- YAML must pass `yamllint` with the repo config (140-char line warning, truthy disabled).
- The default branch is `master`. CI bots commit to it often, so `git pull --rebase` before you push.

## Wiki

`docs/wiki/` is published to the GitHub wiki by `publish-wiki.yml`. When you change how
something works, update the matching wiki page, and add a troubleshooting entry for
any real incident you debug.
