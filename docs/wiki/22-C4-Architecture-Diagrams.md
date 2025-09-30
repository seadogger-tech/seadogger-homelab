![wiki-banner.svg](images/wiki-banner.svg)
![accent-divider.svg](images/accent-divider.svg)
# C4 Architecture Diagrams

These diagrams follow the C4 model (Context, Containers, Components, Code) to visualize the Seadogger Homelab architecture at different levels of abstraction.

> **💡 Tip:** These diagrams are built with Mermaid and render interactively on GitHub. The diagrams may take a moment to load.

## Level 1: System Context

```mermaid
C4Context
    title System Context - Seadogger Homelab

    Person(user, "Homelab User", "Access applications and services")
    Person(admin, "Administrator", "Manages cluster infrastructure")

    System_Boundary(homelab, "Seadogger Homelab") {
        System(cluster, "K3s Cluster", "Raspberry Pi 5 cluster running containerized applications")
    }

    System_Ext(aws, "AWS Bedrock", "AI/ML models (Claude, Sonnet)")
    System_Ext(github, "GitHub", "Git repository hosting")
    System_Ext(s3, "AWS S3 Glacier", "Disaster recovery backup storage")
    System_Ext(hdhomerun, "HDHomeRun", "Live TV tuner")
    System_Ext(devices, "Home Network Devices", "Phones, tablets, computers, TVs")

    Rel(user, cluster, "Uses", "HTTPS")
    Rel(admin, cluster, "Manages", "kubectl, Ansible")
    Rel(cluster, aws, "Calls AI models", "HTTPS/API")
    Rel(cluster, github, "GitOps sync", "HTTPS/Git")
    Rel(cluster, s3, "Backup data", "AWS SDK")
    Rel(cluster, hdhomerun, "Stream TV", "HTTP/RTSP")
    Rel(devices, cluster, "DNS queries", "UDP/53")
```

## Level 2: Container Diagram

```mermaid
C4Container
    title Container Diagram - K3s Cluster Infrastructure

    Person(user, "User")

    Container_Boundary(k3s, "K3s Cluster") {
        Container(traefik, "Traefik", "Ingress Controller", "Routes HTTPS traffic to services")
        Container(pihole, "PiHole", "DNS", "Network DNS and ad-blocking")
        Container(argocd, "ArgoCD", "GitOps", "Manages application deployments")
        Container(prometheus, "Prometheus Stack", "Monitoring", "Metrics, alerts, dashboards")
        Container(certmanager, "cert-manager", "PKI", "Issues and manages TLS certificates")
        Container(ceph, "Rook-Ceph", "Storage", "Distributed block and file storage")
        Container(metallb, "MetalLB", "Load Balancer", "Provides LoadBalancer IPs")

        Container_Boundary(apps, "Applications") {
            Container(nextcloud, "Nextcloud", "File Storage", "Personal cloud storage")
            Container(jellyfin, "Jellyfin", "Media", "Movies, music, live TV")
            Container(openwebui, "OpenWebUI", "AI", "LLM chat interface")
            Container(n8n, "N8N", "Automation", "Workflow automation")
            Container(portal, "Portal", "Dashboard", "Single pane of glass")
        }
    }

    System_Ext(github, "GitHub")
    System_Ext(aws, "AWS Bedrock")
    System_Ext(s3, "AWS S3")

    Rel(user, traefik, "HTTPS requests", "443")
    Rel(user, pihole, "DNS queries", "53")
    Rel(traefik, apps, "Routes to")
    Rel(argocd, apps, "Deploys/manages")
    Rel(argocd, github, "Syncs from")
    Rel(apps, ceph, "Stores data")
    Rel(certmanager, traefik, "Provides TLS certs")
    Rel(metallb, traefik, "Assigns IP")
    Rel(metallb, pihole, "Assigns IP")
    Rel(prometheus, apps, "Scrapes metrics")
    Rel(openwebui, aws, "AI requests")
    Rel(nextcloud, s3, "Backup")
```

## Level 3: Component Diagram - GitOps Pipeline

