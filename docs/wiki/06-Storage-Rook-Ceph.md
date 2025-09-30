![wiki-banner.svg](images/wiki-banner.svg)
![accent-divider.svg](images/accent-divider.svg)
# Storage Architecture: Rook-Ceph

---
> **🌙 Diagram Viewing Recommendation**
>
> The interactive Mermaid diagrams below are **optimized for GitHub Dark Mode** to provide maximum readability and visual impact.
>
> **To enable Dark Mode:** GitHub Settings → Appearance → Theme → **Dark default**
>
> *Light mode users can still view the diagrams, though colors may appear less vibrant.*
---

The cluster's storage is managed by Rook-Ceph, providing both block and filesystem storage. The architecture is designed for a balance of performance, data redundancy, and storage efficiency.

![ceph-dashboard](images/ceph-dashboard.png)


![accent-divider.svg](images/accent-divider.svg)
### CEPH Block Storage
-   **Pool:** `ceph-block-data` (Replicated, size 3)
-   **Storage Class:** `ceph-block-data`
-   **Default:** Yes. This is the default storage class for all general-purpose block storage needs (e.g., application databases).

![accent-divider.svg](images/accent-divider.svg)
### CEPH FileSystem Storage
-   **Filesystem Name:** `ceph-fs`
-   **Pools:**
    1.  `ceph-fs-metadata` (Replicated, size 3): Stores filesystem metadata.
    2.  `ceph-fs-data-replicated` (Replicated, size 3): The required default data pool for the filesystem.
    3.  `ceph-fs-data-ec` (Erasure Coded, 2+1): For high-efficiency bulk data storage.
-   **Storage Classes:**
    1.  `ceph-fs-data-replicated`: Provides replicated, resilient filesystem storage.
    2.  `ceph-fs-data-ec`: Provides erasure-coded, high-efficiency filesystem storage for large datasets.


![accent-divider.svg](images/accent-divider.svg)
| StorageClass               | Type                         | Provisioner                     | ReclaimPolicy | BindingMode            | Expandable | Default | Suggested Use                                                                 | Failure Tolerance*                                   |
|--------------------------- |-----------------------------|---------------------------------|---------------|------------------------|------------|---------|--------------------------------------------------------------------------------|------------------------------------------------------|
| `ceph-block-data`          | Ceph **RBD Block**          | `rook-ceph.rbd.csi.ceph.com`    | Retain        | Immediate              | ✅         | ✅      | General/critical workloads needing block volumes (DBs, app data).            | Replicated pool (e.g., 3×) ⇒ tolerate up to (replicas-1) OSD/node failures. |
| `ceph-fs-data-ec`          | **CephFS (Erasure-Coded)**  | `rook-ceph.cephfs.csi.ceph.com` | Retain        | Immediate              | ✅         | —       | Large media & read-heavy files (e.g., Plex libraries) to maximize capacity.  | EC profile (e.g., 2+1) ⇒ tolerates ≥1 OSD/node failure.                    |
| `ceph-fs-data-replicated`  | **CephFS (Replicated)**     | `rook-ceph.cephfs.csi.ceph.com` | Retain        | Immediate              | ✅         | —       | Shared files where extra redundancy is preferred over raw capacity.          | Replicated pool (e.g., 3×) ⇒ tolerate up to (replicas-1) OSD/node failures. |
| `ceph-bucket`              | **S3-compatible Object**    | `rook-ceph.ceph.rook.io/bucket` | Delete        | Immediate              | ❌         | —       | Apps needing object storage via S3 API.                                       | Depends on RGW/RADOS pool replication; node-resilient if replicated.        |
| `local-path`               | **HostPath (Local)**        | `rancher.io/local-path`         | Delete        | WaitForFirstConsumer   | ❌         | —       | Ephemeral/dev workloads tied to a single node.                                | None (single-node; no redundancy).                                         |

\* Failure tolerance is indicative; exact resilience depends on your Ceph pool replica/EC settings.
![accent-divider.svg](images/accent-divider.svg)
### Storage System (Rook-Ceph)
   - Status: HEALTH_OK
   - Capacity: 11 TiB total available
   - Capacity: 3.8TB in replicated pools
   - Capacity: 6.8TB in EC pools
   - Configuration:

![accent-divider.svg](images/accent-divider.svg)
### Implementation and IaaC 

The new architecture was implemented by making the following changes to the `seadogger-homelab` Infrastructure-as-Code repository:

1.  **`deployments/rook-ceph/rook-ceph-cluster-values.yaml`:**
    *   Updated to define the `ceph-block` and `ceph-fs` filesystems with their corresponding pools and storage classes as detailed above.
    *   Pool names were corrected to their base names (e.g., `data-replicated`), as the Rook operator automatically prepends the filesystem name.

2.  **`ansible/tasks/rook_ceph_deploy_part1.yml`:**
    *   The validation task was updated to check for the existence of the new, correctly named pools (`ceph-fs-metadata`, `ceph-fs-data-replicated`, `ceph-fs-data-ec`).
    *   The task to set the default storage class was updated to target `ceph-block-data`.

3.  **`ansible/tasks/cleanup_infrastructure.yml`:**
    *   The teardown script was updated to correctly identify and delete the newly named StorageClasses, CephFilesystem, and CephNFS resources.

