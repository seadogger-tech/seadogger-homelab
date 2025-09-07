# Technical Context: seadogger-homelab

This document outlines the technologies, development setup, and technical constraints for the `seadogger-homelab` project.

## Core Technologies

*   **Operating System:** Debian GNU/Linux 12 (bookworm) on all Raspberry Pi nodes.
*   **Container Orchestration:** Kubernetes (k3s)
*   **Infrastructure Automation:** Ansible
*   **GitOps:** ArgoCD
*   **Distributed Storage:** Rook-Ceph
*   **Ingress Controller:** Traefik
*   **Load Balancer:** MetalLB
*   **Monitoring:** Prometheus & Grafana
*   **DNS & Ad-Blocking:** PiHole

## Development Environment

*   **Code Editor:** VS Code is recommended, particularly with the SSH Remote and Continue extensions.
*   **Configuration Files:** The primary configuration files for the user are `hosts.ini` and `config.yml` within the `ansible/` directory.
*   **Git:** A working knowledge of Git and GitHub is required for managing the repository and contributing.

## Technical Constraints

*   **Hardware:** The project is specifically designed for Raspberry Pi 5 nodes. While it may be adaptable to other hardware, the documentation and scripts are tailored to this platform.
*   **Networking:** The project assumes a specific networking setup, including static IP assignments for nodes and a designated IP range for MetalLB. Changes to the subnet require modifications throughout the deployment scripts.
    *   MetalLB IP Range: 192.168.1.241-254
    *   Traefik: 192.168.1.241
    *   Bedrock Gateway: 192.168.1.242
    *   OpenWebUI: 192.168.1.243
    *   Prometheus: 192.168.1.244
    *   Grafana: 192.168.1.245
    *   Alertmanager: 192.168.1.246
    *   ArgoCD: 192.168.1.247
    *   Ceph Dashboard: 192.168.1.248
    *   PiHole Web: 192.168.1.249
    *   PiHole DNS: 192.168.1.250
    *   Plex: 192.168.1.251
    *   N8N: 192.168.1.252
*   **Storage:** The Rook-Ceph configuration is designed for the specific NVMe drive setup outlined in the `README.md`. It provides two main storage classes:
    *   `rook-ceph-filesystem-ec`: An erasure-coded filesystem designed to maximize storage capacity for large files and media, suitable for applications like Plex Media Server. It can tolerate at least one node failure.
    *   `ceph-block`: A replicated block storage system that offers higher redundancy and can handle multiple node failures, making it suitable for more critical data.

## Dependencies

*   **Ansible:** Must be installed on the machine used to manage the cluster.
*   **kubectl:** Required for interacting with the Kubernetes cluster.
*   **AWS Account:** An AWS account with Bedrock API tokens is needed for the Bedrock Access Gateway service.
