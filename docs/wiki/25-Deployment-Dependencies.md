![accent-divider.svg](images/accent-divider.svg)
# Deployment Dependencies Analysis

This document analyzes the "spider web" of deployment dependencies in the Seadogger Homelab and proposes solutions to untangle them.

![accent-divider.svg](images/accent-divider.svg)
## Current Deployment Order (main.yml)

```yaml
1. Raspberry Pi Configuration (all nodes)
2. K3s Control Plane (control_plane)
3. K3s Workers (nodes)
4. MetalLB (control_plane)        ← Infrastructure layer
5. Rook-Ceph (control_plane)      ← Infrastructure layer
6. ArgoCD (control_plane)         ← GitOps layer
7. Namespace Pre-cooking          ← Preparation
8. Internal PKI + Cert-Manager    ← Certificate infrastructure
9. Prometheus (control_plane)     ← Monitoring
10. Applications:
    - Bedrock Gateway
    - PiHole
    - OpenWebUI
    - N8N
    - Nextcloud
    - Jellyfin
```

![accent-divider.svg](images/accent-divider.svg)
## Dependency Graph

### Layer 0: Cluster Foundation
```
┌──────────────────┐
│  K3s Cluster     │ (control plane + workers)
└────────┬─────────┘
         │
         └──── Required by: Everything else
```

### Layer 1: Core Infrastructure
```
┌──────────────────┐      ┌──────────────────┐
│    MetalLB       │      │   Rook-Ceph      │
│ (Load Balancer)  │      │   (Storage)      │
└────────┬─────────┘      └────────┬─────────┘
         │                         │
         │                         │
Required by:                Required by:
- Traefik (ingress entry)   - Prometheus PVC
- PiHole DNS LB             - Grafana PVC
                            - Alertmanager PVC
                            - Nextcloud PVC
                            - Jellyfin PVC
                            - All app PVCs
```

### Layer 2: GitOps & PKI
```
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│     ArgoCD       │      │  Cert-Manager    │      │  Internal PKI    │
│   (GitOps)       │      │ (K8s Certs)      │      │ (CA + Certs)     │
└────────┬─────────┘      └────────┬─────────┘      └────────┬─────────┘
         │                         │                         │
Required by:                Required by:                Required by:
- All apps via ArgoCD       - All app TLS certs         - Cert-Manager CA
- Infrastructure mgmt       - Certificate CRDs          - Traefik TLS
                                                        - Node trust stores
```

### Layer 3: Monitoring
```
┌──────────────────┐
│   Prometheus     │
│   Grafana        │
│  Alertmanager    │
└────────┬─────────┘
         │
Required by:
- Backup monitoring
- Cluster health
- App metrics
```

### Layer 4: Applications
```
┌─────────┬─────────┬─────────┬─────────┬─────────┐
│ PiHole  │Nextcloud│Jellyfin │OpenWebUI│   N8N   │
└─────────┴─────────┴─────────┴─────────┴─────────┘
```

![accent-divider.svg](images/accent-divider.svg)
## Detailed Dependency Analysis

### 1. **MetalLB Dependencies**

**What ACTUALLY needs MetalLB:**
- ✅ **Traefik** - Ingress controller entry point (LoadBalancer for HTTP/HTTPS)
- ✅ **PiHole** - DNS service needs LoadBalancer IP for network DNS
  - `pihole-values.yaml` - `serviceDns.loadBalancerIP: 192.168.1.250`

**What SHOULD NOT use MetalLB (use Ingress instead):**
- ❌ **Prometheus/Grafana/Alertmanager** - Currently uses LoadBalancer IPs (wasteful)
  - `prometheus_deploy.yml:90` - `loadBalancerIP: "192.168.1.244"` ← Should use Ingress
  - `prometheus_deploy.yml:111` - `loadBalancerIP: "192.168.1.245"` ← Should use Ingress
  - `prometheus_deploy.yml:131` - `loadBalancerIP: "192.168.1.246"` ← Should use Ingress
  - **Recommendation:** Use Traefik IngressRoute + cert-manager certificates instead
  - **Benefit:** Unified access pattern, automatic TLS, fewer IPs consumed

**What MetalLB depends on:**
- K3s cluster (API server, CNI)
- Nothing else!

**Current ordering:** ✅ **CORRECT** - MetalLB deployed before Traefik/PiHole

**Action Required:** Refactor Prometheus stack to use Ingress instead of LoadBalancer services

---

### 2. **Rook-Ceph Dependencies**

**What depends on Rook-Ceph:**
- ✅ **Prometheus** - Uses `storageClassName: ceph-block-data`
  - PVCs for Prometheus, Grafana, Alertmanager data

