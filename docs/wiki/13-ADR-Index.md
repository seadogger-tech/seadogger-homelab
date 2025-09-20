![wiki-banner.svg](images/wiki-banner.svg)
![accent-divider](images/accent-divider.svg)
# ADR Index

![accent-divider](images/accent-divider.svg)
### ADR-008: Ceph Dashboard Ingress Configuration

- **Status:** Implemented & Verified
- **Date:** 2025-08-29

#### Context
The Ceph dashboard was initially exposed via a LoadBalancer service with SSL disabled, which presented several security and accessibility challenges:
- Direct LoadBalancer exposure increased the attack surface
- Lack of SSL encryption for dashboard access
- Inconsistent with other services in the cluster that use Traefik Ingress

#### Decision
Migrate the Ceph dashboard to use Traefik Ingress with the following key changes:
1. Create a Traefik IngressRoute with both HTTP and HTTPS routes
2. Utilize the existing cert-manager certificate for TLS
3. Enable SSL in the Ceph dashboard configuration
4. Set the dashboard port to 7000
5. Configure a URL prefix for the dashboard

#### Consequences
- **Positive:**
  - Improved security through Traefik Ingress
  - Consistent with other services in the cluster
  - SSL encryption enabled
  - Reuses existing TLS certificate
- **Negative:**
  - Slight increase in complexity compared to direct LoadBalancer
- **Next Steps:**
  - Monitor dashboard accessibility
  - Ensure proper authentication mechanisms are in place

![accent-divider](images/accent-divider.svg)
### ADR-007: Cluster Wipe and Cleanup Playbook Hardening

- **Status:** Implemented & Verified
- **Date:** 2025-08-16

#### Context

During a routine test of the refactored `cleanup.yml` playbook, the cluster was found to be in a severely corrupted state from a previous failed installation. Resources were stuck in a "Terminating" state, namespaces could not be deleted, and the `etcd` datastore was inconsistent. This prevented any automated cleanup or installation playbooks from running successfully, necessitating a deep debugging and hardening session.

#### Decision

The `wipe_k3s_cluster.yml` task was significantly refactored and hardened to transform it from a simple script into a robust, idempotent, and intelligent disaster recovery tool. The `cleanup.yml` playbook was also improved to correctly orchestrate the wipe.

1.  **Refactored `cleanup.yml` Logic:** The playbook was restructured into a two-play playbook. The first play targets the `control_plane` for API-dependent tasks (like deleting namespaces), and the second play targets `all` nodes for the destructive wipe actions (like running `k3s-uninstall.sh`). This ensures the correct nodes are targeted for each task.

2.  **Removed Faulty "Graceful" Cleanup:** A redundant and error-prone "graceful cleanup" section was removed from the beginning of the `wipe_k3s_cluster.yml` task. This logic was unreliable on a corrupted cluster and was duplicative of the main wipe actions.

3.  **Intelligent Service/File Checks:** All tasks that stop services or run uninstall scripts were updated to first check for the existence of the service or script using the `stat` module. This makes the playbook idempotent, allowing it to run on a clean or partially cleaned system without generating "file not found" or "service not found" errors.

4.  **Robust Final Verification:** A sophisticated verification block was added to the end of the playbook to assert the final state of the Ceph storage partition (`/dev/nvme0n1p3`). This assertion is intelligent and adapts its expectation based on the `perform_physical_disk_wipe` flag, ensuring the cluster is left in the desired state.

    ```yaml
    # Final verification logic
    - name: "Assert partition state matches expected policy"
      ansible.builtin.assert:
        that:
          - >
            (perform_physical_disk_wipe | default(false))
            | ternary(
                (fs_check.stdout | trim) == "",
                (fs_check.stdout | trim) in ["", "ceph_bluestore"]
              )
    ```

#### Consequences

-   **Positive:**
    -   The `wipe_k3s_cluster.yml` playbook is now a highly reliable and idempotent tool for disaster recovery, capable of cleaning a cluster in almost any state.
    -   The playbook can be run multiple times on a clean system without producing errors, which is a key principle of good automation.
    -   The risk of failed cleanup runs leaving the cluster in an inconsistent state is significantly reduced.
-   **Negative:**
    -   None. The changes dramatically improved the reliability and robustness of the cluster management automation.

![accent-divider](images/accent-divider.svg)
### ADR-006: Refactor Ansible Playbooks to Fix Circular Dependency

- **Status:** Implemented & Verified
- **Date:** 2025-08-16

