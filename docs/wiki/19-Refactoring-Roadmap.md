![accent-divider.svg](images/accent-divider.svg)
# Refactoring Roadmap

This document provides a comprehensive analysis of the Seadogger Homelab codebase and outlines a prioritized roadmap for refactoring the infrastructure to align with Kubernetes (K3s) industry best practices.

![accent-divider.svg](images/accent-divider.svg)
## Executive Summary

**Current Maturity:** 6/10 - Functional homelab with good automation foundation
**Target Maturity:** 9/10 - Enterprise-grade, production-ready homelab
**Estimated Timeline:** 8-10 weeks for core improvements
**Primary Focus Areas:**
1. 🔴 **CRITICAL:** Disaster Recovery & Backup (S3 Glacier for 4TB data)
2. 🔴 **CRITICAL:** Staging Environment (Virtual ARM64 testing)
3. 🟠 **HIGH:** Deployment Dependencies Refactor (Untangle spider web, GitOps everything)
4. 🟡 **MEDIUM:** Ansible Architecture Improvements
5. 🟡 **MEDIUM:** K3s Best Practices & GitOps Standardization

**⚠️ PRODUCTION STATUS:** Homelab is now in production use. Data loss prevention and safe testing environments are top priorities.

![accent-divider.svg](images/accent-divider.svg)
## Current State Analysis

### Strengths ✅

- **Clean Architecture:** Clear separation between Core (open source) and Pro (commercial) components
- **Staged Deployment:** Well-organized 3-stage approach (wipe → infrastructure → applications)
- **GitOps Foundation:** ArgoCD integration for most application deployments
- **Comprehensive Cleanup:** Dedicated cleanup playbook with granular control
- **Modern Wait Conditions:** Proper use of Kubernetes wait conditions vs hardcoded sleeps
- **Working System:** Fully functional deployment completing in ~30 minutes

### Critical Issues ⚠️

#### 0. **NO DISASTER RECOVERY FOR PRODUCTION DATA** 🔴 **CRITICAL**

**Issue:** 4TB of critical production data (movies, photos, music, files) with no offsite backup

**Current State:**
- ❌ No automated backup of Nextcloud PVC
- ❌ No backup for other critical PVCs (Jellyfin, N8N, etc.)
- ❌ No disaster recovery plan for Rook-Ceph storage failure
- ❌ Data loss risk on hardware failure, accidental deletion, or cluster corruption

**Impact:**
- **CATASTROPHIC DATA LOSS** if Rook-Ceph cluster fails
- No recovery from ransomware/corruption
- No point-in-time restore capability
- 4TB of irreplaceable personal data at risk

**Business Impact:**
- Production homelab cannot tolerate data loss
- Users rely on this data daily
- Recovery time objective (RTO): Hours, not days
- Recovery point objective (RPO): <24 hours

#### 0b. **NO SAFE TESTING ENVIRONMENT** 🔴 **CRITICAL**

**Issue:** Cannot test deployments without risking production data and services

**Current State:**
- ❌ All testing done on production cluster
- ❌ Failed deployments can corrupt PVCs and lose data
- ❌ No ARM64/Raspberry Pi staging environment
- ❌ GitLab CI/CD not configured for virtual ARM64 testing

**Impact:**
- Production outages during testing
- Data loss from failed experiments
- Slow iteration due to fear of breaking production
- Cannot validate changes before deployment

**Examples of Recent Issues:**
- PVC data loss during app redeployments
- Service disruptions testing new configurations
- Unable to test major infrastructure changes safely

#### 1. **Secrets Management (MEDIUM PRIORITY)**

**Issue:** Secrets stored in local `config.yml` files without encryption

**Current State:**
- ✅ `config.yml` is properly gitignored (not in version control)
- ✅ `example.config.yml` uses placeholder values
- ⚠️ Local `config.yml` contains plaintext secrets on deployment machines

**Locations:**
- `ansible/config.yml:27` - GitHub Personal Access Token (local only)
- `core/ansible/config.yml:34-36` - Dashboard passwords and AWS credentials (local only)

**Impact:**
- Risk if deployment machine is compromised
- Secrets visible in plain text during playbook execution
- No audit trail for secret access

**Example (from local config.yml - NOT in Git):**
```yaml
# Local config.yml files contain plaintext secrets
argo_repo_token: "github_pat_..."
dashboard_password: "your-password"
aws_bedrock_api_key_id: "AKIA..."
aws_bedrock_api_access_key: "secret-key"
```

**Note:** These are **not** committed to Git (proper `.gitignore` in place), but should still be encrypted using Ansible Vault for defense-in-depth.

#### 2. **Ansible Architecture Anti-Patterns**

**Duplicated Collections:**
- Both `./ansible/` and `./core/ansible/` contain `community.kubernetes` collection
- Potential for version conflicts and maintenance overhead

**No Role-Based Structure:**
- All tasks in flat `tasks/` directory
- Violates DRY principle (KUBECONFIG setting repeated in every task)
- No reusable components

**Inconsistent Module Usage:**
- Mix of `kubernetes.core.k8s` vs `ansible.builtin.k8s`
- Some tasks use shell commands for helm/kubectl instead of native modules
- Inconsistent patterns across deployment tasks