- ✅ **Nextcloud** - Uses `storageClassName: ceph-filesystem`
  - Stores all user files, photos, documents

- ✅ **Jellyfin** - Uses static PV backed by Ceph
  - `jellyfin/static-pv.yaml` - Media library metadata

- ✅ **N8N** - Workflow persistence
- ✅ **OpenWebUI** - Chat history

**What Rook-Ceph depends on:**
- K3s cluster
- Storage nodes with available disks
- Nothing else!

**Current ordering:** ✅ **CORRECT** - Rook-Ceph deployed before apps

**Issue:** Rook-Ceph is `default(false)` in main.yml but apps assume it exists!

```yaml
# main.yml:51
- name: Deploy Rook-Ceph - Part 1 (Core Components)
  import_tasks: tasks/rook_ceph_deploy_part1.yml
  when: enable_rook_ceph_part1 | default(false)  # ❌ Default FALSE
```

**Risk:** If Rook-Ceph disabled, all apps fail with PVC binding issues!

---

### 3. **ArgoCD Dependencies**

**What depends on ArgoCD:**
- ✅ **Most applications** - Deployed via ArgoCD Application CRDs
  - Nextcloud, PiHole, OpenWebUI, N8N, Jellyfin
  - Prometheus (if using GitOps pattern)

**What ArgoCD depends on:**
- K3s cluster
- Optional: MetalLB for LoadBalancer service
- Nothing else!

**Current ordering:** ✅ **CORRECT** - ArgoCD before apps

**Hybrid Deployment Issue:**
Some components deployed via:
1. **Ansible direct Helm** (MetalLB, Rook-Ceph, sometimes Prometheus)
2. **ArgoCD** (apps via `kubernetes.core.k8s` creating Application CRDs)
3. **Ansible kubectl apply** (Ingress manifests downloaded from GitHub)

This creates inconsistency - no single source of truth!

---

### 4. **Prometheus Dependencies**

**What depends on Prometheus:**
- ✅ **Backup monitoring** - PrometheusRule for backup alerts
- ✅ **Cluster observability** - ServiceMonitors for all apps
- Optional: Grafana dashboards, AlertManager notifications

**What Prometheus depends on:**
- **CRITICAL:** MetalLB (for LoadBalancer IPs)
- **CRITICAL:** Rook-Ceph (for persistent storage)
- **CRITICAL:** Prometheus CRDs must be installed first
  - `prometheus_deploy.yml:8-17` - Manually applies CRDs

**Current ordering:** ✅ **CORRECT** - After MetalLB and Rook-Ceph

**Issue:** CRDs downloaded from external URL every deployment
```yaml
kubectl apply --server-side -f https://raw.githubusercontent.com/prometheus-operator/kube-prometheus/release-0.13/manifests/setup/...
```

**Risk:** Network failure = deployment failure

---

### 5. **Cert-Manager + Internal PKI Dependencies**

**What depends on Cert-Manager:**
- ✅ **All Application TLS Certificates** - Uses Certificate CRD
  - `argocd-certificate.yml` - ArgoCD dashboard HTTPS
  - `nextcloud-certificate.yml` - Nextcloud HTTPS
  - `jellyfin-certificate.yml` - Jellyfin HTTPS
  - `pihole-certificate.yml` - PiHole admin HTTPS
  - `n8n-certificate.yml` - N8N HTTPS
  - `openwebui-certificate.yml` - OpenWebUI HTTPS
  - `ceph-dashboard-certificate.yml` - Ceph dashboard HTTPS

- ✅ **Traefik Ingress** - Consumes TLS secrets created by cert-manager
  - IngressRoute objects reference TLS secrets
  - Traefik terminates TLS at ingress using these certs

- ✅ **Internal PKI ClusterIssuer** - Must exist before Certificate resources
  - `ClusterIssuer: internal-local-issuer` references CA secret

**What Cert-Manager depends on:**
- **CRITICAL:** K3s cluster (API server, CRDs)
- **CRITICAL:** ArgoCD (deployed as ArgoCD Application)
  - `cert-manager-application.yml` - Uses Helm chart from Jetstack
  - Chart version: v1.14.4
  - `installCRDs: true` - Installs Certificate CRDs

**What Internal PKI depends on:**
- **CRITICAL:** Cert-Manager must be running first
  - Creates CA hierarchy on control plane node (yoda)
  - Root CA → Intermediate CA
  - Stores CA keypairs as Kubernetes secrets in `cert-manager` namespace

**Current ordering:** ✅ **CORRECT** - Internal PKI deployed after ArgoCD/cert-manager

