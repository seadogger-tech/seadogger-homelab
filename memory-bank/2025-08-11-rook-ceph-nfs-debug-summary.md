# Rook-Ceph NFS Debugging Summary - 2025-08-11

This document summarizes the debugging session that resolved the failing Rook-Ceph NFS deployment.

## Initial State

The Ansible playbook was failing to deploy a functional NFS share. The primary symptom was that the NFS mount command would time out.

## Investigation and Resolution

The investigation followed a logical path from the client-facing issue down to the root cause:

1.  **NFS Mount Timeout:** The initial `sudo mount` command failed with a timeout, indicating a networking problem between the client and the NFS server.

2.  **Pending External IP:** An inspection of the `rook-nfs-loadbalancer` service revealed that its `EXTERNAL-IP` was stuck in a `<pending>` state. This confirmed that MetalLB was not assigning the requested IP address.

3.  **Missing IPAddressPool:** We discovered that no `IPAddressPool` custom resources were configured in the `metallb-system` namespace, leaving MetalLB with no addresses to assign.

4.  **Failed ArgoCD Application:** The `metallb-config` ArgoCD application, responsible for creating the `IPAddressPool`, was in a `SyncFailed` state.

5.  **Webhook Service Not Found:** The error message for the failed application was `service "metallb-webhook-service" not found`. This indicated that a critical component of the main MetalLB installation was missing.

6.  **Incorrect Helm Configuration:** The root cause was traced to the `metallb` ArgoCD application in `seadogger-homelab/ansible/tasks/metallb_deploy.yml`. It was incorrectly using a `valueFiles` entry that pointed to a manifest instead of a proper Helm values file. This misconfiguration prevented the main MetalLB chart from deploying all of its necessary components, including the webhook service.

## Key Fixes Applied

-   **Corrected `cephx` Key Extraction:** The `rook_ceph_deploy_part2.yml` playbook was modified to use `ceph auth get-key` to retrieve the raw `cephx` key for the NFS user, resolving an issue where the key was being passed with invalid characters.
-   **Fixed Ansible Playbook Syntax:** Corrected indentation errors in `rook_ceph_deploy_part2.yml` that were causing the playbook to fail.

## Current Status

-   The Rook-Ceph cluster and the NFS server components are fully healthy and operational.
-   The NFS export is correctly configured in RADOS and loaded by the Ganesha server.
-   The root cause of the NFS mount failure has been identified as a misconfiguration in the MetalLB deployment.

## Next Steps

The immediate next step is to correct the `metallb` ArgoCD application in the Ansible playbook to allow for a complete and successful deployment of MetalLB.