**Example from [k3s_control_plane.yml:1](core/ansible/tasks/k3s_control_plane.yml#L1):**
```yaml
- name: Install K3s on control plane (takes a while) with etcd.
  ansible.builtin.shell: >-
    curl -sfL https://get.k3s.io | sh -s - server --cluster-init
```

#### 3. **Hardcoded Values**

**Network Configuration:**
- Control plane IP hardcoded: `192.168.1.95` ([k3s_control_plane.yml:129](core/ansible/tasks/k3s_control_plane.yml#L129))
- Traefik ingress IPs: `192.168.1.241` (pihole-values.yaml)
- Makes deployment inflexible for different network topologies

**Software Versions:**
- Helm version pinned to `v3.9.0` (released 2022, outdated)
- No K3s version pinning - uses latest via `curl | sh`
- Component versions not centrally managed

#### 4. **K3s Best Practices Violations**

**Single Point of Failure:**
- Single control plane node (no HA)
- Embedded etcd without backup strategy
- No documented disaster recovery procedure

**Installation Security:**
- Uses `curl | sh` pattern without verification
- No install script integrity checking
- No version pinning for reproducibility

**Missing Operational Features:**
- No automated etcd snapshots
- No rollback capability
- No pre-flight validation checks

#### 5. **GitOps Hybrid Anti-Pattern**

**Inconsistent Deployment Methods:**

Via ArgoCD:
- Nextcloud ([nextcloud_deploy.yml](core/ansible/tasks/nextcloud_deploy.yml))
- PiHole ([pihole_deploy.yml](core/ansible/tasks/pihole_deploy.yml))
- OpenWebUI, N8N, Jellyfin

Via Direct Helm/Shell:
- MetalLB ([metallb_native_deploy.yml](core/ansible/tasks/metallb_native_deploy.yml))
- Prometheus
- Rook-Ceph operator

Via Separate Apply:
- All Ingress resources downloaded via `get_url` and applied separately

**Example inconsistency from [argocd_native_deploy.yml:102-112](core/ansible/tasks/argocd_native_deploy.yml#L102-L112):**
```yaml
# ArgoCD deployed via Helm, but ingress applied separately
- name: Download ArgoCD IngressRoutes manifest from GitHub
  ansible.builtin.get_url:
    url: "https://raw.githubusercontent.com/.../traefik-argocd-ingress.yml"
    dest: "/tmp/traefik-argocd-ingress.yml"

- name: Apply ArgoCD IngressRoutes (no Helm/Argo)
  kubernetes.core.k8s:
    state: present
    src: "/tmp/traefik-argocd-ingress.yml"
```

**Issues:**
- Drift between GitOps-managed and manually-applied resources
- External URL dependencies cause deployment failures on network issues
- Difficult to track which method deploys which component

#### 6. **Inventory and Variable Management**

**Current Structure:**
```ini
# example.hosts.ini
[control_plane]
yoda.local ansible_host=192.168.1.95 ip_host_octet=95

[nodes]
obiwan.local ansible_host=192.168.1.96 ip_host_octet=96
```

**Issues:**
- Dependency on `.local` mDNS resolution (fragile)
- No `group_vars/` or `host_vars/` structure
- All variables in single `config.yml` file
- Storage group defined but never used

#### 7. **Monitoring and Observability Gaps**

**Missing Components:**
- No centralized logging (only metrics via Prometheus)
- No post-deployment validation suite
- No smoke tests after cluster provisioning
- No automated health checks
- No rollback mechanism on deployment failure

#### 8. **Documentation Structure**

**Current State:**
- Deployment guides embedded in task comments
- No architecture diagrams in code
- Version compatibility matrix missing
- No clear upgrade path documentation

![accent-divider.svg](images/accent-divider.svg)
## Prioritized Recommendations

### Priority 0A: Disaster Recovery & Backup Strategy (CRITICAL) 🔴

**GitHub Issue:** [#24](https://github.com/seadogger-tech/seadogger-homelab/issues/24)
**Timeline:** Week 1-2 (IMMEDIATE)
**Impact:** CRITICAL - Prevents catastrophic data loss

#### 0A.1 Implement S3 Glacier Backup for Nextcloud PVC (Priority 1)

**Solution Overview:** Automated nightly rsync of Nextcloud PVC to AWS S3 with lifecycle policy to Glacier Deep Archive

**Implementation:**

**Step 1: Create S3 Bucket with Lifecycle Policy**

```bash
# Create S3 bucket for backups
aws s3 mb s3://seadogger-homelab-backups --region us-east-1

# Create lifecycle policy - move directly to Deep Archive for cost savings
cat > lifecycle-policy.json <<EOF
{
  "Rules": [
    {
      "Id": "MoveToDeepArchiveImmediately",
      "Status": "Enabled",
      "Transitions": [
        {
          "Days": 0,
          "StorageClass": "DEEP_ARCHIVE"
        }
      ],
      "NoncurrentVersionTransitions": [
        {
          "NoncurrentDays": 1,
          "StorageClass": "DEEP_ARCHIVE"
        }
      ]
    }
  ]
}
EOF

aws s3api put-bucket-lifecycle-configuration \
  --bucket seadogger-homelab-backups \
  --lifecycle-configuration file://lifecycle-policy.json

# Enable versioning for point-in-time recovery
aws s3api put-bucket-versioning \
  --bucket seadogger-homelab-backups \
  --versioning-configuration Status=Enabled
```

**Step 2: Deploy Backup CronJob in Kubernetes**

Create `core/deployments/backup/nextcloud-s3-backup.yaml`:

```yaml
---
apiVersion: v1
kind: Secret
metadata:
  name: aws-backup-credentials
  namespace: nextcloud
type: Opaque
stringData:
  AWS_ACCESS_KEY_ID: "AKIA..."
  AWS_SECRET_ACCESS_KEY: "..."
  AWS_DEFAULT_REGION: "us-east-1"

---
apiVersion: batch/v1
kind: CronJob
metadata:
  name: nextcloud-s3-backup
  namespace: nextcloud
spec:
  schedule: "0 2 * * *"  # 2 AM daily
  successfulJobsHistoryLimit: 7
  failedJobsHistoryLimit: 3
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      backoffLimit: 2
      template:
        spec:
          restartPolicy: OnFailure
          containers:
          - name: backup
            image: amazon/aws-cli:2.13.0
            envFrom:
            - secretRef:
                name: aws-backup-credentials
            command:
            - /bin/bash
            - -c
            - |
              set -euo pipefail

              TIMESTAMP=$(date +%Y%m%d-%H%M%S)
              BACKUP_PATH="s3://seadogger-homelab-backups/nextcloud/${TIMESTAMP}"

              echo "Starting Nextcloud backup at ${TIMESTAMP}"
              echo "Target: ${BACKUP_PATH}"

              # Sync Nextcloud data directly to S3 Deep Archive
              # Note: Initial upload goes to STANDARD, lifecycle moves to DEEP_ARCHIVE
              aws s3 sync /nextcloud-data ${BACKUP_PATH} \
                --storage-class STANDARD \
                --delete \
                --exclude "*.log" \
                --exclude "*.tmp" \
                --exclude "cache/*" \
                --exclude "appdata_*/preview/*"

              # Create marker file with backup metadata
              cat > /tmp/backup-info.json <<EOF
              {
                "timestamp": "${TIMESTAMP}",
                "hostname": "$(hostname)",
                "pvc": "nextcloud-data",
                "backup_size_gb": "$(du -sh /nextcloud-data | awk '{print $1}')"
              }
              EOF

              aws s3 cp /tmp/backup-info.json ${BACKUP_PATH}/backup-info.json

              echo "Backup completed successfully"
              echo "Total size: $(du -sh /nextcloud-data | awk '{print $1}')"

              # List recent backups
              echo "Recent backups:"
              aws s3 ls s3://seadogger-homelab-backups/nextcloud/ | tail -5

            volumeMounts:
            - name: nextcloud-data
              mountPath: /nextcloud-data
              readOnly: true
            resources:
              requests:
                memory: "512Mi"
                cpu: "500m"
              limits:
                memory: "2Gi"
                cpu: "2000m"
          volumes:
          - name: nextcloud-data
            persistentVolumeClaim:
              claimName: nextcloud-data
              readOnly: true

---
# Manual job for immediate backup
apiVersion: batch/v1
kind: Job
metadata:
  name: nextcloud-s3-backup-manual
  namespace: nextcloud
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: backup
        image: amazon/aws-cli:2.13.0
        envFrom:
        - secretRef:
            name: aws-backup-credentials
        command:
        - /bin/bash
        - -c
        - |
          set -euo pipefail
          TIMESTAMP=$(date +%Y%m%d-%H%M%S)-manual
          BACKUP_PATH="s3://seadogger-homelab-backups/nextcloud/${TIMESTAMP}"
          echo "Manual backup to ${BACKUP_PATH}"
          aws s3 sync /nextcloud-data ${BACKUP_PATH} --storage-class STANDARD
        volumeMounts:
        - name: nextcloud-data
          mountPath: /nextcloud-data
          readOnly: true
      volumes:
      - name: nextcloud-data
        persistentVolumeClaim:
          claimName: nextcloud-data
          readOnly: true
```

**Step 3: Add Monitoring & Alerts**

Create `core/deployments/backup/backup-monitoring.yaml`:

```yaml
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: backup-monitor-script
  namespace: nextcloud
data:
  check-backup.sh: |
    #!/bin/bash
    # Check if backup completed in last 25 hours
    LAST_BACKUP=$(aws s3 ls s3://seadogger-homelab-backups/nextcloud/ | tail -1 | awk '{print $1" "$2}')
    LAST_BACKUP_EPOCH=$(date -d "$LAST_BACKUP" +%s)
    NOW_EPOCH=$(date +%s)
    HOURS_AGO=$(( (NOW_EPOCH - LAST_BACKUP_EPOCH) / 3600 ))

    if [ $HOURS_AGO -gt 25 ]; then
      echo "ERROR: Last backup was ${HOURS_AGO} hours ago!"
      exit 1
    fi
    echo "OK: Last backup was ${HOURS_AGO} hours ago"

---
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: backup-alerts
  namespace: monitoring
spec:
  groups:
  - name: backup
    interval: 30m
    rules:
    - alert: NextcloudBackupFailed
      expr: kube_job_status_failed{namespace="nextcloud",job_name=~"nextcloud-s3-backup.*"} > 0
      for: 1h
      annotations:
        summary: "Nextcloud S3 backup job failed"
        description: "The automated Nextcloud backup to S3 has failed. Check logs immediately."

    - alert: NextcloudBackupMissing
      expr: time() - kube_job_status_completion_time{namespace="nextcloud",job_name=~"nextcloud-s3-backup.*"} > 86400
      for: 2h
      annotations:
        summary: "Nextcloud backup has not run in 24+ hours"
        description: "No successful Nextcloud backup detected in the last 24 hours."
```

**Step 4: Create Restore Procedure**

Create `docs/wiki/24-Backup-and-Restore.md`:

```markdown
# Backup and Restore Procedures

## Nextcloud Data Restore from S3

### List Available Backups
```bash
aws s3 ls s3://seadogger-homelab-backups/nextcloud/
```

### Restore Full Backup
```bash
# 1. Scale down Nextcloud
kubectl scale deployment nextcloud -n nextcloud --replicas=0

# 2. Launch restore pod
kubectl run nextcloud-restore -n nextcloud \
  --image=amazon/aws-cli:2.13.0 \
  --restart=Never \
  --overrides='
  {
    "spec": {
      "containers": [{
        "name": "restore",
        "image": "amazon/aws-cli:2.13.0",
        "command": ["sleep", "3600"],
        "env": [
          {"name": "AWS_ACCESS_KEY_ID", "valueFrom": {"secretKeyRef": {"name": "aws-backup-credentials", "key": "AWS_ACCESS_KEY_ID"}}},
          {"name": "AWS_SECRET_ACCESS_KEY", "valueFrom": {"secretKeyRef": {"name": "aws-backup-credentials", "key": "AWS_SECRET_ACCESS_KEY"}}}
        ],
        "volumeMounts": [{
          "name": "data",
          "mountPath": "/nextcloud-data"
        }]
      }],
      "volumes": [{
        "name": "data",
        "persistentVolumeClaim": {"claimName": "nextcloud-data"}
      }]
    }
  }'

# 3. Restore data
kubectl exec -n nextcloud nextcloud-restore -- bash -c "
  aws s3 sync s3://seadogger-homelab-backups/nextcloud/YYYYMMDD-HHMMSS/ /nextcloud-data/
"

# 4. Verify restore
kubectl exec -n nextcloud nextcloud-restore -- ls -lah /nextcloud-data

# 5. Scale up Nextcloud
kubectl scale deployment nextcloud -n nextcloud --replicas=1

# 6. Cleanup
kubectl delete pod nextcloud-restore -n nextcloud
```

### Point-in-Time Recovery
Due to S3 versioning, you can recover any file version within retention period.

```bash
# List all versions of a file
aws s3api list-object-versions \
  --bucket seadogger-homelab-backups \
  --prefix nextcloud/20250101-020000/path/to/file.jpg

# Download specific version
aws s3api get-object \
  --bucket seadogger-homelab-backups \
  --key nextcloud/20250101-020000/path/to/file.jpg \
  --version-id <VERSION_ID> \
  file.jpg
```
```

#### 0A.2 Extend Backup to All Critical PVCs

**Additional PVCs to backup (in priority order):**

1. **Nextcloud** (Priority 1 - DONE above)
2. **Jellyfin metadata** (Priority 2 - media libraries config)
3. **N8N workflows** (Priority 3 - automation data)
4. **PiHole config** (Priority 4 - DNS config)
5. **Prometheus metrics** (Priority 5 - historical data)

**Create generic backup CronJob template:**

`core/deployments/backup/generic-pvc-backup-cronjob.yaml`:

```yaml
---
apiVersion: batch/v1
kind: CronJob
metadata:
  name: ${APP_NAME}-s3-backup
  namespace: ${NAMESPACE}
spec:
  schedule: "0 3 * * *"  # 3 AM daily (stagger from Nextcloud)
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          containers:
          - name: backup
            image: amazon/aws-cli:2.13.0
            envFrom:
            - secretRef:
                name: aws-backup-credentials
            command:
            - /bin/bash
            - -c
            - |
              TIMESTAMP=$(date +%Y%m%d-%H%M%S)
              BACKUP_PATH="s3://seadogger-homelab-backups/${APP_NAME}/${TIMESTAMP}"
              aws s3 sync /data ${BACKUP_PATH} --storage-class STANDARD
            volumeMounts:
            - name: data
              mountPath: /data
              readOnly: true
          volumes:
          - name: data
            persistentVolumeClaim:
              claimName: ${PVC_NAME}
              readOnly: true
```

#### 0A.3 Backup Cost Estimation (Direct to Deep Archive)

**S3 Glacier Deep Archive Pricing (us-east-1):**

| Storage Tier | Cost per GB/month | Cost per TB/month |
|--------------|-------------------|-------------------|
| Glacier Deep Archive | $0.00099/GB | **$0.99/TB** |

**Your 4-6TB estimate: ~$4-6/month** ✅

**Why Deep Archive?**
- ✅ Lowest cost storage ($0.99/TB/month)
- ✅ This is disaster recovery only - 12-48hr retrieval is acceptable
- ✅ No need for expensive Standard-IA or Glacier IR tiers
- ✅ Lifecycle policy moves data to Deep Archive immediately (0 days)

**How `aws s3 sync` Works (Incremental):**
- First backup: Uploads full 4TB
- Subsequent backups: **Only uploads changed files**
- Each nightly backup creates a new timestamped folder, but:
  - If a file hasn't changed, S3 just references the existing object (no duplicate storage)
  - Only new/modified files consume additional storage

**Realistic Storage Consumption:**
- **Initial full backup:** 4TB = $3.96/month
- **Daily changes (photos, files added):** ~10GB/day average = 300GB/month
- **Monthly growth in S3:** 300GB × $0.00099 = **$0.30/month additional**
- **After 1 year of daily backups:** 4TB + (300GB × 12) = ~7.6TB = **$7.52/month**

**Nightly vs Weekly Backups:**

Since `aws s3 sync` is incremental, the storage cost difference between nightly and weekly is minimal:

| Frequency | Year 1 Storage | Monthly Cost |
|-----------|----------------|--------------|
| Nightly (365 backups) | ~7.6TB | **$7.52** |
| Weekly (52 backups) | ~7.6TB | **$7.52** (same!) |

**The difference:** Weekly gives you 52 restore points vs 365 restore points for the same cost!

**Recommendation:**
- ✅ **Run nightly backups** - no extra cost vs weekly
- Set retention policy to keep backups for 30 days (or whatever you prefer)
- After 30 days, old backup folders are auto-deleted
- Steady-state cost: **~$5-8/month** for 4-6TB with daily changes

**Data Transfer Costs:**
- ✅ Upload to S3: **FREE**
- Retrieval from Deep Archive: $0.02/GB
  - Full 4TB restore: **$81.92** (one-time, disaster only)
  - Standard retrieval time: **12-48 hours** (acceptable for DR)
  - Bulk retrieval: **48 hours**, only $0.0025/GB ($10.24 for 4TB)

**Bottom Line:**
- **Your original estimate was correct:** ~$5/month for 4-6TB ✅
- Nightly backups with 30-day retention
- Storage only grows as your data grows
- `aws s3 sync` handles deduplication automatically

---

### Priority 0B: Staging Environment for Safe Testing (CRITICAL) 🔴

**GitHub Issue:** [#47](https://github.com/seadogger-tech/seadogger-homelab/issues/47)
**Timeline:** Week 2-3
**Impact:** CRITICAL - Enables safe iteration without production risk

#### 0B.1 Local Virtual ARM64 Staging Cluster

**Solution:** Use QEMU + Multipass or Lima to run ARM64 VMs locally for testing

**Option 1: Multipass with QEMU ARM64 (macOS)**

```bash
# Install Multipass
brew install multipass

# Launch ARM64 Ubuntu VM
multipass launch --cpus 4 --memory 8G --disk 50G --name k3s-staging

# Install K3s
multipass exec k3s-staging -- bash -c "
  curl -sfL https://get.k3s.io | sh -s - server --write-kubeconfig-mode 644 --disable servicelb
"

# Get kubeconfig
multipass exec k3s-staging -- sudo cat /etc/rancher/k3s/k3s.yaml > ~/.kube/k3s-staging.conf

# Update server IP in kubeconfig
STAGING_IP=$(multipass info k3s-staging | grep IPv4 | awk '{print $2}')
sed -i.bak "s/127.0.0.1/$STAGING_IP/g" ~/.kube/k3s-staging.conf

# Test
export KUBECONFIG=~/.kube/k3s-staging.conf
kubectl get nodes
```

**Option 2: Kind with ARM64 emulation**

```bash
# Install Kind
brew install kind

# Create ARM64 cluster (uses QEMU emulation)
cat > kind-arm64-config.yaml <<EOF
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
- role: control-plane
  image: kindest/node:v1.31.0
  extraMounts:
  - hostPath: /tmp/staging-data
    containerPath: /data
EOF

kind create cluster --name staging --config kind-arm64-config.yaml
```

**Option 3: Lima (lighterweight than Multipass)**

```bash
brew install lima

# Create ARM64 VM with K3s
limactl start --name=k3s-staging template://k3s

# Access
limactl shell k3s-staging
```

#### 0B.2 GitLab CI/CD for Automated ARM64 Testing

**Challenge:** GitLab shared runners don't support ARM64 natively

**Solutions:**

**Option A: Self-hosted GitLab Runner on Mac Mini (Recommended)**

```bash
# Install GitLab Runner on your Mac
brew install gitlab-runner

# Register runner for your project
gitlab-runner register \
  --url https://gitlab.com/ \
  --token YOUR_RUNNER_TOKEN \
  --executor shell \
  --description "homelab-arm64-runner" \
  --tag-list "arm64,macos,k3s"

# Start runner
gitlab-runner start
```

**Create `.gitlab-ci.yml` in repo:**

```yaml
stages:
  - test
  - deploy-staging
  - deploy-production

variables:
  STAGING_KUBECONFIG: ~/.kube/k3s-staging.conf

# Run linting and validation
lint:
  stage: test
  tags:
    - arm64
  script:
    - ansible-lint core/ansible/
    - yamllint core/deployments/
    - kubectl apply --dry-run=client -f core/deployments/

# Deploy to staging VM
deploy-staging:
  stage: deploy-staging
  tags:
    - arm64
  script:
    # Start staging VM if not running
    - multipass start k3s-staging || true

    # Deploy to staging
    - export KUBECONFIG=$STAGING_KUBECONFIG
    - cd core/ansible
    - ansible-playbook -i staging-hosts.ini main.yml --tags validate

    # Run smoke tests
    - kubectl get nodes
    - kubectl get pods -A
    - kubectl run test-nginx --image=nginx --restart=Never
    - kubectl wait --for=condition=Ready pod/test-nginx --timeout=60s
    - kubectl delete pod test-nginx
  only:
    - branches
  except:
    - main

# Deploy to production (manual gate)
deploy-production:
  stage: deploy-production
  tags:
    - arm64
  script:
    - cd core/ansible
    - ansible-playbook -i production-hosts.ini main.yml
  when: manual
  only:
    - main
  environment:
    name: production
    url: https://portal.seadogger-homelab
```

**Option B: Use GitLab SaaS with Docker executor + QEMU**

```yaml
# .gitlab-ci.yml with QEMU emulation
test-arm64:
  image: docker:latest
  services:
    - docker:dind
  tags:
    - docker
  before_script:
    # Setup QEMU for ARM64 emulation
    - docker run --rm --privileged multiarch/qemu-user-static --reset -p yes
  script:
    # Test ARM64 image
    - docker build --platform linux/arm64 -t test-arm64 .
    - docker run --platform linux/arm64 test-arm64 uname -m  # Should output "aarch64"
```

**Option C: Use Actuated (ARM64 CI runners as a service)**

Cost: ~$100/month for dedicated ARM64 runners
URL: https://actuated.dev/

```yaml
# .gitlab-ci.yml with Actuated
test-arm64:
  tags:
    - actuated-arm64
  script:
    - k3d cluster create staging
    - kubectl apply -f deployments/
```

#### 0B.3 Create Staging Inventory

**Create `core/ansible/inventory/staging/hosts.ini`:**

```ini
[control_plane]
localhost ansible_connection=local ansible_host=127.0.0.1

[nodes]
# No workers in staging - single node cluster

[cluster:children]
control_plane

[cluster:vars]
ansible_user=ubuntu
ipv4_subnet_prefix="10.0.2"
metallb_ip_range="10.0.2.240-10.0.2.250"
staging_mode=true
```

**Create `core/ansible/inventory/staging/group_vars/all.yml`:**

```yaml
---
# Staging environment overrides
enable_rook_ceph: false  # Use local storage in staging
enable_prometheus: false  # Skip heavy monitoring
enable_jellyfin: false    # Skip media server

# Use smaller resource limits
staging_resource_limits:
  memory: "512Mi"
  cpu: "500m"

# Fast deployments - skip long waits
staging_mode: true
wait_timeout: 60s  # vs 600s in production
```

#### 0B.4 Testing Workflow

**New Development Workflow:**

1. **Develop locally** → Make changes to Ansible/manifests
2. **Test in staging VM** → Run playbook against local VM
3. **Automated CI/CD** → GitLab runs tests on every commit
4. **Manual production deploy** → Approve deployment to real cluster

**Example testing command:**

```bash
# Test new deployment in staging
export KUBECONFIG=~/.kube/k3s-staging.conf

cd core/ansible
ansible-playbook -i inventory/staging/hosts.ini main.yml \
  --tags=pihole \
  --check  # Dry-run first

# Actually apply
ansible-playbook -i inventory/staging/hosts.ini main.yml --tags=pihole

# Validate
kubectl get pods -n pihole
kubectl logs -n pihole -l app=pihole --tail=50

# If good, deploy to production
ansible-playbook -i inventory/production/hosts.ini main.yml --tags=pihole
```

---

### Priority 1: Secrets Management (OPTIONAL) 🟡

**Timeline:** Week 1 (if desired)
**Impact:** Medium - Adds defense-in-depth for local secrets

**Note:** Secrets are already properly excluded from Git via `.gitignore`. This is an optional hardening step.

#### 1.1 Implement Ansible Vault (Optional)

**Action:** Encrypt local config files for additional security

```bash
# Encrypt the config file
ansible-vault encrypt core/ansible/config.yml

# Or encrypt individual variables
ansible-vault encrypt_string 'github_pat_...' --name 'argo_repo_token'
```

**Update playbook execution:**
```bash
ansible-playbook main.yml --ask-vault-pass
# or
ansible-playbook main.yml --vault-password-file ~/.vault_pass
```

**Files to encrypt:**
- `core/ansible/config.yml`
- `ansible/config.yml`
- Any custom `group_vars/` with secrets (future state)

#### 1.2 Adopt External Secrets Operator

**Rationale:** Move secrets out of Git entirely

**Implementation:**
```yaml
# Option A: AWS Secrets Manager
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: aws-secrets-manager
  namespace: default
spec:
  provider:
    aws:
      service: SecretsManager
      region: us-east-1

# Option B: HashiCorp Vault (for on-premise)
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: vault-backend
spec:
  provider:
    vault:
      server: "https://vault.homelab.local"
      path: "homelab"
```

**Benefits:**
- Secrets never committed to Git
- Centralized secret rotation
- Audit trail for secret access

#### 1.3 Verify .gitignore (Already Done ✅)

**Current `.gitignore` properly excludes:**
```gitignore
# Already in place:
config.yml      ✅
hosts.ini       ✅

# Recommended additions:
*.vault
.vault_pass
*.key
*.crt
*.csr
*.pem
kubeconfig
.kube/
.env
.env.local
```

#### 1.4 Secret Scanning (Optional)

**Optional: Scan Git history for any historical secret leaks:**
```bash
# Install gitleaks
brew install gitleaks

# Scan repository
gitleaks detect --source . --verbose
```

**Note:** Since `config.yml` has always been gitignored, this is precautionary.

![accent-divider.svg](images/accent-divider.svg)
### Priority 1.5: Deployment Dependencies Refactor (HIGH) 🟠

**GitHub Issues:**
- [#48 - Parent Issue (Dependencies Refactor)](https://github.com/seadogger-tech/seadogger-homelab/issues/48)
- [#49 - Convert Prometheus to Ingress](https://github.com/seadogger-tech/seadogger-homelab/issues/49)
- [#50 - Move all infrastructure to ArgoCD + Kustomize](https://github.com/seadogger-tech/seadogger-homelab/issues/50)

**Timeline:** Week 2-3
**Impact:** High - Simplifies deployment, enables GitOps consistency
**Reference:** See [21-Deployment-Dependencies.md](21-Deployment-Dependencies.md) for detailed analysis

#### Overview

The current deployment has a "spider web" of implicit dependencies that make it fragile and difficult to maintain. This priority focuses on untangling those dependencies and moving to a pure GitOps model.

#### 1.5.1 Convert Prometheus Stack to Ingress (Remove LoadBalancer Dependencies)

**Current Issue:**
- Prometheus, Grafana, and Alertmanager each use dedicated MetalLB LoadBalancer IPs
- Wastes 3 IPs (192.168.1.244, 192.168.1.245, 192.168.1.246)
- Inconsistent access pattern vs other apps

**Solution:**
```yaml
# Instead of LoadBalancer services, use Traefik IngressRoutes
---
apiVersion: traefik.containo.us/v1alpha1
kind: IngressRoute
metadata:
  name: prometheus
  namespace: monitoring
spec:
  entryPoints: [websecure]
  routes:
  - match: Host(`prometheus.seadogger.internal`)
    kind: Rule
    services:
    - name: prometheus-k8s
      port: 9090
  tls:
    secretName: prometheus-tls  # ← Cert-manager certificate
---
# Repeat for Grafana and Alertmanager
```

**Benefits:**
- ✅ Reduces MetalLB to only Traefik and PiHole (the only services that truly need LoadBalancer)
- ✅ Unified access pattern via Traefik
- ✅ Automatic TLS via cert-manager
- ✅ Simplified dependency: Prometheus only needs Rook-Ceph (storage), not MetalLB

**Files to modify:**
- `core/ansible/tasks/prometheus_deploy.yml` (remove LoadBalancer services)
- `core/deployments/prometheus/prometheus-values.yaml` (set service type to ClusterIP)
- Create: `core/certificates/prometheus-certificate.yml`
- Create: `core/certificates/grafana-certificate.yml`
- Create: `core/certificates/alertmanager-certificate.yml`
- Update: `core/deployments/prometheus/ingress.yaml` (create IngressRoutes)

#### 1.5.2 Document and Validate All Dependencies

**Problem:** Tasks don't validate prerequisites before execution (see Problem 1 & 5 in dependency analysis)

**Solution:** Add pre-flight checks to all deployment tasks:

```yaml
# Example: prometheus_deploy.yml
- name: Pre-flight - Validate Rook-Ceph StorageClass exists
  kubernetes.core.k8s_info:
    kind: StorageClass
    name: ceph-block-data
  register: storage_class
  failed_when: storage_class.resources | length == 0

- name: Pre-flight - Validate cert-manager ready
  kubernetes.core.k8s_info:
    kind: Deployment
    name: cert-manager
    namespace: cert-manager
  register: cert_manager
  failed_when: >
    cert_manager.resources | length == 0 or
    cert_manager.resources[0].status.readyReplicas < 1
```

**Apply to:**
- All Prometheus deployment tasks
- All application deployment tasks
- Rook-Ceph cluster (validate operator ready)
- Internal PKI (validate cert-manager ready)

#### 1.5.3 Move Everything to ArgoCD Apps with Kustomize

**Vision:** Everything except K3s itself should be an ArgoCD Application with Kustomize structure (like the portal in Pro repo)

**Current State:**
| Component | Method | Status |
|-----------|--------|--------|
| MetalLB | Ansible + Helm | ❌ Not GitOps |
| Rook-Ceph | Ansible + Helm | ❌ Not GitOps |
| Cert-Manager | ArgoCD Application | ✅ GitOps |
| Internal PKI | Ansible + OpenSSL | ❌ Not GitOps |
| Prometheus | ArgoCD Application | ✅ GitOps |
| Apps | ArgoCD Application | ✅ GitOps |

**Target Structure:**
```
seadogger-homelab/core/
├── deployments/
│   ├── infrastructure/
│   │   ├── base/
│   │   │   ├── metallb/
│   │   │   ├── rook-ceph-operator/
│   │   │   ├── rook-ceph-cluster/
│   │   │   ├── cert-manager/
│   │   │   ├── internal-pki/
│   │   │   └── prometheus/
│   │   └── overlays/
│   │       ├── production/
│   │       └── staging/
│   ├── apps/
│   │   ├── base/
│   │   └── overlays/
│   └── argocd/
│       ├── root-app.yaml  # App-of-apps
│       └── infrastructure-appset.yaml  # Sync waves
```

**Implementation Phases:**

**Phase 1: Convert MetalLB to Kustomize**
```yaml
# deployments/infrastructure/base/metallb/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: metallb-system
resources:
  - namespace.yaml
  - ipaddresspool.yaml
helmCharts:
  - name: metallb
    repo: https://metallb.github.io/metallb
    version: 0.13.12
```

**Phase 2: Convert Rook-Ceph to Kustomize with Sync Waves**
```yaml
# argocd/infrastructure-appset.yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: infrastructure
spec:
  generators:
  - list:
      elements:
      # Wave 0: Operators
      - name: metallb
        wave: "0"
      - name: rook-ceph-operator
        wave: "0"
      - name: cert-manager
        wave: "0"
      # Wave 1: Clusters
      - name: rook-ceph-cluster
        wave: "1"
      - name: internal-pki
        wave: "1"
      # Wave 2: Monitoring
      - name: prometheus
        wave: "2"
  template:
    metadata:
      name: '{{name}}'
      annotations:
        argocd.argoproj.io/sync-wave: "{{wave}}"
```

**Phase 3: Simplify Internal PKI**
Options:
1. Use cert-manager's CA Injector to generate CA in-cluster
2. Use Sealed Secrets to store CA in Git (encrypted)
3. Use External Secrets Operator with local file backend

**Phase 4: Minimal Ansible Bootstrap**
After conversion, Ansible only does:
1. Install K3s cluster
2. Bootstrap ArgoCD (Helm install)
3. Apply root app-of-apps
4. Done! ArgoCD manages everything else

```yaml
# ansible/playbooks/bootstrap.yml (minimal)
---
- name: Bootstrap Homelab
  hosts: cluster
  tasks:
    - import_role: name=k3s
    - import_role: name=argocd-bootstrap
    - name: Deploy root app
      kubernetes.core.k8s:
        definition: "{{ lookup('file', '../deployments/argocd/root-app.yaml') }}"
```

#### 1.5.4 Fix Default Configuration Conflicts

**Current Issue:** `enable_rook_ceph_part1: default(false)` but apps require it

**Solution:**
- Change all infrastructure defaults to `true`
- Add validation that fails fast if required components disabled
- Document which components are required vs optional

```yaml
# ansible/group_vars/all.yml
enable_metallb_native: true        # Required
enable_rook_ceph_part1: true       # Required (changed from false)
enable_rook_ceph_part2: true       # Required
enable_internal_pki: true          # Required
enable_prometheus: true            # Optional (monitoring)
```

#### 1.5.5 Remove External URL Dependencies

**Current Issue:** Manifests downloaded from GitHub during deployment

**Solution:** Move all manifests to Git repo

```bash
# Create local manifest directory
mkdir -p core/deployments/{prometheus,argocd}/crds

# Download and commit CRDs
kubectl apply --dry-run=client -f https://raw.githubusercontent.com/.../crd.yaml -o yaml \
  > core/deployments/prometheus/crds/servicemonitor.yaml

# Update tasks to use local files
- name: Apply Prometheus CRDs
  kubernetes.core.k8s:
    definition: "{{ lookup('file', '../../deployments/prometheus/crds/' + item) }}"
  loop:
    - servicemonitor.yaml
    - prometheusrule.yaml
```

#### Success Metrics

- ✅ Prometheus stack accessible via Ingress (no LoadBalancer IPs)
- ✅ MetalLB only serves Traefik and PiHole
- ✅ All infrastructure visible in ArgoCD UI
- ✅ Pre-flight checks prevent deployment failures
- ✅ No external URL dependencies
- ✅ Ansible playbook < 100 lines (only bootstrap)
- ✅ All config in Git with Kustomize overlays

#### Estimated Timeline

- Week 2 Day 1-2: Convert Prometheus to Ingress
- Week 2 Day 3-4: Add pre-flight checks
- Week 3 Day 1-3: Convert MetalLB + Rook-Ceph to Kustomize
- Week 3 Day 4-5: ApplicationSet with sync waves
- Week 3 Day 5: Testing and validation

![accent-divider.svg](images/accent-divider.svg)
### Priority 2: Ansible Restructure (MEDIUM) 🟡

**GitHub Issue:** [#32](https://github.com/seadogger-tech/seadogger-homelab/issues/32)
**Related:** [#41 - Centralize subnet config](https://github.com/seadogger-tech/seadogger-homelab/issues/41)
**Timeline:** Week 2
**Impact:** High - Improves maintainability and reusability

#### 2.1 Convert to Ansible Roles

**Target Structure:**
```
core/ansible/
├── ansible.cfg
├── inventory/
│   ├── production/
│   │   ├── hosts.ini
│   │   ├── group_vars/
│   │   │   ├── all.yml
│   │   │   ├── control_plane.yml
│   │   │   └── nodes.yml
│   │   └── host_vars/
│   │       ├── yoda.yml
│   │       └── obiwan.yml
├── playbooks/
│   ├── cluster-install.yml
│   ├── apps-deploy.yml
│   ├── cluster-cleanup.yml
│   └── validate.yml
├── roles/
│   ├── raspberry-pi-config/
│   │   ├── tasks/main.yml
│   │   ├── handlers/main.yml
│   │   └── defaults/main.yml
│   ├── k3s-control-plane/
│   │   ├── tasks/
│   │   │   ├── main.yml
│   │   │   ├── install.yml
│   │   │   ├── configure.yml
│   │   │   └── validate.yml
│   │   ├── templates/
│   │   │   └── k3s-config.yaml.j2
│   │   └── defaults/main.yml
│   ├── k3s-worker/
│   │   └── ...
│   ├── metallb/
│   │   └── ...
│   ├── rook-ceph/
│   │   └── ...
│   ├── argocd/
│   │   └── ...
│   └── app-deployment/
│       └── ...
└── collections/
    └── requirements.yml
```

**Benefits:**
- Reusable, testable components
- Clear separation of concerns
- Reduced code duplication
- Better documentation through role structure

#### 2.2 Implement group_vars and host_vars

**Example: `group_vars/all.yml`**
```yaml
---
# Global configuration
k3s_version: "v1.31.4+k3s1"
helm_version: "v3.16.3"
kubeconfig_path: /etc/rancher/k3s/k3s.yaml

# Network configuration (from config.yml)
ipv4_subnet_prefix: "192.168.1"
ipv4_gateway: "192.168.1.1"
dns4_servers: "{{ ipv4_gateway }}"

# Component toggles
enable_metallb: true
enable_rook_ceph: true
enable_argocd: true
```

**Example: `group_vars/control_plane.yml`**
```yaml
---
# K3s control plane specific
k3s_server_flags:
  - --cluster-init
  - --write-kubeconfig-mode 644
  - --disable servicelb
  - --etcd-snapshot-schedule-cron "0 */6 * * *"
  - --etcd-snapshot-retention 14

# API server access
k3s_api_port: 6443
```

**Example: `host_vars/yoda.yml`**
```yaml
---
# Node-specific overrides
ansible_host: 192.168.1.95
ip_host_octet: 95
node_role: control-plane
```

**Benefits:**
- No more `vars_files: config.yml` in every play
- Hierarchical configuration (host > group > all)
- Environment-specific configurations (dev/prod)

#### 2.3 Standardize Kubernetes Module Usage

**Before (inconsistent):**
```yaml
# Some tasks use builtin
- name: Create namespace
  ansible.builtin.k8s:
    name: argocd
    kind: Namespace

# Others use kubernetes.core
- name: Deploy app
  kubernetes.core.k8s:
    definition: "{{ manifest }}"

# Some use shell
- name: Install with Helm
  ansible.builtin.shell: helm install ...
```

**After (standardized):**
```yaml
# Always use kubernetes.core collection
- name: Create namespace
  kubernetes.core.k8s:
    name: argocd
    api_version: v1
    kind: Namespace
    state: present

# Use helm module instead of shell
- name: Install with Helm
  kubernetes.core.helm:
    name: metallb
    chart_ref: metallb/metallb
    release_namespace: metallb-system
    state: present
```

**Update `requirements.yml`:**
```yaml
collections:
  - name: community.kubernetes
    version: ">=2.0.0,<3.0.0"
  - name: kubernetes.core
    version: ">=3.0.0"
```

#### 2.4 Centralize Version Management

**Create `group_vars/versions.yml`:**
```yaml
---
# Infrastructure versions
k3s_version: "v1.31.4+k3s1"
helm_version: "v3.16.3"
kubectl_version: "v1.31.4"

# Component versions
metallb_chart_version: "0.14.9"
argocd_chart_version: "7.7.11"
rook_ceph_operator_version: "v1.15.7"
prometheus_chart_version: "67.4.0"

# Application versions
pihole_chart_version: "2.26.4"
nextcloud_chart_version: "7.0.2"
jellyfin_chart_version: "1.2.0"

# Checksums for verification
k3s_install_script_sha256: "abc123..."
helm_binary_sha256: "def456..."
```

**Reference in tasks:**
```yaml
- name: Download Helm binary
  ansible.builtin.get_url:
    url: "https://get.helm.sh/helm-{{ helm_version }}-linux-arm64.tar.gz"
    dest: /tmp/helm-arm64.tar.gz
    checksum: "sha256:{{ helm_binary_sha256 }}"
```

![accent-divider.svg](images/accent-divider.svg)
### Priority 3: K3s Best Practices (HIGH) 🟠

**Timeline:** Week 3
**Impact:** High - Improves reliability and disaster recovery

#### 3.1 Implement High Availability Control Plane

**Current State:** Single control plane node (SPOF)

**Target State:** 3-node HA control plane with embedded etcd

**Update `inventory/production/hosts.ini`:**
```ini
[control_plane]
yoda.local ansible_host=192.168.1.95 ip_host_octet=95
luke.local ansible_host=192.168.1.99 ip_host_octet=99
leia.local ansible_host=192.168.1.100 ip_host_octet=100

[nodes]
obiwan.local ansible_host=192.168.1.96 ip_host_octet=96
anakin.local ansible_host=192.168.1.97 ip_host_octet=97
rey.local ansible_host=192.168.1.98 ip_host_octet=98
```

**Update K3s installation (first control plane node):**
```yaml
# roles/k3s-control-plane/tasks/install.yml
- name: Install K3s on first control plane node
  ansible.builtin.shell: >-
    curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION={{ k3s_version }} sh -s - server
    --cluster-init
    --write-kubeconfig-mode 644
    --disable servicelb
    --etcd-snapshot-schedule-cron "0 */6 * * *"
    --etcd-snapshot-retention 14
    --etcd-snapshot-dir /opt/k3s-snapshots
    --tls-san {{ vip_address }}
  when: inventory_hostname == groups['control_plane'][0]
```

**Join additional control plane nodes:**
```yaml
- name: Join additional control plane nodes
  ansible.builtin.shell: >-
    curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION={{ k3s_version }} sh -s - server
    --server https://{{ hostvars[groups['control_plane'][0]]['ansible_host'] }}:6443
    --token {{ k3s_token }}
    --write-kubeconfig-mode 644
    --disable servicelb
  when: inventory_hostname != groups['control_plane'][0]
```

**Benefits:**
- No single point of failure
- Automatic leader election
- Cluster survives control plane node loss

#### 3.2 Configure Automated etcd Backups

**K3s flags (already in install command above):**
```bash
--etcd-snapshot-schedule-cron "0 */6 * * *"  # Every 6 hours
--etcd-snapshot-retention 14                  # Keep 14 snapshots
--etcd-snapshot-dir /opt/k3s-snapshots        # Persistent location
```

**Add backup sync to external storage:**
```yaml
# roles/k3s-control-plane/tasks/backup.yml
- name: Create backup sync script
  ansible.builtin.template:
    src: sync-etcd-backups.sh.j2
    dest: /usr/local/bin/sync-etcd-backups.sh
    mode: '0755'

- name: Schedule backup sync to NFS/S3
  ansible.builtin.cron:
    name: "Sync etcd backups"
    minute: "15"
    hour: "*/6"
    job: "/usr/local/bin/sync-etcd-backups.sh"
```

**Template: `sync-etcd-backups.sh.j2`**
```bash
#!/bin/bash
# Sync K3s etcd snapshots to external storage
BACKUP_DIR=/opt/k3s-snapshots
REMOTE_DIR={{ backup_remote_path }}

# Option 1: Sync to NFS mount
rsync -av --delete $BACKUP_DIR/ $REMOTE_DIR/

# Option 2: Sync to S3
# aws s3 sync $BACKUP_DIR s3://homelab-backups/etcd/

# Keep only last 30 days locally
find $BACKUP_DIR -type f -name "*.zip" -mtime +30 -delete
```

#### 3.3 Add Disaster Recovery Documentation

**Create `docs/wiki/21-Disaster-Recovery.md`:**

```markdown
# Disaster Recovery Procedures

## etcd Restore from Snapshot

### Scenario: Complete Cluster Loss

1. Stop K3s on all nodes:
   ```bash
   ansible all -m systemd -a "name=k3s state=stopped" -b
   ```

2. Restore snapshot on first control plane node:
   ```bash
   k3s server \
     --cluster-reset \
     --cluster-reset-restore-path=/opt/k3s-snapshots/etcd-snapshot-yoda-1234567890.zip
   ```

3. Restart K3s and rejoin other nodes
```

#### 3.4 Pin K3s Version and Verify Installation

**Update installation task:**
```yaml
- name: Download K3s install script
  ansible.builtin.get_url:
    url: https://get.k3s.io
    dest: /tmp/k3s-install.sh
    mode: '0755'
    checksum: "sha256:{{ k3s_install_script_sha256 }}"

- name: Install K3s with pinned version
  ansible.builtin.command:
    cmd: /tmp/k3s-install.sh
  environment:
    INSTALL_K3S_VERSION: "{{ k3s_version }}"
    INSTALL_K3S_EXEC: "{{ k3s_install_flags | join(' ') }}"
  args:
    creates: /usr/local/bin/k3s
```

**Benefits:**
- Reproducible deployments
- Controlled upgrades
- Security verification

#### 3.5 Add Upgrade Strategy

**Create upgrade playbook: `playbooks/cluster-upgrade.yml`**
```yaml
---
- name: Upgrade K3s cluster
  hosts: all
  serial: 1  # Upgrade one node at a time
  tasks:
    - name: Drain node
      kubernetes.core.k8s_drain:
        name: "{{ inventory_hostname }}"
        state: drain
        delete_options:
          ignore_daemonsets: true
      delegate_to: "{{ groups['control_plane'][0] }}"

    - name: Upgrade K3s
      ansible.builtin.shell: |
        curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION={{ k3s_version }} sh -
      environment:
        INSTALL_K3S_SKIP_START: "true"

    - name: Restart K3s
      ansible.builtin.systemd:
        name: k3s
        state: restarted

    - name: Wait for node ready
      kubernetes.core.k8s_info:
        kind: Node
        name: "{{ inventory_hostname }}"
      register: node_info
      until: node_info.resources[0].status.conditions | selectattr('type', 'equalto', 'Ready') | map(attribute='status') | first == 'True'
      retries: 30
      delay: 10

    - name: Uncordon node
      kubernetes.core.k8s_drain:
        name: "{{ inventory_hostname }}"
        state: uncordon
      delegate_to: "{{ groups['control_plane'][0] }}"
```

![accent-divider.svg](images/accent-divider.svg)
### Priority 4: GitOps Consistency (MEDIUM) 🟡

**Timeline:** Week 4
**Impact:** Medium - Standardizes deployment methodology

#### 4.1 Migrate All Infrastructure to ArgoCD

**Current Hybrid Approach:**
- ✅ Applications via ArgoCD (Nextcloud, PiHole, etc.)
- ❌ Infrastructure via Ansible+Helm (MetalLB, Prometheus)
- ❌ Ingress via separate kubectl apply

**Target: Everything via ArgoCD**

**Step 1: Create ArgoCD ApplicationSet for Infrastructure**

**Create `core/argocd/infrastructure-apps.yaml`:**
```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: infrastructure
  namespace: argocd
spec:
  generators:
  - list:
      elements:
      - name: metallb
        namespace: metallb-system
        path: deployments/metallb
        repoURL: https://metallb.github.io/metallb
        chart: metallb
        targetRevision: "0.14.9"
      - name: rook-ceph-operator
        namespace: rook-ceph
        path: deployments/rook-ceph
        repoURL: https://charts.rook.io/release
        chart: rook-ceph
        targetRevision: "v1.15.7"
      - name: prometheus
        namespace: monitoring
        path: deployments/prometheus
        repoURL: https://prometheus-community.github.io/helm-charts
        chart: kube-prometheus-stack
        targetRevision: "67.4.0"
  template:
    metadata:
      name: '{{name}}'
    spec:
      project: default
      source:
        repoURL: '{{repoURL}}'
        chart: '{{chart}}'
        targetRevision: '{{targetRevision}}'
        helm:
          valueFiles:
          - $values/{{path}}/values.yaml
      sources:
      - repoURL: https://github.com/seadogger-tech/seadogger-homelab
        targetRevision: main
        ref: values
      destination:
        server: https://kubernetes.default.svc
        namespace: '{{namespace}}'
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
        syncOptions:
        - CreateNamespace=true
```

**Step 2: Bundle Ingress with Applications**

**Before (separate files):**
```
core/
├── deployments/pihole/pihole-values.yaml
└── ingress/traefik-pihole-ingress.yml
```

**After (bundled):**
```
core/
└── deployments/pihole/
    ├── values.yaml
    ├── templates/
    │   └── ingress.yaml
    └── Chart.yaml
```

**Create `core/deployments/pihole/Chart.yaml`:**
```yaml
apiVersion: v2
name: pihole-bundle
version: 1.0.0
dependencies:
- name: pihole
  version: "2.26.4"
  repository: https://mojo2600.github.io/pihole-kubernetes/
```

**Create `core/deployments/pihole/templates/ingress.yaml`:**
```yaml
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: pihole
  namespace: pihole
spec:
  entryPoints:
    - websecure
  routes:
    - match: Host(`pihole.seadogger-homelab`)
      kind: Rule
      services:
        - name: pihole-web
          port: 80
  tls:
    secretName: pihole-tls
```

**Step 3: Implement App-of-Apps Pattern**

**Create `core/argocd/root-app.yaml`:**
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: root
  namespace: argocd
  finalizers:
  - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  source:
    repoURL: https://github.com/seadogger-tech/seadogger-homelab
    targetRevision: main
    path: argocd/apps
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

**Create `core/argocd/apps/` directory structure:**
```
core/argocd/apps/
├── infrastructure-apps.yaml  (from Step 1)
├── pihole.yaml
├── nextcloud.yaml
├── jellyfin.yaml
└── openwebui.yaml
```

**Update Ansible to only deploy root app:**
```yaml
# roles/argocd/tasks/bootstrap.yml
- name: Deploy ArgoCD root application
  kubernetes.core.k8s:
    state: present
    definition: "{{ lookup('file', 'argocd/root-app.yaml') }}"
```

**Benefits:**
- Single source of truth (Git)
- Automatic drift detection and correction
- Clear dependency ordering
- Consistent deployment method

#### 4.2 Remove External URL Dependencies

**Before (network-dependent):**
```yaml
- name: Download manifest from GitHub
  ansible.builtin.get_url:
    url: "https://raw.githubusercontent.com/.../ingress.yml"
    dest: "/tmp/ingress.yml"

- name: Apply manifest
  kubernetes.core.k8s:
    src: "/tmp/ingress.yml"
```

**After (local files):**
```yaml
- name: Apply bundled manifest
  kubernetes.core.k8s:
    definition: "{{ lookup('file', 'manifests/ingress.yml') }}"
```

**Or via ArgoCD (preferred):**
```yaml
# ArgoCD automatically syncs from Git - no Ansible task needed
```

**Benefits:**
- No network failures during deployment
- Version-controlled manifests
- Faster deployments
- Offline capability

![accent-divider.svg](images/accent-divider.svg)
### Priority 5: Operational Excellence (MEDIUM) 🟡

**Timeline:** Week 5
**Impact:** Medium - Improves observability and reliability

#### 5.1 Pre-flight Validation Checks

**Create `roles/common/tasks/preflight.yml`:**
```yaml
---
- name: Validate OS distribution
  ansible.builtin.assert:
    that:
      - ansible_distribution == "Debian"
      - ansible_distribution_version is version('12', '>=')
    fail_msg: "This playbook requires Debian 12 (bookworm) or newer"
    success_msg: "OS check passed: {{ ansible_distribution }} {{ ansible_distribution_version }}"

- name: Validate minimum memory
  ansible.builtin.assert:
    that:
      - ansible_memtotal_mb >= 4096
    fail_msg: "Minimum 4GB RAM required, found {{ ansible_memtotal_mb }}MB"

- name: Validate network connectivity to nodes
  ansible.builtin.wait_for:
    host: "{{ ansible_host }}"
    port: 22
    timeout: 10
  delegate_to: localhost

- name: Check required ports are available
  ansible.builtin.wait_for:
    port: "{{ item }}"
    state: stopped
    timeout: 1
  loop:
    - 6443  # K3s API
    - 10250 # kubelet
    - 2379  # etcd
  ignore_errors: true
  register: port_check

- name: Validate internet connectivity
  ansible.builtin.uri:
    url: https://get.k3s.io
    method: HEAD
    timeout: 10
  delegate_to: localhost
  run_once: true

- name: Check disk space on /var
  ansible.builtin.assert:
    that:
      - item.mount == '/var' and item.size_available > 10737418240  # 10GB
    fail_msg: "Insufficient disk space on /var"
  loop: "{{ ansible_mounts }}"
  when: item.mount == '/var'
```

**Include in main playbook:**
```yaml
- hosts: all
  tasks:
    - name: Run pre-flight checks
      include_role:
        name: common
        tasks_from: preflight
```

#### 5.2 Post-Deployment Validation Suite

**Create `roles/validation/tasks/smoke-tests.yml`:**
```yaml
---
- name: Validate all nodes are Ready
  kubernetes.core.k8s_info:
    kind: Node
  register: nodes
  failed_when: >
    nodes.resources |
    selectattr('status.conditions', 'defined') |
    map(attribute='status.conditions') |
    selectattr('type', 'equalto', 'Ready') |
    selectattr('status', 'equalto', 'True') |
    list | length != groups['all'] | length

- name: Validate core namespaces exist
  kubernetes.core.k8s_info:
    kind: Namespace
    name: "{{ item }}"
  loop:
    - kube-system
    - metallb-system
    - rook-ceph
    - argocd
    - monitoring
  register: ns_check
  failed_when: ns_check.resources | length == 0

- name: Validate CoreDNS is running
  kubernetes.core.k8s_info:
    kind: Deployment
    name: coredns
    namespace: kube-system
  register: coredns
  failed_when: >
    coredns.resources[0].status.readyReplicas is not defined or
    coredns.resources[0].status.readyReplicas < 1

- name: Validate MetalLB controller is ready
  kubernetes.core.k8s_info:
    kind: Deployment
    name: metallb-controller
    namespace: metallb-system
  register: metallb
  failed_when: >
    metallb.resources[0].status.readyReplicas is not defined or
    metallb.resources[0].status.readyReplicas < 1

- name: Validate at least one MetalLB speaker is running
  kubernetes.core.k8s_info:
    kind: DaemonSet
    name: metallb-speaker
    namespace: metallb-system
  register: speaker
  failed_when: >
    speaker.resources[0].status.numberReady is not defined or
    speaker.resources[0].status.numberReady < 1

- name: Validate ArgoCD server is healthy
  kubernetes.core.k8s_info:
    kind: Deployment
    name: argocd-server
    namespace: argocd
  register: argocd
  failed_when: >
    argocd.resources[0].status.readyReplicas is not defined or
    argocd.resources[0].status.readyReplicas < 1

- name: Test DNS resolution inside cluster
  kubernetes.core.k8s:
    state: present
    definition:
      apiVersion: v1
      kind: Pod
      metadata:
        name: dns-test
        namespace: default
      spec:
        containers:
        - name: test
          image: busybox
          command: ['sh', '-c', 'nslookup kubernetes.default && sleep 10']
        restartPolicy: Never
  register: dns_test

- name: Wait for DNS test completion
  kubernetes.core.k8s_info:
    kind: Pod
    name: dns-test
    namespace: default
  register: dns_result
  until: dns_result.resources[0].status.phase == 'Succeeded'
  retries: 10
  delay: 3

- name: Cleanup DNS test pod
  kubernetes.core.k8s:
    kind: Pod
    name: dns-test
    namespace: default
    state: absent

- name: Validate Rook-Ceph health
  kubernetes.core.k8s_exec:
    namespace: rook-ceph
    pod: "{{ lookup('kubernetes.core.k8s', kind='Pod', namespace='rook-ceph', label_selector='app=rook-ceph-tools').metadata.name }}"
    command: ceph health
  register: ceph_health
  failed_when: "'HEALTH_OK' not in ceph_health.stdout and 'HEALTH_WARN' not in ceph_health.stdout"
  when: enable_rook_ceph | default(true)

- name: Report validation results
  ansible.builtin.debug:
    msg: |
      ✅ Cluster validation passed!
      - All nodes Ready
      - Core services operational
      - DNS resolution working
      - Storage healthy
```

**Add to main playbook:**
```yaml
- hosts: control_plane
  tasks:
    - name: Run post-deployment validation
      include_role:
        name: validation
        tasks_from: smoke-tests
      tags: [validate, always]
```

#### 5.3 Add Centralized Logging

**Deploy Loki + Promtail via ArgoCD:**

**Create `core/argocd/apps/loki-stack.yaml`:**
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: loki-stack
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://grafana.github.io/helm-charts
    chart: loki-stack
    targetRevision: "2.10.2"
    helm:
      values: |
        loki:
          enabled: true
          persistence:
            enabled: true
            size: 50Gi
            storageClassName: ceph-block-data
        promtail:
          enabled: true
        grafana:
          enabled: false  # Already deployed with Prometheus
  destination:
    server: https://kubernetes.default.svc
    namespace: monitoring
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
    - CreateNamespace=true
```

**Add Loki datasource to Grafana:**
```yaml
# In prometheus-values.yaml, add:
grafana:
  additionalDataSources:
  - name: Loki
    type: loki
    url: http://loki-stack:3100
    access: proxy
    isDefault: false
```

**Benefits:**
- Centralized log aggregation
- Correlation between metrics and logs in Grafana
- Troubleshooting with full context
- Log retention and search

#### 5.4 Implement Tagging Strategy

**Add tags to all roles:**
```yaml
# roles/k3s-control-plane/tasks/main.yml
- name: Install K3s
  include_tasks: install.yml
  tags: [k3s, install]

- name: Configure K3s
  include_tasks: configure.yml
  tags: [k3s, configure]

- name: Validate installation
  include_tasks: validate.yml
  tags: [k3s, validate, always]
```

**Usage examples:**
```bash
# Only install without configuration
ansible-playbook playbooks/cluster-install.yml --tags install

# Only run validation
ansible-playbook playbooks/cluster-install.yml --tags validate

# Skip slow tasks
ansible-playbook playbooks/cluster-install.yml --skip-tags backup

# Install only K3s, skip applications
ansible-playbook main.yml --tags k3s
```

#### 5.5 Add Rollback Capability

**Create `playbooks/rollback.yml`:**
```yaml
---
- name: Rollback cluster to previous state
  hosts: control_plane
  tasks:
    - name: Get etcd snapshots
      ansible.builtin.find:
        paths: /opt/k3s-snapshots
        patterns: "*.zip"
      register: snapshots

    - name: Select most recent snapshot
      ansible.builtin.set_fact:
        latest_snapshot: "{{ snapshots.files | sort(attribute='mtime', reverse=true) | first }}"

    - name: Display snapshot info
      ansible.builtin.debug:
        msg: "Will restore from: {{ latest_snapshot.path }}"

    - name: Confirm rollback
      ansible.builtin.pause:
        prompt: "Press ENTER to confirm rollback or Ctrl+C to cancel"

    - name: Stop K3s on all nodes
      ansible.builtin.systemd:
        name: k3s
        state: stopped
      delegate_to: "{{ item }}"
      loop: "{{ groups['all'] }}"

    - name: Restore etcd snapshot
      ansible.builtin.command:
        cmd: "k3s server --cluster-reset --cluster-reset-restore-path={{ latest_snapshot.path }}"
      when: inventory_hostname == groups['control_plane'][0]

    - name: Restart K3s
      ansible.builtin.systemd:
        name: k3s
        state: restarted
      delegate_to: "{{ item }}"
      loop: "{{ groups['all'] }}"
```

![accent-divider.svg](images/accent-divider.svg)
### Priority 6: Documentation & Maintainability (LOW) 🟢

**Timeline:** Ongoing
**Impact:** Low - Improves long-term maintainability

#### 6.1 Add Architecture Diagrams

**Use C4 Model for documentation:**

**Create `docs/architecture/c1-system-context.md`:**
```
┌─────────────┐         ┌──────────────────┐         ┌────────────┐
│   Users     │────────▶│  Homelab Cluster │────────▶│  Internet  │
│             │         │   (Kubernetes)    │         │  Services  │
└─────────────┘         └──────────────────┘         └────────────┘
```

**Create `docs/architecture/c2-container-diagram.md`:**
```
┌────────────────────────────────────────────────┐
│           Seadogger Homelab                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│  │  Traefik │  │  ArgoCD  │  │  Rook    │     │
│  │ (Ingress)│  │ (GitOps) │  │  Ceph    │     │
│  └──────────┘  └──────────┘  └──────────┘     │
│  ┌──────────────────────────────────────┐     │
│  │        Application Layer              │     │
│  │  PiHole | Nextcloud | Jellyfin | ... │     │
│  └──────────────────────────────────────┘     │
└────────────────────────────────────────────────┘
```

#### 6.2 Create Compatibility Matrix

**Create `docs/wiki/22-Version-Compatibility.md`:**

| Component      | Version       | K3s Compatibility | Tested On        |
|----------------|---------------|-------------------|------------------|
| K3s            | v1.31.4+k3s1  | Self              | 2025-09-29      |
| Helm           | v3.16.3       | K3s 1.28+         | 2025-09-29      |
| MetalLB        | 0.14.9        | K3s 1.28+         | 2025-09-29      |
| Rook-Ceph      | v1.15.7       | K3s 1.29+         | 2025-09-29      |
| ArgoCD         | 7.7.11        | K3s 1.28+         | 2025-09-29      |
| Traefik        | v3.2          | K3s 1.28+         | 2025-09-29      |
| Prometheus     | 67.4.0        | K3s 1.28+         | 2025-09-29      |

**Auto-generate with script:**
```bash
#!/bin/bash
# scripts/generate-version-matrix.sh
kubectl version --short
helm version --short
kubectl get deployments -A -o json | jq -r '.items[] | "\(.metadata.namespace)/\(.metadata.name): \(.spec.template.spec.containers[0].image)"'
```

#### 6.3 Add Makefile for Common Tasks

**Create `Makefile` in repo root:**
```makefile
.PHONY: help install validate clean upgrade backup restore

help:
	@echo "Seadogger Homelab - Common Tasks"
	@echo ""
	@echo "  make install     - Deploy full cluster"
	@echo "  make validate    - Run validation checks"
	@echo "  make clean       - Clean up cluster"
	@echo "  make upgrade     - Upgrade K3s cluster"
	@echo "  make backup      - Trigger etcd backup"
	@echo "  make restore     - Restore from backup"

install:
	@echo "🚀 Installing homelab cluster..."
	cd core/ansible && ansible-playbook playbooks/cluster-install.yml

validate:
	@echo "🔍 Running validation checks..."
	cd core/ansible && ansible-playbook playbooks/validate.yml

clean:
	@echo "🧹 Cleaning up cluster..."
	cd core/ansible && ansible-playbook cleanup.yml

upgrade:
	@echo "⬆️  Upgrading cluster..."
	cd core/ansible && ansible-playbook playbooks/cluster-upgrade.yml

backup:
	@echo "💾 Triggering etcd backup..."
	kubectl -n kube-system exec etcd-0 -- etcdctl snapshot save /tmp/backup.db

restore:
	@echo "♻️  Restoring from backup..."
	cd core/ansible && ansible-playbook playbooks/rollback.yml
```

**Usage:**
```bash
make install    # Deploy everything
make validate   # Check health
make upgrade    # Upgrade K3s
```

#### 6.4 Document Upgrade Paths

**Create `docs/wiki/23-Upgrade-Guide.md`:**

```markdown
# Upgrade Guide

## K3s Cluster Upgrade

### Pre-upgrade Checklist
- [ ] Take etcd snapshot: `make backup`
- [ ] Review changelog: https://github.com/k3s-io/k3s/releases
- [ ] Check compatibility matrix
- [ ] Notify users of maintenance window

### Upgrade Process

1. Update version in `group_vars/versions.yml`:
   ```yaml
   k3s_version: "v1.32.0+k3s1"  # New version
   ```

2. Run upgrade playbook:
   ```bash
   cd core/ansible
   ansible-playbook playbooks/cluster-upgrade.yml
   ```

3. Validate upgrade:
   ```bash
   make validate
   kubectl get nodes
   ```

### Rollback

If upgrade fails:
```bash
make restore  # Restores from last etcd snapshot
```

## Application Upgrades

Applications managed by ArgoCD auto-upgrade based on chart versions in Git.

To pin a specific version, update `targetRevision` in ArgoCD application:
```yaml
spec:
  source:
    targetRevision: "2.26.4"  # Pin to specific chart version
```
```

![accent-divider.svg](images/accent-divider.svg)
## Implementation Roadmap

### Phase 0: Disaster Recovery & Staging (CRITICAL) 🔴
**Timeline:** Weeks 1-3 (IMMEDIATE)
**Status:** CRITICAL - Production data at risk

#### Week 1: S3 Backup Implementation
- [ ] Create S3 bucket with Glacier lifecycle policy
- [ ] Deploy Nextcloud S3 backup CronJob
- [ ] Configure AWS credentials secret
- [ ] Test manual backup
- [ ] Verify automated nightly backup runs
- [ ] Set up Prometheus alerts for backup failures
- [ ] Document restore procedures
- [ ] Test full restore in staging (once staging exists)

**Success Criteria:**
- Automated nightly backups running successfully
- Backups visible in S3 console
- Prometheus alerts configured
- Restore procedure documented and tested

**Testing:**
```bash
# Trigger manual backup
kubectl create job --from=cronjob/nextcloud-s3-backup nextcloud-backup-test -n nextcloud

# Watch backup progress
kubectl logs -n nextcloud -l job-name=nextcloud-backup-test --follow

# Verify in S3
aws s3 ls s3://seadogger-homelab-backups/nextcloud/

# Test restore (in staging!)
# Follow procedures in docs/wiki/24-Backup-and-Restore.md
```

#### Week 2-3: Staging Environment Setup
- [ ] Install Multipass on Mac
- [ ] Create K3s staging VM
- [ ] Configure staging Ansible inventory
- [ ] Test basic deployment in staging
- [ ] Set up GitLab runner on Mac (if using Option A)
- [ ] Create `.gitlab-ci.yml` with staging pipeline
- [ ] Test automated deployment to staging
- [ ] Document staging workflow

**Success Criteria:**
- Local staging VM running K3s
- Can deploy apps to staging without affecting production
- GitLab CI/CD running tests automatically
- Development workflow documented

**Testing:**
```bash
# Deploy to staging
export KUBECONFIG=~/.kube/k3s-staging.conf
cd core/ansible
ansible-playbook -i inventory/staging/hosts.ini main.yml --tags=test-app

# Verify
kubectl get pods -A

# Run smoke tests via GitLab CI (triggered on commit)
git commit -m "test: verify staging pipeline"
git push origin feature-branch
```

**Deliverables:**
1. 4TB of data backed up to S3 Glacier (ongoing)
2. Safe testing environment operational
3. CI/CD pipeline preventing production breaks
4. Documented backup/restore and staging procedures

---

### Phase 1: Secrets Hardening (Optional)
**Status:** 🟡 OPTIONAL - Already gitignored properly

**Current State:**
- ✅ Secrets already excluded from Git via `.gitignore`
- ✅ `example.config.yml` uses placeholders
- ⚠️ Local secrets in plaintext (acceptable for homelab)

**Optional Improvements (if desired):**
- [ ] Implement Ansible Vault for local `config.yml` encryption
- [ ] Add External Secrets Operator for K8s secrets
- [ ] Scan Git history with `gitleaks` (precautionary)
- [ ] Document vault usage if implemented

**Success Criteria:**
- Config files remain gitignored ✅ (already done)
- Optional: Vault encryption works if implemented

**Testing:**
```bash
# Verify secrets not in repo (should pass already)
gitleaks detect --source . --verbose

# If vault implemented, test:
ansible-playbook main.yml --ask-vault-pass
```

---

### Phase 2: Ansible Restructure (Weeks 4-5)
**Status:** 🟠 HIGH - Foundation for improvements
**Prerequisites:** Phase 0 complete (can test safely in staging)

- [ ] Create roles directory structure
- [ ] Convert `raspberry_pi_config.yml` to role
- [ ] Convert `k3s_control_plane.yml` to role
- [ ] Convert `k3s_worker.yml` to role
- [ ] Convert infrastructure tasks to roles
- [ ] Create `group_vars` and `host_vars`
- [ ] Migrate all variables from `config.yml`
- [ ] Standardize on `kubernetes.core.*` modules
- [ ] Create `group_vars/versions.yml`
- [ ] Update all version references
- [ ] Test full deployment with new structure

**Success Criteria:**
- All tasks in roles
- No `vars_files: config.yml`
- Consistent module usage
- Centralized version management

**Testing:**
```bash
# Lint all roles
ansible-lint roles/

# Test deployment
ansible-playbook playbooks/cluster-install.yml --check
```

---

### Phase 3: K3s Best Practices (Weeks 5-6)
**Status:** 🟠 HIGH - Reliability improvement
**Prerequisites:** Phase 2 complete (role-based structure ready)

- [ ] Provision 2 additional control plane nodes (hardware)
- [ ] Update inventory with 3 control plane nodes
- [ ] Implement HA control plane installation
- [ ] Configure automated etcd backups
- [ ] Create backup sync script (to NFS/S3)
- [ ] Add K3s version pinning
- [ ] Create disaster recovery playbook
- [ ] Document DR procedures
- [ ] Create upgrade playbook
- [ ] Document upgrade process
- [ ] Test DR restore from snapshot

**Success Criteria:**
- 3-node control plane operational
- etcd snapshots every 6 hours
- Successful DR test
- Documented upgrade path

**Testing:**
```bash
# Verify HA
kubectl get nodes
# Should show 3 control-plane nodes

# Test leader election
kubectl -n kube-system get endpoints kube-controller-manager

# Verify backups
ls -lh /opt/k3s-snapshots/

# Test DR restore (in dev cluster first!)
ansible-playbook playbooks/rollback.yml
```

---

### Phase 4: GitOps Consistency (Weeks 6-7)
**Status:** 🟡 MEDIUM - Standardization
**Prerequisites:** Phase 3 complete (HA cluster ready)

- [ ] Create infrastructure ApplicationSet
- [ ] Migrate MetalLB to ArgoCD
- [ ] Migrate Rook-Ceph to ArgoCD
- [ ] Migrate Prometheus to ArgoCD
- [ ] Bundle ingress with each application
- [ ] Convert applications to Helm charts (if needed)
- [ ] Implement App-of-Apps pattern
- [ ] Create root application
- [ ] Update Ansible to deploy only root app
- [ ] Remove external URL dependencies
- [ ] Migrate all manifests to Git
- [ ] Test full GitOps deployment

**Success Criteria:**
- All components managed by ArgoCD
- Single `kubectl apply` for root app
- No external URL downloads
- Consistent deployment pattern

**Testing:**
```bash
# Verify all apps synced
kubectl get applications -n argocd

# Check sync status
argocd app list

# Test drift detection
kubectl delete deployment pihole -n pihole
# ArgoCD should auto-recreate
```

---

### Phase 5: Operational Excellence (Weeks 7-8)
**Status:** 🟡 MEDIUM - Maturity improvement
**Prerequisites:** Phase 4 complete (GitOps fully operational)

- [ ] Create pre-flight validation role
- [ ] Add to all playbooks
- [ ] Create smoke test suite
- [ ] Add post-deployment validation
- [ ] Deploy Loki + Promtail
- [ ] Configure Grafana Loki datasource
- [ ] Add Ansible tags to all roles
- [ ] Test tag-based execution
- [ ] Create rollback playbook
- [ ] Document rollback procedures
- [ ] Test rollback in dev cluster

**Success Criteria:**
- Pre-flight checks prevent invalid deployments
- Smoke tests catch deployment failures
- Centralized logging operational
- Rollback tested and documented

**Testing:**
```bash
# Test pre-flight failure
ansible-playbook main.yml  # With insufficient resources

# Test validation
ansible-playbook playbooks/validate.yml

# Test tags
ansible-playbook main.yml --tags k3s,validate

# Test logs in Grafana
# Query: {namespace="default"}
```

---

### Phase 6: Documentation (Ongoing)
**Status:** 🟢 LOW - Continuous improvement

- [ ] Create C4 architecture diagrams
- [ ] Add diagrams to wiki
- [ ] Create version compatibility matrix
- [ ] Add auto-generation script
- [ ] Create Makefile
- [ ] Document common commands
- [ ] Create upgrade guide
- [ ] Document all upgrade paths
- [ ] Add troubleshooting scenarios
- [ ] Create runbook templates

**Success Criteria:**
- Clear architecture visualization
- Up-to-date compatibility matrix
- Easy-to-use Makefile
- Comprehensive upgrade guide

---

![accent-divider.svg](images/accent-divider.svg)
## Success Metrics

### Before Refactoring
- **Security:** ❌ Secrets in Git
- **Maintainability:** 5/10 - Flat task structure
- **Reliability:** 6/10 - Single control plane
- **Consistency:** 5/10 - Mixed deployment methods
- **Observability:** 6/10 - No logging aggregation
- **Documentation:** 7/10 - Good wiki, missing diagrams

### After Refactoring
- **Security:** ✅ Vault-encrypted secrets
- **Maintainability:** 9/10 - Role-based, DRY
- **Reliability:** 9/10 - HA control plane + backups
- **Consistency:** 9/10 - Full GitOps
- **Observability:** 9/10 - Metrics + logs
- **Documentation:** 9/10 - Diagrams + matrices

---

![accent-divider.svg](images/accent-divider.svg)
## Comparison with Industry Standards

### Benchmark: k3s-ansible Official Project

**Repository:** https://github.com/k3s-io/k3s-ansible

**Seadogger Homelab vs k3s-ansible:**

| Feature                  | k3s-ansible | Seadogger (Before) | Seadogger (After) |
|--------------------------|-------------|--------------------|--------------------|
| Role-based structure     | ✅          | ❌                 | ✅                 |
| group_vars/host_vars     | ✅          | ❌                 | ✅                 |
| Version pinning          | ✅          | ❌                 | ✅                 |
| HA control plane         | ✅          | ❌                 | ✅                 |
| etcd backups             | ⚠️ Manual   | ❌                 | ✅ Automated       |
| Secrets management       | ⚠️ Docs only| ❌ Plaintext       | ✅ Vault           |
| GitOps (ArgoCD)          | ❌          | ⚠️ Partial         | ✅ Full            |
| Pre-flight checks        | ❌          | ❌                 | ✅                 |
| Post-deploy validation   | ❌          | ❌                 | ✅                 |
| Centralized logging      | ❌          | ❌                 | ✅                 |
| Applications included    | ❌          | ✅                 | ✅                 |
| Monitoring stack         | ❌          | ✅                 | ✅                 |

**Key Differentiators (After Refactoring):**
1. **Full-stack homelab** - Infrastructure + applications
2. **Enterprise GitOps** - ArgoCD for everything
3. **Operational maturity** - Validation, logging, rollback
4. **Security-first** - Vault integration, external secrets

**Unique Value:** Seadogger provides a complete, production-ready homelab solution, not just K3s installation.

---

![accent-divider.svg](images/accent-divider.svg)
## References and Resources

### Official Documentation
- [K3s Documentation](https://docs.k3s.io/)
- [Ansible Best Practices](https://docs.ansible.com/ansible/latest/tips_tricks/ansible_tips_tricks.html)
- [ArgoCD Best Practices](https://argo-cd.readthedocs.io/en/stable/user-guide/best_practices/)
- [Kubernetes Patterns](https://kubernetes.io/docs/concepts/configuration/)

### Industry Benchmarks
- [k3s-ansible](https://github.com/k3s-io/k3s-ansible) - Official K3s Ansible deployment
- [kubespray](https://github.com/kubernetes-sigs/kubespray) - Production-grade K8s
- [k8s-at-home](https://github.com/k8s-at-home) - Homelab community

### Security Tools
- [ansible-vault](https://docs.ansible.com/ansible/latest/vault_guide/index.html)
- [External Secrets Operator](https://external-secrets.io/)
- [gitleaks](https://github.com/gitleaks/gitleaks) - Secret scanning
- [git-secrets](https://github.com/awslabs/git-secrets) - Prevent commits with secrets

### Validation & Testing
- [ansible-lint](https://ansible.readthedocs.io/projects/lint/)
- [molecule](https://molecule.readthedocs.io/) - Ansible testing framework
- [kube-score](https://github.com/zegl/kube-score) - Static analysis for Kubernetes

### Monitoring & Logging
- [Prometheus Operator](https://github.com/prometheus-operator/prometheus-operator)
- [Grafana Loki](https://grafana.com/oss/loki/)
- [Promtail](https://grafana.com/docs/loki/latest/send-data/promtail/)

---

![accent-divider.svg](images/accent-divider.svg)
## Next Steps

1. **Review this roadmap** with the team
2. **Prioritize** based on your timeline and resources
3. **Start with Priority 1** (Security) immediately
4. **Create GitHub issues** for each phase
5. **Track progress** using GitHub Projects or similar

**Questions or feedback?** Open an issue in the repository.

---

**Last Updated:** 2025-09-29
**Author:** Claude Code Analysis
**Status:** Proposed