```mermaid
C4Component
    title Component Diagram - GitOps Deployment Pipeline

    Container_Boundary(git, "Git Repository") {
        Component(manifests, "Kubernetes Manifests", "YAML", "Application definitions")
        Component(kustomize, "Kustomize Overlays", "YAML", "Environment-specific configs")
        Component(helm, "Helm Values", "YAML", "Chart configurations")
    }

    Container_Boundary(argocd, "ArgoCD") {
        Component(appcontroller, "Application Controller", "Go", "Reconciles desired vs actual state")
        Component(reposerver, "Repo Server", "Go", "Fetches and renders manifests")
        Component(syncwaves, "Sync Waves", "Annotations", "Orders deployment dependencies")
        Component(ui, "ArgoCD UI", "React", "Web dashboard")
    }

    Container_Boundary(k3s, "K3s API Server") {
        Component(crds, "Custom Resources", "CRDs", "Application, AppProject, ApplicationSet")
        Component(controllers, "Controllers", "Go", "Watches and reconciles resources")
    }

    Container_Boundary(cluster, "Workloads") {
        Component(infrastructure, "Infrastructure", "Pods", "MetalLB, Rook-Ceph, cert-manager")
        Component(applications, "Applications", "Pods", "Nextcloud, Jellyfin, OpenWebUI")
    }

    Rel(reposerver, manifests, "Fetches")
    Rel(reposerver, kustomize, "Renders")
    Rel(reposerver, helm, "Templates")
    Rel(appcontroller, reposerver, "Gets rendered manifests")
    Rel(appcontroller, crds, "Creates/updates")
    Rel(controllers, crds, "Watches")
    Rel(controllers, infrastructure, "Deploys (wave 0-1)")
    Rel(controllers, applications, "Deploys (wave 2+)")
    Rel(syncwaves, controllers, "Orders deployment")
```

## Level 3: Component Diagram - Storage Architecture

```mermaid
C4Component
    title Component Diagram - Rook-Ceph Storage Architecture

    Container_Boundary(rookceph, "Rook-Ceph") {
        Component(operator, "Rook Operator", "Go", "Manages Ceph cluster lifecycle")
        Component(mon, "MON Daemons", "Ceph", "Cluster monitors (3x)")
        Component(mgr, "MGR Daemon", "Ceph", "Cluster management")
        Component(osd, "OSD Daemons", "Ceph", "Object Storage Daemons on NVMe")
        Component(mds, "MDS Daemons", "Ceph", "Metadata servers for CephFS")
    }

    Container_Boundary(storage, "Storage Classes") {
        Component(block, "ceph-block", "RBD", "Block storage for databases")
        Component(blockdata, "ceph-block-data", "RBD EC", "Erasure coded block storage")
        Component(fs, "ceph-filesystem", "CephFS", "Shared filesystem storage")
    }

    Container_Boundary(apps, "Applications") {
        Component(prometheus, "Prometheus", "Pod", "Uses ceph-block-data PVC")
        Component(nextcloud, "Nextcloud", "Pod", "Uses ceph-filesystem PVC")
        Component(jellyfin, "Jellyfin", "Pod", "Uses ceph-filesystem PVC")
    }

    Container_Boundary(hardware, "Hardware") {
        Component(nvme1, "yoda:/dev/nvme0n1", "4TB NVMe", "Physical storage")
        Component(nvme2, "anakin:/dev/nvme0n1", "4TB NVMe", "Physical storage")
        Component(nvme3, "obiwan:/dev/nvme0n1", "4TB NVMe", "Physical storage")
    }

    Rel(operator, mon, "Manages")
    Rel(operator, mgr, "Manages")
    Rel(operator, osd, "Manages")
    Rel(osd, nvme1, "Uses")
    Rel(osd, nvme2, "Uses")
    Rel(osd, nvme3, "Uses")
    Rel(block, osd, "Backed by")
    Rel(blockdata, osd, "Backed by (erasure coded)")
    Rel(fs, mds, "Backed by")
    Rel(mds, osd, "Stores metadata on")
    Rel(prometheus, block, "Mounts PVC")
    Rel(nextcloud, fs, "Mounts PVC")
    Rel(jellyfin, fs, "Mounts PVC")
```

## Level 3: Component Diagram - Network & Security

