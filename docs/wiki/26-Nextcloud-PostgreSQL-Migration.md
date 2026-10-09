# Nextcloud PostgreSQL migration

This runbook prepares and executes the Nextcloud 32.0.6 SQLite-to-PostgreSQL 17 conversion. Publishing these files does not deploy the new database or change the live Nextcloud values. Staging the database and beginning application downtime are separate, explicit operations. Schedule the cutover before executing mutation phases; allow roughly two hours and time to investigate an overrun.

The conversion uses the existing production file volume. It creates no isolated recovery environment and retrieves no archived S3 objects. The accepted recovery evidence is a complete filename-and-size comparison within the existing mirror exclusions. This is not file-content verification or proof of a successful restore.

## Deployment and backup layout

- `deployments/nextcloud/postgresql/`: a separate `nextcloud-db` StatefulSet, two Services, retained 10Gi RWO `ceph-block-data` PVC, initialization/backup scripts, suspended native-backup CronJob and failed/stale backup alerts.
- `ansible/nextcloud_postgresql.yml`: explicit staging, with credentials from gitignored `ansible/config.yml`; not imported by `main.yml`.
- `deployments/nextcloud/nextcloud-postgresql-values.yaml`: opt-in external-database overlay. The bundled PostgreSQL must be disabled because chart 8.9.1 gives it precedence over `externalDatabase`.
- `ansible/nextcloud_migration.yml` and `useful_scripts/nextcloud-migration/migrate.py`: bounded phases, private state, no cluster mutation without `--execute`.
- `ansible/nextcloud-database.local.json`: gitignored database/image selection written by the runner and loaded by ordinary Nextcloud deployment tasks. Preserve this file with the private configuration. It prevents later Ansible runs from selecting the old database. Reconstruct it from the successful run evidence when moving operator workstations.

The application gets a separate, non-superuser `nextcloud` role and database. PostgreSQL requests 100m CPU/512Mi memory, with 1 CPU/1Gi limits; native backup requests 100m/128Mi, with 1 CPU/512Mi limits. The maintenance pod requests 100m/256Mi and uses the captured application image digest. No recursive ownership change is performed on the source PVC.

Pinned images, rechecked against registry manifests on 2026-10-08:

| Publisher/image | Tag | Index digest |
| --- | --- | --- |
| Docker Official `library/postgres` | `17.11-bookworm` | `sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826` |
| Amazon `amazon/aws-cli` | `2.37.10` | `sha256:3dacc5db57c923c4223e949795f538ecf1f2212b2b7d5a028b47b97f91564c0d` |

Both indexes contain `linux/arm64`. Review maintenance status, release notes and ARM64 manifests when updating pins; do not float a major version. The old `bitnamilegacy` workload is not the new database. Cutover protects its tracked resources with `Prune=false,Delete=false` before disabling its subchart. Its retirement requires a separate inspection of data and consumers; this procedure never deletes it.

Native dumps run nightly at **03:15 America/New_York** after activation, and before subsequent database/application changes. Each attempt writes a unique timestamp/Pod-UID directory to `s3://seadogger-homelab-backup/nextcloud-postgresql/`. The dump container uses `pg_dump -Fc`, parses the complete archive with `pg_restore --file=/dev/null`, and writes `SHA256SUMS` and metadata. The separate AWS CLI container uploads it. No database restore is executed. Keep every dump initially; no retention deletion is configured. Kubernetes Job-history limits delete Job records, not S3 objects.

The existing native-file mirror is `s3://homelab-nextcloud-backup-708765384784-us-east-1-an/nextcloud-data/`. It covers the entire PVC, with its existing cache/tmp/appdata/trash/version/log exclusions. The other bucket holds K3s/Velero backups and the separately named native database artifacts. Do not change either bucket lifecycle or the existing FPA AWS profile. The homelab AWS MCP connection uses the separately configured backup identity.

## Before staging