#### Context

A circular dependency was identified in the Ansible playbooks where ArgoCD was responsible for deploying MetalLB, but ArgoCD itself required a LoadBalancer from MetalLB to be fully functional. This created a bootstrapping problem and made the deployment process fragile.

#### Decision

The deployment process was refactored to follow a logical, sequential deployment of infrastructure components *before* any applications are deployed.

1.  **Refactored `main.yml` Deployment Order:** The `main.yml` playbook was restructured to deploy Rook-Ceph, then MetalLB, then ArgoCD, and finally the applications.
2.  **Created New Native Helm Deployment Tasks:** New tasks were created to deploy MetalLB and ArgoCD directly using Helm, removing the dependency on ArgoCD for their installation.
3.  **Refactored `cleanup.yml`:** The `cleanup.yml` playbook was updated to reflect the new deployment order, ensuring that applications are removed before the infrastructure they depend on.
4.  **Updated `config.yml` and Documentation:** The `config.yml` and `example.config.yml` files were updated to include new flags for the native deployments, and the documentation was updated to reflect the new deployment and cleanup procedures.
5.  **Cleaned Up Old Files:** The old, now-redundant deployment files were deleted.

#### Consequences

-   **Positive:**
    -   The circular dependency between ArgoCD and MetalLB has been resolved.
    -   The deployment process is now more logical, robust, and idempotent.
-   **Negative:**
    -   None. The change corrected a fundamental design flaw.

![accent-divider](images/accent-divider.svg)
### ADR-005: Ansible Playbook Robustness and Logic Corrections

- **Status:** Implemented & Verified
- **Date:** 2025-08-15

#### Context
During a deployment attempt on a freshly imaged cluster, a cascading series of failures occurred in the Ansible playbooks. The initial root cause was traced to unstable power from a faulty PoE network switch port, which led to filesystem corruption on one node. Resolving this uncovered several latent bugs in the playbooks that prevented them from running successfully in a clean environment.

#### Decision
A series of fixes were implemented to make the Ansible automation more robust, idempotent, and logically correct. For a full chronological detail of the debugging session, see the entry `memory-bank/2025-08-15-ansible-playbook-debugging-session.md`.

The key decisions were:

1.  **Add `iptables` Dependency:** The `wipe_k3s_cluster.yml` playbook failed with a "command not found" error because it assumed `iptables` was installed. A task was added to the beginning of the playbook to ensure the `iptables` package is present on all nodes.

2.  **Correct `localhost` Delegation:** Multiple tasks delegated to `localhost` (the Ansible controller) were failing with `sudo: a password is required` or `Read-only file system: /root` errors. This was caused by tasks inheriting a play-level `become: true` and Ansible incorrectly resolving the user's home directory.
    -   All delegated `localhost` tasks had `become: false` added to prevent unnecessary privilege escalation.
    -   The `{{ ansible_env.HOME }}` variable was replaced with `{{ lookup('env', 'HOME') }}` to ensure the correct local user's home directory is always used.

3.  **Fix Undefined `env_vars` Variable:** The `rook_ceph_deploy_part2.yml` playbook failed because it referenced an undefined variable `env_vars`. This was corrected by replacing the reference with the proper `environment: { KUBECONFIG: ... }` block for `kubectl` commands.

4.  **Stricter `config.yml` Logic:** The logic for enabling application deployments in `config.yml` was changed from `or` to `and`. This provides more granular control, requiring both the global stage flag (e.g., `cold_start_stage_3_install_applications`) and the individual application's manual flag (e.g., `manual_install_prometheus`) to be `true` for a deployment to run.

#### Consequences

-   **Positive:**
    -   The playbooks are now significantly more robust and can run successfully on freshly imaged nodes without manual intervention.
    -   The logic for enabling/disabling deployment stages is stricter and less prone to accidental execution.
    -   The fixes for `localhost` delegation follow Ansible best practices.
-   **Negative:**
    -   None. The changes corrected clear bugs and improved the automation's reliability.

![accent-divider](images/accent-divider.svg)
### ADR-004: Prometheus Stack Network Policy Configuration

- **Status:** Implemented & Verified
- **Date:** 2025-08-15

#### Context
The Prometheus monitoring stack deployment initially faced accessibility issues due to restrictive network policies. The default policies from kube-prometheus only allowed internal cluster communication, preventing external access to the Prometheus, Grafana, and Alertmanager UIs through their LoadBalancer services.

