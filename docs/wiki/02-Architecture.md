![wiki-banner.svg](images/wiki-banner.svg)
![accent-divider.svg](images/accent-divider.svg)
# Architecture

This document describes the system architecture, key technical decisions, and design patterns used in the `seadogger-homelab` project.

![accent-divider.svg](images/accent-divider.svg)
## Interactive Architecture Diagrams

Visual representations at different levels of abstraction, following C4 model principles.

---
> **🌙 Diagram Viewing Recommendation**
>
> The interactive Mermaid diagrams below are **optimized for GitHub Dark Mode** to provide maximum readability and visual impact.
>
> **To enable Dark Mode:** GitHub Settings → Appearance → Theme → **Dark default**
>
> *Light mode users can still view the diagrams, though colors may appear less vibrant.*
---

### Level 1: System Context

Shows the homelab system, users, and external integrations.

```mermaid
graph TB
    LAN_User([👤 LAN User<br/>Local Network])
    VPN_User([👤 External User<br/>WireGuard VPN])
    Admin([👤 Administrator])

    subgraph UDM["🛡️ Ubiquiti Dream Machine"]
        Firewall[Firewall<br/>+ WireGuard Server]
    end

    subgraph Homelab["🏠 Seadogger Homelab"]
        K3s[K3s Cluster<br/>Raspberry Pi 5 × 4]
    end

    subgraph AWS_Cloud["☁️ AWS"]
        Bedrock[Bedrock API<br/>Claude/Sonnet Models]
        S3[S3 Glacier<br/>Disaster Recovery]
    end

    GitHub[🔧 GitHub<br/>GitOps Repository]
    HDHomeRun[📺 HDHomeRun<br/>Live TV Tuner]
    Devices[📱 Home Devices<br/>Smart TVs, Phones]

    LAN_User -->|Direct HTTPS| K3s
    VPN_User -->|Encrypted Tunnel| Firewall
    Firewall -->|HTTPS| K3s
    Admin -->|kubectl/Ansible| K3s

    K3s -->|API + TLS| Bedrock
    K3s -->|GitOps Sync| GitHub
    K3s -->|Encrypted Backup| S3
    K3s -->|Stream TV| HDHomeRun
    Devices -->|DNS:53| K3s

    style UDM fill:#1e3a5f,stroke:#4a90e2,stroke-width:3px
    style Homelab fill:#2d5016,stroke:#5a9216,stroke-width:3px
    style K3s fill:#2c5aa0,stroke:#4a90e2,stroke-width:2px,color:#fff
    style AWS_Cloud fill:#ff9900,stroke:#ff9900,stroke-width:3px
    style Bedrock fill:#2c5aa0,stroke:#4a90e2,stroke-width:2px,color:#fff
    style S3 fill:#2c5aa0,stroke:#4a90e2,stroke-width:2px,color:#fff
    style GitHub fill:#24292e,stroke:#ffffff,stroke-width:2px,color:#fff
```

**Key Access Patterns:**
- **LAN Users:** Direct access to homelab services (HTTPS only)
- **External Users:** WireGuard VPN through Ubiquiti Dream Machine → Homelab
- **Administrators:** Direct kubectl/Ansible access for management
- **Security:** All external traffic encrypted via VPN tunnel

![accent-divider.svg](images/accent-divider.svg)
### Level 2: Container Diagram - K3s Infrastructure

Shows major services and applications within the cluster.

```mermaid
graph TB
    User([👤 User<br/>LAN or VPN])

    subgraph K3s["K3s Cluster"]
        subgraph Infrastructure["🏗️ Infrastructure"]
            Traefik[Traefik<br/>Ingress Controller]
            MetalLB[MetalLB<br/>Load Balancer]
            Ceph[Rook-Ceph<br/>Distributed Storage]
            CertMgr[cert-manager<br/>TLS Certificates]
            ArgoCD[ArgoCD<br/>GitOps Engine]
            Prom[Prometheus Stack<br/>Monitoring]
            PiHole[PiHole<br/>DNS & Ad-Blocking]
        end

        subgraph Apps["📦 Open Source Apps"]
            Nextcloud[Nextcloud<br/>File Storage]
            Jellyfin[Jellyfin<br/>Media Server]
            OpenWebUI[OpenWebUI<br/>AI Chat]
            N8N[N8N<br/>Automation]
            Bedrock_GW[Bedrock Gateway<br/>AWS Proxy]
        end

        subgraph Pro["💼 Pro Features"]
            Portal[Portal<br/>Dashboard]
            Keycloak[Keycloak<br/>SSO - Future]
        end
    end

    subgraph Secrets["🔐 Encrypted Secrets"]
        AWS_Secret[aws-credentials<br/>K8s Secret]
    end

    GitHub[🔧 GitHub]
    AWS[☁️ AWS Bedrock]
    S3[💾 S3 Glacier]

    User -->|HTTPS:443| Traefik
    User -->|DNS:53| PiHole

    Traefik --> Nextcloud
    Traefik --> Jellyfin
    Traefik --> OpenWebUI
    Traefik --> N8N
    Traefik --> Portal
    Traefik --> Prom
    Traefik --> Bedrock_GW

    ArgoCD -->|Deploys| Apps
    ArgoCD -->|Deploys| Pro
    ArgoCD -->|Syncs| GitHub

    MetalLB -->|192.168.1.241| Traefik
    MetalLB -->|192.168.1.250| PiHole
    MetalLB -->|192.168.1.242| Bedrock_GW

    CertMgr -->|TLS Certs| Traefik

    Nextcloud --> Ceph
    Jellyfin --> Ceph
    Prom --> Ceph

    Bedrock_GW --> AWS_Secret
    AWS_Secret -.->|Encrypted| Bedrock_GW

    Prom -->|Scrapes| Apps
    OpenWebUI -->|HTTP:6880| Bedrock_GW
    Bedrock_GW -->|HTTPS + TLS 1.3| AWS
    Nextcloud -->|Encrypted| S3

    style Infrastructure fill:#1e3a5f,stroke:#4a90e2,stroke-width:3px
    style Apps fill:#2d5016,stroke:#5a9216,stroke-width:3px
    style Pro fill:#7b1fa2,stroke:#9c27b0,stroke-width:3px,stroke-dasharray: 5 5
    style K3s fill:#1e3a5f,stroke:#4a90e2,stroke-width:3px
    style Secrets fill:#7b1fa2,stroke:#9c27b0,stroke-width:2px
```

