# Ceph Dashboard Exposure and Password Management Troubleshooting

## Date: 2025-08-16

### Context
The goal was to expose the Rook-Ceph dashboard via a `LoadBalancer` service and ensure the admin password could be managed persistently.

### Initial Problem: Dashboard Not Accessible
- A `LoadBalancer` service was created for the Ceph dashboard.
- `curl` commands to the service's external IP timed out.

### Troubleshooting Steps

1.  **Service Endpoint Check:**
    - `kubectl get endpoints` for the service revealed `<none>`.
    - **Conclusion:** The service selector was not matching any pods.

2.  **Pod Status Check:**
    - `kubectl get pods -l app=rook-ceph-mgr` showed the manager pod was in a `Pending` state.
    - **Conclusion:** The pod could not be scheduled, which is why the service had no endpoints.

3.  **Pod Scheduling Investigation:**
    - `kubectl describe pod` on the pending manager pod revealed the error: `FailedScheduling: 4 node(s) didn't have free ports for the requested pod ports`.
    - The pod was configured with `hostPort` definitions, binding it directly to the node's network and causing port conflicts.
    - **Conclusion:** Host networking was the root cause of the scheduling failure.

4.  **Resolution Part 1: Disabling Host Networking**
    - The `hostPort`s were being set because the `CephCluster` custom resource had `spec.network.provider` set to `host`.
    - **Action:** Patched the `CephCluster` resource to set the provider to `""`, effectively disabling host networking.
    - `kubectl patch cephcluster rook-ceph -n rook-ceph --type=merge -p '{"spec":{"network":{"provider":""}}}'`
    - The old manager pod was deleted to force the creation of a new one with the updated settings.
    - **Result:** The new manager pod started successfully, and the `LoadBalancer` service received an endpoint. The dashboard became accessible.

### Follow-up Problem: Password Reverting
- After manually changing the admin password in the dashboard UI, it would revert to the original default password.

### Troubleshooting Steps

1.  **Operator Log Analysis:**
    - `kubectl logs` on the `rook-ceph-operator` pod showed log entries like `setting ceph dashboard "admin" login creds`.
    - **Conclusion:** The Rook operator was actively managing the password secret and resetting it during its reconciliation loop.

2.  **Resolution Part 2: Centralized Password Management**
    - To prevent the operator from overwriting the password, we needed to provide our own secret.
    - **Action 1:** Added a `dashboard_password` variable to `ansible/config.yml`.
    - **Action 2:** Added a task to `ansible/tasks/rook_ceph_deploy_part1.yml` to create a Kubernetes secret named `rook-ceph-dashboard-password` from the new variable.
    - **Action 3:** Modified `deployments/rook-ceph/rook-ceph-cluster-values.yaml` to tell the operator to use the provided secret by setting `dashboard.security.adminPasswordSecretName: rook-ceph-dashboard-password`.

### Final Outcome
- The Ceph dashboard is now reliably exposed via a `LoadBalancer`.
- The admin password is now persistently managed via Ansible configuration, preventing the Rook operator from resetting it.
