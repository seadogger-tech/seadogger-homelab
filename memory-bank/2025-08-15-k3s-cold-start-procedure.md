# K3s Cluster Cold Start Procedure

**Date:** 2025-08-15

## Overview

This document outlines the standardized procedure for performing a "cold start" of the k3s cluster. A cold start is a process that allows for a complete, controlled rebuild of the cluster. This is essential for verifying the integrity of the Infrastructure as Code (IaaC) setup and ensuring a clean, predictable deployment.

The procedure is now divided into three distinct stages, controlled by master switches in the `ansible/config.yml` file. This allows for granular control over wiping, installing infrastructure, and deploying applications as separate, independent steps.

## Prerequisites

1.  **Ansible Environment:** Ensure your local machine has Ansible installed and is correctly configured to connect to all cluster nodes.
2.  **Configuration Files:** The `hosts.ini` and `config.yml` files in the `ansible` directory must be correctly populated with your network settings and secrets.
3.  **Backup (Optional):** If you have critical data that is not managed by the GitOps workflow, ensure it is backed up before proceeding. Stage 1 is destructive and will wipe all data on the Ceph cluster.

## Stage 1: Wipe Cluster (Destructive)

This stage is controlled by the `cold_start_stage_1_wipe_cluster` flag in `config.yml`. When this flag is set to `true`, the Ansible playbook will perform a complete teardown of the cluster.

### Actions Performed in Stage 1:

*   **Wipe k3s Cluster:** All existing k3s services and data are removed from all nodes.
*   **Wipe Ceph Disks:** The storage disks used by Rook-Ceph are completely wiped. **This is a highly destructive operation.**
*   **Clean ArgoCD Install:** The ArgoCD installation is forcibly removed.

### How to Execute Stage 1:

1.  Open `seadogger-homelab/ansible/config.yml`.
2.  Set `cold_start_stage_1_wipe_cluster: true`.
3.  Ensure the other stage flags are `false`.
4.  From the `seadogger-homelab/ansible` directory, run the main playbook:
    ```bash
    ansible-playbook main.yml
    ```

## Stage 2: Install Infrastructure

This stage is controlled by the `cold_start_stage_2_install_infrastructure` flag in `config.yml`. It deploys the core cluster components onto a clean environment.

### Actions Performed in Stage 2:

*   **Configure Raspberry Pi Nodes:** Applies base configuration and firmware updates.
*   **Deploy k3s:** A new k3s cluster is deployed to the control plane and worker nodes.
*   **Deploy Rook-Ceph (Part 1):** The core Rook-Ceph storage components are deployed.
*   **Automated Kubeconfig:** The `kubeconfig` file is automatically fetched from the master node and configured on your local machine.

### How to Execute Stage 2:

1.  Ensure the cluster is in a clean state (either freshly wiped via Stage 1 or new hardware).
2.  Open `seadogger-homelab/ansible/config.yml`.
3.  Set `cold_start_stage_2_install_infrastructure: true`.
4.  Ensure the other stage flags are `false`.
5.  Run the main playbook:
    ```bash
    ansible-playbook main.yml
    ```
6.  Upon successful completion, you will have a functional k3s cluster with a configured storage layer.

## Stage 3: Application Deployment

This stage is controlled by the `cold_start_stage_3_install_applications` flag in `config.yml`. It deploys the entire suite of applications and services.

### Actions Performed in Stage 3:

*   **Deploy Core Services:** ArgoCD, MetalLB, and the Rook-Ceph NFS server (Part 2) are deployed.
*   **Deploy Applications:** All ArgoCD-managed applications are deployed.

### How to Execute Stage 3:

1.  Ensure Stage 2 has completed successfully.
2.  Open `seadogger-homelab/ansible/config.yml`.
3.  Set `cold_start_stage_3_install_applications: true`.
4.  Ensure the other stage flags are `false`.
5.  Run the main playbook:
    ```bash
    ansible-playbook main.yml
    ```

## Manual and Staged Deployments

The `config.yml` file provides granular control over which applications are deployed. The logic is as follows:

An application's deployment task (e.g., `enable_prometheus`) is only activated if **both** of the following conditions are met:
1.  The master switch for Stage 3, `cold_start_stage_3_install_applications`, is set to `true`.
2.  The specific application's manual switch, `manual_install_prometheus`, is also set to `true`.

This allows you to use the `manual_install_*` flags as a checklist for which applications you want to include in a Stage 3 deployment, preventing accidental deployment of unwanted services. For example, to deploy everything except Plex, you would set `cold_start_stage_3_install_applications: true` and ensure all `manual_install_*` flags are `true` except for `manual_install_plex: false`.

---

## Known Issues: Stage 1 Instability

**Date:** 2025-08-16

### Current Status

The `ansible-playbook main.yml` command, which handles the initial "Stage 1" deployment of the entire cluster, is currently unstable. The playbook frequently fails during the cleanup phase because of file locks and resources on the worker and control plane nodes that fail to release properly.

### Current Workaround

The deployment will eventually complete, but it may require two to four attempts. Because the playbook is designed to be idempotent, each subsequent run will skip the completed tasks and pick up where the last one failed.

### Current Workaround

The deployment can be successfully completed, but it is a messy process that requires manual intervention:

1.  Run `ansible-playbook main.yml`.
2.  Wait for it to fail with the `objc` / `dead state` error.
3.  Immediately re-run `ansible-playbook main.yml`.
4.  Repeat this process several times. Because the playbook is designed to be idempotent, each subsequent run will skip the completed tasks and pick up where the last one failed. Eventually, all tasks will complete successfully.

While this works, it is not an acceptable long-term solution.

### Next Steps: Stabilizing Stage 1

The immediate priority is to refactor the deployment process to make it robust and eliminate the need for manual intervention.

1.  **Refactor `main.yml` into Modular Playbooks:**
    *   The monolithic `main.yml` is too large and complex, increasing the chances of hitting the fork issue. It should be broken down into smaller, purpose-built playbooks.
    *   **Proposed Playbooks:**
        *   `playbook-01-cluster-prep.yml`: Handles OS-level configuration, package installation, and prerequisites.
        *   `playbook-02-k3s-install.yml`: Deploys the K3s cluster itself.
        *   `playbook-03-core-services.yml`: Deploys essential services like storage (Rook-Ceph), networking (MetalLB), and GitOps (ArgoCD).
        *   `playbook-04-applications.yml`: Deploys the user-facing applications (Prometheus, Grafana, Plex, etc.).
    *   This modular approach will allow for more targeted deployments and make debugging significantly easier.

2.  **Isolate the Ansible Environment:**
    *   Investigate running the Ansible playbooks from within a Docker container. This would provide a consistent Linux-based environment for Ansible to execute in, completely bypassing the macOS-specific forking problems.

3.  **Improve Task Idempotency and Error Handling:**
    *   Review all tasks to ensure they are fully idempotent and can recover gracefully from interruptions.
    *   Add more explicit `until` loops and checks to validate the state of the cluster before and after major changes, reducing reliance on long, monolithic plays.

By implementing these changes, we can create a stable, reliable, and repeatable deployment process that aligns with IaC best practices.
