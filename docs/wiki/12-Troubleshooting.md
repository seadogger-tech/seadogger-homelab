![wiki-banner.svg](images/wiki-banner.svg)
# Troubleshooting

![accent-divider](images/accent-divider.svg)
# Ansible Playbook Debugging Session

- **Date:** 2025-08-15
- **Service:** Ansible Deployment
- **Type** Debug / Tech Debt
- **Status:** Complete

## Summary
This document outlines a comprehensive debugging session that resolved a cascading series of failures in the Ansible deployment playbook. The root cause of the initial instability was traced to faulty hardware (a PoE network port), which was causing filesystem corruption on the `anakin.seadogger-homelab` node. Subsequent investigation revealed and corrected multiple latent bugs in the Ansible playbooks.

## Issues and Resolutions

### 1. Initial Node Instability and Filesystem Corruption
- **Symptom:** The `anakin.seadogger-homelab` node was frequently going down, and its root filesystem was mounting as read-only (`ro`). The node also required an SD card to boot despite having its rootfs on an NVMe drive.
- **Investigation:**
  - Confirmed the Pi's EEPROM bootloader was not configured to prioritize the NVMe drive.
  - Identified that running the `wipe_k3s_cluster.yml` playbook was making the node unbootable, suggesting a destructive operation was corrupting the disk.
- **Resolution:**
  - The primary root cause was discovered to be a faulty PoE port on the network switch, which was providing unstable power to the node. Moving the node to a different port resolved the instability.
  - As a preventative measure, a dangerous `sgdisk --zap-all` command, which was likely corrupting the disk's partition table, was commented out from the `wipe_k3s_cluster.yml` playbook.

### 2. Ansible: `iptables: not found`
- **Symptom:** The `wipe_k3s_cluster.yml` playbook failed on the `[Flush all iptables rules]` task with a "command not found" error on freshly imaged nodes.
- **Resolution:** An `ansible.builtin.apt` task was added to the beginning of the `wipe_k3s_cluster.yml` playbook to ensure the `iptables` package is installed on all nodes before it is used.

### 3. Ansible: `sudo: a password is required` on `localhost`
- **Symptom:** The `k3s_control_plane.yml` playbook failed on tasks delegated to `localhost` because it was unnecessarily trying to use `sudo`.
- **Resolution:** The `become: false` directive was added to all tasks delegated to `localhost` within the `k3s_control_plane.yml` playbook, preventing them from attempting privilege escalation on the Ansible controller machine.

### 4. Ansible: `Read-only file system: /root` on `localhost`
- **Symptom:** Even with `become: false`, a delegated task failed while trying to create `~/.kube/config`, with the path incorrectly resolving to `/root/.kube`.
- **Resolution:** The variable `{{ ansible_env.HOME }}` was replaced with `{{ lookup('env', 'HOME') }}` for all `localhost` tasks. This ensures the path correctly resolves to the home directory of the user running the playbook, not the `root` user.

### 5. Ansible: `env_vars is undefined`
- **Symptom:** The `rook_ceph_deploy_part2.yml` playbook failed because it was trying to use an undefined variable `env_vars` for `kubectl` commands.
- **Resolution:** All instances of `environment: "{{ env_vars }}"` were replaced with a correct environment block defining the `KUBECONFIG` variable: `environment: { KUBECONFIG: /etc/rancher/k3s/k3s.yaml }`.

### 6. Configuration Logic Enhancement
- **Symptom:** The user requested stricter control over which applications are deployed.
- **Resolution:** The logic in `config.yml` for all `enable_*` application flags was changed from `or` to `and`. An application is now only deployed if the global `cold_start_stage_3_install_applications` flag is true AND its specific `manual_install_*` flag is also true.

![accent-divider](images/accent-divider.svg)
# Summary of Rook-Ceph NFS Debugging Session

- **Date:** 2025-08-11
- **Service:** Rook-Ceph NFS Ganesha Server
- **Type** Debug / Tech Debt
- **Ansible Playbook:** `seadogger-homelab/ansible/tasks/rook_ceph_deploy.yml`
- **Status:** Deprecated

## 1. Initial Problem

The primary issue was the inability to mount the Rook-Ceph NFS share on any client. The initial investigation pointed towards a networking problem, as the `rook-nfs-loadbalancer` service in the `rook-ceph` namespace was stuck in a `<pending>` state for its external IP address.

## 2. Investigation & Resolution Steps

### Step 2.1: MetalLB Fix

-   **Problem:** The MetalLB deployment, managed by ArgoCD, was failing. Logs from the MetalLB controller indicated a configuration issue.
-   **Analysis:** We inspected the `metallb` ArgoCD application and its corresponding Helm chart configuration in `seadogger-homelab/ansible/tasks/metallb_deploy.yml`.
-   **Root Cause:** A `helm.valueFiles` override was incorrectly pointing to a non-existent values file, which was a remnant from a previous configuration. This caused the entire MetalLB installation to fail.
-   **Resolution:** The faulty `helm.valueFiles` section was removed from `metallb_deploy.yml`. After redeploying the Ansible playbook, MetalLB started correctly, and the `rook-nfs-loadbalancer` service successfully acquired the IP address `192.168.1.254`.

