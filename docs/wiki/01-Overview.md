![wiki-banner.svg](images/wiki-banner.svg)
![accent-divider.svg](images/accent-divider.svg)
# Overview

The primary goal of this project is to create a robust and well-documented guide for deploying a Kubernetes (k3s) cluster on a set of Raspberry Pi 5 nodes. The deployment should be automated using Ansible and manage applications via ArgoCD, following GitOps best practices.

![accent-divider.svg](images/tech-stack.png)

![accent-divider.svg](images/accent-divider.svg)
# Problem Statement

Setting up a personal homelab, especially a Kubernetes cluster on Raspberry Pi hardware, can be a complex and error-prone process. Many guides are incomplete, outdated, or lack the automation needed for a reliable and maintainable setup. This project aims to solve that by providing a comprehensive, automated, and well-documented solution.

![accent-divider.svg](images/accent-divider.svg)
# Key Goals

*   **Reproducibility:** The setup and deployment process should be clearly documented and scripted to allow others to reproduce the homelab environment with minimal effort.
*   **Automation:** Leverage Ansible for infrastructure provisioning and configuration to ensure consistency and reduce manual intervention.
*   **GitOps:** Use ArgoCD to manage all Kubernetes applications, ensuring that the cluster state is defined declaratively in a Git repository.
*   **Comprehensive Documentation:** Provide detailed guides, diagrams, and explanations covering hardware setup, software configuration, and operational procedures.
*   **Extensibility:** The architecture should be modular to allow for the addition of new services and applications over time.

![accent-divider.svg](images/accent-divider.svg)
# Target Audience

*   **Hobbyists and Enthusiasts:** Individuals interested in learning about Kubernetes, cloud-native technologies, and running their own services at home.
*   **Developers:** Engineers who want a local development environment that mirrors production cloud environments.
*   **Students and Learners:** Anyone looking for a hands-on project to understand modern infrastructure and DevOps practices.

![accent-divider.svg](images/accent-divider.svg)
# How It Works

The project provides a set of Ansible playbooks and Kubernetes and Helm manifests that automate the entire setup process, from configuring the Raspberry Pi nodes to deploying a suite of useful applications. Users clone the repository, customize a few configuration files, and run a single command to bring up the entire cluster.

![accent-divider.svg](images/accent-divider.svg)
# User Experience Goals

*   **Simplicity:** The setup process should be as simple as possible, abstracting away much of the underlying complexity.
*   **Clarity:** The documentation should be clear, concise, and easy to follow, with diagrams and examples to aid understanding.
*   **Reliability:** The resulting homelab should be stable and reliable, providing a solid platform for running various services.
*   **Flexibility:** While providing a default set of applications, the project should be flexible enough to allow users to easily add or remove services to suit their needs.

![accent-divider.svg](images/accent-divider.svg)
# Core Technologies

*   **Operating System:** Debian GNU/Linux 12 (bookworm) on all Raspberry Pi nodes.
*   **Container Orchestration:** Kubernetes (k3s)
*   **Infrastructure Automation:** Ansible
*   **GitOps:** ArgoCD
*   **Distributed Storage:** Rook-Ceph
*   **Ingress Controller:** Traefik
*   **PKI:** Cert-Manager w/ Traefik TLS termination
*   **Load Balancer & IP L2Advertisement:** MetalLB
*   **Monitoring:** Prometheus, Alertmanager, & Grafana
*   **DNS & Ad-Blocking:** PiHole
*   **User Apps/Services:** Nextcloud, Jellyfin, OpenwebUI, N8N
*   **Hardware:** Raspberry Pi 5 nodes. While it may be adaptable to other hardware, the documentation and scripts are tailored to this platform.
*   **Networking:** The project assumes a specific networking setup including static IP assignments, designated IP range for MetalLB, and Traefik routing 
*   **Storage:** Rook-Ceph

![accent-divider.svg](images/accent-divider.svg)
# Development Environment

*   **Code Editor:** VS Code is recommended, particularly with the SSH Remote and Continue extensions.
*   **Configuration Files:** The primary configuration files for the user are `hosts.ini` and `config.yml` within the `ansible/` directory.
*   **Git:** A working knowledge of Git and GitHub is required for managing the repository and contributing.

![accent-divider.svg](images/accent-divider.svg)
# Dependencies

*   **Ansible:** Must be installed on the machine used to manage the cluster.
*   **kubectl:** Required for interacting with the Kubernetes cluster.
*   **AWS Account:** An AWS account with Bedrock API tokens is needed for the Bedrock Access Gateway service.

![accent-divider.svg](images/accent-divider.svg)
# Project Status

**Status:** Production (September 2025)
**Deployment Time:** ~30 minutes (fully automated)
**Cluster State:** Running 24/7 with active users and ~4TB of production data

The homelab is fully functional and serving production workloads. Core infrastructure is stable and reliable. Current development focuses on operational excellence, disaster recovery, and pure GitOps conversion.