```mermaid
C4Component
    title Component Diagram - Network & Security Architecture

    Person(user, "User")

    Container_Boundary(metallb, "MetalLB") {
        Component(speaker, "Speaker DaemonSet", "Go", "Announces IPs via L2")
        Component(controller, "Controller", "Go", "Assigns IPs from pool")
        Component(ippool, "IP Address Pool", "CRD", "192.168.1.241-254")
    }

    Container_Boundary(traefik, "Traefik") {
        Component(entrypoints, "EntryPoints", "HTTP/HTTPS", "Ports 80/443")
        Component(routers, "IngressRoutes", "CRD", "Routing rules")
        Component(middleware, "Middlewares", "CRD", "HTTP→HTTPS redirect")
        Component(tlsstore, "TLS Store", "Secrets", "Certificate storage")
    }

    Container_Boundary(certmgr, "cert-manager") {
        Component(controller2, "Controller", "Go", "Issues/renews certificates")
        Component(issuer, "ClusterIssuer", "CRD", "internal-local-issuer")
        Component(rootca, "Root CA", "Secret", "Self-signed CA")
        Component(intermediateca, "Intermediate CA", "Secret", "Signs app certs")
    }

    Container_Boundary(apps, "Applications") {
        Component(nextcloud, "Nextcloud", "Pod", "Receives HTTPS traffic")
        Component(prometheus, "Prometheus", "Pod", "Receives HTTPS traffic")
    }

    Rel(user, entrypoints, "HTTPS", "443")
    Rel(controller, ippool, "Assigns from")
    Rel(speaker, entrypoints, "Announces IP")
    Rel(entrypoints, routers, "Routes via")
    Rel(routers, middleware, "Applies")
    Rel(middleware, nextcloud, "Forwards to")
    Rel(middleware, prometheus, "Forwards to")
    Rel(routers, tlsstore, "Uses cert")
    Rel(controller2, issuer, "Uses")
    Rel(issuer, intermediateca, "Signs with")
    Rel(intermediateca, rootca, "Chained to")
    Rel(controller2, tlsstore, "Stores cert in")
```

## Legend

- **Person**: External users or administrators
- **System**: External systems (AWS, GitHub, etc.)
- **Container**: High-level technology/service (applications, databases, etc.)
- **Component**: Lower-level building blocks within containers
- **Boundary**: Logical grouping of related elements

## Notes

- All diagrams can be viewed on GitHub as it renders Mermaid natively
- These diagrams represent the **target architecture** after GitOps migration (see [[21-Deployment-Dependencies]])
- Current state still has some infrastructure deployed via Ansible (being migrated)
- Sync waves enforce deployment order: Wave 0 (operators) → Wave 1 (clusters) → Wave 2+ (applications)
![accent-divider.svg](images/accent-divider.svg)
## How to View These Diagrams

### On GitHub Wiki
1. Navigate to this page on GitHub: https://github.com/seadogger-tech/seadogger-homelab/wiki/22-C4-Architecture-Diagrams
2. GitHub automatically renders Mermaid diagrams
3. Diagrams may take 5-10 seconds to render (be patient!)

### In VS Code
1. Install the "Markdown Preview Mermaid Support" extension
2. Open this file and press `Cmd+Shift+V` (macOS) or `Ctrl+Shift+V` (Windows/Linux)
3. Diagrams render inline

### Online Mermaid Editor
If diagrams don't render, you can view/edit them at:
- https://mermaid.live/
- Copy any `mermaid` code block and paste into the editor

![accent-divider.svg](images/accent-divider.svg)
## See Also

- **[[02-Architecture]]** - High-level architecture overview
- **[[21-Deployment-Dependencies]]** - Deployment order and dependencies
- **[[13-ADR-Index]]** - Architecture Decision Records
- **[[14-Design-Deep-Dives]]** - Technical deep dives

**Related Issues:**
- [#48 - Deployment Dependencies Refactor](https://github.com/seadogger-tech/seadogger-homelab/issues/48) - GitOps migration to match target architecture
- [#50 - Move infrastructure to ArgoCD](https://github.com/seadogger-tech/seadogger-homelab/issues/50) - Implementing sync waves shown in diagrams