#### Decision
We implemented custom network policies in the Ansible deployment playbook to allow external access while maintaining security. The solution involved:

1. Creating separate network policies for each component:
   - Prometheus (port 9090)
   - Grafana (port 3000)
   - Alertmanager (port 9093)

2. Using pod label selectors to precisely target each component:
   ```yaml
   podSelector:
     matchLabels:
       app.kubernetes.io/name: prometheus  # Similar for grafana and alertmanager
   ```

3. Allowing ingress traffic to specific ports while maintaining existing internal cluster communication rules.

4. Integrating the network policy deployment into our Ansible playbook to ensure consistent application through our GitOps workflow.

#### Consequences

- **Positive:**
  - All monitoring UIs are now accessible via their LoadBalancer IPs
  - Security is maintained through specific port and pod targeting
  - Configuration is version controlled and automated
  - Solution integrates cleanly with our existing GitOps practices

- **Negative:**
  - None significant. The implementation follows best practices for network security while enabling required functionality.

- **Next Steps:**
  - Configure Grafana dashboards
  - Set up alerting rules
  - Configure external service monitoring

#### Context

After successfully configuring the Rook-Ceph NFS server and verifying its accessibility from a Linux client (`yoda.local`), all attempts to mount the NFS share from a macOS client failed. The error message on the macOS client was `rpc.gssapi.mechis.mech_gss_log_status: a gss_display_status() failed`, which misleadingly suggested a Kerberos or GSSAPI authentication issue, even though the server was configured for simple `AUTH_SYS`.

#### Decision

To diagnose the issue at a protocol level, a packet capture (`tcpdump`) was performed on the macOS client during a mount attempt. Analysis of the resulting `nfs_traffic.pcap` file in Wireshark revealed the true root cause.

The macOS client initiated the connection using NFSv4.0. The Rook-Ceph Ganesha NFS server, which was expecting a v4.1+ session, responded to the client's initial request with an `NFS4ERR_MINOR_VERS_MISMATCH` error. This error indicates a fundamental incompatibility between the specific minor version of the NFSv4 protocol implemented by the macOS client and the one implemented by the NFS-Ganesha server in this version of Rook-Ceph.

Since this is a protocol-level incompatibility and not a configuration error on our part, no further configuration changes on the server can resolve it. The decision is to accept this as a known limitation of the current setup.

#### Consequences

-   **Positive:**
    -   The root cause of the mount failure is definitively identified and understood.
    -   Prevents future time wasted on debugging this specific client-server combination.
    -   The NFS service remains fully functional and accessible for compatible clients (e.g., Linux).

-   **Negative:**
    -   The NFS share cannot be used by macOS clients in its current state.
    -   Future workarounds might involve using a different file sharing protocol for macOS (like Samba) or waiting for future updates to either the macOS client or the NFS-Ganesha server that might resolve the version mismatch.

![accent-divider](images/accent-divider.svg)
### ADR-003: NFS Client Incompatibility (macOS)

- **Status:** Implemented & Verified
- **Date:** 2025-08-11

#### Decision

We adopted Nextcloud to serve media to the media player instead on using NFS.

![accent-divider](images/accent-divider.svg)
### ADR-002: MetalLB Webhook and ArgoCD Configuration

- **Status:** Implemented & Verified
- **Date:** 2025-08-11

#### Context

Following the successful deployment of the Rook-Ceph NFS server, the `mount` command from a client failed with a timeout. Investigation revealed that the `rook-nfs-loadbalancer` service had a `<pending>` external IP, indicating that MetalLB was failing to assign one.

#### Decision

The investigation traced the failure to the `metallb-config` ArgoCD application, which was failing to sync because a required `metallb-webhook-service` was not found. The root cause was an incorrect configuration in the main `metallb` ArgoCD application within `seadogger-homelab/ansible/tasks/metallb_deploy.yml`. It was using a `valueFiles` entry that pointed to a raw manifest instead of a Helm values file, which prevented the main MetalLB chart from deploying all its required components.

The fix involved removing the incorrect `valueFiles` override from the `metallb` ArgoCD application definition. This allowed the main MetalLB chart to deploy correctly, including the essential webhook service. Once the webhook was running, the `metallb-config` application could sync successfully, create the `IPAddressPool`, and assign the external IP to the NFS service.

#### Consequences

-   **Positive:**
    -   MetalLB now deploys correctly and reliably assigns IP addresses to LoadBalancer services.
    -   The NFS share is now accessible from outside the cluster.
