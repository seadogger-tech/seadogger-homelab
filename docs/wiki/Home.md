![wiki-banner.svg](images/wiki-banner.svg)

# Welcome to Seadogger Homelab

> **Production-Ready Kubernetes Homelab on Raspberry Pi 5 Cluster**
>
> A modern, enterprise-grade homelab deployment featuring K3s, ArgoCD, Rook-Ceph, and AI-powered applications running on ARM64 hardware.

![accent-divider.svg](images/accent-divider.svg)

## 🚀 Quick Start

**New to this project?** Start here:

1. **[[01-Overview]]** - Understanding the Seadogger Homelab architecture
2. **[[03-Hardware-and-Network]]** - Hardware requirements and network setup
3. **[[04-Bootstrap-and-Cold-Start]]** - Deploy from scratch in 30 minutes
4. **[[09-Apps]]** - Explore available applications

**Upgrading or troubleshooting?**
- **[[12-Troubleshooting]]** - Common issues and solutions
- **[[17-Runbooks]]** - Operational procedures
- **[[19-Refactoring-Roadmap]]** - Current development priorities

![accent-divider.svg](images/accent-divider.svg)

## 📚 Documentation Structure

### 🧭 Essentials
Get started and understand the fundamentals.

| Document | Description |
|----------|-------------|
| **[[01-Overview]]** | Project vision, features, and architecture overview |
| **[[02-Architecture]]** | System architecture and design decisions |

### ⚙️ Platform
Core infrastructure components and deployment.

| Document | Description |
|----------|-------------|
| **[[03-Hardware-and-Network]]** | Raspberry Pi 5 cluster hardware and network topology |
| **[[04-Bootstrap-and-Cold-Start]]** | Complete deployment guide with Ansible automation |
| **[[05-GitOps-and-IaC]]** | GitOps workflow with ArgoCD and Infrastructure as Code |

### 📦 Services
Infrastructure services powering the homelab.

| Document | Description |
|----------|-------------|
| **[[06-Storage-Rook-Ceph]]** | Distributed storage with Rook-Ceph erasure coding |
| **[[07-Networking-and-Ingress]]** | MetalLB, Traefik ingress, and internal routing |
| **[[08-Security-and-Certificates]]** | Internal PKI, cert-manager, and TLS certificates |
| **[[09-Apps]]** | Applications: Nextcloud, Jellyfin, OpenWebUI, N8N, PiHole |
| **[[20-HDHomeRun-Guide]]** | HDHomeRun integration for live TV streaming |
| **[[16-Pro-Overlays-and-SSO]]** | Pro features: Portal and Single Sign-On |

### 🧩 Setting Up Apps
Configuration guides for specific applications.

| Document | Description |
|----------|-------------|
| **[[18-Setting-Up-n8n-Connections]]** | Configure N8N workflow automation connections |

### 📊 Operations
Monitor, maintain, and troubleshoot your homelab.

| Document | Description |
|----------|-------------|
| **[[10-Benchmarking]]** | Performance benchmarks and testing |
| **[[11-Monitoring]]** | Prometheus, Grafana, and Alertmanager setup |
| **[[12-Troubleshooting]]** | Common problems and debugging procedures |
| **[[15-CI-CD-and-GitHub-Actions]]** | Continuous integration and deployment |
| **[[17-Runbooks]]** | Operational runbooks and procedures |

### 🧠 Knowledge
Deep dives, design decisions, and planning.

| Document | Description |
|----------|-------------|
| **[[13-ADR-Index]]** | Architecture Decision Records (ADRs) |
| **[[14-Design-Deep-Dives]]** | Technical deep dives into complex topics |
| **[[19-Refactoring-Roadmap]]** | Development priorities and improvement roadmap |
| **[[21-Deployment-Dependencies]]** | Dependency analysis and GitOps conversion plan |

![accent-divider.svg](images/accent-divider.svg)

## 🎯 Current Focus

