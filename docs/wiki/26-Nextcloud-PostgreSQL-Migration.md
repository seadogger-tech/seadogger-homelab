# Nextcloud PostgreSQL migration

This runbook prepares and executes the Nextcloud 32.0.6 SQLite-to-PostgreSQL 17 conversion. Publishing these files does not deploy the new database or change the live Nextcloud values. Staging the database and beginning application downtime are separate, explicit operations. Schedule the cutover before executing mutation phases; allow roughly two hours and time to investigate an overrun.

The conversion uses the existing production file volume. It creates no isolated recovery environment and retrieves no archived S3 objects. The accepted recovery evidence is a complete filename-and-size comparison within the existing mirror exclusions. This is not file-content verification or proof of a successful restore.

## Deployment and backup layout

- `deployments/nextcloud/postgresql/`: a separate `nextcloud-db` StatefulSet, two Services, retained 10Gi RWO `ceph-block-data` PVC, initialization/backup scripts, suspended native-backup CronJob and failed/stale backup alerts.
- `ansible/main.yml`: the normal application-stage entry point imports `tasks/nextcloud_postgresql_deploy.yml` before Nextcloud when `enable_nextcloud_postgresql` is selected. Ansible provisions the Secret and ArgoCD Application; ArgoCD renders Kustomize and owns the database, PVC, backups and alerts.
- `ansible/nextcloud_postgresql.yml`: explicit database-only staging, with the same shared tasks and gitignored `ansible/config.yml`; it neither enables other applications nor converts Nextcloud.
- `deployments/nextcloud/nextcloud-postgresql-values.yaml`: opt-in external-database overlay. The bundled PostgreSQL must be disabled because chart 8.9.1 gives it precedence over `externalDatabase`.
- `ansible/nextcloud_migration.yml` and `useful_scripts/nextcloud-migration/migrate.py`: bounded phases, private state, no cluster mutation without `--execute`.
- `ansible/nextcloud-database.local.json`: gitignored database/image selection written by the runner and loaded by ordinary Nextcloud deployment tasks. Preserve this file with the private configuration. Deployment rejects a missing marker when live PostgreSQL settings or a migrated image pin exist, a stale marker that disagrees with the live Helm values, and paused/running Nextcloud reconciliation. This protects both PostgreSQL and rollback-to-SQLite selections.

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

The example configuration leaves `manual_install_nextcloud_postgresql: false`. For the normal application stage, set it to true together with `cold_start_stage_3_install_applications: true`, and set `nextcloud_postgresql_revision` to the reviewed commit. Their conjunction selects `enable_nextcloud_postgresql`; either switch false leaves the database untouched. Existing private configurations without this new enable variable also leave it disabled. As with other applications, an explicit `enable_nextcloud_postgresql: true` override selects it independently. No staging path changes Nextcloud's selected database.

For a database-only run of the normal entry point, use `main.yml --tags nextcloud_postgresql` with that selection enabled. This tag excludes unrelated application, namespace and infrastructure tasks; the Nextcloud namespace and ArgoCD must already exist. For a normal multi-application run, PostgreSQL is ordered before Nextcloud. This change does not alter any existing infrastructure or cold-start switches; `cleanup.yml` is never called by these tasks.

Alternatively, after staging has been reviewed and authorized, invoke the dedicated entry point below. It requires `nextcloud_postgresql_apply=true` and imports the identical database tasks, independently of the stage/manual switches. Replace the commit placeholder:

```bash
ansible-playbook -i /Users/jason/dev/seadogger-homelab-pro/core/ansible/hosts.ini /Users/jason/dev/seadogger-homelab-pro/core/ansible/nextcloud_postgresql.yml -e nextcloud_postgresql_apply=true -e nextcloud_postgresql_revision=REVIEWED_CORE_COMMIT
```

Inspect the new PVC, database logs, rollout, resource use, empty target and backup rules. The CronJob remains suspended. Do not connect Nextcloud yet. A partially initialized PVC/target is retained for inspection, never automatically wiped or reinitialized.

## Prepare the private run

Use one new absolute state directory on durable private workstation storage; mode 0700. Keep it outside Git. It contains deployment/configuration references, manifests, potentially sensitive error output and operation flags. Do not paste its contents into issues.

Create `webdav-credentials.json` inside it with mode 0600, containing JSON keys `username` and `password`. Use an existing account's protected app password with permission to create the four validation files. Enter it through a local password manager/editor, not shell history. `prepare` requires this file; the authenticated validation proves its actual access later.

