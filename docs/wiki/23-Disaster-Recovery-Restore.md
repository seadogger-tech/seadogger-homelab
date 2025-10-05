# 23. Disaster Recovery and Restore Procedures

## Overview

This guide covers disaster recovery procedures for restoring data from Velero backups stored in AWS S3 Glacier Deep Archive. Velero uses Kopia for incremental, deduplicated file-level backups of all PVCs and Kubernetes resources.

**IMPORTANT**: S3 Deep Archive has a 12-48 hour retrieval time for bulk retrieval. Plan disaster recovery operations accordingly.

## Backup Architecture

- **Backup Tool**: Velero v1.16.0 (Kubernetes backup operator)
- **Uploader**: Kopia (replaces Restic - content-addressable storage)
- **Storage**: AWS S3 (seadogger-homelab-backup bucket, us-east-1)
- **Lifecycle**: 7 days in S3 Standard → Glacier Deep Archive (permanent retention)
- **Encryption**: AES-256 server-side encryption (AWS S3)
- **Deduplication**: Kopia SHA-256 content checksums

### Backup Schedule

**Week 1 Strategy** (Initial 3.3TB Upload):
| Schedule | Namespaces | Frequency | Time | TTL |
|----------|-----------|-----------|------|-----|
| `weekly-nextcloud-backup` | nextcloud | Weekly (Sunday) | 2:00 AM | 30 days |
| `daily-backup` | openwebui, n8n, jellyfin, pihole, portal | Daily | 2:00 AM | 30 days |

**Week 2+ Strategy** (After Initial Upload):
| Schedule | Namespaces | Frequency | Time | TTL |
|----------|-----------|-----------|------|-----|
| `daily-backup` | nextcloud, openwebui, n8n, jellyfin, pihole, portal | Daily | 2:00 AM | 30 days |

## Application Restore Procedures and Verification Status

### Restore Procedure #1: Standard Application Restore

This procedure applies to most ArgoCD-managed applications that store data in PVCs.

**Steps**:
1. Delete ArgoCD Application: `kubectl delete application <app-name> -n argocd`
2. Delete namespace: `kubectl delete namespace <namespace>`
3. Create Velero restore:
   ```bash
   cat <<EOF | kubectl create -f -
   apiVersion: velero.io/v1
   kind: Restore
   metadata:
     name: <app>-restore-$(date +%Y%m%d-%H%M%S)
     namespace: velero
   spec:
     backupName: <backup-name>
   EOF
   ```
4. Wait for restore to complete: `kubectl get restore -n velero -w`
5. Set Ansible deployment variable to `true` in `ansible/config.yml`
6. Run Ansible playbook: `ansible-playbook ansible/main.yml --tags <app>`
7. Verify pod is running: `kubectl get pods -n <namespace>`

### Verification Status

| Application | Restore Procedure | Verified | Notes |
|-------------|------------------|----------|-------|
| OpenWebUI | Procedure #1 | ✅ | Successfully restored 20 items. Pod running healthy. All configuration loaded from database. No encryption key issues. |
| N8N | Procedure #1 | ❌ | **ENCRYPTION KEY MISMATCH**: N8N stores encryption key in both `/home/node/.n8n/config` (PVC) and Kubernetes secret. Restored config file encryption key doesn't match Helm-generated secret causing "Mismatching encryption keys" error. See [Issue #7](https://github.com/seadogger-tech/seadogger-homelab-pro/issues/7) for resolution. |
| Jellyfin | Procedure #1 | ⏳ | **NOT TESTED**: Needs verification. Special consideration: AWS Glacier retrieval for media files (3TB+). |
| Nextcloud | Procedure #1 | ⏳ | **NOT TESTED**: Large backup (~3.3TB). Requires separate testing due to size and AWS Glacier retrieval time. |
| Pihole | Procedure #1 | ⏳ | Not yet tested. |
| Portal | Procedure #1 | ⏳ | Not yet tested. |

## Prerequisites for Restore

### 1. Access Velero UI

Velero UI provides a visual interface for managing backups and restores:

```
https://velero.seadogger-homelab
```

### 2. Install Velero CLI (Optional)

For advanced operations, install the Velero CLI:

```bash
# macOS
brew install velero

# Linux
wget https://github.com/vmware-tanzu/velero/releases/download/v1.16.0/velero-v1.16.0-linux-amd64.tar.gz
tar -xvf velero-v1.16.0-linux-amd64.tar.gz
sudo mv velero-v1.16.0-linux-amd64/velero /usr/local/bin/
```

### 3. S3 Glacier Deep Archive Retrieval