-   **Negative:**
    -   None. The change corrected a fundamental misconfiguration.

![accent-divider](images/accent-divider.svg)
### ADR-001: NFS Ganesha Configuration for Rook-Ceph v1.17.7 (Deprecated by ADR-003 & ADR-004)

- **Status:** Deprecated Capability (Replaced with Nextcloud)
- **Date:** 2025-08-10

#### Context

The project required a stable, persistent, and shareable storage solution for various applications within the Kubernetes cluster (e.g., Plex, N8N). The chosen storage backend is a Rook-Ceph cluster utilizing an erasure-coded CephFS filesystem for data efficiency. The goal was to expose this CephFS filesystem via an NFS share.

Initial attempts to configure the NFS share using high-level abstractions provided by Rook-Ceph failed. Specifically, for Rook version `v1.17.7`, the following approaches were unsuccessful:
1.  Defining the NFS server and export via the `cephNFS` block in the Helm `values.yaml` for the `rook-ceph-cluster` chart.
2.  Creating a `CephNFSExport` Custom Resource Definition (CRD) to define the share.
3.  Using the `ceph fs export create` command from within the `rook-ceph-tools` pod, which was not available in this version.

These failures led to the conclusion that the standard, documented methods were not applicable to this specific, and somewhat dated, version of Rook-Ceph. The deployment consistently failed during the Ansible task designed to verify the NFS Ganesha server startup, with the `rook-ceph-nfs` pod entering a `CrashLoopBackOff` state.

#### Decision

We adopted a low-level configuration approach that bypasses the high-level Rook APIs and interacts directly with the underlying RADOS (Reliable Autonomic Distributed Object Store) layer of Ceph. This method is the canonical way Ganesha itself is configured when using Ceph as a backend.

The implemented solution, codified within the `seadogger-homelab/ansible/tasks/rook_ceph_deploy.yml` playbook, involved several key fixes:

1.  **Correct `cephx` User ID Format:** The primary issue causing the `CrashLoopBackOff` was an authentication failure within Ganesha. The `User_Id` in the `FSAL` block of the RADOS export configuration was incorrectly specified as `"client.nfs.nfs-ec"`. Ganesha automatically prepends the `client.` prefix, resulting in a malformed user ID (`client.client.nfs.nfs-ec`) and a `Permission denied` error. The fix was to provide the `User_Id` without the prefix.

    ```yaml
    # Snippet from the corrected EXPORT object configuration
    EXPORT {
      # ... other parameters
      FSAL {
        Name = CEPH;
        User_Id = "nfs.nfs-ec"; # Corrected: Removed "client." prefix
        Secret_Access_Key = "{{ nfs_user_key }}";
        Filesystem = "ec-fs";
      }
    }
    ```

2.  **Robust Verification Task:** The Ansible task to verify the Ganesha export was made more resilient. It was modified to use `/bin/bash` explicitly to avoid `pipefail` errors on certain shells and the log-checking regex was improved for more reliable detection of the successful export creation.

3.  **Playbook Cleanup:** A redundant `Create Ganesha metadata pool` task was removed from the playbook. Rook automatically creates the necessary `.nfs` pool, making this task unnecessary and a potential source of conflict.

4.  **RADOS Configuration Update:** The core logic remains the same: create a RADOS object for the export configuration and update the main Ganesha config object (`conf-nfs.nfs-ec`) to point to it using a `%url` directive.

    ```
    %url "rados://.nfs/nfs-ec/export-100"
    ```

5.  **Pod Reload:** After the RADOS configuration is updated, the `nfs-nfs-ec-*` pods are reloaded to force them to read the new configuration from RADOS and apply the changes.

This entire process is now idempotent and fully automated via the Ansible playbook, ensuring the NFS share can be reliably provisioned.

#### Consequences

-   **Positive:**
    -   Provides a stable, working NFS share on the desired erasure-coded CephFS backend. The Ansible playbook now completes successfully.
    -   The solution is automated and idempotent, aligning with the project's GitOps principles.
    -   The configuration and the logic behind the fix are now explicitly documented and managed in source control.

-   **Negative:**
    -   The solution is highly specific to this version of Rook-Ceph and the underlying Ganesha implementation. It may break with future upgrades if the low-level configuration mechanism changes.
    -   It requires a deeper understanding of Ceph and RADOS to troubleshoot, as the configuration is abstracted away from the more user-friendly Kubernetes CRDs.

-   **Next Steps:**
    -   The NFS deployment is now fully functional.