1. Review the diff and choose an immutable, published 40-character Core commit. Confirm the original `nextcloud-values.yaml` is unchanged.
2. Recheck four Ready nodes, Ceph `HEALTH_OK`, scheduler reservations, actual memory, and no unexpected eviction/OOM/crash loop. The October 8 preflight found about 4TiB raw Ceph free; rey reserved 5612Mi of 8052Mi before these workloads. These are snapshots, not a capacity guarantee.
3. Verify `ceph-block-data` is expandable with reclaim policy `Retain`; the staging playbook enforces both. The cluster advertises two default classes, so the explicit class is essential.
4. Inspect `monitoring/k8s` Prometheus selection and kube-state-metrics. Staging requires empty rule and namespace selectors so the new rules in `nextcloud` are selected. Verify their successful loading and the failed-job/36-hour stale expressions after staging. An existing monitoring stack does not prove notification delivery; check its receiver separately.
5. Using the homelab AWS MCP identity, inspect the existing workload identity/policy and destination lifecycle. Confirm `ListBucket` for the two prefixes, read access needed for verification, and `PutObject` (plus applicable multipart/KMS rights) for the mirror, `nextcloud-postgresql/` and `nextcloud-migration/`. Do not infer write access from a successful listing. The execution checkpoint/dump uploads must succeed before reopening; no speculative IAM changes are part of staging.
6. Add two distinct passwords of at least 24 characters to gitignored `ansible/config.yml`: `nextcloud_postgresql_admin_password` and `nextcloud_postgresql_password`. Do not put credentials in command arguments, Git, chat, or public logs. The playbook masks Secret handling and refuses implicit rotation of an existing database Secret.

After the staging workload has been reviewed and authorized, run from the operator workstation (replace the commit placeholder):

```bash
ansible-playbook -i /Users/jason/dev/seadogger-homelab-pro/core/ansible/hosts.ini /Users/jason/dev/seadogger-homelab-pro/core/ansible/nextcloud_postgresql.yml -e nextcloud_postgresql_apply=true -e nextcloud_postgresql_revision=REVIEWED_CORE_COMMIT
```

Inspect the new PVC, database logs, rollout, resource use, empty target and backup rules. The CronJob remains suspended. Do not connect Nextcloud yet. A partially initialized PVC/target is retained for inspection, never automatically wiped or reinitialized.

## Prepare the private run

Use one new absolute state directory on durable private workstation storage; mode 0700. Keep it outside Git. It contains deployment/configuration references, manifests, potentially sensitive error output and operation flags. Do not paste its contents into issues.

Create `webdav-credentials.json` inside it with mode 0600, containing JSON keys `username` and `password`. Use an existing account's protected app password with permission to create the four validation files. Enter it through a local password manager/editor, not shell history. `prepare` requires this file; the authenticated validation proves its actual access later.

Before asserting writer review, inspect application and Argo ownership, all PVC mounts (including aliases of the same Ceph volume), CronJobs/active Jobs, node timers, shell imports, external clients and administrative automation. Jellyfin may continue only with verified read-only mounts. Do not overlap weekly backup activity. Stop external maintenance/deployment automation for the window: neither a human nor another controller may redeploy Nextcloud while the phase runner holds the barrier. Record the inventory and fresh cluster/storage health in private notes.

The standard Ansible phase invocation is:

```bash
ansible-playbook /Users/jason/dev/seadogger-homelab-pro/core/ansible/nextcloud_migration.yml -e nextcloud_migration_action=prepare -e nextcloud_migration_state=/ABSOLUTE/PRIVATE/RUN -e nextcloud_migration_execute=true -e nextcloud_migration_writers_reviewed=true
```

Without `nextcloud_migration_execute=true`, it only prints a plan. `prepare` reads the live state and records it privately; it requires the staged database Application to reference an immutable commit. The direct equivalent is:

