![wiki-banner.svg](images/wiki-banner.svg)
![accent-divider](images/accent-divider.svg)
# Runbooks

This page provides step-by-step operational procedures for common tasks.

![accent-divider](images/accent-divider.svg)
## Cold Start Cycle
1) Stage 1 — Wipe (destructive):
- Set in `ansible/config.yml`: `cold_start_stage_1_wipe_cluster: true` and optionally `perform_physical_disk_wipe: true`.
- Run: `ansible-playbook cleanup.yml`.

2) Stage 2 — Install Infrastructure:
- Set: `cold_start_stage_2_install_infrastructure: true`.
- Run: `ansible-playbook main.yml`.

3) Stage 3 — Deploy Applications:
- Set: `cold_start_stage_3_install_applications: true` and enable per-app `manual_install_*` flags.
- Run: `ansible-playbook main.yml`.

![accent-divider](images/accent-divider.svg)
## Reset an Application (keep or delete data)
1) In `ansible/config.yml` set `run_pod_cleanup: true`.
2) In `pod_cleanup_list`, keep only the target app and choose `delete_pvc: true|false`.
3) Run: `ansible-playbook cleanup.yml`.
4) Redeploy via Stage 3 if desired.

![accent-divider](images/accent-divider.svg)
## Rotate Internal CA
1) Create a new Intermediate CA signed by the offline Root CA.
2) Update cert-manager `ClusterIssuer` to reference the new Intermediate.
3) Trigger re-issuance of app certificates.
4) Distribute (or ensure trust of) the Root CA on client devices.

![accent-divider](images/accent-divider.svg)
## Add/Replace a Node
1) Image OS, set static DHCP reservation, ensure SSH.
2) Join as worker with k3s token; verify with `kubectl get nodes`.
3) Label/taint as needed and confirm workloads schedule as expected.

![accent-divider](images/accent-divider.svg)
## Upgrade k3s
1) Drain control plane node; upgrade; uncordon.
2) Sequentially drain/upgrade worker nodes; uncordon each.
3) Verify node readiness and workload recovery.

![accent-divider](images/accent-divider.svg)
## Observability Quick-Checks
- Prefer accessing UIs via Ingress + TLS at Traefik VIP.
- Verify Prometheus, Grafana, Alertmanager UIs load and show healthy targets.
- Check node-exporter and kube-state-metrics.

![accent-divider](images/accent-divider.svg)
## Secrets & Credentials
- Do not commit real credentials. Use Ansible Vault for secrets and GitHub Actions secrets for CI.
- If secrets were previously committed, rotate immediately and remove from repo history if necessary.

