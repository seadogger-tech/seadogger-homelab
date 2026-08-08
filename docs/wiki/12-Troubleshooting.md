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



![accent-divider.svg](images/accent-divider.svg)
## ArgoCD GitHub Authentication Failures

- **Date:** 2026-03-07
- **Service:** ArgoCD
- **Type:** Authentication / GitOps
- **Status:** Known Issue - GitHub App migration needed
- **Update (2026-07-21):** `portal` and `velero-ui` both synced cleanly
  throughout a long session of frequent pushes (dozens of commits across
  both repos). Whether this means the PAT was rotated, GitHub App auth
  was already migrated, or the token simply hasn't hit its expiry yet
  is unconfirmed — don't treat this as resolved without checking
  `repo-credentials` directly.

### Symptoms
ArgoCD Applications fail to sync with error:
```
Failed to load target state: failed to generate manifest for source 1 of 1:
rpc error: code = Unknown desc = failed to list refs: authentication required:
Invalid username or token. Password authentication is not supported for Git operations.
```

**Affected Applications:**
- `portal` (seadogger-homelab-pro repo)
- `velero-ui` (seadogger-homelab-pro repo)

### Root Cause
ArgoCD uses GitHub Personal Access Token (PAT) stored in `repo-credentials` secret. PATs expire periodically (typically 90 days to 1 year), requiring manual rotation.

### Temporary Workaround
Deploy affected applications manually:
```bash
# Portal
cd /path/to/seadogger-homelab-pro/deployments/portal
kubectl apply -k .

# Velero UI
cd /path/to/seadogger-homelab-pro/deployments/velero-ui
kubectl apply -k .
```

### Permanent Solution
Migrate to GitHub App authentication (tokens auto-refresh, never expire):

1. **Create GitHub App:**
   - Go to Settings → Developer settings → GitHub Apps → New GitHub App
   - Set Homepage URL (any valid URL)
   - Permissions: Repository → Contents (Read-only)
   - Install app on `seadogger-homelab-pro` repository

2. **Get credentials:**
   - Note the App ID
   - Generate and download private key
   - Note the Installation ID

3. **Update ArgoCD secret:**
   ```bash
   kubectl create secret generic repo-credentials \
     --from-literal=type=git \
     --from-literal=url=https://github.com/seadogger-tech/seadogger-homelab-pro \
     --from-file=githubAppPrivateKey=/path/to/private-key.pem \
     --from-literal=githubAppID=<APP_ID> \
     --from-literal=githubAppInstallationID=<INSTALLATION_ID> \
     --dry-run=client -o yaml | kubectl apply -f - -n argocd
   ```

4. **Verify:**
   ```bash
   kubectl get application -n argocd portal -o jsonpath='{.status.sync.status}'
   kubectl get application -n argocd velero-ui -o jsonpath='{.status.sync.status}'
   ```

