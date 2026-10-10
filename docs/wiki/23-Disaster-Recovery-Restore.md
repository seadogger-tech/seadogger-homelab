# Backup and disaster recovery

This guide describes the backup sources and recovery boundaries in the current
Core and Pro manifests. Use it with the [diagnose-before-recovery runbook](17-Runbooks#diagnose-before-recovery).
A production restore changes data and requires a separately reviewed recovery
plan. Keep the original data and backup artifacts until the restored application
has been verified.

## Backup sources

| Source | Owner | Coverage and schedule | Check before relying on it |
| --- | --- | --- | --- |
| Velero with Kopia | Pro `deployments/velero/schedule.yaml` | Daily backup of application namespaces except Nextcloud; separate weekly Nextcloud backup | Backup, PodVolumeBackup and storage-location status; matching objects in the configured S3 destination |
| Nextcloud file mirror | Core `deployments/nextcloud/s3-backup-cronjob.yaml` | Nightly copy of included Nextcloud data files | Recent Job result and destination comparison; the mirror excludes cache, temporary files, appdata, trash, versions and logs |
| Nextcloud PostgreSQL native dump | Core `deployments/nextcloud/postgresql/backup-cronjob.yaml` | 03:15 America/New_York after activation; initially suspended during staging | Job and both container results, archive validation, and three nonempty objects for the same attempt |

Read the manifests and live Schedule/CronJob objects for the selected revision.
A configured schedule does not prove that a backup ran or that its data can be
restored. The file mirror uses `aws s3 sync --delete`; never use that command as
a restore recipe. A native database dump and a file mirror protect different
parts of Nextcloud and must be selected as a consistent pair for recovery.

## Read-only inventory

Record the observation time and keep command output in a private operator
evidence location. These commands only
inspect Kubernetes resources:

```bash
kubectl get schedules,backups,backupstoragelocations -n velero
kubectl get podvolumebackups -n velero
kubectl get cronjobs,jobs -n nextcloud
kubectl get applications -n argocd
kubectl get pvc -A
```

For a candidate backup, inspect its status, errors and covered namespaces.
Inspect any PodVolumeBackups for the relevant PVCs. For a native database dump,
check the dump and upload container exit codes and logs; match the attempt
identifier to the S3 directory and verify `nextcloud.dump`, `SHA256SUMS` and
`metadata.txt` are present and nonempty. Check the mirror's included file set
separately. Keep exact object keys and receipts in private evidence.

## Choose a recovery path

1. Identify the failure boundary and stop new writes before restoring data.
   For Nextcloud, inventory all writers and follow the database/file consistency
   boundaries in the [PostgreSQL migration runbook](26-Nextcloud-PostgreSQL-Migration).
2. Select a backup taken before the damage. Compare its timestamp, completed
   status, source revision, namespace and volume coverage with the recovery goal.
3. Check the S3 storage class for every required object. Kopia may need index
   and metadata blobs before it can identify data packs. Objects in Deep Archive
   must be retrieved before the restore can read them; a successful listing is
   not proof that retrieval has completed.
4. Prepare an isolated restore target and review namespace mapping, PVC names,
   storage classes, Secret handling and available capacity. A restore into the
   live namespace can overwrite or conflict with current resources.
5. Execute the reviewed restore through the owning Velero or application
   workflow. Observe the Restore and PodVolumeRestore results, then validate
   application behavior and data consistency. Do not treat a completed Restore
   object alone as proof of usable data.
6. Record the final state and retain the original PVCs, database and backup
   artifacts until the recovery decision explicitly disposes of them.

For a Velero recovery, first confirm the BackupStorageLocation is available
and the selected Backup is complete. Build a `velero.io/v1` Restore manifest
for the reviewed backup and target namespace; inspect the rendered object before
submitting it. Restore the namespace and its volumes together. If the source
namespace is still live, test with a distinct namespace and review whether any
cluster-scoped or external resources need separate handling. The Pro Velero
schedule excludes K3s system namespaces, Rook-Ceph and Velero itself; rebuild
those through their owning installation procedures rather than assuming a
Velero backup covers them.

Use this only as a starting point for a reviewed, isolated Restore manifest;
replace every placeholder and inspect the Backup's included resources and
volume coverage first:

```yaml
apiVersion: velero.io/v1
kind: Restore
metadata:
  name: reviewed-isolated-restore
  namespace: velero
spec:
  backupName: REVIEWED_BACKUP_NAME
  includedNamespaces:
    - SOURCE_NAMESPACE
  namespaceMapping:
    SOURCE_NAMESPACE: ISOLATED_NAMESPACE
```

After submission, inspect the Restore's warnings/errors, its
PodVolumeRestores, the target PVCs and the recovered application. Do not remove
the source namespace or its volumes as a prerequisite to this check.

## Nextcloud recovery boundary

The Nextcloud file tree, configuration and database form one application state.
Choose a file backup and database backup that can be reconciled at a known
point in time. The native file mirror is a copy of selected files, not a database
backup or a complete replacement for a Velero snapshot. The PostgreSQL dump
contains database state, not user file bytes. Do not pair a stale SQLite
checkpoint with files that received later writes, and do not switch database
selection merely to make a restore start.

Before using a native PostgreSQL dump, copy the selected attempt to private
working storage and verify it without connecting to production:

```bash
cd /PRIVATE/RESTORE-WORKDIR
sha256sum -c SHA256SUMS
pg_restore --list nextcloud.dump >/dev/null
pg_restore --file=/dev/null nextcloud.dump
```

These checks establish file integrity and archive readability, not a working
database restore. Restore into an isolated PostgreSQL target first, validate
schema and application behavior with the matching files, then plan any
production cutover. Use the [migration runbook](26-Nextcloud-PostgreSQL-Migration)
for the saved deployment selection, writer barrier and reopening boundary.

## Deep Archive and Kopia

S3 lifecycle rules may move Kopia data packs into Deep Archive. Kopia repository
configuration, index and metadata must remain readable for maintenance and
restore planning. If any required index or metadata object has also moved to
Deep Archive, retrieve it before asking Kopia to enumerate data packs; changing
an S3 lifecycle rule does not retrieve existing objects. Inspect the current
bucket policy and object storage classes through an authorized identity before
choosing a retrieval tier. Retrieval time and cost depend on the actual object
set and storage class; record measured outcomes rather than assuming a fixed
restore time.

## Verification and handoff

- Compare recovered application files, database records and configuration with
  the chosen backup point. Perform authenticated reads and a bounded write test
  in the isolated target where appropriate.
- Check controller health, PVC mounts, application logs, backup schedules and
  ArgoCD reconciliation after any approved production transition.
- Record what was restored, what was excluded, the observed completion state and
  any untested recovery path. Keep raw receipts and object identifiers in
  private evidence; publish only a reviewed, sanitized conclusion.

See [Deployment and Validation](27-Deployment-and-Validation) for ownership and
[Storage and Rook-Ceph](06-Storage-Rook-Ceph) for the storage classes. The older
Velero/rclone example is historical and is not a source of current deployment
commands.