```bash
python3 /Users/jason/dev/seadogger-homelab-pro/core/useful_scripts/nextcloud-migration/migrate.py prepare --state-dir /ABSOLUTE/PRIVATE/RUN --execute --writers-reviewed
```

Run `status` against that same directory to inspect phase flags. Each subsequent invocation uses the same directory. The kube context is captured and later calls explicitly select it. A local lock prevents concurrent phases in one run; it does not coordinate a second workstation or a second run directory.

## Scheduled cutover phases

Run one phase at a time, inspect its outcome, then continue. Use the invocation above with the action changed. Do not put the sequence in an unattended retry loop.

| Phase | Required result |
| --- | --- |
| `fence` | Disable Nextcloud Argo automation, suspend the existing mirror, wait for existing operations, enable maintenance, scale normal web/cron pods to zero and verify no Service endpoints. Create a UID33 CLI-only maintenance pod on the original PVC. Authenticate and transactionally test a public-schema write in the empty target; the test transaction rolls back. |
| `checkpoint` | Native SQLite backup API captures committed WAL data. Require integrity and matching table counts. Preserve database digest, user/share/file-reference fingerprints, full configuration tar and completion marker under `data/.postgresql-migration/RUN/`. Preserve original DB and user files. |
| `refresh` | Reject escaping/cyclic links, upload the separately named checkpoint, run the existing mirror exclusions with **no `--delete`**, then compare every included key/size with fully paginated S3 listings. Recheck the source manifest. Remote-only objects are counted and retained. |
| `convert` | Recheck the independent barrier and empty target. Run the reviewed 32.0.6 upstream converter, with password only in memory. Stop on any omission/question; retain private stdout/stderr even on failure. Never clear or retry a partial target. |
| `validate` | Check every source table count except regenerated `oc_migrations`, original migration-version inclusion, user/share/file-reference fingerprints, sequence positions, enabled apps, effective database host and Nextcloud bootstrap. |
| `canary` | Start Apache only on loopback in the maintenance pod; independently inspect socket bindings. Port-forward only to workstation loopback. Create a unique folder and four tiny simultaneous uploads, read each back, then remove only recognized new artifacts. Reject foreign contents or an uncertain write outcome. |
| `backup` | Create the first native dump Job from the suspended CronJob. Require successful archive validation/upload and all three nonempty S3 artifacts for this Pod UID. This confirms object presence/size, not an isolated restore. |
| `reopen` | Requires the runtime review below. Protect legacy resources, render external DB values with replicas zero and the captured application digest, verify effective environment, persist the local Ansible selection, stop the maintenance pod, then record the irreversible reopening boundary **before** requesting normal replicas. Verify normal Service HTTP and PostgreSQL bootstrap before restoring mirror/Argo policies and activating nightly dumps. |

Before `reopen`, inspect the new PostgreSQL/maintenance Pod logs and relevant Nextcloud errors privately; review application/table/reference validation, current Ceph/node/PVC health, OOM/restart/resource use, cleanup evidence, real dump S3 receipt and loaded backup alerts. Record the findings. Supply `nextcloud_migration_health_reviewed=true` to the Ansible invocation (or `--health-reviewed` directly) only after completing that review. The attestation is an operator check, not an automatic cluster-health test.

After reopening, confirm ordinary client login/files/shares and app operation, Argo reconciliation, restored mirror schedule and unsuspended native backups. Record the completed state and retain all recovery evidence. Do not delete the SQLite checkpoint or legacy database workload as part of this cutover.

## Failure boundaries and recovery

Before normal reopening, a failure in refresh/conversion/validation/canary/backup/reopening preparation attempts the accepted safe SQLite rollback. The rollback first proves the barrier still holds, checks the checkpoint, accounts for canary artifacts, and verifies there are no PHP/Apache/cron processes. It preserves the current SQLite/WAL/SHM and complete configuration under `preserved-before-rollback`, installs the validated checkpoint/configuration pair and restores matching deployment settings. Failed PostgreSQL contents are retained. An uncertain canary write, unexpected file, running process, failed checkpoint check or uncertain barrier stops rollback and leaves access paused for investigation.

