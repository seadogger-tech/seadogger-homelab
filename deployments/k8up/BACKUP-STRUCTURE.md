# K8up Backup Structure in S3

## Understanding the S3 Bucket Layout

The S3 bucket `seadogger-homelab-backup` uses Restic's repository format. **All data is encrypted** with your Restic password before being uploaded to S3.

### Directory Structure

```
seadogger-homelab-backup/
├── config              # Repository configuration (encrypted)
├── keys/               # Encryption keys
│   └── f5f6cff...      # Master key (encrypted with Restic password)
├── data/               # Actual backup data (encrypted, deduplicated)
│   ├── 2b/
│   │   └── 2b666560... # Data chunks (encrypted)
│   ├── 55/
│   │   └── 551f6723... # Data chunks (encrypted)
│   └── ...
├── index/              # Index files for fast searches (encrypted)
│   └── 5e2ad888...
└── snapshots/          # Snapshot metadata (encrypted)
    └── 87583cda...     # Snapshot info: hostname, paths, timestamp
```

### How Restic Organizes Backups

**All namespaces share the same S3 bucket** - Restic handles deduplication automatically:
- If N8N and Nextcloud have identical files, they're stored only once
- Each snapshot (backup run) has metadata showing which namespace it belongs to
- The `hostname` field in snapshots identifies the namespace

## Viewing Backup Information

### Method 1: Kubernetes Snapshot Resources (Easiest)

```bash
# View all snapshots across all namespaces
kubectl get snapshots -A

# View snapshots for specific namespace
kubectl get snapshots -n nextcloud
kubectl get snapshots -n n8n
kubectl get snapshots -n jellyfin

# Get detailed snapshot info
kubectl describe snapshot <snapshot-name> -n <namespace>
```

**Example Output:**
```
NAMESPACE   NAME       DATE TAKEN             PATHS                        REPOSITORY
n8n         87583cda   2025-10-04T16:54:26Z   /data/n8n-main-persistence   s3:https://s3.amazonaws.com/seadogger-homelab-backup
nextcloud   a1b2c3d4   2025-10-05T02:00:15Z   /data/nextcloud-data         s3:https://s3.amazonaws.com/seadogger-homelab-backup
```

The `NAME` field (first 8 chars of snapshot ID) matches the filename in `s3://seadogger-homelab-backup/snapshots/`.

### Method 2: Restic CLI (Most Detailed)

Install Restic on your Mac:

```bash
brew install restic
```

Set environment variables (get these from your `config.yml`):

```bash
export AWS_ACCESS_KEY_ID="<your-k8up-aws-access-key>"
export AWS_SECRET_ACCESS_KEY="<your-k8up-aws-secret-key>"
export RESTIC_PASSWORD="<your-k8up-restic-password>"
export RESTIC_REPOSITORY="s3:https://s3.amazonaws.com/seadogger-homelab-backup"
```

View all snapshots:

```bash
restic snapshots
```

**Example Output:**
```
repository c1b071b1 opened successfully, password is correct
ID        Time                 Host       Tags        Paths
-----------------------------------------------------------------------------------
87583cda  2025-10-04 16:54:26  n8n                    /data/n8n-main-persistence
a1b2c3d4  2025-10-05 02:00:15  nextcloud              /data/nextcloud-data
b2c3d4e5  2025-10-05 03:00:12  n8n                    /data/n8n-main-persistence
-----------------------------------------------------------------------------------
3 snapshots
```

The **Host** column shows which namespace the backup came from.

View files in a specific snapshot:

```bash
# List files in snapshot
restic ls 87583cda

# Browse snapshot interactively
restic mount /tmp/restic-mount
# Then open /tmp/restic-mount in Finder to browse all snapshots
```

Check repository statistics:

```bash
# Repository size and statistics
restic stats

# Check repository integrity
restic check
```

### Method 3: K8up Backup Resources

```bash
# View backup jobs
kubectl get backups -A

# View backup schedules
kubectl get schedules -A

# View backup job details
kubectl describe backup <backup-name> -n <namespace>
```