4.  **`ansible/tasks/rook_ceph_deploy.yml`:**
    *   This outdated, monolithic deployment file was deleted to prevent confusion.

5.  **Application Helm Values:**
    *   All `values.yaml` files were reviewed, and any hardcoded `storageClassName` was updated from `ceph-block` or `rook-ceph-filesystem-ec` to the new, correct names (`ceph-block-data` or `ceph-fs-data-ec`).
    *   A new `nextcloud-values.yaml` was created to ensure it uses the correct storage class.

This comprehensive update ensures the entire storage infrastructure is now correctly defined in code, leading to a reliable and repeatable deployment process.

![accent-divider.svg](images/accent-divider.svg)
## See Also

- **[[03-Hardware-and-Network]]** - NVMe hardware setup for Rook-Ceph
- **[[04-Bootstrap-and-Cold-Start]]** - Rook-Ceph deployment procedures
- **[[02-Architecture]]** - C4 Storage Architecture diagram
- **[[12-Troubleshooting]]** - Rook-Ceph troubleshooting

**Related Issues:**
- [#24 - Disaster Recovery](https://github.com/seadogger-tech/seadogger-homelab/issues/24) - S3 backup strategy for Ceph data
- [#50 - Move infrastructure to ArgoCD](https://github.com/seadogger-tech/seadogger-homelab/issues/50) - Rook-Ceph GitOps migration

![accent-divider.svg](images/accent-divider.svg)
### Level 3: Storage Architecture

Shows Rook-Ceph distributed storage with actual storage classes.

```mermaid
graph TB
    subgraph RookCeph["🗄️ Rook-Ceph Cluster"]
        Operator[Rook Operator<br/>Lifecycle Manager]

        subgraph Daemons["Ceph Daemons"]
            MON[MON × 3<br/>Cluster Monitors]
            MGR[MGR × 1<br/>Management]
            OSD[OSD × 3<br/>Storage Daemons]
            MDS[MDS × 2<br/>Metadata Servers]
        end
    end

    subgraph Storage["💾 Storage Classes"]
        direction TB
        Default[ceph-block-data<br/>RBD Replicated<br/>DEFAULT]
        Bucket[ceph-bucket<br/>S3-compatible<br/>Object Storage]
        FSEC[ceph-fs-data-ec<br/>CephFS Erasure Coded<br/>2+1 EC]
        FSRep[ceph-fs-data-replicated<br/>CephFS Replicated<br/>3× Replica]
        LocalPath[local-path<br/>K3s Local Storage<br/>Single Node]
    end

    subgraph Hardware["🖥️ Physical Hardware"]
        NVMe1[yoda:/dev/nvme0n1<br/>4TB NVMe]
        NVMe2[anakin:/dev/nvme0n1<br/>4TB NVMe]
        NVMe3[obiwan:/dev/nvme0n1<br/>4TB NVMe]
    end

    subgraph AppsLayer["📦 Application Usage"]
        PrometheusApp[Prometheus<br/>→ ceph-block-data]
        NextcloudApp[Nextcloud<br/>→ ceph-fs-data-ec]
        JellyfinApp[Jellyfin<br/>→ ceph-fs-data-ec]
        N8NApp[N8N<br/>→ ceph-block-data]
        OpenWebUIApp[OpenWebUI<br/>→ ceph-block-data]
        JellyfinMedia[Jellyfin Media<br/>Read-Only]
    end

    Operator --> MON
    Operator --> MGR
    Operator --> OSD
    Operator --> MDS

    OSD --> NVMe1
    OSD --> NVMe2
    OSD --> NVMe3

    Default --> OSD
    Bucket --> OSD
    FSEC --> MDS
    FSRep --> MDS
    MDS --> OSD

    PrometheusApp --> Default
    NextcloudApp --> FSEC
    JellyfinApp --> FSEC
    N8NApp --> Default
    OpenWebUIApp --> Default

    style RookCeph fill:#1e3a5f,stroke:#4a90e2,stroke-width:3px
    style Storage fill:#7b1fa2,stroke:#9c27b0,stroke-width:3px
    style Hardware fill:#8b4513,stroke:#d2691e,stroke-width:3px
    style AppsLayer fill:#2d5016,stroke:#5a9216,stroke-width:3px
    style Default fill:#2c5aa0,stroke:#4a90e2,stroke-width:2px,color:#fff
```

**Storage Classes Details:**
- **ceph-block-data** (DEFAULT): Block storage with replication (RBD)
  - Used by: N8N (n8n-main-persistence), OpenWebUI (open-webui)
- **ceph-bucket**: S3-compatible object storage for backups
- **ceph-fs-data-ec**: CephFS with erasure coding (2+1 EC) for large files
  - Used by: Nextcloud (nextcloud-nextcloud), Jellyfin config/cache (jellyfin-config, jellyfin-cache)
- **ceph-fs-data-replicated**: CephFS with 3× replication for high availability
- **local-path**: K3s built-in, single-node local storage
- **No storage class**: Read-only volume mounts (e.g., Jellyfin media library)

**Reclaim Policy:** All Ceph storage classes use `Retain` policy to prevent accidental data loss