If a previous conversion identified omitted empty tables, review their complete
SQLite table/index definitions before another attempt. To preserve those schemas,
place a private `reviewed-empty-tables.json` list in the new run directory before
`prepare`. Each entry contains `name` and `schema_sha256`: SHA-256 of all
`sqlite_master.sql` values for that table, ordered by `type,name`, joined with a
newline (null SQL becomes an empty string). An absent file means an empty list.
The read-only `reviewed-empty-tables.php REVIEW.json SOURCE.db` command checks
the review against a SQLite database. Triggers, changed definitions and nonempty
tables are refused. Keep actual names, fingerprints and review evidence private.

Preparation captures this list in the run state. The converter verifies it before
and after native schema creation, requires the exact omitted-table set, then
creates those empty schemas through the pinned application's Doctrine library.
It preserves columns, indexes and defaults; SQLite BINARY collation maps to
PostgreSQL C on character columns and is removed from noncharacter columns.
Other explicit collations stop conversion. Review generated PostgreSQL DDL and
validate it transactionally before the window. The ordinary table-count and
sequence checks still apply to every preserved table; no omission prompt is
accepted and no source table is removed.

Native schema migrations can also change application configuration and invalidate
mount caches on the live SQLite connection. The wrapper therefore uses the
verified checkpoint as the source for the upstream data-copy implementation.
It opens SQLite with immutable/read-only flags, checks integrity and the saved
digest, requires matching source/target column sets, and rechecks the digest
after copying. Historical migration records absent from current migration files
are inserted only when missing from the generated target history; retired
migrations are not executed. Strict table/reference/sequence validation remains
required. A mismatch still stops conversion and retains the target.

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

If an inventory receipt is invalid JSON, inspect Job logs and node container-log
rotation before assuming an S3 mismatch. Listings request only `Key` and `Size`
as a compact JSON string to keep receipts small, including container-log
per-line overhead, with AWS CLI JSON pagination enabled. The collector decodes
the string and then the inventory array. A truncated receipt
cannot satisfy verification: retain it and stop; never compare only the remaining
objects or suppress the parse failure. If even the compact receipt exceeds the
node log capacity, arrange durable receipt collection before a new attempt.

If the maintenance pod stays in `ContainerCreating`, inspect its events and the
node's kubelet logs before retrying the fence. A PVC declared under two volume
names can leave kubelet waiting for an unmounted alias even when the CephFS
mount exists. The maintenance pod must reuse the original PVC volume name for
its `/source` mount, without a `subPath`; keep the original application mounts
and their subpaths intact. Do not add a second volume for the same claim or
introduce `fsGroup` traversal as a workaround.

For an interrupted fence, preserve the original pod definition and private
state. Verify the normal writer barrier and whether the temporary container
ever started before considering replacement of only that temporary pod. After
an authorized repair, independently verify readiness, the barrier and the
empty-target transactional write check before recording maintenance readiness
and continuing to checkpoint. Do not clear phase flags or rerun the entire
fence blindly; no PVC or application-data deletion is needed for this repair.

Before normal reopening, a failure in refresh/conversion/validation/canary/backup/reopening preparation attempts the accepted safe SQLite rollback. The rollback first proves the barrier still holds, checks the checkpoint, accounts for canary artifacts, and verifies there are no PHP/Apache/cron processes. It preserves the current SQLite/WAL/SHM and complete configuration under `preserved-before-rollback`, installs the validated checkpoint/configuration pair and restores matching deployment settings. Failed PostgreSQL contents are retained. An uncertain canary write, unexpected file, running process, failed checkpoint check or uncertain barrier stops rollback and leaves access paused for investigation.

After `reopening_started` is persisted, **never automatically restore SQLite**. A failed check disables Argo automation, suspends the mirror and scales normal writers to zero while retaining PostgreSQL and current files. The same boundary applies to `rollback_reopening_started`: after reopening SQLite, preserve its current state and never install the earlier checkpoint again. Once access might have resumed, an earlier database copy is stale. Investigate and repair/recover forward with a separately reviewed procedure.

Failures during `fence` or `checkpoint` may leave maintenance enabled or reconciliation suspended. Those phases intentionally refuse blind retries. Preserve their state, inspect active operations/processes and checkpoint completeness, then prepare a concrete recovery action from the captured original settings. Do not delete flags to trick the runner into continuing. If the maintenance pod was already stopped during reopening preparation, automatic rollback cannot establish its checks; keep normal replicas zero and recreate/review the maintenance barrier before any manual recovery.

A finished or rolled-back run cannot be repeated. Keep its directory and marker. A new migration attempt requires inspecting the retained target, marker and recovery artifacts first; never automatically clear the target. Normal Nextcloud deployment refuses paused reconciliation, including a migration in progress or a post-reopening failure. Do not restore automation merely to bypass this guard.