### Step 2.2: NFS Service Annotation Fix

-   **Problem:** Even with a valid IP, the NFS share was still not accessible. Further inspection of the `rook-nfs-loadbalancer` service revealed that while an IP was assigned, it might not have been correctly configured.
-   **Analysis:** We reviewed the service definition within `seadogger-homelab/ansible/tasks/rook_ceph_deploy_part2.yml`.
-   **Root Cause:** The service was using the deprecated `metallb.universe.tf/loadBalancerIPs` annotation to request a specific IP. The correct method for the installed version of MetalLB is to use the `spec.loadBalancerIP` field directly in the service specification.
-   **Resolution:** The YAML in `rook_ceph_deploy_part2.yml` was updated to remove the annotation and add the `spec.loadBalancerIP: 192.168.1.254` field.

### Step 2.3: Client-Specific Mount Failure

-   **Problem:** After fixing the service IP assignment, the NFS share could be successfully mounted from a Linux client (`yoda.local`), but all mount attempts from a macOS client failed with `rpc.gssapi.mechis.mech_gss_log_status: a gss_display_status() failed`.
-   **Analysis:** This error pointed towards a GSSAPI/Kerberos or authentication-level issue. However, given the server was configured for `AUTH_SYS`, this was misleading. To get to the true root cause, we performed a packet capture on the client during a mount attempt using `tcpdump`.
-   **Root Cause:** Analysis of the `nfs_traffic.pcap` file in Wireshark definitively showed the server responding to the macOS client's `NFSv4.1` `CREATE_SESSION` request with an `NFS4ERR_MINOR_VERS_MISMATCH` error. This indicates a fundamental protocol incompatibility between the macOS NFSv4.1 client and the Ganesha NFS server's v4.1 implementation as configured by Rook-Ceph. The Linux client, which likely defaulted to a compatible minor version (or NFSv3), succeeded.
-   **Resolution:** No immediate code fix is possible. This is a known incompatibility. The resolution is to document this limitation and use Linux clients or explore alternative file-sharing solutions for macOS if required.

## 3. Final Conclusion

The `seadogger-homelab` NFS service is correctly configured and fully functional. The inability for macOS clients to connect is not a bug in our configuration but a fundamental protocol version mismatch between the client and the server. The issue is now considered understood and documented as a known limitation.

![accent-divider](images/accent-divider.svg)
# Rook-Ceph NFS Ganesha Debugging Summary Issue #1

- **Date:** 2025-08-10
- **Service:** Rook-Ceph NFS Ganesha Server
- **Type** Debug / Tech Debt
- **Ansible Playbook:** `seadogger-homelab/ansible/tasks/rook_ceph_deploy.yml`
- **Status:** Deprecated

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

![accent-divider](images/accent-divider.svg)
# NFS Troubleshooting Summary Issue #2

- **Date:** 2025-08-10
- **Service:** Rook-Ceph NFS Ganesha Server
- **Type** Debug / Tech Debt
- **Ansible Playbook:** `seadogger-homelab/ansible/tasks/rook_ceph_deploy.yml`
- **Status:** Deprecated

We diagnosed a failing NFS deployment and, after a lengthy investigation, arrived at a definitive solution.

## Problem-Solving Steps:
1.  **Initial State:** The NFS server pods were in a `CrashLoopBackOff` state, and the `LoadBalancer` service was missing.
2.  **Pod Crash Analysis:** Log analysis revealed the pods were crashing due to a Kerberos-related error (`gssd_refresh_krb5_machine_credential`). This was caused by an incorrect security configuration.
3.  **CRD Schema Investigation:** Multiple attempts to fix the configuration via manual `kubectl apply` commands failed due to a fundamental misunderstanding of the `CephNFS` CRD schema for Rook v1.14. We incorrectly assumed the NFS server was configured via a `ganeshaConfig` block or a separate `CephNFSExport` resource.
4.  **Definitive Discovery:** By consulting the official `values.yaml` for the `rook-ceph-cluster` Helm chart (version `release-1.14`), we discovered that the NFS server is **not** configured via the Helm chart at all. It must be deployed as a separate Kubernetes resource.

## Final Plan:
The definitive plan is to manage the `CephNFS` resource declaratively within the Ansible playbook, separate from the Helm release.

1.  **Clean `values.yaml`:** Remove the invalid `cephNFS` block from `deployments/rook-ceph/rook-ceph-cluster-values.yaml`.
2.  **Update Ansible Playbook:** Add a new task to `ansible/tasks/rook_ceph_deploy.yml` that uses the `ansible.builtin.k8s` module to create the `CephNFS` resource directly. This new resource will contain the correct security settings to prevent the pod crash.
3.  **Deploy and Verify:** Run the updated Ansible playbook and verify that the NFS share is accessible.


