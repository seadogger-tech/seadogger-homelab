![wiki-banner.svg](images/wiki-banner.svg)
![accent-divider.svg](images/accent-divider.svg)
# Architecture

This document describes the system architecture, key technical decisions, and design patterns used in the `seadogger-homelab` project.

## Architecture Diagrams

**High-Level Overview:**
![Pi Cluster Architecture](images/Architecture.png)

**Detailed C4 Diagrams:** For interactive, detailed architecture diagrams following the C4 model (Context, Containers, Components), see **[C4 Architecture Diagrams](images/c4-architecture.md)**:
- **System Context** - External systems and user interactions
- **Container Diagram** - K3s cluster infrastructure and services
- **Component Diagrams** - GitOps pipeline, storage architecture, network & security
- All diagrams are Mermaid-based and render interactively on GitHub

![accent-divider.svg](images/accent-divider.svg)
## Core Architecture

The architecture is based on a Kubernetes (k3s) cluster running on a group of Raspberry Pi 5 nodes.

*   **Control Plane:** A single Raspberry Pi 5 node acts as the master, running the Kubernetes control plane components.
*   **Worker Nodes:** Three additional Raspberry Pi 5 nodes serve as workers, running the application workloads.
*   **Storage:** A distributed storage solution, Rook-Ceph, is deployed across the worker nodes, providing persistent storage for stateful applications.
*   **Networking:** MetalLB is used to provide LoadBalancer services for exposing applications to the local network. Traefik is used as the Ingress controller.

![accent-divider.svg](images/accent-divider.svg)
## Key Technical Decisions

*   **Kubernetes Distribution:** k3s was chosen for its lightweight nature and suitability for resource-constrained environments like the Raspberry Pi.
*   **Infrastructure as Code:** Ansible is used for provisioning and configuring the cluster nodes, ensuring a declarative and repeatable setup process.
*   **GitOps:** ArgoCD is the cornerstone of the application deployment strategy. All application configurations are stored in a Git repository, and ArgoCD ensures the cluster state matches the desired state in Git. Currently, some infrastructure (MetalLB, Rook-Ceph) is deployed via Ansible, but migration to pure GitOps is in progress (see [[21-Deployment-Dependencies]]).
*   **Distributed Storage:** Rook-Ceph is used to provide a resilient and scalable storage layer, abstracting the underlying NVMe drives on the worker nodes.

![accent-divider.svg](images/accent-divider.svg)
## Design Patterns

*   **Declarative Configuration:** All aspects of the system, from infrastructure to applications, are defined declaratively in configuration files (Ansible playbooks, Kubernetes manifests).
*   **Immutable Infrastructure:** The goal is to treat the cluster nodes as immutable. Changes are made by updating the Ansible playbooks and re-running them, rather than making manual changes to the nodes.
*   **Separation of Concerns:** The project is structured to separate concerns:
    *   `.github/workflow/`: Automated workflow that will sync the Wiki docs when anything is checked into the source repo.
    *   `ansible/`: Infrastructure provisioning.
    *   `benchmarks/`: Scripts to benchmark system storage capabilities.
    *   `certificates/`: Manifests which create TLS certs from the cert-manager for each app.
    *   `deployments/`: This directory contains Helm values files and Kubernetes manifests that are referenced by ArgoCD for application deployment.
    *   `docs/wiki/`: Project Wiki repository.
    *   `ingress/`: Manifest which setup ingress routes for each app thru Traefik.
    *   `useful_scripts/`: Scripts for partitioning 4TB NVMe drive as well as getting the RPi5 to boot from the NVMe vs. SDCard.
    *   `memory-bank/`: Project documentation waiting to be integrated into the project Wiki.
*   **Application Deployment Workflow:** Application deployments follow a GitOps pattern:
    1.  **Git Configuration:** Application manifests, Helm values, or Kustomize overlays are stored in Git
    2.  **ArgoCD Application:** ArgoCD `Application` resources define what to deploy and where
    3.  **Automated Sync:** ArgoCD continuously monitors Git and ensures cluster state matches desired state
    4.  **Self-Healing:** ArgoCD automatically corrects drift from the desired state

    **Current State:** Most applications follow this pattern. Infrastructure components (MetalLB, Rook-Ceph) are transitioning from Ansible deployment to ArgoCD Applications with Kustomize (see [[21-Deployment-Dependencies]]).

![accent-divider.svg](images/accent-divider.svg)
## See Also

- **[[21-Deployment-Dependencies]]** - Detailed analysis of deployment dependencies and GitOps migration plan
- **[[13-ADR-Index]]** - Architecture Decision Records documenting key technical choices
- **[[14-Design-Deep-Dives]]** - In-depth technical discussions on specific topics
- **[[19-Refactoring-Roadmap]]** - Current development priorities and improvement roadmap
