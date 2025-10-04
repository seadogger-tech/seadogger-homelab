# 23. Disaster Recovery and Restore Procedures

## Overview

This guide covers disaster recovery procedures for restoring data from K8up backups stored in AWS S3 Deep Archive. K8up uses Restic under the hood to create encrypted, deduplicated backups of all PVCs in the cluster.

**IMPORTANT**: S3 Deep Archive has a 12-48 hour retrieval time. Plan disaster recovery operations accordingly.

## Backup Architecture

- **Backup Tool**: K8up (Kubernetes backup operator)
- **Backend**: Restic (deduplication and encryption)
- **Storage**: AWS S3 (seadogger-homelab-backup bucket)
- **Storage Class**: S3 Deep Archive (after 1 day)
- **Encryption**: AES-256 via Restic password

### Backup Schedule

| Application | Frequency | Time (PT) | Retention |
|------------|-----------|-----------|-----------|
| Nextcloud | Daily | 2:00 AM | 7 daily, 4 weekly, 6 monthly |
| N8N | Daily | 3:00 AM | 14 daily, 8 weekly, 6 monthly |
| Jellyfin | Weekly (Sunday) | 4:00 AM | 4 weekly, 12 monthly |

## Prerequisites for Restore

### 1. S3 Deep Archive Retrieval

Before you can restore, you must retrieve objects from Deep Archive:

```bash
# List all objects in the backup bucket
aws s3 ls s3://seadogger-homelab-backup/ --recursive

# Initiate restore for specific objects (bulk restore)
aws s3api restore-object \
  --bucket seadogger-homelab-backup \
  --key <object-key> \
  --restore-request Days=1,GlacierJobParameters={Tier=Bulk}

# Bulk retrieval: 12-48 hours
# Expedited retrieval: 1-5 minutes (more expensive)
```

**Retrieval Tiers**:
- **Bulk**: 12-48 hours, lowest cost (~$0.0025 per request)
- **Standard**: 12 hours, moderate cost
- **Expedited**: 1-5 minutes, highest cost (~$0.03 per request)

### 2. Obtain Restic Password

The Restic password is stored in the `k8up-s3-credentials` secret in each namespace:

```bash
kubectl get secret k8up-s3-credentials -n nextcloud -o jsonpath='{.data.RESTIC_PASSWORD}' | base64 -d
```

Or retrieve from your local `config.yml` file:
```yaml
k8up_restic_password: "YOUR_RESTIC_PASSWORD"
```

### 3. AWS Credentials

Retrieve AWS credentials from the secret:

```bash
kubectl get secret k8up-s3-credentials -n nextcloud -o jsonpath='{.data.AWS_ACCESS_KEY_ID}' | base64 -d
kubectl get secret k8up-s3-credentials -n nextcloud -o jsonpath='{.data.AWS_SECRET_ACCESS_KEY}' | base64 -d
```

## Restore Procedures

### Method 1: Restore Entire PVC (Full Restore)

**Use Case**: Complete data loss, need to restore entire persistent volume

1. **Create a Restore Job CRD**:

```yaml
apiVersion: k8up.io/v1
kind: Restore
metadata:
  name: nextcloud-restore
  namespace: nextcloud
spec:
  # S3 backend configuration
  backend:
    s3:
      endpoint: https://s3.amazonaws.com
      bucket: seadogger-homelab-backup
      accessKeyIDSecretRef:
        name: k8up-s3-credentials
        key: AWS_ACCESS_KEY_ID
      secretAccessKeySecretRef:
        name: k8up-s3-credentials
        key: AWS_SECRET_ACCESS_KEY
    repoPasswordSecretRef:
      name: k8up-s3-credentials
      key: RESTIC_PASSWORD

  # Restore to a new PVC
  restoreMethod:
    folder:
      claimName: nextcloud-restore-pvc

  # Optional: restore specific snapshot
  # snapshot: <snapshot-id>

  # Tags to identify what to restore (optional)
  # tags:
  #   - app=nextcloud
```

2. **Apply the Restore Job**:

```bash
kubectl apply -f nextcloud-restore.yaml
```

3. **Monitor the Restore Job**:

