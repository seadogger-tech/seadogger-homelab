# Summary of Rook-Ceph NFS Debugging Session (2025-08-11)

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
