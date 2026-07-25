![wiki-banner.svg](images/wiki-banner.svg)
![accent-divider](images/accent-divider.svg)
# ADR Index

![accent-divider](images/accent-divider.svg)
### ADR-011: Adopting Unmerged Upstream PRs (Reusable Pattern)

- **Status:** Implemented & Verified
- **Date:** 2026-07-25

#### Context

Mealie's AI-import features (recipe-from-URL, ingredient parsing) route
through the in-cluster AWS Bedrock Access Gateway
(`ghcr.io/seadogger-tech/aws-bedrock-gateway`, auto-rebuilt from
`aws-samples/bedrock-access-gateway`'s `main` every 6 hours). Testing
revealed the gateway silently dropped the OpenAI `response_format`
field entirely — accepted, never enforced — so every model free-texted
its own JSON style. Claude Haiku sometimes wrapped output in
` ```json ` fences, breaking Mealie's strict `json.loads()` parser
unpredictably.

This was a confirmed, tracked upstream gap
([aws-samples/bedrock-access-gateway#162](https://github.com/aws-samples/bedrock-access-gateway/issues/162)),
not a missing config option. A complete, tested fix existed as an
**open, unmerged, unreviewed community PR**
([#255](https://github.com/aws-samples/bedrock-access-gateway/pull/255))
that maps `response_format.json_schema` to Bedrock's native
`outputConfig.textFormat` — real schema enforcement at the AWS API
level, not a prompt trick.

A follow-up, broader survey (prompted by "are there other PRs we should
adopt" and specifically "you're only looking at this from Mealie's
angle — what about OpenWebUI") found the gateway also actively serves
OpenWebUI (confirmed via its stored connection config pointing at
`192.168.1.242:6880`), which has different, real needs: tool/function-
calling reliability and newer-model support. Five more open PRs applied
cleanly and address real (if not yet triggered) failure modes for that
client. The same pattern surfaced again independently for Mealie itself
— two more open PRs
([#7618](https://github.com/mealie-recipes/mealie/pull/7618),
[#7825](https://github.com/mealie-recipes/mealie/pull/7825)) add a
"Force AI Import" checkbox and a "Create from Text" page to Mealie's own
UI, since Mealie's scraper-selection order is hardcoded server-side with
no request-level override — the only way to force the AI path today is
a manual URL-fetch/extract/API-import workaround.

#### Decision

When a real, active bug has a complete, tested, currently-open PR
upstream — reviewed or not — prefer adopting it over waiting indefinitely
or hand-rolling an equivalent patch from scratch. Two different adoption
shapes exist depending on how the upstream image is built here:

**Shape A — continuous auto-rebuild** (`aws-bedrock-gateway`,
`.github/workflows/upstream-rebuild.yaml`): the pipeline checks out
upstream's default branch fresh on every scheduled run, then cherry-picks
the adopted PR commit(s) on top before building. This keeps tracking
all *other* upstream changes automatically — only the specific adopted
fix is pinned to a manual step, not the whole codebase.

**Shape B — pinned stable tag** (`mealie`,
`.github/workflows/mealie-rebuild.yaml`): the pipeline checks out a
fixed upstream release tag (not the active dev branch) and cherry-picks
on top of that. Used when the upstream project's default branch is
genuinely active development that could introduce breaking changes
(schema migrations, etc.) — appropriate for Mealie, which holds real
household data, inappropriate for treating like the gateway's
continuous-tracking model.

**Every adoption, regardless of shape, includes:**
1. **A merge-status check step** that queries `gh pr view <N> --json
   state` for each adopted PR and emits a GitHub Actions warning
   annotation the moment it's no longer `OPEN` upstream — so a human
   notices and removes the now-unnecessary cherry-pick, rather than it
   silently becoming a no-op (if the diff is now redundant) or eventually
   conflicting (if the surrounding code has since changed). This check
   does not fail the build; it only warns.
2. **Explicit code comments** at the cherry-pick step naming the PR,
   why it's needed, which real client/use-case depends on it, and what
   to do once it merges.
3. **Verification before adoption, not after** — the exact cherry-pick
   commands intended for the workflow are run locally first, against a
   fresh clone, before committing them. When a cherry-pick conflicts
   with another adopted PR (two additive patches touching adjacent code
   are not a sign either is wrong — just that they land near each
   other), the conflict is resolved via a **separate, committed,
   testable script** (e.g. `.github/scripts/resolve_bedrock_gateway_conflicts.py`)
   rather than inline Python heredocs embedded in the workflow YAML —
   the latter is fragile (whitespace/quoting inside a YAML block scalar
   is easy to break silently) and hard to validate ahead of time.
4. **A syntax-validation step** (`python3 -c "import ast; ast.parse(...)"`
   for Python targets) immediately after all cherry-picks, so a bad
   patch application fails the build loudly instead of shipping broken
   code.

PRs adopted under this pattern (as of 2026-07-25):

| Repo | PR | What it fixes | Client that needs it |
|---|---|---|---|
| bedrock-access-gateway | [#255](https://github.com/aws-samples/bedrock-access-gateway/pull/255) | `response_format`/`json_schema` → Bedrock structured output | Mealie |
| bedrock-access-gateway | [#246](https://github.com/aws-samples/bedrock-access-gateway/pull/246) | Drop orphan `tool_use`/`tool_result` pairs before Converse translation | OpenWebUI (explicitly reproduces an OpenWebUI history-rewrite scenario in its own PR description) |
| bedrock-access-gateway | [#247](https://github.com/aws-samples/bedrock-access-gateway/pull/247) | Non-negative tool-call indexes in streamed responses | OpenWebUI |
| bedrock-access-gateway | [#239](https://github.com/aws-samples/bedrock-access-gateway/pull/239) | Allow replayed tool blocks without a `tools` array (conversation compaction) | OpenWebUI — real hard-crash scenario, documented in 3+ other projects' trackers |
| bedrock-access-gateway | [#198](https://github.com/aws-samples/bedrock-access-gateway/pull/198) | Return `tool_calls` instead of dropping them on `max_tokens` truncation | OpenWebUI |
| bedrock-access-gateway | [#249](https://github.com/aws-samples/bedrock-access-gateway/pull/249) | Claude Opus 4.7 adaptive-thinking request format | OpenWebUI — Opus 4.7 is already selectable in its model list; reasoning requests fail today without this |
| mealie | [#7618](https://github.com/mealie-recipes/mealie/pull/7618) | "Force OpenAI Scraper" checkbox on Import-from-URL | Real UI button for forcing AI import, replacing the manual workaround |
| mealie | [#7825](https://github.com/mealie-recipes/mealie/pull/7825) | "Create from Text" page | Same — pastes plain text straight to the AI parser, no URL/HTML scraping |

#### Consequences

- **Positive:**
  - Real bugs get fixed today instead of waiting on an indeterminate
    upstream review timeline — several of these PRs had zero comments
    or reviews at time of adoption, which is normal for a healthy but
    under-resourced open-source project, not a sign of rejection.
  - The merge-status check means this doesn't silently rot — a human
    gets a visible signal to clean up, rather than the workflow becoming
    an unmaintained pile of dead cherry-picks over time.
  - Conflict resolution is tested and versioned, not improvised at
    build time.
- **Negative:**
  - Each adopted PR is a maintenance liability until it merges upstream
    (or we decide to drop it) — a rebase may eventually be needed if
    upstream touches the same code.
  - Someone has to actually notice and act on the merge-status warning
    annotations; they don't block anything by themselves.
  - Building Mealie from source (Shape B) is a much heavier CI job than
    a small Python service like the gateway (full Yarn frontend build +
    multi-arch Python backend) — acceptable for an infrequent, manually
    re-triggered build, not something to run on the gateway's aggressive
    6-hour schedule.

![accent-divider](images/accent-divider.svg)
### ADR-010: Pin Rook-Ceph Helm Chart Versions

- **Status:** Implemented & Verified
- **Date:** 2026-07-21

#### Context

Both Rook-Ceph installs (`ansible/tasks/rook_ceph_deploy_part1.yml`) used
`helm upgrade --install` against `rook-release/rook-ceph` /
`rook-release/rook-ceph-cluster` with no `--version` pin. While
right-sizing CSI plugin/provisioner CPU requests (over-provisioned
relative to observed usage after a node outage exposed how tight
cluster-wide CPU had become), a routine `helm repo update` silently
picked up chart `v1.20.2` — several minor versions ahead of the
`v1.19.2` that had actually been running. `v1.20.2` ships a breaking
change to the CSI controller-plugin's ServiceAccount wiring: the
`rbd`/`cephfs` `ctrlplugin` Deployments came up looking for a
ServiceAccount (`rbd-ctrlplugin-sa`) that chart version never created,
so their pods failed to schedule (`FailedCreate`,
"serviceaccount ... not found").

Caught within minutes (ctrlplugin replica count dropping to 0/2) and
rolled back via `helm rollback rook-ceph 4` before it affected any
actual storage I/O — the CSI **node** plugins (the ones that handle
live mounts) were never affected, only the controller-plugin sidecars.

#### Decision

Pin both Rook Helm releases to the versions actually verified working:
operator `1.19.2`, cluster `1.18.1`, via explicit `--version` flags in
the `helm upgrade --install` commands. Future chart version bumps must
be deliberate — edit the pin, verify CSI ctrlplugin pods come up, before
trusting the new version.

#### Consequences

- **Positive:**
  - Eliminates an entire class of "chart moved out from under me"
    incidents — the same risk that showed up here could just as easily
    hit `rook-ceph-cluster`, or any other unpinned Helm-chart Application
    in this repo. Every Helm-chart-backed app added since (Home Assistant
    via `ansible/tasks/ha_deploy.yml`, `deployments/velero`) pins
    `targetRevision` explicitly for this reason — bump deliberately,
    verify after.
  - The actual CSI resource right-sizing this was blocking (see
    `deployments/home-assistant` and CPU request notes in
    `12-Troubleshooting.md`) applied cleanly once re-run against the
    pinned version.
- **Negative:**
  - Chart security/bugfix updates now require a manual bump + verification
    step rather than arriving automatically on the next `helm repo update`.
    Given what just happened, that's the intended tradeoff, not a cost.

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
### ADR-009: Migrate from K8up to Velero for Kubernetes Backup/Restore

- **Status:** Implemented & Verified
- **Date:** 2025-10-04

#### Context

The homelab requires a reliable backup and restore solution for Kubernetes persistent volumes. Initial implementation using K8up v2.13.1 with Restic and AWS S3 encountered numerous production-blocking issues including namespace deletion edge cases, complex restore orchestration, multi-attach PVC errors, extensive RBAC requirements, and post-restore application failures (n8n "Command start not found"). Restore success rate was < 50% and required manual intervention.

#### Decision

Migrate to Velero v1.16.0, a mature CNCF sandbox project with 6+ years of development, comprehensive namespace backup capabilities, and proven restore reliability. Velero backs up entire namespaces (not just PVCs) and uses Kopia for incremental, deduplicated file-level backups to AWS S3 Glacier Deep Archive.

Key technical decisions:
1. **Kopia Uploader**: Replaced Restic with Kopia for content-addressable storage and better deduplication
2. **Node-Agent Daemonset**: Deployed on all nodes for file-level PVC backups via `defaultVolumesToFsBackup: true`
3. **AWS S3 Lifecycle**: 7 days in S3 Standard → Glacier Deep Archive (permanent retention)
4. **Backup Strategy**:
   - Week 1: Weekly Nextcloud backup (Sunday 2 AM) to allow 48-hour 3.3TB initial upload
   - Week 2+: Daily backups for all namespaces (Nextcloud, OpenWebUI, N8N, Jellyfin, PiHole, Portal)
5. **Exclusion Handling**: Jellyfin media volume excluded via `backup.velero.io/backup-volumes-excludes: media` (prevents duplicate 3.3TB backup of read-only Nextcloud mount)

#### Consequences

- **Positive:**
  - Industry-standard solution with proven reliability
  - Backs up all Kubernetes resources, not just PVCs
  - Better GitOps integration with ArgoCD (managed in Pro repo)
  - Cost-effective: ~$3.30/month for 3.3TB in Glacier Deep Archive
  - Incremental backups with Kopia deduplication (only changed data uploaded)
  - Velero UI for backup monitoring and management
  - Deterministic restore outcomes

- **Negative:**
  - 12-48 hour retrieval time for backups >7 days old (Glacier Deep Archive)
  - Bulk retrieval cost: $0.02/GB for disaster recovery
  - Migration effort completed (deployment, schedules, testing, documentation, K8up cleanup)

- **Implementation Status:**
  - ✅ Velero v1.16.0 deployed via Helm in Pro repo
  - ✅ Node-agent daemonset running on all nodes
  - ✅ Backup schedules configured (`daily-backup`, `weekly-nextcloud-backup`)
  - ✅ S3 bucket lifecycle policy configured (7 days → Deep Archive)
  - ✅ Jellyfin media volume exclusion implemented
  - ✅ Storage wiki documentation updated with architecture diagrams
  - ✅ All k8up references removed from codebase
  - ✅ S3 bucket cleaned (all k8up/test backups deleted)

See `.memory_bank/k8up_failure_analysis.md` for detailed technical analysis of K8up failures.

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