**Current implementation flow:**
```yaml
# Step 1: ArgoCD deploys cert-manager (via Application CRD)
# Step 2: Ansible waits for cert-manager pods ready
# Step 3: Generate Root CA on yoda.local:
#   - openssl genrsa (4096-bit root CA key)
#   - openssl req -x509 (self-signed root cert, 10 years)
# Step 4: Generate Intermediate CA on yoda.local:
#   - openssl genrsa (4096-bit intermediate key)
#   - openssl req + x509 (signed by root CA, 5 years)
# Step 5: Create Kubernetes secrets in cert-manager namespace:
#   - internal-intermediate-ca-secret (type: kubernetes.io/tls)
#   - internal-root-ca-secret (type: Opaque, archival)
# Step 6: Create ClusterIssuer pointing to intermediate CA secret
# Step 7: Apply Certificate manifests for all apps
# Step 8: Distribute root CA to all nodes' trust stores
#   - /usr/local/share/ca-certificates/internal-root-ca.crt
#   - update-ca-certificates (Debian/Ubuntu)
```

**Key Files:**
- `ansible/tasks/internal_pki_deploy.yml` (492 lines)
- `certificates/cert-manager-application.yml` (ArgoCD app)
- `certificates/*-certificate.yml` (7 app certificates)

**Issue:** Complex multi-step process mixing OpenSSL, Ansible, and Kubernetes
- CA generation on one node (yoda.local)
- Manual secret creation
- Certificate application via kubectl
- Trust distribution via Ansible

**Opportunity:** Could be simplified with cert-manager CA Injector or external-secrets operator

---

### 6. **Application Dependencies**

**Nextcloud:**
- **CRITICAL:** Rook-Ceph (`ceph-filesystem` StorageClass)
- **CRITICAL:** ArgoCD (deployed via Application CRD)
- Optional: MetalLB (if using LoadBalancer vs Ingress)

**PiHole:**
- **CRITICAL:** MetalLB (DNS needs LoadBalancer IP)
- **CRITICAL:** ArgoCD (deployed via Application CRD)
- Optional: Rook-Ceph (persistence disabled in current config)

**Jellyfin:**
- **CRITICAL:** Rook-Ceph (static PV for metadata)
- **CRITICAL:** ArgoCD (deployed via Application CRD)
- **CRITICAL:** Pre-existing PV/PVC for media mount

**Prometheus/Grafana/Alertmanager:**
- **CRITICAL:** MetalLB (LoadBalancer IPs)
- **CRITICAL:** Rook-Ceph (persistent volumes)
- **CRITICAL:** Prometheus Operator CRDs

![accent-divider.svg](images/accent-divider.svg)
## Problems with Current Approach

### Problem 1: **Implicit Dependencies**

Dependencies are encoded in task execution order, not declared explicitly.

**Example:** Prometheus task assumes MetalLB exists but doesn't validate:
```yaml
# prometheus_deploy.yml:78-97
- name: Create Prometheus LoadBalancer Service
  ansible.builtin.k8s:
    definition:
      spec:
        type: LoadBalancer
        loadBalancerIP: "192.168.1.244"  # ❌ No check if MetalLB ready!
```

If MetalLB isn't running, service stays in `Pending` forever.

### Problem 2: **Default Configuration Conflicts**

```yaml
# main.yml
enable_rook_ceph_part1: default(false)     # Disabled by default!
enable_metallb_native: default(true)       # Enabled by default

# But apps assume both are enabled:
# nextcloud-values.yaml:
storageClassName: ceph-filesystem          # ❌ Fails if Rook-Ceph disabled!

# pihole-values.yaml:
serviceDns:
  type: LoadBalancer
  loadBalancerIP: 192.168.1.250            # ❌ Pending if MetalLB disabled!
```

### Problem 3: **External URL Dependencies**

Multiple tasks download from GitHub during deployment:

```yaml
# argocd_native_deploy.yml:103-106
- name: Download ArgoCD IngressRoutes manifest from GitHub
  ansible.builtin.get_url:
    url: "https://raw.githubusercontent.com/seadogger/seadogger-homelab/master/ingress/traefik-argocd-ingress.yml"
```

**Risk:**
- GitHub down = deployment fails
- Manifest changed = unexpected behavior
- No version control of exact manifest used

### Problem 4: **Mixed Deployment Methods**