**Legend:**
- 🏗️ Infrastructure - Core cluster services
- 📦 Open Source - Community applications
- 💼 Pro Features - Commercial/premium (dashed border)
- 🔐 Secrets - Kubernetes secrets (encrypted at rest)

**AWS Bedrock Integration:**
- **OpenWebUI** → HTTP requests to **Bedrock Gateway** (192.168.1.242:6880)
- **Bedrock Gateway** → Authenticates using Kubernetes secrets (aws-credentials)
- **Bedrock Gateway** → HTTPS + TLS 1.3 to AWS Bedrock API (Claude/Sonnet models)
- Gateway built from [aws-samples/bedrock-access-gateway](https://github.com/aws-samples/bedrock-access-gateway)
- Auto-rebuilds via GitHub Actions when upstream changes (every 6 hours check)

**Security Notes:**
- AWS credentials stored as Kubernetes secrets (encrypted at rest)
- Bedrock Gateway proxies requests with TLS 1.3 encryption to AWS
- All ingress traffic uses TLS certificates from cert-manager
- External access requires WireGuard VPN authentication

![accent-divider.svg](images/accent-divider.svg)
### Level 3: GitOps Deployment Pipeline

Shows how ArgoCD deploys applications from Git to cluster.

```mermaid
graph LR
    subgraph Git["📁 Git Repository"]
        Manifests[Kubernetes<br/>Manifests]
        Kustomize[Kustomize<br/>Overlays]
        Helm[Helm<br/>Values]
    end

    subgraph ArgoCD["🔄 ArgoCD"]
        RepoServer[Repo Server<br/>Fetch & Render]
        AppController[Application<br/>Controller]
        SyncWaves[Sync Waves<br/>Wave 0→1→2+]
    end

    subgraph K3s["☸️ K3s API"]
        CRDs[Custom Resources<br/>Application CRDs]
        Controllers[K8s Controllers<br/>Reconcile]
    end

    subgraph Cluster["🚀 Running Workloads"]
        Infra[Infrastructure<br/>Wave 0-1]
        Applications[Applications<br/>Wave 2+]
    end

    Manifests --> RepoServer
    Kustomize --> RepoServer
    Helm --> RepoServer

    RepoServer --> AppController
    AppController --> CRDs

    CRDs --> Controllers
    SyncWaves -.->|Orders| Controllers

    Controllers -->|Deploy| Infra
    Controllers -->|Deploy| Applications

    style Git fill:#24292e,stroke:#ffffff,stroke-width:2px,color:#fff
    style ArgoCD fill:#ff9900,stroke:#ff9900,stroke-width:2px
    style K3s fill:#1e3a5f,stroke:#4a90e2,stroke-width:2px
    style Cluster fill:#2d5016,stroke:#5a9216,stroke-width:2px
```

![accent-divider.svg](images/accent-divider.svg)
### Level 3: Storage Architecture

See **[[06-Storage-Rook-Ceph]]** for detailed storage architecture diagrams and Rook-Ceph deployment structure.

![accent-divider.svg](images/accent-divider.svg)
### Level 3: Network & Security

See **[[07-Networking-and-Ingress]]** for detailed network and security diagrams including MetalLB, Traefik, and cert-manager flows.

![accent-divider.svg](images/accent-divider.svg)
## Deployment Order (Sync Waves)

See **[[05-GitOps-and-IaC]]** for detailed deployment order diagrams showing ArgoCD sync waves and dependencies.

![accent-divider.svg](images/accent-divider.svg)
## Diagram Legend

| Symbol | Meaning |
|--------|---------|
| 👤 | User (LAN or VPN) |
| 🛡️ | Network Security Device |
| ☁️ | External Cloud Service |
| 🔧 | External Tool/Platform |
| 🏠 | System Boundary |
| 📦 | Application/Container |
| 💼 | Pro Feature (dashed border) |
| 🗄️ | Storage System |
| ⚖️ | Load Balancer |
| 🔀 | Ingress/Router |
| 🔐 | Security/Certificates/Secrets |
| 🌊 | Deployment Wave |

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
*   **External Access:** WireGuard VPN through Ubiquiti Dream Machine for secure remote access
*   **Encryption:** TLS certificates for all services, encrypted VPN tunnels, and Kubernetes secrets for AWS credentials

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

**Related Issues:**
- [#48 - Deployment Dependencies Refactor](https://github.com/seadogger-tech/seadogger-homelab/issues/48) - GitOps migration progress
- [#50 - Move infrastructure to ArgoCD](https://github.com/seadogger-tech/seadogger-homelab/issues/50) - Implementing sync waves
- [Pro #4 - HTTP→HTTPS redirect middleware](https://github.com/seadogger-tech/seadogger-homelab-pro/issues/4) - Security enhancement