For an authorized new attempt after completed SQLite rollback, first verify the
live SQLite selection, restored schedules and original marker against the old
run. Retain the partial PostgreSQL database under a separately reviewed name and
create a fresh empty target with the original owner and database settings; never
drop or truncate the partial target. Archive the inactive deployment marker with
the completed private run only after checking that it matches live settings.
Keep external deployment automation held while the new run has no marker. Use a
new state directory, repeat writer/health checks and take a new checkpoint.
Never clear old phase flags or install the earlier checkpoint over resumed writes.

For a later pre-change dump, an operator can create a uniquely named Job from `nextcloud-db-backup`, wait for completion, and verify its three S3 artifacts and Pod UID. Do this before the authorized change. Do not equate a CronJob definition or an old successful Job with a fresh backup.

## Private configuration on a new workstation

Back up the protected `ansible/config.yml`, `ansible/hosts.ini`, `ansible/nextcloud-database.local.json` and complete private run directory together through the operator's existing secure storage. The marker is required after **either** successful PostgreSQL reopening or SQLite rollback reopening. It retains the captured image, database selection and reviewed overlay revision; none of these files belong in Git or issue attachments.

On a new checkout, recover these exact files from that secure copy into the same relative locations, set the marker and credential files to mode 0600, and retain the private run directory at mode 0700. Review the finished run (`schedules_restored` or `rolled_back`) and the current read-only ArgoCD Application before any deployment. The Ansible guard compares the restored selection and Helm values to the live Application before writing it. Do not manufacture an empty marker, clear its run ID or set an active flag to bypass a mismatch. If the marker or completed evidence cannot be recovered, stop and reconstruct the selection through a separately reviewed recovery action; an unverified checkout is not allowed to redeploy.

Recover original database passwords from protected configuration/secret backup. Reruns compare both credentials with the existing Secret and refuse implicit rotation. If retained database storage exists but its Secret is missing, staging stops before creating replacement credentials. Restore the original Secret through a reviewed recovery action; do not initialize another password against the retained volume. Existing database Application Kustomize patches, including nightly backup activation, survive ordinary staging reruns.

## Spec coverage and execution evidence

The following maps the approved migration requirements to preparation and later acceptance. Local simulations exercise the real CLI/Ansible entry points at the Kubernetes/AWS boundary; they do not establish live service or S3 behavior.

| Spec stories / requirement | Implemented behavior and local evidence | Remaining runtime acceptance |
| --- | --- | --- |
| 1–8: maintained ARM64 PostgreSQL, dedicated persistence, resources, credentials, separate staging | Official digest pins; retained expandable 10Gi explicit Ceph PVC; bounded workloads; separate non-admin role; shared Ansible → ArgoCD → Kustomize tasks. Entry-point tests cover stage/manual switches, staging equivalence, check mode, credentials and retained storage. | Ticket 27: current capacity, target startup and transactional writes, Secret readability, role permissions. |
| 9–12: preserve application/files and maintain independent writer barrier | Captured 32.0.6 digest; maintenance pod; repeated replicas/pods/endpoints/controller checks. CLI fault tests refuse an open barrier. Ansible refuses paused reconciliation. | Ticket 22: approved window, fresh external/host writer inventory, actual barrier and image verification. |
| 13–16: complete checkpoint and accepted S3 comparison | Real temporary SQLite WAL backup/integrity/preservation tests; full config tar and completion evidence; separate S3 checkpoint; upload-only refresh. CLI tests cover every simulated key, missing/sized/remote-only objects and pagination/deletion arguments. | Tickets 27/22: exact destination rights and real complete uploads/metadata comparison. No checksum or restore claim. |
| 17–18: omissions and partial targets | Pinned converter refuses every question; CLI tests simulate its nonzero omission result, retain private transcript, and refuse nonempty/retried targets without clearing them. | Ticket 22: actual pinned Nextcloud command and table inventory; local simulation does not run the upstream converter. |
| 19–20: data/reference/database consistency | Table/migration/sequence checks, canonical reference fingerprints and enabled-app comparison; real collation-independence test. | Ticket 22: actual PostgreSQL comparisons and users/shares/files behavior. |
| 21–23: private HTTP and bounded concurrent canaries | Loopback-only Apache/port-forward, four tiny parallel uploads/readbacks, recognized-artifact cleanup and uncertain-write refusal. Existing cleanup-limit tests retained. | Ticket 22: authenticated live HTTP, socket exposure, concurrent uploads and cleanup. |
| 24–26: initial/nightly/pre-change native backups and alerts | Custom dump/full archive parse, unique S3 artifacts, suspended 03:15 schedule, failed/stale rules; render checks and rerun preservation of activation. | Tickets 22/28: real initial/nightly receipt, loaded rule evaluation and receiver verification. |
| 27–28: recovery boundaries | Real SQLite preservation tests plus CLI faults before reopening, after either reopening, and failure while automatic rollback reopens SQLite. Verify one restore at most, then pause without touching the current database. | Ticket 22: actual controlled phase outcomes; no isolated recovery environment. |
| 29–30: repeat deployment and public/private evidence | Ansible tests cover active PostgreSQL and rollback SQLite image preservation, missing/stale marker refusal, deploy ordering and shared staging. Recovery instructions above; private logs retained. | Tickets 27/28: secure configuration custody and operational handoff. |
| 31–32: preserve FPA, lifecycle and legacy artifacts | No FPA or bucket-policy changes; upload commands omit deletion; legacy prune protection and retained target/checkpoints. | Tickets 22/28: confirm preserved resources. Retirement and retention remain separate decisions. |