| Component | Method | Managed By | Issue |
|-----------|--------|------------|-------|
| MetalLB | Ansible + Helm | Ansible | Can't see in ArgoCD UI |
| Rook-Ceph | Ansible + Helm | Ansible | Can't see in ArgoCD UI |
| Cert-Manager | ArgoCD Application | ArgoCD | ✅ Consistent |
| Internal PKI | Ansible + OpenSSL | Ansible | Manual CA generation on yoda.local |
| Prometheus CRDs | Ansible + kubectl | Ansible | Manual CRD management |
| Prometheus | ArgoCD Application | ArgoCD | Depends on manually applied CRDs |
| Nextcloud | ArgoCD Application | ArgoCD | ✅ Consistent |
| Ingress | Ansible + kubectl | Ansible | Separate from app deployment |

**Problem:** No single source of truth, drift between Ansible state and cluster state.

### Problem 5: **No Dependency Validation**

Tasks don't check prerequisites:

```yaml
# nextcloud_deploy.yml - No check for:
# ✓ Is ArgoCD running?
# ✓ Is Rook-Ceph ready?
# ✓ Does ceph-filesystem StorageClass exist?

- name: Create Nextcloud ArgoCD Application
  kubernetes.core.k8s:
    state: present
    definition:
      apiVersion: argoproj.io/v1alpha1
      kind: Application
      # ... creates app that will fail if deps missing
```

### Problem 6: **Namespace Pre-cooking is Misplaced**

```yaml
# main.yml:60-66
# Namespaces created AFTER ArgoCD deployed
- name: Pre-cook Namespaces
  import_tasks: tasks/namespaces_precook.yml
```

But ArgoCD has `syncOptions: - CreateNamespace=true` so this is redundant!

### Problem 7: **Complex PKI Bootstrap Process**

The internal PKI setup is a 492-line Ansible task that:
- Runs OpenSSL commands on one specific node (yoda.local)
- Generates CA hierarchy outside Kubernetes
- Manually creates secrets in cert-manager namespace
- Distributes CA to all node trust stores via Ansible
- Applies Certificate manifests via kubectl

**Issues:**
- Fragile: Depends on yoda.local being available
- Not GitOps: CA generation not declarative
- Manual: Certificate manifests applied via Ansible, not ArgoCD
- Drift risk: Node trust stores managed outside K8s

![accent-divider.svg](images/accent-divider.svg)
## Proposed Solutions

### Solution 1: **Explicit Dependency Checks (Immediate)**

Add validation tasks before each deployment:

**Example: Pre-flight checks for Prometheus**
```yaml
---
# tasks/prometheus_deploy.yml (refactored)

- name: Validate MetalLB is ready
  kubernetes.core.k8s_info:
    kind: DaemonSet
    name: metallb-speaker
    namespace: metallb-system
  register: metallb_speaker
  failed_when: >
    metallb_speaker.resources | length == 0 or
    metallb_speaker.resources[0].status.numberReady < 1

- name: Validate Rook-Ceph StorageClass exists
  kubernetes.core.k8s_info:
    kind: StorageClass
    name: ceph-block-data
  register: storage_class
  failed_when: storage_class.resources | length == 0

- name: Validate Rook-Ceph is healthy
  kubernetes.core.k8s_exec:
    namespace: rook-ceph
    pod: "{{ lookup('kubernetes.core.k8s', kind='Pod', namespace='rook-ceph', label_selector='app=rook-ceph-tools').metadata.name }}"
    command: ceph health
  register: ceph_health
  failed_when: "'HEALTH_OK' not in ceph_health.stdout and 'HEALTH_WARN' not in ceph_health.stdout"

# Only proceed if all checks pass
- name: Deploy Prometheus
  # ... existing deployment
```

**Benefits:**
- ✅ Fail fast with clear error messages
- ✅ Prevents partial deployments
- ✅ Self-documenting dependencies

### Solution 2: **Dependency Declaration with Ansible Role Dependencies**

Restructure as roles with `meta/main.yml` dependencies:

```yaml
# roles/prometheus/meta/main.yml
---
dependencies:
  - role: metallb
    when: enable_metallb | default(true)
  - role: rook-ceph
    when: enable_rook_ceph | default(true)
```

```yaml
# roles/nextcloud/meta/main.yml
---
dependencies:
  - role: rook-ceph
  - role: argocd
```

Ansible automatically ensures dependencies are installed first!

**Benefits:**
- ✅ Explicit dependency graph
- ✅ Automatic ordering
- ✅ Can run `ansible-playbook` targeting any role

### Solution 3: **ArgoCD ApplicationSets with Waves**

Use ArgoCD sync waves to control ordering:

