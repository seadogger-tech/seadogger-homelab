![wiki-banner.svg](images/wiki-banner.svg)
![accent-divider.svg](images/accent-divider.svg)
# GitOps & IaC

This document outlines the structured test plan for validating the new idempotent Ansible deployment (`main.yml`) and granular cleanup (`cleanup.yml`) playbooks. The tests will be performed incrementally on an existing, fully deployed cluster.

![accent-divider.svg](images/accent-divider.svg)
## Test Plan

![accent-divider.svg](images/accent-divider.svg)
### Test Case 1: Single Non-Stateful Application (Bedrock)

1.  **Deploy:**
    *   In `config.yml`, set `cold_start_stage_3_install_applications: true` and `manual_install_bedrock: true`. All other `manual_install_*` flags should be `false`.
    *   Run `ansible-playbook main.yml`.
2.  **Verify Deployment:** Check that the `bedrock-access-gateway` pods are running in the `bedrock-gateway` namespace.
3.  **Cleanup:**
    *   In `config.yml`, set `run_pod_cleanup: true` and ensure only the `bedrock-access-gateway` entry is active in the `pod_cleanup_list`.
    *   Run `ansible-playbook cleanup.yml`.
4.  **Verify Cleanup:** Check that the `bedrock-access-gateway` pods and the `bedrock-gateway` namespace have been removed.

![accent-divider.svg](images/accent-divider.svg)
### Test Case 2: Single Stateful Application (OpenWebUI)

1.  **Deploy:**
    *   In `config.yml`, set `manual_install_bedrock: false` and `manual_install_openwebui: true`.
    *   Run `ansible-playbook main.yml`.
2.  **Verify Deployment:** Check that the `openwebui` pods and its corresponding PVC are created and bound.
3.  **Cleanup (Preserve Data):**
    *   In `config.yml`, set `run_pod_cleanup: true`, configure `pod_cleanup_list` for `openwebui`, and ensure its `delete_pvc` flag is `false`.
    *   Run `ansible-playbook cleanup.yml`.
4.  **Verify Cleanup & Redeploy:**
    *   Confirm the `openwebui` pods are gone, but the PVC remains.
    *   Rerun the deployment from step 1 and confirm the application comes back online, re-attaching to the existing PVC.
5.  **Cleanup (Destroy Data):**
    *   In `config.yml`, set the `delete_pvc` flag for `openwebui` to `true`.
    *   Run `ansible-playbook cleanup.yml`.
6.  **Verify Cleanup:** Confirm that both the pods and the PVC for `openwebui` have been deleted.

![accent-divider.svg](images/accent-divider.svg)
### Test Case 3: All Applications

1.  **Deploy:**
    *   In `config.yml`, set `cold_start_stage_3_install_applications: true` and enable all `manual_install_*` flags for the applications.
    *   Run `ansible-playbook main.yml`.
2.  **Cleanup:**
    *   In `config.yml`, set `run_pod_cleanup: true` and ensure all applications are active in the `pod_cleanup_list`.
    *   Run `ansible-playbook cleanup.yml`.
3.  **Verify Cleanup:** Check that all application namespaces and their resources are gone.

![accent-divider.svg](images/accent-divider.svg)
### Test Case 4: All Applications + Prometheus

1.  **Deploy:**
    *   Same deployment as Test Case 3, ensuring `manual_install_prometheus: true`.
2.  **Cleanup:**
    *   In `config.yml`, set `run_pod_cleanup: true` (for all apps) and `run_prometheus_cleanup: true`.
    *   Run `ansible-playbook cleanup.yml`.
3.  **Verify Cleanup:** Check that all application and Prometheus resources, including cluster-level CRDs, are removed.

![accent-divider.svg](images/accent-divider.svg)
### Test Case 5: All Applications + Prometheus + Infrastructure

1.  **Deploy:**
    *   In `config.yml`, set both `cold_start_stage_2_install_infrastructure: true` and `cold_start_stage_3_install_applications: true`.
    *   Run `ansible-playbook main.yml`.
2.  **Cleanup:**
    *   In `config.yml`, enable all three cleanup flags: `run_pod_cleanup`, `run_prometheus_cleanup`, and `run_infrastructure_cleanup`.
    *   Run `ansible-playbook cleanup.yml`.
3.  **Verify Cleanup:** Check that all applications and infrastructure components (MetalLB, Rook-Ceph operators) are gone, leaving a bare k3s cluster.

![accent-divider.svg](images/accent-divider.svg)
### Test Case 6: Full Cold Start Cycle

1.  **Deploy:**
    *   Ensure a full deployment is running as per Test Case 5.
2.  **Full Teardown:**
    *   In `config.yml`, set the master switch `cold_start_stage_1_wipe_cluster: true`.
    *   Set `perform_physical_disk_wipe: true` to test the most destructive path.
    *   Run `ansible-playbook cleanup.yml`.
3.  **Verify Teardown:** Confirm the cluster is completely inaccessible and nodes are clean.
4.  **Full Re-installation:**
    *   In `config.yml`, set all cleanup/wipe flags to `false`.
    *   Set `cold_start_stage_2_install_infrastructure: true` and `cold_start_stage_3_install_applications: true`.
    *   Run `ansible-playbook main.yml`.
5.  **Verify Re-installation:** Confirm the entire cluster and all applications are back online and fully functional from a clean slate.