For backups older than 7 days (stored in Deep Archive), initiate retrieval:

```bash
# Check which lifecycle class objects are in
aws s3api head-object \
  --bucket seadogger-homelab-backup \
  --key <object-key>

# Initiate bulk retrieval (12-48 hours, $0.02/GB)
aws s3api restore-object \
  --bucket seadogger-homelab-backup \
  --key <object-key> \
  --restore-request Days=1,GlacierJobParameters={Tier=Bulk}

# Check retrieval status
aws s3api head-object \
  --bucket seadogger-homelab-backup \
  --key <object-key> \
  | jq '.Restore'
```

**Retrieval Tiers**:
- **Bulk**: 12-48 hours, ~$0.02/GB
- **Standard**: 3-5 hours, ~$0.03/GB
- **Expedited**: Not available for Deep Archive

## Quick Reference: Common Restore Scenarios

### Scenario 1: "I Deleted Something in N8N - Restore from Latest Backup"

**Goal**: Restore N8N to most recent backup (within last 7 days)
**Time**: 5-10 minutes

```bash
# Step 1: List available backups
kubectl get backups -n velero | grep n8n

# Step 2: Scale down N8N (prevents conflicts)
kubectl scale deployment n8n -n n8n --replicas=0

# Step 3: Create restore from latest backup
velero restore create n8n-restore-$(date +%Y%m%d-%H%M%S) \
  --from-backup daily-backup-20251004020000 \
  --include-namespaces n8n

# Step 4: Watch restore progress
velero restore describe n8n-restore-20251004-120000
kubectl get restore -n velero -w

# Step 5: Verify and restart N8N
kubectl get pods -n n8n
kubectl scale deployment n8n -n n8n --replicas=1
```

### Scenario 2: "Restore Nextcloud from Last Week"

**Goal**: Restore Nextcloud to a point-in-time backup

```bash
# Step 1: List all Nextcloud backups
kubectl get backups -n velero | grep nextcloud

# Or use Velero CLI for detailed info
velero backup get | grep nextcloud

# Step 2: Scale down Nextcloud
kubectl scale deployment nextcloud -n nextcloud --replicas=0

# Step 3: Restore from specific backup
velero restore create nextcloud-restore-$(date +%Y%m%d-%H%M%S) \
  --from-backup weekly-nextcloud-backup-20251001020000 \
  --include-namespaces nextcloud

# Step 4: Monitor restore (3.3TB may take 1-2 hours)
velero restore logs nextcloud-restore-20251004-120000
kubectl get pods -n nextcloud -w

# Step 5: Restart Nextcloud
kubectl scale deployment nextcloud -n nextcloud --replicas=1
```

### Scenario 3: "Test Restore Without Overwriting Production"

**Goal**: Verify backup integrity without touching live data

```bash
# Step 1: Create temporary test namespace
kubectl create namespace n8n-test

# Step 2: Restore to test namespace
velero restore create n8n-test-restore \
  --from-backup daily-backup-20251004020000 \
  --include-namespaces n8n \
  --namespace-mappings n8n:n8n-test

# Step 3: Verify restored data
kubectl get all -n n8n-test
kubectl exec -it <pod-name> -n n8n-test -- ls -lah /data

# Step 4: Cleanup when done
kubectl delete namespace n8n-test
```

### Scenario 4: "Which Backups Are Available?"

**Goal**: List all backups with dates to choose specific restore point

```bash
# Method 1: Velero UI
# Navigate to https://velero.seadogger-homelab

# Method 2: kubectl
kubectl get backups -n velero

# Method 3: Velero CLI with details
velero backup get
velero backup describe daily-backup-20251004020000

# Filter by namespace
kubectl get backups -n velero -o json | jq '.items[] | select(.spec.includedNamespaces[] == "nextcloud") | .metadata.name'
```

## Restore Procedures

### Method 1: Restore Entire Namespace (Full Restore)

**Use Case**: Complete data loss, need to restore entire application and its data

```bash
# 1. List available backups
velero backup get

# 2. Scale down application (if running)
kubectl scale deployment <app-name> -n <namespace> --replicas=0

# 3. Create restore
velero restore create <restore-name> \
  --from-backup <backup-name> \
  --include-namespaces <namespace>

# 4. Monitor restore progress
velero restore describe <restore-name>
velero restore logs <restore-name>

# 5. Verify restoration
kubectl get all -n <namespace>
kubectl get pvc -n <namespace>

# 6. Scale up application
kubectl scale deployment <app-name> -n <namespace> --replicas=1
```