```yaml
---
# argocd/infrastructure-appset.yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: infrastructure
  namespace: argocd
spec:
  generators:
  - list:
      elements:
      # Wave 0: Core infrastructure
      - name: metallb
        namespace: metallb-system
        wave: "0"
        chart: metallb/metallb

      - name: rook-ceph-operator
        namespace: rook-ceph
        wave: "0"
        chart: rook-release/rook-ceph

      - name: cert-manager
        namespace: cert-manager
        wave: "0"
        chart: jetstack/cert-manager

      # Wave 1: Storage cluster + PKI (depends on operator)
      - name: rook-ceph-cluster
        namespace: rook-ceph
        wave: "1"
        chart: rook-release/rook-ceph-cluster

      - name: internal-pki
        namespace: cert-manager
        wave: "1"
        path: deployments/infrastructure/base/internal-pki

      # Wave 2: Monitoring (depends on MetalLB + Rook-Ceph)
      - name: prometheus
        namespace: monitoring
        wave: "2"
        chart: prometheus-community/kube-prometheus-stack

  template:
    metadata:
      name: '{{name}}'
      annotations:
        argocd.argoproj.io/sync-wave: "{{wave}}"  # ← Controls order!
    spec:
      project: default
      source:
        repoURL: '{{chart}}'
        targetRevision: '{{version}}'
      destination:
        server: https://kubernetes.default.svc
        namespace: '{{namespace}}'
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
        syncOptions:
        - CreateNamespace=true
        # Wait for previous wave to complete
        - RespectIgnoreDifferences=true
```

**Benefits:**
- ✅ ArgoCD enforces dependencies automatically
- ✅ Visible in ArgoCD UI with sync waves
- ✅ Can manually re-sync any wave
- ✅ Removes Ansible from deployment loop (only bootstrap ArgoCD)

### Solution 4: **Health Checks with Retry Logic**

Add retries for services that depend on eventual consistency:

```yaml
- name: Wait for MetalLB IP allocation
  kubernetes.core.k8s_info:
    kind: Service
    name: prometheus-k8s-lb
    namespace: monitoring
  register: svc
  until: >
    svc.resources | length > 0 and
    svc.resources[0].status.loadBalancer.ingress is defined
  retries: 30
  delay: 10
```

### Solution 5: **Remove External URL Dependencies**

Store all manifests in Git repo:

**Before:**
```yaml
- name: Download ArgoCD IngressRoutes from GitHub
  ansible.builtin.get_url:
    url: "https://raw.githubusercontent.com/.../traefik-argocd-ingress.yml"
```

**After:**
```yaml
- name: Apply ArgoCD IngressRoutes from local repo
  kubernetes.core.k8s:
    definition: "{{ lookup('file', 'manifests/ingress/argocd.yml') }}"
```

Or better, bundle with Helm chart:
```yaml
# argocd-chart/templates/ingress.yaml
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
# ...
```

### Solution 6: **Configuration Validation**

Add Ansible assertions at playbook start:

```yaml
---
# playbooks/validate-config.yml
- hosts: localhost
  tasks:
    - name: Validate required components are enabled
      ansible.builtin.assert:
        that:
          - enable_metallb_native | bool
          - enable_rook_ceph_part1 | bool
          - enable_argocd_native | bool
        fail_msg: |
          ERROR: Core infrastructure components must be enabled!
          Set in config.yml:
            enable_metallb_native: true
            enable_rook_ceph_part1: true
            enable_argocd_native: true

    - name: Validate storage class configuration
      ansible.builtin.assert:
        that:
          - enable_rook_ceph_part1 | bool or default_storage_class is defined
        fail_msg: "ERROR: No storage backend configured!"
```

![accent-divider.svg](images/accent-divider.svg)
## Recommended Implementation Plan

### Phase 1: Add Immediate Safeguards (Week 1)

1. **Add pre-flight checks to each task**
   - Validate MetalLB before Prometheus
   - Validate Rook-Ceph before app deployments
   - Validate ArgoCD before creating Applications

2. **Add configuration validation playbook**
   - Run before main.yml
   - Fail fast if requirements not met

3. **Fix default values**
   ```yaml
   # config.yml
   enable_rook_ceph_part1: true  # Changed from false!
   ```

### Phase 2: Store Manifests Locally (Week 2)

1. **Copy all external manifests to repo**
   ```
   core/manifests/
   ├── ingress/
   │   ├── argocd.yml
   │   ├── prometheus.yml
   │   └── ...
   ├── crds/
   │   └── prometheus-operator/
   └── configs/
   ```

2. **Update tasks to use local files**

### Phase 3: Migrate to ArgoCD Sync Waves (Weeks 3-4)

1. **Create ApplicationSets for infrastructure**
   - Wave 0: MetalLB, Rook-Ceph Operator
   - Wave 1: Rook-Ceph Cluster
   - Wave 2: Prometheus, ArgoCD itself