```bash
# Watch the restore job
kubectl get restore -n nextcloud -w

# Check restore pod logs
kubectl logs -n nextcloud -l job-name=nextcloud-restore

# View detailed job status
kubectl describe restore nextcloud-restore -n nextcloud
```

4. **Verify Restored Data**:

```bash
# Create a temporary pod to inspect restored data
kubectl run -it --rm debug --image=busybox --restart=Never -n nextcloud \
  --overrides='{"spec":{"containers":[{"name":"debug","image":"busybox","stdin":true,"tty":true,"volumeMounts":[{"mountPath":"/data","name":"restore"}]}],"volumes":[{"name":"restore","persistentVolumeClaim":{"claimName":"nextcloud-restore-pvc"}}]}}' \
  -- ls -la /data
```

5. **Replace Original PVC** (DANGER):

```bash
# Scale down the application
kubectl scale deployment nextcloud -n nextcloud --replicas=0

# Backup current PVC (optional safety measure)
kubectl get pvc nextcloud-pvc -n nextcloud -o yaml > nextcloud-pvc-backup.yaml

# Delete old PVC (DESTRUCTIVE)
kubectl delete pvc nextcloud-pvc -n nextcloud

# Rename restored PVC
kubectl patch pvc nextcloud-restore-pvc -n nextcloud --type='json' \
  -p='[{"op": "replace", "path": "/metadata/name", "value":"nextcloud-pvc"}]'

# Scale up the application
kubectl scale deployment nextcloud -n nextcloud --replicas=1
```

### Method 2: Restore Individual Files/Folders (Selective Restore)

**Use Case**: Recover specific files or directories without full restore

1. **Create a Restore Job with Path Filter**:

```yaml
apiVersion: k8up.io/v1
kind: Restore
metadata:
  name: nextcloud-selective-restore
  namespace: nextcloud
spec:
  backend:
    s3:
      endpoint: https://s3.amazonaws.com
      bucket: seadogger-homelab-backup
      accessKeyIDSecretRef:
        name: k8up-s3-credentials
        key: AWS_ACCESS_KEY_ID
      secretAccessKeySecretRef:
        name: k8up-s3-credentials
        key: AWS_SECRET_ACCESS_KEY
    repoPasswordSecretRef:
      name: k8up-s3-credentials
      key: RESTIC_PASSWORD

  restoreMethod:
    folder:
      claimName: nextcloud-selective-restore-pvc

  # Restore specific paths only
  restoreFilter: "/data/user123/files/Documents"
```

2. **Apply and Monitor**:

```bash
kubectl apply -f nextcloud-selective-restore.yaml
kubectl logs -n nextcloud -l job-name=nextcloud-selective-restore -f
```

### Method 3: Direct Restic CLI Restore (Advanced)

**Use Case**: Maximum control, scripted restores, or debugging

1. **Install Restic on Recovery Machine**:

```bash
# macOS
brew install restic

# Linux
sudo apt-get install restic
```

2. **Set Environment Variables**:

```bash
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export RESTIC_PASSWORD="your-restic-password"
export RESTIC_REPOSITORY="s3:s3.amazonaws.com/seadogger-homelab-backup"
```

3. **List Snapshots**:

```bash
restic snapshots
```

4. **Restore Specific Snapshot**:

```bash
# Restore entire snapshot to local directory
restic restore <snapshot-id> --target /path/to/restore

# Restore specific path from snapshot
restic restore <snapshot-id> --target /path/to/restore --include /data/important-file.txt

# Restore latest snapshot
restic restore latest --target /path/to/restore
```

5. **Browse Snapshot Contents**:

```bash
# List files in a snapshot
restic ls <snapshot-id>

# Mount snapshot as filesystem (requires FUSE)
mkdir /mnt/restic
restic mount /mnt/restic
# Browse files, then unmount
fusermount -u /mnt/restic
```

## Emergency Full Cluster Restore

### Scenario: Total Cluster Loss

**Timeline**: 3-5 days (including S3 retrieval time)

1. **Day 1: Initiate S3 Deep Archive Retrieval**
   - Use AWS Console or CLI to restore all backup objects
   - Choose Bulk retrieval (12-48 hours) to minimize cost
   - Wait for objects to become available