### 🔴 Critical Priorities
1. **Disaster Recovery** - S3 Glacier backup for 4TB+ production data ([#24](https://github.com/seadogger-tech/seadogger-homelab/issues/24))
2. **Staging Environment** - Safe ARM64 testing without production risk ([#47](https://github.com/seadogger-tech/seadogger-homelab/issues/47))

### 🟠 High Priorities
3. **Deployment Dependencies Refactor** - Pure GitOps with ArgoCD + Kustomize ([#48](https://github.com/seadogger-tech/seadogger-homelab/issues/48))
   - Convert Prometheus to Ingress ([#49](https://github.com/seadogger-tech/seadogger-homelab/issues/49))
   - Move all infrastructure to ArgoCD ([#50](https://github.com/seadogger-tech/seadogger-homelab/issues/50))

See **[[19-Refactoring-Roadmap]]** for complete roadmap and **[GitHub Issues](https://github.com/seadogger-tech/seadogger-homelab/issues)** for tracking.

![accent-divider.svg](images/accent-divider.svg)

## 🏗️ Tech Stack

**Platform:**
- **Compute:** 3× Raspberry Pi 5 (8GB) with 4TB NVMe storage
- **OS:** Raspberry Pi OS (Bookworm, ARM64)
- **Kubernetes:** K3s (lightweight Kubernetes)

**Infrastructure:**
- **GitOps:** ArgoCD for declarative deployments
- **Storage:** Rook-Ceph with erasure coding (3-node cluster)
- **Load Balancer:** MetalLB (bare-metal LoadBalancer)
- **Ingress:** Traefik with automatic TLS
- **Certificates:** cert-manager with internal PKI
- **Monitoring:** Prometheus, Grafana, Alertmanager

**Applications:**
- **File Sharing:** Nextcloud (personal cloud storage)
- **Media Server:** Jellyfin (movies, music, live TV via HDHomeRun)
- **DNS/Ad Blocking:** PiHole (network-wide ad blocking)
- **AI Assistant:** OpenWebUI + AWS Bedrock (Claude, Sonnet models)
- **Workflow Automation:** N8N (automation and integrations)
- **Dashboard:** Custom portal with SSO (Pro feature)

![accent-divider.svg](images/accent-divider.svg)

## 📖 Learning Resources

**New to Kubernetes?**
- [K3s Documentation](https://docs.k3s.io/)
- [Kubernetes Basics](https://kubernetes.io/docs/tutorials/kubernetes-basics/)

**New to GitOps?**
- [ArgoCD Getting Started](https://argo-cd.readthedocs.io/en/stable/getting_started/)
- [Kustomize Tutorial](https://kubectl.docs.kubernetes.io/guides/introduction/kustomize/)

**Ansible Automation:**
- [Ansible Documentation](https://docs.ansible.com/)
- [Jeff Geerling's Pi Cluster](https://github.com/geerlingguy/turing-pi-cluster)

![accent-divider.svg](images/accent-divider.svg)

## 🤝 Contributing

This is a personal homelab project, but contributions are welcome!

- **Found a bug?** [Open an issue](https://github.com/seadogger-tech/seadogger-homelab/issues/new)
- **Have a suggestion?** [Start a discussion](https://github.com/seadogger-tech/seadogger-homelab/discussions)
- **Want to contribute?** Fork the repo and submit a pull request

![accent-divider.svg](images/accent-divider.svg)

## 📊 Project Status

**Current Version:** Production (September 2025)
**Cluster Uptime:** Running 24/7 with active users
**Data Under Management:** ~4TB (Nextcloud, Jellyfin, media)
**Active Development:** See [[19-Refactoring-Roadmap]] for current priorities

---

<div align="center">

**Built with ❤️ using Raspberry Pi, Kubernetes, and Open Source**

[GitHub Repository](https://github.com/seadogger-tech/seadogger-homelab) • [Issue Tracker](https://github.com/seadogger-tech/seadogger-homelab/issues) • [Wiki Home](Home)

</div>