### References
- [ArgoCD GitHub App Documentation](https://argo-cd.readthedocs.io/en/stable/user-guide/private-repositories/#github-app-credential)
- [Issue #8](https://github.com/seadogger-tech/seadogger-homelab-pro/issues/8) - Tracking issue for migration

![accent-divider.svg](images/accent-divider.svg)
## anakin PoE+ HAT Failure and Cluster Recovery

- **Date:** 2026-07-18 through 2026-07-21
- **Service:** anakin node (PoE+ HAT), Rook-Ceph, cluster-wide CPU allocation
- **Type:** Hardware failure / Multi-day recovery
- **Status:** Resolved

### 1. Hardware Failure

- **Symptom:** `anakin.local` went `NotReady`; kubelet stopped posting
  status. Not a DNS issue (the usual macOS mDNS cache problem, see below)
  — the node didn't respond to ping or SSH by IP either.
- **Root cause:** the node's PoE+ HAT failed. Confirmed physically: the
  Ubiquiti switch showed PoE+ being drawn, but the Pi's own Ethernet
  jack showed zero link/activity lights — the fault was on the Pi side,
  not the network. Plugging in a USB-C power supply directly produced a
  burnt-electronics smell, confirming actual hardware damage (not just a
  loose connection).
- **Resolution:** physical HAT replacement. Verified by temporarily
  borrowing a known-good HAT from `obiwan` (see below) before the
  replacement part arrived.

### 2. Ceph Degraded (2 of 3 OSDs)

- With `anakin`'s OSD down, `ceph -s` reported `HEALTH_WARN`, 24%
  degraded objects, 142 undersized PGs. `ceph-fs-data-ec` uses `k=2,m=1`
  erasure coding across exactly 3 hosts — with only 2 up, EC pools
  cannot reach full redundancy no matter how long you wait; this is
  expected, not a separate bug.
- Marking the down OSD `out` (`ceph osd out osd.0`) is safe and fully
  reversible — it just tells Ceph to stop counting on that device for
  placement. When the node returns, `ceph osd in osd.0` (or Rook's own
  reconciliation) rebalances data back onto it automatically; no data is
  lost by marking it out in the meantime.
- Stuck `Terminating` pods on the dead node (ArgoCD, Jellyfin, monitoring,
  Rook CSI controllers) needed `kubectl delete pod --grace-period=0
  --force` — the API server can't get a graceful-termination
  confirmation from a kubelet that will never respond again.

### 3. HAT Swap Test Caused a Second, Deliberate Outage

- To verify the HAT theory before the replacement part arrived, `obiwan`'s
  HAT was temporarily moved to `anakin`. **Every Ceph pool has
  `min_size: 2`** (replicated pools included, not just the `k=2,m=1` EC
  pool) — so taking down a *second* node, even briefly, drops the
  cluster to 1 of 3 OSDs and makes **all** storage read/write
  unavailable, not just degraded. This was done deliberately, with
  `obiwan` cordoned and its non-Ceph workloads evicted first, and
  the outage window was bounded (a few minutes) before the HAT went
  back.
- Confirmed the theory: `anakin` came up cleanly and pinged
  immediately once given a working HAT.

### 4. Post-Recovery: Stale CSI VolumeAttachments

- After both nodes were back and OSDs re-joined, several pods
  (`hermes-jason`'s dev pod, `signal-cli`) stayed stuck on
  `FailedAttachVolume: volume attachment is being deleted` or
  `Multi-Attach error`, long after the underlying node problems were
  fixed.
- **Root cause:** force-deleting pods on an unreachable node (step 1
  above) doesn't cleanly release their CSI `VolumeAttachment` objects —
  the attach/detach controller is left waiting for a detach
  confirmation from a kubelet that already restarted. These stale
  `VolumeAttachment`s then blocked *new* attach attempts for the same
  PVC on any node.
- **Resolution:** `kubectl patch volumeattachment <name> -p
  '{"metadata":{"finalizers":null}}' --type=merge` clears the stuck
  object without waiting for the CSI driver's own confirmation. Safe for
  CephFS-backed volumes (`RWX`, no exclusive-lock risk); would warrant
  more caution on RBD (`RWO`, exclusive-lock) volumes, since it bypasses
  the detach protocol.
- Also required a restart of the CephFS/RBD CSI **ctrlplugin** pods
  (`kubectl delete pod ...`) to clear an in-memory "operation already in
  progress" lock left over from the same force-deletes.

### 5. Unrelated: Rook Chart Version Drift → ADR-010

While investigating cluster-wide CPU pressure exposed by this outage
(see below), an unpinned `helm upgrade` against the Rook chart repo
picked up a breaking version and briefly took down the CSI
controller-plugin. See **[[13-ADR-Index]]** ADR-010 for the full
incident and the chart-pinning fix.

### 6. Root Cause of Tight CPU Headroom: containerd Image Bloat

- Losing a node exposed that all 4 nodes were running close to 90%+ CPU
  *requested* (not actually *used* — real usage was 13-47%). Chasing
  this down to yoda's mon disk-space warning (`MON_DISK_LOW`) revealed
  the real, unrelated cause: yoda's mon store is only 113 MB, but its
  root disk (which yoda's mon shares with the k3s control plane and
  containerd — yoda holds no Ceph OSD) was at 77% (334 GB) because
  containerd's image cache had accumulated ~50-60 GB of stale,
  unreferenced `hermes-agent` image layers (`imagePullPolicy: Always` +
  `:latest` + frequent upstream rebuilds = old layers pile up, never
  garbage collected).
- **Fix:** `k3s crictl rmi --prune` on yoda freed ~188 GB (77% → 34%
  disk usage), which cleared the `MON_DISK_LOW` warning immediately.
- **Attempted but reverted:** lowering kubelet's image-GC thresholds
  (default 85%/80%) via `--kubelet-arg=image-gc-high-threshold-percent`
  briefly crash-looped yoda's kubelet — those flags were removed from
  kubelet in this Kubernetes version in favor of a structured
  `KubeletConfiguration` YAML file. Reverted; the underlying disk-bloat
  problem is solved via the manual prune above, the proactive-GC-tuning
  idea is parked, not implemented.
- Separately, actual CPU **requests** (not disk) were right-sized:
  Rook CSI plugin/provisioner containers (~1.1 cores freed, see
  ADR-010) and several idle-most-of-the-time app requests — jellyfin,
  hermes, signal-cli, bedrock-gateway, minecraft pack-manager/UI
  (~840m freed) — were lowered to match observed usage. OSD/mon/mgr/rgw
  requests were deliberately left untouched; they exist specifically to
  guarantee CPU during the kind of recovery burst this incident
  produced.

### Key Takeaways

- A node's kubelet going silent and a DNS resolution failure produce
  similar-looking symptoms from `kubectl` — always independently verify
  with `ping`/`ssh` by IP before assuming it's the known macOS mDNS
  cache issue.
- Check `min_size` on *every* pool before taking down a second node for
  any reason, even briefly — it's easy to reason correctly about the EC
  pool's tolerance and forget that replicated pools have their own,
  possibly different, threshold.
- Force-deleting pods on a dead node is necessary but not free — it can
  leave stale `VolumeAttachment` objects and CSI driver in-memory locks
  that block scheduling long after the node itself recovers. Check for
  these explicitly during recovery, don't assume "node is Ready again"
  means "fully recovered."
- `kubectl top nodes` requests-vs-usage gaps are worth investigating
  even when nothing is on fire — this incident's disk-space root cause
  (containerd image bloat) had been silently accumulating for weeks and
  would have eventually caused its own outage independent of the
  hardware failure.

![accent-divider.svg](images/accent-divider.svg)
## Power Failure → Cluster-Wide DNS Deadlock (2026-08-04)

**Symptom:** After a house power failure, "every wired interface is
down." Nothing resolves — but the network is actually fine. Nodes ping,
the gateway responds, k3s is `Ready` on all four nodes. Nearly every pod
sits in `ImagePullBackOff` with:

```
dial tcp: lookup registry-1.docker.io: Try again
```

### Root cause — a three-way circular dependency

1. **Pi-hole's only upstream is its own `cloudflared` sidecar**
   (`FTLCONF_dns_upstreams=127.0.0.1#5053`, DoH). No fallback.
2. That sidecar is `crazymax/cloudflared:latest` with
   **`imagePullPolicy: Always`**. `Always` forces kubelet to contact
   Docker Hub on *every* container start — even when a valid copy is
   cached locally. Reaching Docker Hub needs DNS.
3. **Every node resolves via `192.168.1.250`** — the Pi-hole
   LoadBalancer. Pi-hole runs *on* the cluster that depends on it.

So: DNS needs cloudflared → cloudflared needs a registry pull → the pull
needs DNS. Nothing recovers on its own.

**Compounding factor:** Raspberry Pis have no battery-backed RTC. Three
of four nodes came back with clocks up to **2m39s** off. That skewed the
Ceph mons (`clock skew detected on mon.d, mon.e`, 143 slow ops), which
made PVC mounts time out — so Pi-hole couldn't start even once its image
was available. NTP couldn't correct it because NTP also needs DNS.

### Recovery procedure

```bash
# 1. Break the DNS loop — temporary public resolver on every node.
#    NOTE: ansible_user is `pi`, not your laptop username.
for h in 192.168.1.95 192.168.1.96 192.168.1.97 192.168.1.98; do
  ssh pi@$h 'sudo sed -i "1i nameserver 1.1.1.1" /etc/resolv.conf'
done

# 2. Resync clocks (fixes the Ceph mon skew / slow ops)
for h in 192.168.1.96 192.168.1.97 192.168.1.98; do
  ssh pi@$h 'sudo systemctl restart systemd-timesyncd'
done
# verify: timedatectl | grep synchronized   -> "yes" on all nodes

# 3. Let the images pull, then kick anything stuck in backoff
kubectl get pods -A --no-headers | awk '$4 ~ /ImagePull|ErrImage/ {print $1" "$2}' \
  | while read ns p; do kubectl delete pod -n "$ns" "$p" --wait=false; done

# 4. Once Pi-hole is 2/2 and resolving, remove the temporary resolver
for h in 192.168.1.95 192.168.1.96 192.168.1.97 192.168.1.98; do
  ssh pi@$h 'sudo sed -i "/^nameserver 1.1.1.1$/d" /etc/resolv.conf'
done
```

### Traps found the hard way

- **`/etc/resolv.conf` is managed by NetworkManager on these nodes**
  (`systemd-resolved` and `dhcpcd` are both inactive). A manual edit is
  **not persistent** — it is lost on reboot, so this workaround does not
  protect against the *next* power failure. See
  [19-Refactoring-Roadmap](19-Refactoring-Roadmap) Priority 9 for the
  durable options.
- **Don't restart CoreDNS to "fix" DNS during an outage.** Doing so
  during this incident rescheduled it onto a node with no cached CoreDNS
  image, taking cluster DNS down completely. If you must, pin it first:
  `kubectl patch deploy coredns -n kube-system -p '{"spec":{"template":{"spec":{"nodeSelector":{"kubernetes.io/hostname":"<node-with-image>"}}}}}'`
- **Check which nodes actually have an image cached** before letting a
  pod reschedule:
  ```bash
  kubectl get nodes -o json | python3 -c "
  import json,sys
  for n in json.load(sys.stdin)['items']:
      names=[i for img in n['status'].get('images',[]) for i in img.get('names',[])]
      print(n['metadata']['name'], [i for i in names if 'cloudflared' in i] or 'NOT CACHED')"
  ```
  Note this list can be **stale** — it may report an image kubelet no
  longer has. Trust the `Pulling` event over the node status.
- **ArgoCD is also DNS-blocked during the outage** (`failed to get
  command args to log: helm pull ... lookup ... server misbehaving`), so
  `selfHeal` won't fight your emergency patches — but it *will* revert
  them the moment DNS recovers. Anything you want to keep must go in git.

### Permanent fixes applied (2026-08-05)

The manual recovery above should no longer be needed. All of this is now
either in git or in the UDM controller config:

| Fix | Where | Effect |
|---|---|---|
| cloudflared pinned `2025.9.1` + `IfNotPresent` | `deployments/pihole/pihole-values.yaml` | kubelet no longer needs a registry round-trip to start the DoH sidecar. Chart default was already `IfNotPresent`; the values file had overridden it to `Always`. |
| Node DNS = Pi-hole primary + `1.1.1.1` fallback | `ansible/tasks/pihole_deploy.yml` (NetworkManager profile) | Nodes can resolve during a Pi-hole outage → images pull → cluster self-heals |
| CoreDNS forwards explicitly to Pi-hole | `forward . 192.168.1.250` | Pods cannot reach the node fallback, so filtering is never bypassed |
| CoreDNS image seeded on all 4 nodes | one-time pre-pull | A CoreDNS reschedule can no longer land on a node without the image |

**Why the node fix lives in NetworkManager, not `/etc/resolv.conf`:**
NM owns that file on these nodes (`systemd-resolved` and `dhcpcd` are
both inactive) and rewrites it on reboot. Editing `resolv.conf` directly
looks like it works and then silently vanishes — which is exactly how the
deadlock stays armed.

**Why CoreDNS must be pinned explicitly:** it previously used
`forward . /etc/resolv.conf`, inheriting whatever the node used. Once the
node gained a `1.1.1.1` fallback, CoreDNS would have inherited it too —
and its `forward` plugin defaults to `policy random`, which
*load-balances* rather than failing over. Roughly half of all pod DNS
would have gone to `1.1.1.1` unfiltered, permanently. Pinning is what
makes the node fallback safe to have.

![accent-divider.svg](images/accent-divider.svg)
## DNS Enforcement on the UDM (2026-08-05)

Before this work, "everything uses Pi-hole" was a **convention, not a
rule** — DHCP handed out `192.168.1.250` on all three networks, but
nothing stopped a device from ignoring it.

### What was actually broken

Four DNS firewall rules existed and were enabled, and had **matched zero
packets** since they were written:

```
num   pkts bytes target
1        0     0 RETURN   ← allow Pi-hole DNS
4        0     0 DROP     ← "drop hardcoded DNS"
7    3626K  926M RETURN   ← default allow-everything
```

Three independent defects:

1. **Port group on both Source and Destination.** The rule required
   *source port 53 AND destination port 53*. Real queries use an
   ephemeral source port (`sport=33124 dport=53`), so nothing ever
   matched.
2. **Wrong source address.** The allow rules matched
   `src = 192.168.1.250`, the MetalLB VIP. Kubernetes SNATs pod egress to
   the **node IP**, so the VIP never appears as a source. The VIP is
   ingress-only.
3. **Dead MAC filter.** The allow rules were pinned to
   `dc:a6:32:f2:73:9d` — a `dc:a6:32` (Pi 4-era) MAC with no active
   lease. The current nodes are all `2c:cf:67` (Pi 5). It was almost
   certainly the original Pi-hole host from before the Pi 5 rebuild.

### The corrected design

```
group "K3s Nodes Pi-hole Egress" = 192.168.1.95, .96, .97, .98

20001 ACCEPT  src=K3s Nodes            dst=port 53    (recovery escape hatch)
20002 ACCEPT  src=K3s Nodes            dst=port 443   (Pi-hole's cloudflared DoH)
20003 DROP    src=(any)                dst=port 53    (hardcoded DNS)
20004 DELETED
```

The node group does double duty: it is both Pi-hole's real egress
identity *and* the power-failure recovery exception. Because Pi-hole
relocates between nodes, **all four IPs must be listed** — a rule pinned
to one node IP works until the next reschedule.

> ⚠️ **Rule 20004 was deleted, not fixed.** It targeted `DNSSEC_Port`,
> which is **port 443**. Correcting it the way 20003 needed correcting —
> `any → dst port 443` — would have dropped **all outbound HTTPS for the
> entire network**. DNSSEC is port 53; port 443 for DNS is DoH, and DoH
> can only be blocked by destination address, never by port.

### Closing the router's own DNS hole

`WAN_OUT` rules structurally cannot see LAN→router traffic, and blocking
it was impossible on two of three networks anyway — `br2` (IoT) and `br3`
(gaming) use `UBIOS_GUEST_LOCAL_USER`, whose **built-in allow sits above
any user rule**:

```
1  RETURN tcp dpt:53
2  RETURN udp dpt:53   ← built-in, cannot be overridden
7  DROP all
```

The real cause was not a missing rule but a **Google fallback on the WAN
interface**:

```
wan_dns1: 192.168.1.250      wan_dns2: 8.8.8.8   ← the hole
```

dnsmasq queried both, so roughly half the answers it returned to LAN
clients were unfiltered Google results. **Clearing `wan_dns2`** makes
Pi-hole the router's only upstream, so every device still querying
`192.168.1.1` now receives Pi-hole-filtered answers — corralled rather
than broken, across all three networks, with no firewall rules and no
IoT breakage.

Verified:

```
via router 192.168.1.1:  doubleclick.net → 0.0.0.0       (filtered)
                         github.com      → 140.82.114.4
via Pi-hole    .250:     doubleclick.net → 0.0.0.0       (identical)
```

**Tradeoff:** the UDM now depends solely on Pi-hole for its own DNS.
During a Pi-hole outage the router loses name resolution — UniFi cloud,
update checks, speed tests. Routing, NAT, DHCP and firewalling are all
IP-based and unaffected, so the internet keeps working.

### Verifying enforcement is live

```bash
ssh udm 'iptables -L UBIOS_WAN_OUT_USER -v -n --line-numbers'
```

DROP counters climbing = hardcoded DNS is being blocked. Allow counters
climbing = Pi-hole egress and the node escape hatch are working. **All
zeros means the rules are silently doing nothing** — which is exactly the
state this section exists to prevent recurring.

![accent-divider.svg](images/accent-divider.svg)
## VLAN Isolation Severs DNS (2026-08-08)

Adding "block IoT → trusted LAN" isolation rules took **DNS down for the
entire IoT VLAN**. Symptoms looked unrelated: phones reported "no
internet", and the Samsung FamilyHub fridge could not load its Home
Assistant dashboard.

### Root cause

**Pi-hole lives on the trusted LAN at `192.168.1.250`.** A reject rule
covering `IoT → 192.168.1.0/24` therefore blackholes DNS along with
everything else. No resolution means clients never even attempt a
connection — so the Home Assistant allow rule read **0 packets** and
looked broken, when in fact nothing ever got far enough to use it.

The tell was in the packet capture — every IoT client, including the
fridge, talking only to port 53 and getting nowhere:

```
192.168.50.61  → 192.168.1.250:53   A? api-global.netflix.com
192.168.50.80  → 192.168.1.250:53   A? pool.ntp.org        ← the fridge
```

An earlier capture filtered with `not port 53` showed **nothing at all**,
which was misread as "no traffic" when it actually meant "the only
traffic here is the DNS we excluded."

### Three compounding traps

1. **UniFi appends new rules to the bottom.** The DNS and Home Assistant
   ACCEPTs were created *after* the rejects, so they landed at
   `rule_index` 20003/20004 — below all three drops, permanently dead.
   Rules whose names contain "**else**" belong last; anything created
   later lands in the dead zone by default.
2. **The controller renders from an in-memory cache, not Mongo.** Editing
   `rule_index` directly changed the DB but left iptables untouched.
   Only a **reboot** made the controller re-read from disk. Worse, a GUI
   save in that state can write the *stale cached order* back to Mongo
   and silently undo the edit.
3. **Established connections bypass the USER chain.** They match the
   conntrack `ESTABLISHED,RELATED` fast path first, so an allow rule
   counts only *new* connections (the SYN). A rule reading 0 while
   traffic flows is normal — check `/proc/net/nf_conntrack` before
   concluding the path is broken.

### Working configuration

```
20000 ACCEPT  IoT → 192.168.1.250   tcp+udp 53     (Pi-hole)
20001 ACCEPT  192.168.50.80 → 192.168.1.241  tcp 443   (fridge → HA)
20002 REJECT  IoT → Trusted LAN
20003 REJECT  IoT → VPN
20004 REJECT  IoT → Gaming
```

`l2_isolation` is safe to leave **on**: it blocks client-to-client
traffic *within* the VLAN, while the fridge→HA path is routed via the
gateway and unaffected.

> **DNSSEC needs no extra ports.** It rides on port 53 and only enlarges
> responses. Allow **TCP 53 as well as UDP** — oversized signed answers
> set the truncate bit and force a TCP retry. UDP-only DNS works until it
> randomly doesn't.

### Rule of thumb

Any new VLAN isolation rule must carve out the infrastructure that VLAN
depends on — **DNS to `192.168.1.250` first** — and the carve-out must be
ordered *above* the drops. Verify with counters, never with the UI:

```bash
ssh udm 'iptables -L UBIOS_LAN_IN_USER -v -n --line-numbers'
```

Allow counters climbing and REJECT counters flat means it is working. An
allow rule at 0 while a REJECT climbs means the rule is below the drops
or scoped past the client you are testing from — the same failure that
consumed most of this incident.

![accent-divider.svg](images/accent-divider.svg)
## See Also

- **[[04-Bootstrap-and-Cold-Start]]** - Deployment procedures and common issues
- **[[11-Monitoring]]** - Using Prometheus/Grafana for debugging
- **[[17-Runbooks]]** - Operational procedures
- **[[21-Deployment-Dependencies]]** - Understanding deployment failures

**Related Issues:**
- [#43 - Fix "latest" versions](https://github.com/seadogger-tech/seadogger-homelab/issues/43) - Version pinning
- [#31 - NVMe boot fragility](https://github.com/seadogger-tech/seadogger-homelab/issues/31) - Boot issues