2. **Create ApplicationSets for apps**
   - Wave 3: PiHole, Nextcloud, etc.

3. **Simplify Ansible to only:**
   - Bootstrap K3s
   - Deploy root ArgoCD application
   - Everything else via GitOps

### Phase 4: Convert to Ansible Roles (Weeks 5-6)

1. **Create role structure**
2. **Add `meta/main.yml` dependencies**
3. **Test in staging environment**

![accent-divider.svg](images/accent-divider.svg)
## Dependency Matrix

| Component | Depends On | Used By | Critical Path? |
|-----------|------------|---------|----------------|
| K3s Cluster | Hardware | Everything | ✅ YES |
| MetalLB | K3s | Prometheus, PiHole, Apps (optional) | ✅ YES |
| Rook-Ceph | K3s, Storage devices | Prometheus, Nextcloud, Jellyfin, All Apps | ✅ YES |
| ArgoCD | K3s | App deployments | ✅ YES |
| Internal PKI | K3s | Traefik TLS | ⚠️ Optional |
| Prometheus | MetalLB, Rook-Ceph, CRDs | Monitoring, Alerts | ⚠️ Recommended |
| Namespaces | K3s | Apps | ❌ Auto-created by ArgoCD |
| Nextcloud | Rook-Ceph, ArgoCD | User files | App-level |
| PiHole | MetalLB, ArgoCD | DNS | App-level |
| Jellyfin | Rook-Ceph, ArgoCD, Static PV | Media | App-level |

**Critical Path:** K3s → MetalLB + Rook-Ceph → ArgoCD → Apps

![accent-divider.svg](images/accent-divider.svg)
## Example: Improved Prometheus Deployment

**Before (implicit dependencies):**
```yaml
# tasks/prometheus_deploy.yml (current)
- name: Deploy Prometheus
  # Just creates resources, no validation
```

**After (explicit dependencies + validation):**
```yaml
---
# roles/prometheus/tasks/preflight.yml
- name: Check MetalLB is operational
  kubernetes.core.k8s_info:
    kind: DaemonSet
    namespace: metallb-system
    name: metallb-speaker
  register: metallb
  failed_when: metallb.resources | length == 0 or metallb.resources[0].status.numberReady < 1

- name: Check Rook-Ceph StorageClass exists
  kubernetes.core.k8s_info:
    kind: StorageClass
    name: ceph-block-data
  register: sc
  failed_when: sc.resources | length == 0

- name: Check Prometheus CRDs are installed
  kubernetes.core.k8s_info:
    kind: CustomResourceDefinition
    name: "{{ item }}"
  loop:
    - prometheuses.monitoring.coreos.com
    - servicemonitors.monitoring.coreos.com
    - alertmanagers.monitoring.coreos.com
  register: crds
  failed_when: crds.results | selectattr('resources', 'equalto', []) | list | length > 0

---
# roles/prometheus/tasks/main.yml
- name: Run pre-flight checks
  include_tasks: preflight.yml

- name: Deploy Prometheus via ArgoCD
  kubernetes.core.k8s:
    definition:
      apiVersion: argoproj.io/v1alpha1
      kind: Application
      metadata:
        name: prometheus
        namespace: argocd
        annotations:
          argocd.argoproj.io/sync-wave: "2"
      # ...

---
# roles/prometheus/meta/main.yml
dependencies:
  - role: metallb
  - role: rook-ceph
```

![accent-divider.svg](images/accent-divider.svg)
## Conclusion

The current deployment has an **implicit dependency spider web** where:
- Dependencies are encoded in execution order, not declared
- No validation that prerequisites are met
- Mixed deployment methods (Ansible + ArgoCD + kubectl)
- External URL dependencies create brittleness

**Solutions:**
1. **Immediate:** Add pre-flight validation to each task
2. **Short-term:** Store manifests locally, fix configuration defaults
3. **Medium-term:** Migrate to ArgoCD sync waves for GitOps consistency
4. **Long-term:** Convert to Ansible roles with explicit dependencies

**Benefits:**
- ✅ Fail fast with clear errors
- ✅ Self-documenting dependencies
- ✅ Testable in staging
- ✅ Single source of truth (Git)
- ✅ Visible dependency graph

This transforms the "spider web" into a **directed acyclic graph (DAG)** that's explicit, validated, and maintainable.
![accent-divider.svg](images/accent-divider.svg)
## Can Everything Be an ArgoCD App with Kustomize?

### TL;DR: **YES, with one exception (K3s itself)**