After `reopening_started` is persisted, **never automatically restore SQLite**. A failed check disables Argo automation, suspends the mirror and scales normal writers to zero while retaining PostgreSQL and current files. The same boundary applies to `rollback_reopening_started`: after reopening SQLite, preserve its current state and never install the earlier checkpoint again. Once access might have resumed, an earlier database copy is stale. Investigate and repair/recover forward with a separately reviewed procedure.

Failures during `fence` or `checkpoint` may leave maintenance enabled or reconciliation suspended. Those phases intentionally refuse blind retries. Preserve their state, inspect active operations/processes and checkpoint completeness, then prepare a concrete recovery action from the captured original settings. Do not delete flags to trick the runner into continuing. If the maintenance pod was already stopped during reopening preparation, automatic rollback cannot establish its checks; keep normal replicas zero and recreate/review the maintenance barrier before any manual recovery.

A finished or rolled-back run cannot be repeated. Keep its directory and marker. A new migration attempt requires inspecting the retained target, marker and recovery artifacts first; never automatically clear the target. Do not rerun `main.yml` from a different checkout missing the database marker during or after the cutover.

For a later pre-change dump, an operator can create a uniquely named Job from `nextcloud-db-backup`, wait for completion, and verify its three S3 artifacts and Pod UID. Do this before the authorized change. Do not equate a CronJob definition or an old successful Job with a fresh backup.

## Validation evidence and remaining runtime checks

Local preparation validation on 2026-10-08:

- PHP syntax, Python compilation and 16 local integration/failure tests pass. These include a real WAL checkpoint, corrupt-checkpoint rejection, preserved rollback state, traversal failures, writer-barrier failures, partial-target refusal, canary cleanup limits and pre/post-reopening failure dispatch.
- Helm 3.19.0 renders the actual Nextcloud chart 8.9.1 with replicas zero, external PostgreSQL Secret references, immutable image, and no bundled PostgreSQL/wait container.
- Kustomize renders seven namespaced resources, a suspended CronJob and explicit retained PVC. Repository YAML lint and both Ansible syntax checks pass.
- Independent standards/spec review found and corrected bundled-chart precedence, empty Argo automation configuration, lost failure transcripts, image pinning and insufficient post-start health verification.

These are preparation checks. The homelab AWS MCP confirmed the backup identity, but its IAM policy-listing requests returned AccessDenied. Scoped destination writes remain unproven until the real uploads succeed; the FPA connection was unchanged.

New database startup, Secret readability under the intended UID, actual target writes/conversion, protected WebDAV access, scoped S3 uploads, loaded rule evaluation and client operation must succeed in the separately authorized staging/cutover. No production migration or restore was executed to produce the local evidence.

Run the local tests without cluster or AWS access:

```bash
python3 -m unittest discover -s /Users/jason/dev/seadogger-homelab-pro/core/useful_scripts/nextcloud-migration/tests -v
```

Primary references: [Nextcloud conversion and omitted tables](https://docs.nextcloud.com/server/32/admin_manual/configuration_database/db_conversion.html), [pinned converter source](https://github.com/nextcloud/server/blob/v32.0.6/core/Command/Db/ConvertType.php), [PostgreSQL dump](https://www.postgresql.org/docs/17/app-pgdump.html), [archive parsing versus restore](https://www.postgresql.org/docs/17/app-pgrestore.html), [Docker Official PostgreSQL image](https://github.com/docker-library/postgres), [supported AWS CLI container interface](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-docker.html), [Argo automated sync](https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/), [Argo resource prune protection](https://argo-cd.readthedocs.io/en/stable/user-guide/sync-options/#no-prune-resources).
