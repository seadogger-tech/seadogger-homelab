# K3s Cluster Cold Start Procedure (Revised)

- **Date:** 2025-08-16
- **Status:** Active

## Overview

This document outlines the official procedure for performing a full, destructive "cold start" of the Kubernetes cluster. This process is used to validate the Infrastructure as Code (IaaC) configuration from a clean slate.

The cold start process has been significantly refactored to improve safety, clarity, and reliability. It is now a deliberate, two-playbook process that separates destruction from installation.

## Procedure

### Step 1: Cluster Teardown (`cleanup.yml`)

The `cleanup.yml` playbook is the single entry point for all destructive operations.

1.  **Configure Teardown:** Open `ansible/config.yml` and set the following master switch to `true`:
    ```yaml
    cold_start_stage_1_wipe_cluster: true
    ```
2.  **(Optional) Configure Disk Wipe:** For a complete teardown that includes wiping the Ceph OSD partitions, also set the following flag to `true`.
    ```yaml
    # WARNING: This is a data-loss operation for the Ceph cluster.
    perform_physical_disk_wipe: true
    ```
3.  **Execute Teardown:** Run the cleanup playbook from the `ansible` directory.
    ```bash
    ansible-playbook cleanup.yml
    ```
    This command will execute a graceful, ordered teardown of all applications and infrastructure *before* wiping the k3s installation from all nodes.

The `cleanup.yml` playbook is organized into three stages:
1.  **Application and Service Cleanup:** This stage iterates through the `pod_cleanup_list` in `config.yml` and gracefully removes each application.
2.  **Core Infrastructure Cleanup:** This stage removes the core infrastructure components (Prometheus, ArgoCD, MetalLB, and Rook-Ceph) in the correct order.
3.  **Cluster Wipe:** This stage performs a full, destructive wipe of the k3s cluster.

### Step 2: Cluster Installation (`main.yml`)

The `main.yml` playbook is now solely responsible for installation and idempotent upgrades.

1.  **Configure Installation:** Open `ansible/config.yml` and set the following master switches to `true`. Ensure the wipe switches from Step 1 are set back to `false`.
    ```yaml
    cold_start_stage_2_install_infrastructure: true
    cold_start_stage_3_install_applications: true
    ```
    This will enable the native deployment of MetalLB and ArgoCD as part of the infrastructure stage.
2.  **Execute Installation:** Run the main playbook from the `ansible` directory.
    ```bash
    ansible-playbook main.yml
    ```
    This command will configure the nodes, install k3s, deploy the core infrastructure, and then deploy all applications.

## Known Issues

- The initial installation of Rook-Ceph can sometimes be slow or require a second run if the OSDs take a long time to initialize. The playbook has been made more robust, but this remains an area for observation.
