# Stable Deployment and Cold Start Procedure

**Date:** 2025-08-17

## 1. Summary

This document outlines the final, stable storage architecture for the Rook-Ceph cluster and the official, validated procedure for performing a "cold start" (a complete teardown and redeployment) of the entire homelab stack. These changes were the result of extensive troubleshooting to resolve persistent deployment failures and race conditions within the Ansible automation.

## 2. Final Storage Architecture

The storage layer has been re-architected to be stable, efficient, and correctly configured from a clean deployment.

### CEPH Block Storage
-   **Pool:** `ceph-block-data` (Replicated, size 3)
-   **Storage Class:** `ceph-block-data`
-   **Default:** Yes. This is the default storage class for all general-purpose block storage needs.

### CEPH FileSystem Storage
-   **Filesystem Name:** `ceph-fs`
-   **Pools:**
    1.  `ceph-fs-metadata` (Replicated, size 3)
    2.  `ceph-fs-data-replicated` (Replicated, size 3) - The required default data pool.
    3.  `ceph-fs-data-ec` (Erasure Coded, 2+1) - For bulk data.
-   **Storage Classes:**
    1.  `ceph-fs-data-replicated`
    2.  `ceph-fs-data-ec`

This configuration resolves the critical issue where CephFS would fail to initialize because it was incorrectly configured to use an erasure-coded pool as its default data pool.

## 3. IaaC Corrections and Hardening

To support the new architecture and improve reliability, the following changes were made to the Infrastructure-as-Code (IaaC) repository:

1.  **Ansible Playbooks:** All playbooks (`rook_ceph_deploy_part1.yml`, `rook_ceph_deploy_part2.yml`, `cleanup_infrastructure.yml`) were updated to use the new, consistent naming scheme for filesystems, pools, and storage classes.
2.  **Application `values.yaml`:** The Helm `values.yaml` files for all stateful applications (Plex, Prometheus, NFS-Server, OpenWebUI, Nextcloud) were audited and corrected to reference the new, correct `storageClassName`.
3.  **Race Condition Fixes:** Validation tasks were added to the Ansible playbooks to prevent race conditions, such as attempting to create a service in a namespace before the namespace exists.
4.  **Code Cleanup:** The old, monolithic `rook_ceph_deploy.yml` was deleted to prevent its use.

## 4. Official Cold Start Procedure

The following two-step process is the official and validated method for performing a full, destructive cold start of the cluster.

### Step 1: Teardown (`cleanup.yml`)

This playbook is the single entry point for all destructive operations.

1.  **Configure Cleanup:** Edit `ansible/config.yml` and set `cold_start_stage_1_wipe_cluster: true`.
2.  **Execute Cleanup:** Run the command from the `seadogger-homelab/ansible` directory:
    ```bash
    ansible-playbook cleanup.yml
    ```
3.  **(Optional) Deep Clean:** For a full storage wipe, also set `perform_physical_disk_wipe: true` in `config.yml`. **Warning:** This is a data-loss operation and will erase the Ceph partitions.

### Step 2: Installation (`main.yml`)

This playbook is now solely responsible for installation and upgrades.

1.  **Configure Installation:** Edit `ansible/config.yml` and set `cold_start_stage_2_install_infrastructure: true` and `cold_start_stage_3_install_applications: true`.
2.  **Execute Installation:** Run the command from the `seadogger-homelab/ansible` directory:
    ```bash
    ansible-playbook main.yml
    ```

This refined two-step process ensures a reliable and repeatable deployment, which is critical for maintaining the health and stability of the homelab.