2. **Day 2-3: Wait for S3 Retrieval**
   - Monitor retrieval status in AWS Console
   - Objects will be available in S3 Standard tier temporarily

3. **Day 3: Rebuild Cluster Infrastructure**
   - Reinstall K3s cluster using Ansible playbook
   - Deploy Rook-Ceph storage
   - Install K8up operator
   - Recreate secrets with AWS and Restic credentials

4. **Day 3-4: Restore Applications**
   - Create empty PVCs for each application
   - Apply K8up Restore CRDs for each PVC
   - Wait for restore jobs to complete
   - Deploy applications using ArgoCD

5. **Day 4-5: Validate and Resume Operations**
   - Verify data integrity
   - Test application functionality
   - Resume normal backup schedules
   - Document lessons learned

## Monitoring and Verification

### Check Backup Health

```bash
# View backup schedules
kubectl get schedules --all-namespaces

# View recent backup jobs
kubectl get backups --all-namespaces

# Check backup job logs
kubectl logs -n nextcloud -l k8up.io/owned-by=backup_<job-name>

# View backup metrics in Grafana
# Dashboard: "K8up Backup Monitoring"
# URL: https://grafana.seadogger-homelab/d/k8up-backup-monitoring
```

### Test Restore Regularly

**Best Practice**: Perform quarterly restore drills

```bash
# Create test restore job
kubectl apply -f test-restore.yaml

# Verify restored data
kubectl run test-verify --rm -it --image=busybox \
  --overrides='<volume-mount-config>' -- ls -la /restore
```

## Troubleshooting

### Issue: Restore Job Stuck or Failing

```bash
# Check restore pod logs
kubectl logs -n <namespace> -l k8up.io/owned-by=restore_<job-name>

# Check for PVC binding issues
kubectl get pvc -n <namespace>

# Verify S3 credentials
kubectl get secret k8up-s3-credentials -n <namespace> -o yaml
```

### Issue: S3 Deep Archive Objects Not Available

```bash
# Check restore status
aws s3api head-object \
  --bucket seadogger-homelab-backup \
  --key <object-key>

# Look for "Restore" field in output
# "ongoing-request": true = still retrieving
# "expiry-date": <date> = available until this date
```

### Issue: Restic Repository Errors

```bash
# Check repository integrity
restic check

# Rebuild index if corrupted
restic rebuild-index

# Unlock repository if locked
restic unlock
```

## Cost Considerations

### Backup Storage Costs

- **Deep Archive Storage**: $0.00099/GB/month ($1/TB/month)
- **Estimated 1TB backups**: ~$1/month storage cost

### Restore Costs

- **Bulk Retrieval**: $0.0025 per 1000 requests + $0.02/GB
- **Expedited Retrieval**: $0.03 per 1000 requests + $0.10/GB
- **Data Transfer Out**: $0.09/GB (first 10TB/month)

**Example**: Restoring 500GB backup:
- Bulk: ~$10 + 12-48 hours wait
- Expedited: ~$50 + 1-5 minutes wait

## Security Best Practices

1. **Restic Password**: Store in secure vault, rotate annually
2. **AWS Credentials**: Use IAM user with minimal S3 permissions only
3. **Encryption**: All backups are encrypted at rest with Restic AES-256
4. **Access Control**: Limit who has access to restore procedures
5. **Audit**: Log all restore operations for compliance

## Related Documentation

- [06. Storage and Rook-Ceph](./06-Storage-Rook-Ceph.md) - Backup strategy overview
- [GitHub Issue #24](https://github.com/seadogger/seadogger-homelab/issues/24) - K8up implementation tracking
- [K8up Documentation](https://k8up.io/k8up/2.0/index.html) - Official K8up docs
- [Restic Documentation](https://restic.readthedocs.io/) - Official Restic docs

## Contact and Support

For disaster recovery assistance:
1. Review this documentation thoroughly
2. Check Grafana dashboard for backup health
3. Consult K8up operator logs
4. If needed, contact cluster administrator

---

**Last Updated**: 2025-10-03
**Maintained By**: Seadogger Homelab Team
**Review Frequency**: Quarterly