**What CAN be ArgoCD apps:**
- ✅ MetalLB
- ✅ Rook-Ceph (both operator and cluster)
- ✅ Cert-Manager (already is!)
- ✅ Internal PKI (CA secrets + ClusterIssuer)
- ✅ ArgoCD itself (self-managed!)
- ✅ Prometheus
- ✅ All applications (Nextcloud, PiHole, etc.)
- ✅ Ingress resources

**What CANNOT:**
- ❌ K3s installation (cluster must exist first)
- ❌ ArgoCD bootstrap (chicken-and-egg, but see below)
- ⚠️ CA generation (OpenSSL commands, but can be improved)

### The Bootstrap Problem

You need ArgoCD to exist before it can manage itself. Solution: **Bootstrap then self-manage**

```yaml
# Step 1: Ansible installs ArgoCD initially
- name: Bootstrap ArgoCD
  kubernetes.core.helm:
    name: argocd
    chart_ref: argo/argo-cd
    namespace: argocd

# Step 2: ArgoCD Application that manages ArgoCD itself
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: argocd
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/seadogger-tech/seadogger-homelab
    path: deployments/argocd  # ← Kustomize overlay
    targetRevision: main
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

After bootstrap, **ArgoCD manages itself** via GitOps!

### Proposed Kustomize Structure

```
seadogger-homelab/
├── deployments/
│   ├── infrastructure/
│   │   ├── base/
│   │   │   ├── metallb/
│   │   │   │   ├── kustomization.yaml
│   │   │   │   ├── namespace.yaml
│   │   │   │   └── ipaddresspool.yaml
│   │   │   ├── rook-ceph-operator/
│   │   │   │   ├── kustomization.yaml
│   │   │   │   └── helm-values.yaml
│   │   │   ├── rook-ceph-cluster/
│   │   │   │   ├── kustomization.yaml
│   │   │   │   ├── cluster.yaml
│   │   │   │   └── storageclass.yaml
│   │   │   ├── cert-manager/
│   │   │   │   ├── kustomization.yaml
│   │   │   │   └── helm-values.yaml
│   │   │   ├── internal-pki/
│   │   │   │   ├── kustomization.yaml
│   │   │   │   ├── ca-secret.yaml  # ← Sealed or external-secrets
│   │   │   │   ├── clusterissuer.yaml
│   │   │   │   └── certificates/  # ← All app certs
│   │   │   └── prometheus/
│   │   │       ├── kustomization.yaml
│   │   │       ├── crds/  # ← Store CRDs in Git!
│   │   │       └── values.yaml
│   │   └── overlays/
│   │       ├── production/
│   │       │   └── kustomization.yaml  # IP addresses, sizes
│   │       └── staging/
│   │           └── kustomization.yaml  # Smaller, different IPs
│   │
│   ├── apps/
│   │   ├── base/
│   │   │   ├── nextcloud/
│   │   │   │   ├── kustomization.yaml
│   │   │   │   ├── values.yaml
│   │   │   │   └── ingress.yaml
│   │   │   ├── pihole/
│   │   │   ├── jellyfin/
│   │   │   └── portal/  # ← Already done in Pro!
│   │   └── overlays/
│   │       ├── production/
│   │       └── staging/
│   │
│   └── argocd/
│       ├── root-app.yaml  # App-of-apps
│       ├── infrastructure-appset.yaml
│       └── apps-appset.yaml
│
└── ansible/
    └── playbooks/
        └── bootstrap.yml  # ONLY installs K3s + ArgoCD root app
```

### How ArgoCD Handles Helm with Kustomize

**Option 1: ArgoCD native Helm support (Current)**

```yaml
# argocd/apps/nextcloud.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: nextcloud
spec:
  source:
    repoURL: https://nextcloud.github.io/helm/
    chart: nextcloud
    targetRevision: "7.0.2"
    helm:
      valueFiles:
      - $values/deployments/nextcloud/values.yaml
  sources:
  - repoURL: https://github.com/seadogger-tech/seadogger-homelab
    targetRevision: main
    ref: values
```

**Option 2: Kustomize with helmCharts (More flexible)**

```yaml
# deployments/nextcloud/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

helmCharts:
- name: nextcloud
  repo: https://nextcloud.github.io/helm/
  version: "7.0.2"
  releaseName: nextcloud
  namespace: nextcloud
  valuesFile: values.yaml

resources:
- ingress.yaml  # Bundle ingress with app!

patches:
- target:
    kind: Deployment
    name: nextcloud
  patch: |-
    - op: add
      path: /spec/template/spec/nodeSelector
      value:
        kubernetes.io/arch: arm64
