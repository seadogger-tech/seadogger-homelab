# Progress: seadogger-homelab

This document tracks what works, what's left to build, and the current status of the `seadogger-homelab` project.

## What Works

*   **Core Infrastructure:** The Kubernetes (k3s) cluster is up and running on the Raspberry Pi 5 nodes.
*   **Node Configuration:** The control plane and worker nodes are configured and managed by Ansible.
*   **Storage System:** Rook-Ceph is deployed and providing distributed storage with both erasure-coded and replicated pools.
*   **Network Configuration:** MetalLB and Traefik are functioning, providing load balancing and ingress for deployed services.
*   **GitOps:** ArgoCD is successfully managing the deployment of most applications.
*   **Core Services:** PiHole, OpenWebUI, and the Bedrock Access Gateway are deployed and operational.

## What's Left to Build

*   **NFS File Sharing:** A stable and cross-platform solution for NFS file sharing needs to be implemented.
*   **Plex Media Server:** The Plex application is yet to be deployed.
*   **Monitoring:** The Prometheus and Grafana stack needs to be fixed to provide reliable monitoring and metrics.
*   **Remote Storage Integration:** A solution for connecting the local Ceph cluster to remote storage has not been implemented yet.

## Current Status

The project is in a partially functional state. The core infrastructure is solid, but several key user-facing services are either not yet deployed or not fully functional. The immediate priority is to resolve the NFS file sharing issues, which is a blocker for the Plex deployment.

## Known Issues

*   **NFS Compatibility:** Ganesha NFS (via CephFS) has compatibility issues with macOS clients, preventing reliable file access.
*   **Monitoring Stack:** The Prometheus and Grafana deployments are not stable and require troubleshooting.
