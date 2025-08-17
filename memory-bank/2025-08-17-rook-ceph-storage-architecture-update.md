# Rook-Ceph Storage Architecture Update

**Date:** 2025-08-17

## 1. Problem Summary

The Rook-Ceph cluster deployment was consistently failing. The primary symptom was that the Ceph Filesystem (CephFS) Metadata Server (MDS) pods were stuck in a `standby` state, preventing the filesystem from becoming active. This blocked all dependent applications from utilizing CephFS.

## 2. Investigation and Root Cause

A thorough investigation of the `rook-ceph-operator` logs revealed an `exit status 22` (Invalid Argument) error during the CephFS creation process. Manually executing the underlying `ceph fs new` command exposed the root cause:

`Error EINVAL: pool 'ec-fs-data' is an erasure-coded pool. Use of an EC pool for the default data pool is discouraged... Use --force to override.`

The core issue was a fundamental design flaw in the Helm-based deployment. The `rook-ceph-cluster-values.yaml` was configured to create a CephFS using only an erasure-coded (EC) pool as its data pool. Ceph intentionally prevents this configuration by default because EC pools have limitations (e.g., overwrites can be inefficient) that make them unsuitable as the *sole* or *default* data pool for a filesystem. The Rook operator does not use the `--force` flag, leading to the persistent failure.

The key realization was that **CephFS requires at least one replicated data pool to function correctly when deployed via the Rook Helm chart.**

## 3. New Architectural Design

To resolve this issue and create a stable, idempotent, and flexible storage backend, the following architecture was designed and implemented.

### CEPH Block Storage
-   **Filesystem Name:** `ceph-block`
-   **Pool:** `ceph-block-data` (Replicated)
-   **Storage Class:** `ceph-block-data` (This is the default StorageClass for general-purpose PVCs)

### CEPH FileSystem Storage
-   **Filesystem Name:** `ceph-fs`
-   **Pools:**
    1.  `ceph-fs-metadata` (Replicated): For filesystem metadata.
    2.  `ceph-fs-data-replicated` (Replicated): The required default data pool for the filesystem.
    3.  `ceph-fs-data-ec` (Erasure Coded): For high-efficiency bulk data storage.
-   **Storage Classes:**
    1.  `ceph-fs-data-replicated`: Tied to the replicated data pool.
    2.  `ceph-fs-data-ec`: Tied to the erasure-coded data pool, for applications that can leverage it.

## 4. Implementation and IaaC Changes

The new architecture was implemented by making the following changes to the `seadogger-homelab` Infrastructure-as-Code repository:

1.  **`helm-deployments/rook-ceph/rook-ceph-cluster-values.yaml`:**
    *   Updated to define the `ceph-block` and `ceph-fs` filesystems with their corresponding pools and storage classes as detailed above.
    *   Pool names were corrected to their base names (e.g., `data-replicated`), as the Rook operator automatically prepends the filesystem name.

2.  **`ansible/tasks/rook_ceph_deploy_part1.yml`:**
    *   The validation task was updated to check for the existence of the new, correctly named pools (`ceph-fs-metadata`, `ceph-fs-data-replicated`, `ceph-fs-data-ec`).
    *   The task to set the default storage class was updated to target `ceph-block-data`.

3.  **`ansible/tasks/rook_ceph_deploy_part2.yml`:**
    *   All hardcoded references to the old filesystem (`ec-fs`) and its associated resources were updated to `ceph-fs`.

4.  **`ansible/tasks/cleanup_infrastructure.yml`:**
    *   The teardown script was updated to correctly identify and delete the newly named StorageClasses, CephFilesystem, and CephNFS resources.

5.  **`ansible/tasks/rook_ceph_deploy.yml`:**
    *   This outdated, monolithic deployment file was deleted to prevent confusion.

6.  **Application Helm Values (`nfs-server`, `plex`, `prometheus`, `nextcloud`):**
    *   All `values.yaml` files were reviewed, and any hardcoded `storageClassName` was updated from `ceph-block` or `rook-ceph-filesystem-ec` to the new, correct names (`ceph-block-data` or `ceph-fs-data-ec`).
    *   A new `nextcloud-values.yaml` was created to ensure it uses the correct storage class.

This comprehensive update ensures the entire storage infrastructure is now correctly defined in code, leading to a reliable and repeatable deployment process.