```

### Rook-Ceph as ArgoCD App (Full Example)

**Operator Application:**
```yaml
---
# argocd/infrastructure-apps/rook-ceph-operator.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: rook-ceph-operator
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "0"
spec:
  project: default
  source:
    repoURL: https://github.com/seadogger-tech/seadogger-homelab
    path: deployments/infrastructure/base/rook-ceph-operator
    targetRevision: main
  destination:
    server: https://kubernetes.default.svc
    namespace: rook-ceph
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
    - CreateNamespace=true
```

**Cluster Application (waits for operator):**
```yaml
---
# argocd/infrastructure-apps/rook-ceph-cluster.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: rook-ceph-cluster
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "1"  # After operator!
spec:
  project: default
  source:
    repoURL: https://github.com/seadogger-tech/seadogger-homelab
    path: deployments/infrastructure/overlays/production/rook-ceph-cluster
    targetRevision: main
  destination:
    server: https://kubernetes.default.svc
    namespace: rook-ceph
  syncPolicy:
    automated:
      prune: false  # Don't auto-delete storage!
      selfHeal: true
    syncOptions:
    - ServerSideApply=true  # For large CRDs
```

**Kustomize structure:**
```yaml
# deployments/infrastructure/base/rook-ceph-cluster/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
- cluster.yaml
- storageclass-block.yaml
- storageclass-filesystem.yaml
- toolbox.yaml
- ingress.yaml  # ← Bundle ingress!
```

**Production overlay:**
```yaml
# deployments/infrastructure/overlays/production/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
- ../../base/rook-ceph-cluster

patches:
- target:
    kind: CephCluster
  patch: |-
    - op: replace
      path: /spec/storage/devices
      value:
      - name: /dev/nvme0n1p3  # Production NVMe
```

### What Ansible Does (Minimal!)

```yaml
---
# ansible/playbooks/bootstrap.yml
- name: Bootstrap Homelab
  hosts: cluster
  tasks:
    # Stage 1: Install K3s
    - import_role:
        name: k3s

    # Stage 2: Install ArgoCD
    - import_role:
        name: argocd-bootstrap

    # Stage 3: Deploy root app
    - name: Deploy root app-of-apps
      kubernetes.core.k8s:
        definition: "{{ lookup('file', '../deployments/argocd/root-app.yaml') }}"

    # DONE! ArgoCD handles the rest
```

### Migration Path

**Phase 1: Store everything in Git** (Week 1)
```bash
# Move external URLs to Git
mkdir -p core/deployments/manifests/{crds,ingress}

# Prometheus CRDs
curl https://raw.githubusercontent.com/.../alertmanager.yaml \
  > core/deployments/prometheus/crds/alertmanager.yaml

# All ingress manifests
mv core/ingress/*.yml core/deployments/manifests/ingress/
```

**Phase 2: Convert to Kustomize** (Weeks 2-3)
```bash
# For each component:
mkdir -p deployments/infrastructure/base/metallb
# Create kustomization.yaml, resources
```

**Phase 3: Create ArgoCD Apps** (Weeks 3-4)
```bash
# Deploy via ArgoCD
kubectl apply -f deployments/argocd/infrastructure-appset.yaml
```

**Phase 4: Remove Ansible** (Weeks 4-5)
```bash
# Delete deployment tasks, keep only bootstrap
rm ansible/tasks/*_deploy.yml
```

### Portal Proof of Concept (Already Working!)

```yaml
# deployments/portal/kustomization.yaml (Pro repo)
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: portal

resources:
  - deployment.yaml
  - service.yaml
  - ingressroutes.yml
  - certificate.yml

configMapGenerator:
  - name: portal-html
    files:
      - index.html=portal.html
```

**This pattern works!** Just replicate for all components.

### Benefits of Full GitOps

✅ **Single source of truth** - Everything in Git
✅ **Visible in ArgoCD UI** - See all apps, dependencies, health
✅ **Automatic sync** - Git commit = cluster update
✅ **Easy rollback** - Revert Git commit
✅ **Production/Staging overlays** - Same base, different configs
✅ **No Ansible sprawl** - Just bootstrap, rest is GitOps
✅ **Testable** - Staging environment uses same manifests

### Answer: YES, Everything Can Be ArgoCD + Kustomize!

**Summary:**
1. ✅ **K3s** - Ansible only (must exist first)
2. ✅ **ArgoCD** - Bootstrap with Ansible, then self-manage
3. ✅ **MetalLB** - ArgoCD app (wave 0)
4. ✅ **Rook-Ceph** - ArgoCD apps (wave 0-1)
5. ✅ **Prometheus** - ArgoCD app (wave 2)
6. ✅ **All Apps** - ArgoCD apps (wave 3+)
7. ✅ **Ingress** - Bundled with each app

Portal in Pro already proves this works!
