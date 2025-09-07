# Bootstrap & Cold Start (IaC)
*Generated — 2025-09-07 23:19 UTC*

## Stages
- **Stage 1 – Core Infra:** Node prep → K3s → Rook-Ceph → MetalLB
- **Stage 2 – Platform Infra:** ArgoCD (Helm) → Traefik + TLS base
- **Stage 3 – Apps:** Observability → Apps

## Enforcement Patterns
```yaml
when:
  - stages.infra_core | default(false) | bool
  - components.rook_ceph | default(false) | bool
```
```yaml
when:
  - stages.apps | default(false) | bool
  - apps.plex | default(false) | bool
```

## Clean/Wipe
- Remove finalizers; delete stuck namespaces; wipe storage only when intended.
- After wipe, re-run Stage 1 → Stage 2 → Stage 3 progressively.

## From the Memory Bank
- [Rook-Ceph NFS Ganesha Debugging Summary](memory_bank/2025-08-10-rook-ceph-nfs-debug-summary.md)
- [Summary of Rook-Ceph NFS Debugging Session (2025-08-11)](memory_bank/2025-08-11-rook-ceph-nfs-debug-summary.md)
- [Internal PKI and HTTPS Data Flow Architecture](memory_bank/2025-08-12-internal-pki-and-https-flow.md)
- [Ansible Playbook Debugging Session - 2025-08-15](memory_bank/2025-08-15-ansible-playbook-debugging-session.md)
- [K3s Cluster Cold Start Procedure (Revised)](memory_bank/2025-08-15-k3s-cold-start-procedure.md)
- [Prometheus Stack Deployment Verification](memory_bank/2025-08-15-prometheus-deployment-verification.md)
- [Ansible Deployment Idempotency Refactor Plan](memory_bank/2025-08-16-ansible-idempotency-refactor-plan.md)
- [Ceph Dashboard Exposure and Password Management Troubleshooting](memory_bank/2025-08-16-ceph-dashboard-troubleshooting.md)
- [Summary of Cluster Recovery and Playbook Hardening Session](memory_bank/2025-08-16-cluster-recovery-and-playbook-hardening.md)
- [Ansible Idempotency and Cold Start Test Plan](memory_bank/2025-08-16-cold-start-test-plan.md)
- [Rook-Ceph Storage Architecture Update](memory_bank/2025-08-17-rook-ceph-storage-architecture-update.md)
- [Stable Deployment and Cold Start Procedure](memory_bank/2025-08-17-stable-deployment-and-cold-start-procedure.md)
- [Active Context: seadogger-homelab](memory_bank/activeContext.md)
- [Product Context: seadogger-homelab](memory_bank/productContext.md)
- [Progress: seadogger-homelab](memory_bank/progress.md)
- [Project Brief: seadogger-homelab](memory_bank/projectbrief.md)
- [Rook-Ceph CephFS with Erasure Coding Lessons](memory_bank/rook-ceph-ec-filesystem-lessons.md)
- [System Patterns: seadogger-homelab](memory_bank/systemPatterns.md)
- [Technical Context: seadogger-homelab](memory_bank/techContext.md)