Integration gaps corrected in ticket 26: PostgreSQL was absent from the normal Ansible flow; a missing marker could remove migrated settings; reruns could undo paused reconciliation; a missing Secret could install replacement credentials over retained database storage; and validation incorrectly rejected the `host:5432` saved by the pinned upstream converter. All now stop or behave as described above. No production action is required to establish this preparation evidence.

## Validation evidence and remaining runtime checks

Local preparation validation on 2026-10-08:

- PHP syntax, Python compilation and 33 local integration/failure tests pass. These include a real WAL checkpoint, corrupt-checkpoint rejection, preserved rollback state, traversal failures, writer-barrier failures, partial-target refusal, canary cleanup limits and pre/post-reopening failure dispatch.
- Helm 3.19.0 renders the actual Nextcloud chart 8.9.1 with replicas zero, external PostgreSQL Secret references, immutable image, and no bundled PostgreSQL/wait container.
- Kustomize renders seven namespaced resources, a suspended CronJob and explicit retained PVC. Repository YAML lint and Ansible syntax checks pass for the main, staging and phase entry points.
- Independent standards/spec review found and corrected bundled-chart precedence, empty Argo automation configuration, lost failure transcripts, image pinning and insufficient post-start health verification.

These are preparation checks. At that point, the homelab AWS MCP confirmed the backup identity, but its IAM policy-listing requests returned AccessDenied. The later staging evidence below establishes the native-dump upload path; it does not establish checkpoint-prefix writes or migration success. The FPA connection was unchanged.

No production migration or restore was executed to produce the local evidence. Database conversion, private application validation, concurrent uploads and production-database backups remain cutover acceptance.