## How Different Namespaces Are Distinguished

Restic uses the `--host` flag when creating backups. K8up automatically sets this to the **namespace name**:

- N8N backups: `--host n8n`
- Nextcloud backups: `--host nextcloud`
- Jellyfin backups: `--host jellyfin`

When you run `restic snapshots`, the Host column shows which namespace each snapshot belongs to.

## Why Everything Shares One Bucket

**Deduplication Benefits:**
- If multiple namespaces have identical files (e.g., common libraries, duplicate media), Restic stores them only once
- Saves storage space and costs
- Faster backups after the first one

**Example:**
- If N8N and Nextcloud both have a 100MB Docker image layer, it's stored once
- Total storage: 100MB (not 200MB)

## Restoring Specific Namespaces

When restoring, you specify which snapshot (by ID or namespace):

```yaml
apiVersion: k8up.io/v1
kind: Restore
metadata:
  name: n8n-restore
  namespace: n8n
spec:
  snapshot: "87583cda"  # Specific snapshot ID
  # OR use latest from host
  restoreFilter: "n8n"
  # ...
```

K8up will only restore data from snapshots tagged with that hostname/namespace.

## Security Notes

- **All data in S3 is encrypted** with your Restic password before upload
- S3 bucket permissions only allow the k8up-backup-user IAM user
- Even if someone accessed your S3 bucket, they cannot decrypt without the Restic password
- Restic password is stored in Kubernetes Secrets (never in Git)

## Monitoring Backups

### Quick Status Check

```bash
# Check recent backups across all namespaces
kubectl get backups -A --sort-by=.metadata.creationTimestamp

# Check snapshot count per namespace
kubectl get snapshots -A -o json | jq '.items | group_by(.metadata.namespace) | map({namespace: .[0].metadata.namespace, count: length})'
```

### Grafana Dashboard

Import the K8up monitoring dashboard:
- File: `core/docs/grafana-dashboards/k8up-backup-monitoring.json`
- Shows last backup time, success rate, duration, snapshot counts per namespace

### Prometheus Queries

```promql
# Last successful backup per namespace
time() - k8up_backup_last_success_timestamp_seconds

# Backup duration
k8up_backup_duration_seconds

# Total snapshots in repository
k8up_backup_snapshots_total
```

## Troubleshooting

### "How do I know if my backup worked?"

```bash
# Check backup status
kubectl get backup <backup-name> -n <namespace> -o yaml | grep -A 5 status

# Check for "Completed: True"
# Check logs
kubectl logs -n <namespace> -l job-name=<backup-job-name>
```

### "How much space am I using?"

```bash
# Install restic locally
brew install restic

# Set environment variables (see Method 2 above)
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export RESTIC_PASSWORD="..."
export RESTIC_REPOSITORY="s3:https://s3.amazonaws.com/seadogger-homelab-backup"

# Check stats
restic stats
```

### "I can't see recent backups in S3 console"

S3 Deep Archive transitions happen after 1 day. Objects are still accessible via Restic immediately, but AWS Console may show them as "Glacier Deep Archive" after 24 hours.

## Cost Tracking

Track S3 costs in AWS Console:
1. Go to AWS Cost Explorer
2. Filter by Service: S3
3. Filter by Bucket: seadogger-homelab-backup
4. View monthly trends

Expected costs:
- First month (current data): ~$0.023/GB (Standard storage)
- After 1 day: ~$0.00099/GB/month (Deep Archive)
- 100GB backups ≈ $0.10/month
- 1TB backups ≈ $1/month

## Next Steps

1. **Monitor first scheduled backups**: Check tomorrow at 2:00 AM for Nextcloud backup
2. **Import Grafana dashboard**: Visualize backup health
3. **Test a restore**: Quarterly drill to ensure recovery procedures work
4. **Review retention policies**: Adjust in schedule YAML if needed

## References

- K8up Docs: https://k8up.io/k8up/2.0/index.html
- Restic Docs: https://restic.readthedocs.io/
- Disaster Recovery: `core/docs/wiki/23-Disaster-Recovery-Restore.md`
