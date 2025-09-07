# Summary of Cluster Recovery and Playbook Hardening Session

- **Date:** 2025-08-16
- **Status:** Completed

## 1. Overview

This document details an intensive debugging and hardening session that transformed the `cleanup.yml` and `wipe_k3s_cluster.yml` Ansible playbooks into a robust disaster recovery solution. The initial goal was to test a refactored cleanup process, but the effort quickly pivoted to a full-scale cluster recovery upon discovering a deeply corrupted Kubernetes state.

## 2. Initial State and Problem Discovery

The session began with the intent to run the `cleanup.yml` playbook. However, the playbook failed immediately, revealing that the cluster was in a non-responsive state. Initial investigation using `kubectl` showed multiple resources, including the `rook-ceph` and `ingress-nginx` namespaces, stuck in a "Terminating" state. Even a full reboot of all cluster nodes failed to resolve the issue, indicating a persistent corruption in the `etcd` datastore.

## 3. Troubleshooting and Manual Intervention

With the automated playbooks unable to proceed, we shifted to manual intervention using `kubectl`:

- **Forced Namespace Deletion:** We attempted to forcefully delete the stuck namespaces by removing their finalizers. This involved retrieving the namespace definition as JSON, removing the `finalizers` array, and `PUT`ing the modified definition back to the API server via a temporary proxy.

- **Identifying the Root Cause:** The inability to delete namespaces even after removing finalizers confirmed that the `etcd` datastore, the core of the Kubernetes control plane, was irreparably corrupted. At this point, the only viable path forward was a complete and destructive wipe of the k3s installation on all nodes.

## 4. Hardening the `wipe_k3s_cluster.yml` Playbook

The focus shifted to improving the `wipe_k3s_cluster.yml` playbook to ensure it could reliably clean a cluster in any state, including the corrupted one we faced. The following key improvements were made iteratively:

1.  **Correct Play Targeting:** The parent `cleanup.yml` playbook was refactored. API-dependent cleanup tasks (like deleting resources) were targeted specifically at the `control_plane`, while the destructive wipe tasks were targeted at `all` nodes. This corrected a fundamental logic error.

2.  **Elimination of Faulty Logic:** A "graceful cleanup" section at the beginning of the wipe playbook was removed. It was redundant and prone to failure on a corrupted cluster, preventing the more robust wipe commands from ever running.

3.  **Idempotency via `stat` Checks:** The playbook was made idempotent by adding checks before acting. Instead of blindly trying to stop services or run uninstall scripts (and failing if they didn't exist), we used the `stat` module to verify their existence first. This allows the playbook to run successfully on a clean system without generating errors.

4.  **Intelligent Final State Verification:** The most critical improvement was the addition of a final verification block. This block uses `lsblk` to check the filesystem type of the Ceph storage partition (`/dev/nvme0n1p3`) and asserts that its state matches the desired policy.
    -   If `perform_physical_disk_wipe` is `true`, it asserts the partition is completely empty.
    -   If `perform_physical_disk_wipe` is `false`, it asserts the partition is either empty or still formatted as `ceph_bluestore`.
    -   This provides definitive proof that the playbook achieved the desired end state.

## 5. Final Outcome

After multiple iterations and refinements, the final version of the `cleanup.yml` and `wipe_k3s_cluster.yml` playbooks was run against the corrupted cluster. The playbook executed flawlessly from start to finish, successfully wiping the k3s installation, cleaning up all associated files, and leaving the nodes in a pristine state, ready for a fresh installation. The final verification step passed, confirming the success of the operation.

## 6. Lessons Learned

-   **Robust Automation is Crucial:** A simple uninstall script is not enough for disaster recovery. A truly robust playbook must be idempotent and intelligent enough to handle unexpected states without failing.
-   **Verification is Key:** Don't just assume a task succeeded. A good automation process includes final verification steps to assert that the system is in the expected state.
-   **Understand the System:** When automation fails, a deep understanding of the underlying system (in this case, Kubernetes `etcd` and finalizers) is essential for effective manual intervention.