**Example YAML** (alternative to CLI):

```yaml
apiVersion: velero.io/v1
kind: Restore
metadata:
  name: nextcloud-restore
  namespace: velero
spec:
  backupName: daily-backup-20251004020000
  includedNamespaces:
    - nextcloud
  restorePVs: true
```

### Method 2: Restore Specific Resources (Selective Restore)

**Use Case**: Recover specific resources without full namespace restore

```bash
# Restore only PVCs from a backup
velero restore create pvc-only-restore \
  --from-backup daily-backup-20251004020000 \
  --include-namespaces n8n \
  --include-resources persistentvolumeclaims

# Restore only ConfigMaps and Secrets
velero restore create config-restore \
  --from-backup daily-backup-20251004020000 \
  --include-namespaces n8n \
  --include-resources configmaps,secrets

# Restore with label selector
velero restore create app-restore \
  --from-backup daily-backup-20251004020000 \
  --selector app=n8n
```

### Method 3: Restore to Different Namespace

**Use Case**: Clone application to staging/test environment

```bash
# Restore n8n production to n8n-staging
velero restore create n8n-staging-clone \
  --from-backup daily-backup-20251004020000 \
  --include-namespaces n8n \
  --namespace-mappings n8n:n8n-staging

# Verify
kubectl get all -n n8n-staging
```

## Emergency Full Cluster Restore

### Scenario: Total Cluster Loss

**Timeline**: 3-5 days (including S3 retrieval time)

#### Day 1: Initiate S3 Deep Archive Retrieval

```bash
# List all objects in backup bucket
aws s3 ls s3://seadogger-homelab-backup/ --recursive

# Initiate bulk retrieval for all backup objects
aws s3api restore-object \
  --bucket seadogger-homelab-backup \
  --key velero/backups/<backup-name>/<object> \
  --restore-request Days=1,GlacierJobParameters={Tier=Bulk}

# Monitor retrieval status
aws s3api head-object \
  --bucket seadogger-homelab-backup \
  --key velero/backups/<backup-name>/<object>
```

#### Day 2-3: Wait for S3 Retrieval

Monitor retrieval progress in AWS Console or via CLI. Objects will temporarily return to S3 Standard tier for 1 day.

#### Day 3: Rebuild Cluster Infrastructure

```bash
# 1. SSH to control plane
ssh pi@yoda.local

# 2. Run infrastructure rebuild (from Mac)
cd /Users/jason/Desktop/Development/seadogger-homelab-pro/core/ansible
ansible-playbook main.yml --tags infrastructure

# This will deploy:
# - K3s control plane and workers
# - Rook-Ceph storage
# - MetalLB
# - ArgoCD
# - Prometheus
```

#### Day 3-4: Restore Applications

```bash
# 1. Deploy Velero (from Pro repo)
cd /Users/jason/Desktop/Development/seadogger-homelab-pro/ansible
ansible-playbook main.yml

# 2. Verify Velero sees backups
velero backup get

# 3. Restore all namespaces one by one
velero restore create nextcloud-restore --from-backup daily-backup-20251004020000 --include-namespaces nextcloud
velero restore create n8n-restore --from-backup daily-backup-20251004020000 --include-namespaces n8n
velero restore create jellyfin-restore --from-backup daily-backup-20251004020000 --include-namespaces jellyfin
velero restore create openwebui-restore --from-backup daily-backup-20251004020000 --include-namespaces openwebui
velero restore create pihole-restore --from-backup daily-backup-20251004020000 --include-namespaces pihole
velero restore create portal-restore --from-backup daily-backup-20251004020000 --include-namespaces portal

# 4. Monitor all restores
velero restore get
kubectl get pods --all-namespaces
```

#### Day 4-5: Validate and Resume Operations

```bash
# Verify applications
kubectl get deployments --all-namespaces
kubectl get pvc --all-namespaces

# Test application functionality
curl https://nextcloud.seadogger-homelab
curl https://n8n.seadogger-homelab
curl https://jellyfin.seadogger-homelab

# Resume normal backup schedules
kubectl get schedules -n velero

# Verify backups are running
velero backup get
```

## Monitoring and Verification

### Check Backup Health

```bash
# View backup schedules
kubectl get schedules -n velero

# View all backups
kubectl get backups -n velero

# View backup details
velero backup describe daily-backup-20251004020000

# Check Velero server logs
kubectl logs deployment/velero -n velero

# Check node-agent status (Kopia uploaders)
kubectl get pods -n velero -l name=node-agent
kubectl logs <node-agent-pod> -n velero
```

### Test Restore Regularly

