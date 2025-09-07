
<p align="center">
  <img src="images/wiki-banner.svg" alt="SeaDogger Homelab — Wiki" width="100%"/>
</p>

<p align="center">
  <a href="https://github.com/seadogger/seadogger-homelab">Source Repo</a> ·
  <a href="./13-ADR-Index.md">ADRs</a> ·
  <a href="./11-Runbooks.md">Runbooks</a> ·
  <a href="./Images-Index.md">Images</a>
</p>

<p align="center">
  <img alt="Docs" src="https://img.shields.io/badge/docs-automated-1f2a44?labelColor=0b1221&logo=markdown&logoColor=white">
  <img alt="GitOps" src="https://img.shields.io/badge/GitOps-ArgoCD-1f2a44?labelColor=0b1221">
  <img alt="K3s" src="https://img.shields.io/badge/K3s-Raspberry%20Pi-1f2a44?labelColor=0b1221">
</p>

<p align="center">
  <img src="images/accent-divider.svg" alt="" width="70%" />
</p>

> **Zero‑friction**: edit files under **`docs/wiki/**`** in the source repo. On merge to **main**, CI rebuilds indexes and **publishes to the GitHub Wiki** automatically.

**Snapshot (as of 2025-09-07)**
- K3s on Raspberry Pi 5 · Debian 12  
- Rook‑Ceph (RBD + CephFS EC) · MetalLB + Traefik · ArgoCD (GitOps)  
- Apps: Pi‑hole, OpenWebUI, Bedrock Gateway, n8n, Prometheus/Grafana/Alertmanager, Plex

<p align="center">
  <img src="images/accent-divider.svg" alt="" width="70%" />
</p>

## Quick Links

| Overview | Architecture | Bootstrap | GitOps/IaC | Storage | Networking | Security |
|---|---|---|---|---|---|---|
| [[01-Overview]] | [[02-Architecture]] | [[04-Bootstrap-and-Cold-Start]] | [[05-GitOps-and-IaC]] | [[06-Storage-Rook-Ceph]] | [[07-Networking-and-Ingress]] | [[08-Security-and-Certificates]] |

| Apps | Benchmarking | Runbooks | Troubleshooting | ADRs | Memory Bank | Images |
|---|---|---|---|---|---|---|
| [[09-Apps]] | [[10-Benchmarking]] | [[11-Runbooks]] | [[12-Troubleshooting]] | [[13-ADR-Index]] | [[14-Memory-Bank-Index]] | [[Images-Index]] |

### Conventions
- Memory Bank in **`docs/wiki/memory_bank/`**
- Images in **`docs/wiki/images/`** (`![...](images/...)`)
- CI generates **14-Memory-Bank-Index** and topic backlinks automatically
