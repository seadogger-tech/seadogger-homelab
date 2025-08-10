# Active Context: seadogger-homelab

This document tracks the current work focus, recent changes, and next steps for the `seadogger-homelab` project.

## Current Focus

The primary focus is on deploying an application to manage media files and provide access to other systems on the network. The leading candidate is Ganesha NFS, which is part of CephFS. However, we are facing challenges with macOS clients due to issues with NFSv4 and newer.

## Recent Changes

*   Initialized the `memory-bank` directory and its core documentation.
*   Conducted an extensive debugging session on the NFS Ganesha deployment.

## NFS Troubleshooting Summary (August 10, 2025)

We diagnosed a failing NFS deployment and, after a lengthy investigation, arrived at a definitive solution.

### Problem-Solving Steps:
1.  **Initial State:** The NFS server pods were in a `CrashLoopBackOff` state, and the `LoadBalancer` service was missing.
2.  **Pod Crash Analysis:** Log analysis revealed the pods were crashing due to a Kerberos-related error (`gssd_refresh_krb5_machine_credential`). This was caused by an incorrect security configuration.
3.  **CRD Schema Investigation:** Multiple attempts to fix the configuration via manual `kubectl apply` commands failed due to a fundamental misunderstanding of the `CephNFS` CRD schema for Rook v1.14. We incorrectly assumed the NFS server was configured via a `ganeshaConfig` block or a separate `CephNFSExport` resource.
4.  **Definitive Discovery:** By consulting the official `values.yaml` for the `rook-ceph-cluster` Helm chart (version `release-1.14`), we discovered that the NFS server is **not** configured via the Helm chart at all. It must be deployed as a separate Kubernetes resource.

### Final Plan:
The definitive plan is to manage the `CephNFS` resource declaratively within the Ansible playbook, separate from the Helm release.

1.  **Clean `values.yaml`:** Remove the invalid `cephNFS` block from `helm-deployments/rook-ceph/rook-ceph-cluster-values.yaml`.
2.  **Update Ansible Playbook:** Add a new task to `ansible/tasks/rook_ceph_deploy.yml` that uses the `ansible.builtin.k8s` module to create the `CephNFS` resource directly. This new resource will contain the correct security settings to prevent the pod crash.
3.  **Deploy and Verify:** Run the updated Ansible playbook and verify that the NFS share is accessible.

## Next Steps

1.  **Implement the Final NFS Plan:** Execute the plan outlined above to bring the NFS server online.
2.  **Deploy Plex Media Server:** Once the media file sharing is stable, deploy Plex Media Server as a follow-on enhancement.
3.  **Fix Monitoring Stack:** Address issues with the Prometheus and Grafana deployments to ensure proper metrics collection and cluster status visibility.
4.  **Remote Ceph Storage:** Implement a solution to connect the local Ceph cluster to remote storage for backup or tiering.