**See [[19-Refactoring-Roadmap]] for current priorities and [GitHub Issues](https://github.com/seadogger-tech/seadogger-homelab/issues) for active development.**

![accent-divider.svg](images/accent-divider.svg)
## What Works

*   **Core Infrastructure:** The Kubernetes (k3s) cluster is up and running on the Raspberry Pi 5 nodes.
*   **Node Configuration:** The control plane and worker nodes are configured and managed by Ansible.
*   **Storage System:** Rook-Ceph is deployed and providing distributed storage with both erasure-coded and replicated pools.
*   **Network Configuration:** MetalLB and Traefik are functioning, providing load balancing and ingress for deployed services.
*   **GitOps:** ArgoCD is successfully managing the deployment of most applications.
*   **Monitoring Stack:** The Prometheus and Grafana deployments are stable.
*   **User Apps & Services:** PiHole, OpenWebUI, Bedrock Access Gateway, N8N, JellyFin, and Nextcloud are deployed and operational.
*   **Portal (Pro):** Single pane of glass to access applications and monitor tech stack.

![accent-divider.svg](images/accent-divider.svg)
## Current Development Priorities

### 🔴 Critical
1. **Disaster Recovery** ([#24](https://github.com/seadogger-tech/seadogger-homelab/issues/24)) - S3 Glacier backup for production data
2. **Staging Environment** ([#47](https://github.com/seadogger-tech/seadogger-homelab/issues/47)) - Safe ARM64 testing without production risk

### 🟠 High Priority
3. **Deployment Dependencies Refactor** ([#48](https://github.com/seadogger-tech/seadogger-homelab/issues/48)) - Pure GitOps with ArgoCD + Kustomize
4. **Ansible Restructure** ([#32](https://github.com/seadogger-tech/seadogger-homelab/issues/32)) - Convert to role-based structure

### 🟡 Medium Priority
5. **Single Sign On (Pro)** ([#3](https://github.com/seadogger-tech/seadogger-homelab-pro/issues/3)) - SSO integration for unified authentication

**Full details:** [[19-Refactoring-Roadmap]] | **Dependency Analysis:** [[21-Deployment-Dependencies]]

![accent-divider.svg](images/accent-divider.svg)
## Known Issues & Limitations

*   **NFS Compatibility:** Ganesha NFS (via CephFS) has compatibility issues with macOS clients - using Nextcloud instead
*   **Image Versions:** Some deployments use "latest" tag - see [#43](https://github.com/seadogger-tech/seadogger-homelab/issues/43)
*   **Subnet Hardcoding:** Network subnet scattered across multiple files - see [#41](https://github.com/seadogger-tech/seadogger-homelab/issues/41)
*   **Mixed Deployment Methods:** Infrastructure split between Ansible and ArgoCD - migration in progress
*   **Plex Media Server:** Plex states support for k3s but Plex Pass is a PITA to deploy locally w/o Plex supervision.  Replaced media capabilities with JellyFin

![accent-divider.svg](images/accent-divider.svg)
# Prerequisites

![accent-divider.svg](images/accent-divider.svg)
## Hardware Requirements
- Raspberry Pi 5 nodes (1 control plane + 3 workers)
- POE switch (recommended: Ubiquiti Dream @Machine SE)
  - Powers Raspberry Pis via POE HAT
  - Simplifies the wiring and setup, but not totally necessary.  
  - **If you do not use POE, adjust the BoM (e.g. rack mounted solution will be different, likely)**
- Ethernet cables for hardwired connections
  - WiFi is disabled and not recommended for k3s clusters

![accent-divider.svg](images/accent-divider.svg)
## Network Setup
- DHCP static IP assignments for all Raspberry Pis
  - Configured on network switch for centralized management
  - Static IPs required for k3s cluster nodes
- DHCP service range configuration
  - Reserve IPs up to 192.168.1.239
  - Leaves space for MetalLB allocation above this range
  - If you use a different subnet, set the network variables in `ansible/config.yml` (`ipv4_subnet_prefix`, `ipv4_gateway`, `dns4_servers`) and update MetalLB `IPAddressPool` and VIPs to match.
- WireGuard (optional)
  - Required only for remote access
  - Provides encrypted tunnels for services like OpenWebUI, PiHole when you are not on your network

![accent-divider.svg](images/accent-divider.svg)
## Software Requirements
- SSH enabled on all Raspberry Pis
- AWS account with [Bedrock](https://jrpospos.blog/posts/2024/08/using-amazon-bedrock-with-openwebui-when-working-with-sensitive-data/) API tokens
- Working knowledge of:
  - Docker containers and orchestration
  - Basic AWS services
  - Git and GitHub CLI tools

![accent-divider.svg](images/accent-divider.svg)
# Learning Outcomes

![accent-divider.svg](images/accent-divider.svg)
## Technologies
- [Kubernetes (k3s)](https://docs.k3s.io/architecture) architecture and deployment
- [kubectl](https://kubernetes.io/docs/reference/kubectl/) for cluster management

![accent-divider.svg](images/accent-divider.svg)
# Author
The repository was forked from [Jeff Geerling](https://www.jeffgeerling.com)'s Pi-Cluster project and was modified by [seadogger-tech](https://github.com/seadogger-tech).
