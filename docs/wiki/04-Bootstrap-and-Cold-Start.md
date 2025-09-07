
# Bootstrap & Cold Start (IaC)

**Stages**
- **Stage 1 – Core Infra:** Node prep → K3s → Rook‑Ceph → MetalLB
- **Stage 2 – Platform Infra:** ArgoCD (native Helm) → Traefik + TLS base
- **Stage 3 – Apps:** Observability → Apps

**Config flags (example)** `ansible/group_vars/all/config.yml`
```yaml
stages:
  infra_core: true
  infra_platform: true
  apps: false   # enable only after Stage 1 & 2 are healthy

components:
  rook_ceph: true
  metallb: true
  argocd: true
  traefik: true

apps:
  pihole: false
  openwebui: false
  bedrock_gateway: false
  n8n: false
  plex: false
```

**Enforcement pattern**
```yaml
# infra gate
when:
  - stages.infra_core | default(false) | bool
  - components.rook_ceph | default(false) | bool
```
```yaml
# app gate
when:
  - stages.apps | default(false) | bool
  - apps.plex | default(false) | bool
```

**Clean/Wipe**
- Remove finalizers; delete stuck namespaces; wipe storage only when intended.
- After wipe, re-run Stage 1 → Stage 2 → Stage 3 progressively.
