# Ansible Deployment Idempotency Refactor Plan

- **Date:** 2025-08-16
- **Status:** Agreed upon. Pending implementation.

## 1. Problem Statement

The current Ansible deployment process for many applications follows a destructive "delete namespace and redeploy" pattern. This causes instability and failures, particularly with shared infrastructure components like MetalLB and Rook-Ceph, which cannot be torn down without affecting other running applications. The goal of this refactor is to move to a fully idempotent deployment model, where playbooks can be run multiple times safely, only applying changes as needed.

## 2. Core Strategy

The strategy is to externalize all cleanup and teardown logic from the deployment playbooks into a new, centralized, and intelligent cleanup mechanism. Deployment playbooks will be refactored to be purely idempotent, responsible only for installation and upgrades.

## 3. Deployment Classification

To handle the unique needs of different components, deployments are classified into three patterns:

| Pattern | Components | Characteristics |
| :--- | :--- | :--- |
| **Infrastructure** | `rook-ceph`, `metallb` | Core services with complex dependencies, CRDs, and potential for hanging finalizers. Require a careful, ordered teardown. |
| **Hybrid** | `prometheus` | An application that also installs cluster-wide CRDs. Requires special cleanup handling for these CRDs. |
| **POD Application**| All others (`plex`, `pihole`, `n8n`, etc.) | Self-contained applications, managed via ArgoCD. Can be cleaned up uniformly, with consideration for PVCs and pre-deployment secrets. |

## 4. Phase 1: New Multi-Stage Cleanup Playbook

A new `ansible/cleanup.yml` playbook will be created to orchestrate a graceful, multi-stage teardown.

- **Correct Teardown Order:**
    1.  **Clean POD Applications:** (`tasks/cleanup_pods.yml`) Terminates user-facing apps, releasing dependencies on infrastructure.
    2.  **Clean Prometheus (Hybrid):** (`tasks/cleanup_prometheus.yml`) A dedicated task to tear down the monitoring stack and its CRDs.
    3.  **Clean Infrastructure:** (`tasks/cleanup_infrastructure.yml`) Safely terminates MetalLB and Rook-Ceph after all dependents are gone.

- **Features (Hybrid Model):**
    - **Discovery-Based Cleanup:** For the POD Application pattern, the cleanup task will use a label selector to automatically discover and delete all associated namespaced resources (Services, Deployments, etc.). This reduces configuration and adapts to changes in Helm charts.
    - **Explicit Control for Critical Resources:**
        - **PVCs:** A `delete_pvc: true/false` flag in the config provides a deliberate safety mechanism to prevent accidental data loss.
        - **CRDs:** Cleanup of cluster-scoped CRDs (for Prometheus, Rook-Ceph) will be handled explicitly in dedicated, ordered tasks, never via discovery.
    - The infrastructure cleanup for Rook-Ceph remains a surgical, ordered process that **will not** touch physical disks.

## 5. Phase 2: Refactor All Deployment Playbooks

Every deployment task file in `ansible/tasks/` will be refactored:

- **All destructive logic will be removed.** No more `helm uninstall`, `kubectl delete namespace`, or disk wiping commands.
- The standard deployment method will be `helm upgrade --install --create-namespace` or `kubectl apply`, ensuring idempotency.
- Playbooks will be simplified to only handle secrets/config creation and the idempotent deployment itself.
- Unique characteristics, like the `kubectl patch` in the `n8n` deploy, will be preserved.

## 6. Phase 3: Overhaul `wipe_k3s_cluster.yml` (Cold Start)

The cold start playbook will be made safer and more reliable.

1.  **Rename:** The file will be renamed to `wipe_k3s_cluster.yml` for consistency.
2.  **Integrate Graceful Cleanup:** The playbook will now begin by executing the new three-stage cleanup process (PODs -> Prometheus -> Infrastructure). This ensures a clean state before attempting to uninstall k3s.
3.  **Isolate Destructive Operations:**
    - The `wipe_ceph_disks_on_install` variable will be **removed**.
    - A new, explicit variable, `perform_physical_disk_wipe: false`, will be introduced in `config.yml`.
    - The disk wiping tasks (`sgdisk --zap-all`, `dd`) in the wipe playbook will be gated *exclusively* by this new flag, making data loss a deliberate, explicit action.

This plan ensures a transition to a robust, safe, and idempotent deployment system that respects dependencies and separates application lifecycle from destructive cluster operations.

## 7. Future Tasks & Technical Debt

As a result of this analysis, the following items have been identified as technical debt to be addressed in the future:

1.  **Integrate Prometheus CRDs into Helm Chart:** The current practice of applying Prometheus CRDs from external URLs is brittle. A future task should investigate methods to vendor these CRDs directly into a custom Helm chart or leverage a chart that properly manages its own CRD lifecycle. This would simplify the deployment and cleanup logic.
2.  **Resolve `n8n` Helm Values "Hack":** The `n8n-deploy.yml` playbook contains a `kubectl patch` command to set an environment variable because the Helm values file is not working as expected. This should be investigated and fixed in the `n8n-values.yaml` file, allowing the removal of the patch command. This is tentatively linked to the future implementation of HTTPS, which may alter cookie requirements.