Run the complete reproducible checks without cluster or AWS access (see [prerequisites and offline use](27-Deployment-and-Validation#local-and-ci-validation)):

```bash
python3 /Users/jason/dev/seadogger-homelab-pro/core/useful_scripts/nextcloud-migration/check.py
```

## Staging evidence: 2026-10-09 UTC

The operator authorized database-only staging and its persistence/backup checks for Pro ticket 27. The dedicated Ansible entry point deployed Core revision `3678b682e3b62c683858b81fa52e6c42d9325649` through the separate `nextcloud-db` ArgoCD Application. Nextcloud remains on SQLite, online, at version 32.0.6; the database conversion has not run.

| Check | Observed result |
| --- | --- |
| Preconditions | Four Ready nodes, no node memory/disk/PID pressure, Ceph `HEALTH_OK`, about 4 TiB raw free. Rey had about 1.8 GiB measured memory headroom and 69% reserved before adding the 512Mi database request and transient 128Mi backup request. The API initially returned 503 during a K3s restart, then passed readiness checks without intervention. Recheck health before any later phase. |
| Placement and storage | Official PostgreSQL 17.11 ran on ARM64 worker rey with the pinned image, declared probes/resources and a new Bound 10Gi RWO `ceph-block-data` PVC. The class is expandable with `Retain`; the original Nextcloud PVC and legacy database remain in place. |
| Identity and permissions | UID/GID 999 could read the mounted database Secret. TCP authentication used SCRAM. The application role owns its dedicated database and has no superuser, createdb, createrole, replication or bypass-RLS attributes. A create/insert/read transaction succeeded and rolled back, leaving zero public tables. |
| Persistence | One authorized replacement of only `nextcloud-db-0` changed the Pod UID while retaining the PostgreSQL system identifier, PVC/PV identity and database roles. Authenticated transaction checks passed again. |
| Repeat deployment | The same Ansible staging entry point succeeded again, preserving the Secret UID/resourceVersion, PVC, database identity, revision and suspended backup state. Ansible reported the Application task changed; this is evidence of preserved settings, not a claim of a zero-change playbook recap. |
| Native backup | The manually created `nextcloud-db-backup-stage-20261009` Job completed in 15 seconds. Both dump and upload containers ran as UID/GID 999, exited zero and had no restarts. Full archive decoding succeeded before upload. |
| S3 receipt | Listing and individual object HEAD checks found `nextcloud.dump` (1,098 bytes), `SHA256SUMS` (81 bytes) and `metadata.txt` (221 bytes) in the unique attempt directory whose suffix matches the backup Pod UID. All three reported AES256 server-side encryption. Private evidence retains the exact keys and version IDs. |
| Monitoring | Both database-backup rules were loaded, health `ok`, and evaluated successfully. The staging Job's succeeded metric was 1 and failed metric 0; CronJob suspension was 1. No external notification receiver was configured, so delivery is unconfigured and untested. |
| Resource observations | Initial Pod creation to Ready took about 57 seconds; sampled database working set peaked near 51 MiB. The empty-target dump container ran about two seconds and upload about one second. The short Job yielded no Prometheus memory sample; these measurements do not size the future production dump. |
| Application validation | After correcting the protected local app-password file, an authenticated depth-0 WebDAV read returned HTTP 207 through the normal CA-verified HTTPS route. This confirms validation-account access without listing files or reading file contents. The earlier credentials returned HTTP 401; no account password was reset. Ticket 27's authenticated-read requirement is satisfied. |

The dump is **pre-cutover evidence from an empty target**, not a backup of the production Nextcloud database. Object sizes and archive decoding do not prove a restore. The nightly 03:15 America/New_York database schedule remains suspended. The existing native-file mirror remains unsuspended; no bucket lifecycle, IAM policy or FPA configuration changed. Policy/encryption-configuration introspection remained denied, while the actual workload upload and object HEAD requests succeeded.

At the final authenticated-access check, both Nextcloud Applications remained Healthy/Synced, but Ceph reported `HEALTH_WARN MON_DISK_LOW`: monitor `e` on anakin had 25% space available. This differs from the healthy staging preflight. No disk cleanup or recovery action was performed. Investigate the monitor's backing filesystem and re-establish the cutover health prerequisites before ticket 22; successful staging is not authorization to begin conversion.

The current Kubernetes inventory identifies the normal Nextcloud Deployment as a source-volume writer, the file mirror as a read-only source mount, and Jellyfin's alias of the same CephFS volume as read-only. No active mirror or Velero Backup was observed. The new database mounts only its dedicated PVC. Preserve the staging Job/artifacts, legacy workload and all original data. Before the cutover window, repeat this inventory and inspect host timers, administrative imports, external clients and backup operations; this staging snapshot does not establish the writer barrier.

For an authorized persistence check, record the original Pod UID, database system identifier, Secret identity and PVC/PV identity first. After requesting one Pod replacement, wait for a **different UID** to become Ready and compare database/storage identity. Ansible's name-based `state: absent, wait: true` waiter timed out after the StatefulSet had already recreated the same Pod name; do not repeat the deletion in response to that timeout. The replacement's UID and successful database checks established the outcome.

For the manual staging backup, derive a uniquely named Job from the deployed `nextcloud-db-backup` CronJob using client-side rendering, then submit that definition through Ansible's `kubernetes.core.k8s` task. This preserves the suspended schedule and the deployed image, identity, resource and credential settings. Inspect both container exit codes and the dump log, then match the three nonempty S3 objects to the backup Pod UID. Retain the receipts privately and identify their pre-cutover purpose.

Primary references: [Nextcloud conversion and omitted tables](https://docs.nextcloud.com/server/32/admin_manual/configuration_database/db_conversion.html), [pinned converter source](https://github.com/nextcloud/server/blob/v32.0.6/core/Command/Db/ConvertType.php), [PostgreSQL dump](https://www.postgresql.org/docs/17/app-pgdump.html), [archive parsing versus restore](https://www.postgresql.org/docs/17/app-pgrestore.html), [Docker Official PostgreSQL image](https://github.com/docker-library/postgres), [supported AWS CLI container interface](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-docker.html), [Argo automated sync](https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/), [Argo resource prune protection](https://argo-cd.readthedocs.io/en/stable/user-guide/sync-options/#no-prune-resources).