**Best Practice**: Perform quarterly restore drills

```bash
# Create test namespace
kubectl create namespace restore-test

# Perform test restore
velero restore create quarterly-drill-$(date +%Y%m%d) \
  --from-backup daily-backup-$(date +%Y%m%d)020000 \
  --include-namespaces n8n \
  --namespace-mappings n8n:restore-test

# Verify restored data
kubectl get all -n restore-test
kubectl exec -it <pod> -n restore-test -- ls -lah /data

# Cleanup
kubectl delete namespace restore-test
```

## Troubleshooting

### Issue: Restore Stuck in "InProgress"

```bash
# Check restore details
velero restore describe <restore-name>

# Check restore logs
velero restore logs <restore-name>

# Check node-agent logs (Kopia)
kubectl logs <node-agent-pod> -n velero

# Check for PVC binding issues
kubectl get pvc -n <namespace>
kubectl describe pvc <pvc-name> -n <namespace>
```

### Issue: PVC Not Restoring

```bash
# Verify backup includes PVCs
velero backup describe <backup-name> | grep "Persistent Volumes"

# Check if node-agent pods are running
kubectl get pods -n velero -l name=node-agent

# Verify defaultVolumesToFsBackup is enabled
kubectl get backup <backup-name> -n velero -o yaml | grep defaultVolumesToFsBackup

# Check Kopia repository status
kubectl exec <node-agent-pod> -n velero -- kopia repository status
```

### Issue: S3 Deep Archive Objects Not Available

```bash
# Check object storage class
aws s3api head-object \
  --bucket seadogger-homelab-backup \
  --key velero/backups/<backup-name>/velero-backup.json

# Check if retrieval is ongoing
aws s3api head-object \
  --bucket seadogger-homelab-backup \
  --key <object-key> \
  | jq '.Restore'

# Output:
# "ongoing-request": "true" = still retrieving
# "expiry-date": "<date>" = available until this date
```

### Issue: "Backup Not Found" Error

```bash
# Verify backup exists in S3
aws s3 ls s3://seadogger-homelab-backup/velero/backups/

# Resync Velero backup location
velero backup-location get
kubectl delete backupstoragelocation default -n velero
# Velero will recreate it automatically

# Wait for sync
velero backup get
```

## Cost Considerations

### Backup Storage Costs

- **S3 Standard** (first 7 days): $0.023/GB/month
- **Glacier Deep Archive** (after 7 days): $0.00099/GB/month ($0.99/TB/month)
- **Kopia Metadata** (S3 Standard): ~$0.002/month (~100MB)

**Example - 3.3TB Nextcloud**:
- Month 1: ~$3.30/month (all in Deep Archive after week 1)
- Month 2+: ~$3.30/month (stable cost)

### Restore Costs

- **Recent backups** (<7 days in S3 Standard): Free retrieval
- **Bulk Retrieval** (Deep Archive): $0.02/GB + 12-48 hours wait
- **Standard Retrieval** (Deep Archive): $0.03/GB + 3-5 hours wait
- **Data Transfer Out**: First 100GB/month free, then $0.09/GB

**Example - Restoring 500GB backup**:
- Recent backup: $0 (instant)
- Bulk retrieval: ~$10 + 12-48 hours
- Standard retrieval: ~$15 + 3-5 hours

## Security Best Practices

1. **S3 Encryption**: All backups encrypted with AWS S3 AES-256 server-side encryption
2. **AWS Credentials**: IAM user with minimal S3 permissions (`velero-backup-user`)
3. **RBAC**: Velero service account has limited cluster permissions
4. **Access Control**: Limit who can create/delete backups and restores
5. **Audit**: All Velero operations logged in Kubernetes audit logs

## Related Documentation

- [06. Storage and Rook-Ceph](./06-Storage-Rook-Ceph.md) - Backup architecture and strategy
- [13. ADR Index - ADR-009](./13-ADR-Index.md) - K8up to Velero migration decision
- [Velero Documentation](https://velero.io/docs/v1.16/) - Official Velero docs
- [Kopia Documentation](https://kopia.io/docs/) - Official Kopia docs

## Contact and Support

For disaster recovery assistance:
1. Review this documentation thoroughly
2. Check Velero UI at https://velero.seadogger-homelab
3. Consult Velero server logs: `kubectl logs deployment/velero -n velero`
4. Review backup schedules: `kubectl get schedules -n velero`
5. If needed, contact cluster administrator

---

**Last Updated**: 2025-10-04
**Maintained By**: Seadogger Homelab Team
**Review Frequency**: Quarterly
