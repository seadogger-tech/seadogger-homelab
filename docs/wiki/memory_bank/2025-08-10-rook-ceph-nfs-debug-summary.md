# Rook-Ceph NFS Ganesha Debugging Summary

- **Date:** 2025-08-10
- **Service:** Rook-Ceph NFS Ganesha Server
- **Ansible Playbook:** `seadogger-homelab/ansible/tasks/rook_ceph_deploy.yml`

## Initial Problem

The Ansible playbook deployment consistently failed at the `Verify Ganesha loaded export-100 from RADOS` task. Inspection of the Kubernetes cluster revealed that the `rook-ceph-nfs-nfs-ec-...` pod was in a `CrashLoopBackOff` state.

## Debugging Process

1.  **Log Analysis:**
    - Used `kubectl logs -n rook-ceph rook-ceph-nfs-nfs-ec-... --previous` to inspect the logs of the crashed container.
    - The logs revealed a `Permission denied` error originating from the NFS Ganesha process. This pointed towards an authentication issue with the `cephx` user configured for the CephFS filesystem access.

2.  **Configuration Inspection:**
    - The Ganesha configuration is not stored in a standard ConfigMap but directly within Ceph's RADOS object store.
    - The Ansible playbook creates a RADOS object named `export-100` in the `.nfs` pool within the `nfs-ec` namespace.
    - The `FSAL` (File System Abstraction Layer) block within this object contained the `cephx` credentials.

3.  **Identifying the Root Cause:**
    - The `User_Id` in the `FSAL` block was set to `client.nfs.nfs-ec`.
    - Through research and analysis of Ganesha's behavior with Ceph, it was discovered that Ganesha automatically prepends the `client.` prefix to the `User_Id` when authenticating.
    - This resulted in an incorrect, double-prefixed user ID being sent to Ceph (`client.client.nfs.nfs-ec`), causing the authentication to fail and the pod to crash.

## Implemented Solution

1.  **Corrected `User_Id`:**
    - The `fsal_user_id` variable in the Ansible playbook was changed to provide the user ID *without* the `client.` prefix (i.e., `"nfs.nfs-ec"`).
    - This allowed Ganesha to correctly form the `cephx` user ID (`client.nfs.nfs-ec`) and successfully authenticate with the Ceph cluster.

2.  **Improved Verification Task:**
    - The verification task in the Ansible playbook was prone to shell-specific errors (`Illegal option -o pipefail`).
    - The task was updated to explicitly use `/bin/bash` as the executable, ensuring consistent behavior.
    - The `grep` command's regex was also made more flexible to reliably detect the "export created" message in the Ganesha logs.

3.  **Removed Redundant Task:**
    - The playbook contained a task to create the `.nfs` metadata pool for Ganesha.
    - It was determined that Rook creates this pool automatically when the `CephNFS` CRD is created.
    - This redundant task was removed to simplify the playbook and prevent potential conflicts.

## Outcome

After applying these fixes, the Ansible playbook `seadogger-homelab/ansible/tasks/rook_ceph_deploy.yml` executed successfully from start to finish. The `rook-ceph-nfs` pod now starts up and remains in a stable, `Running` state.

## Next Steps

Although the deployment is now successful, a subsequent manual test to mount the NFS share from a client machine failed with a timeout. Initial investigation with `kubectl get svc -n rook-ceph` revealed that the `rook-nfs-loadbalancer` service was being assigned multiple external IP addresses by MetalLB, instead of the single static IP (`192.168.1.253`) defined in its configuration. The next phase of work will be to diagnose and resolve this MetalLB issue.
