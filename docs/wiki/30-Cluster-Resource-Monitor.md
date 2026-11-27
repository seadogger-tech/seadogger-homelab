# Cluster Resource Monitor

The cluster resource monitor records node and container measurements before
daily cleanup, preserves short lived containers in history, and reports gaps
that prevent a clean measurement window. Pro owns the host collector and the
resource-monitor application; node-sensors exposes their host textfile metrics
through node-exporter.

## Host housekeeping

Pro Ansible installs the host collector only when the runner is invoked with
`enable_node_housekeeping=true`. The flag defaults to `false`; with it off, the
playbook neither installs nor removes host files.

Each of the four cluster nodes runs `/usr/local/libexec/node-housekeeping` as
root through two systemd timers:

| Timer | Schedule | Work |
|---|---|---|
| `node-housekeeping-sample.timer` | Every 60 seconds (`OnUnitActiveSec=60s`) | Sample each Kubernetes container cgroup and atomically publish container high-water metrics. |
| `node-housekeeping-daily.timer` | 04:15 America/New_York, persistent across downtime | Snapshot exited containers, images and `/` usage, then clean up eligible exited containers and unused images. |

The 04:15 run records the pre-cleanup counts and root filesystem usage first.
It then re-checks each candidate with `crictl inspect` and removes it only if
its state is still exited. It runs `crictl rmi --prune` afterwards. Running or
paused containers are never removed, and kubelet garbage-collection settings
are not changed. Freed bytes are the positive reduction in root filesystem
usage across the cleanup.

The sampler uses each container ID as its lifetime key. Working-set use is
`memory.current - inactive_file`; anon use is read from `memory.stat`. The
working-set and anon high-water values never decrease during that container
lifetime. A restart has a new ID and starts a new high-water record. The
collector caches namespace, pod, pod UID and container identity from
`crictl inspect` labels.

When a cgroup disappears, the last sample that saw it becomes its end
timestamp. The collector retains its identity, high-water values, cgroup
`memory.peak` and `oom_kill` count with `state="ended"` for 14 days. This keeps
short-lived backup Jobs available to the next scrape and lets the monitor join
them to the pod's requests, limits and workload record. A container that lives
and ends between two samples may not have a host record; the monitor reports
that as `peak_unmeasured`.

The sampler stores its previous sample time and cumulative gap counter on
disk. If two consecutive samples are more than 120 seconds apart, the full
interval is added to `node_housekeeping_sampler_gap_seconds_total`, including
intervals that span a reboot. A rise in this counter makes the monitor's
observation window unclean.

The script atomically replaces
`/var/lib/node-housekeeping/textfile/housekeeping.prom` using a temporary file
in the same directory and rename. Node-exporter v1.12.1 reads this host
directory through a read-only `Directory` hostPath mount at `/host-textfile`;
the sensor helper and its in-memory file are unchanged.

### Host metric contract

Per-container series carry `namespace`, `pod`, `pod_uid`, `container`,
`container_id` and `state` labels (`running` or `ended`). End timestamp is
exported for ended containers only.

| Series | Unit | Source and meaning |
|---|---|---|
| `node_housekeeping_exited_containers` | count | Daily count from `crictl ps -a --state exited -q`, before cleanup. |
| `node_housekeeping_images` | count | Daily count from `crictl images -q`, before cleanup. |
| `node_housekeeping_rootfs_used_bytes` | bytes | Used bytes on `/`, before cleanup. |
| `node_housekeeping_rootfs_size_bytes` | bytes | Total bytes on `/`, before cleanup. |
| `node_housekeeping_removed_containers` | count | Exited containers successfully removed after state re-check. |
| `node_housekeeping_removed_images` | count | Images absent after `crictl rmi --prune`. |
| `node_housekeeping_freed_bytes` | bytes | Positive decrease in `/` used bytes across cleanup. |
| `node_housekeeping_container_working_set_peak_bytes` | bytes | 60-second high-water of `memory.current - inactive_file`. |
| `node_housekeeping_container_anon_peak_bytes` | bytes | 60-second high-water of cgroup anon bytes. |
| `node_housekeeping_container_memory_peak_bytes` | bytes | Cgroup `memory.peak`, including page cache. |
| `node_housekeeping_container_oom_kills` | count | Cgroup `memory.events` `oom_kill` value. |
| `node_housekeeping_container_start_timestamp_seconds` | seconds | First sample for the container ID. |
| `node_housekeeping_container_end_timestamp_seconds` | seconds | Last sample that saw an ended container ID. |
| `node_housekeeping_sampler_gap_seconds_total` | seconds | Persistent sum of sampling intervals longer than 120 seconds. |
| `node_housekeeping_last_run_timestamp_seconds{run}` | seconds | Last successful sample or daily run timestamp. |

## Privilege and rollback

The collector runs as root on the host because it reads cgroup files and uses
the local CRI socket for inspection and cleanup. Neither node-sensors
container gains host privilege, capabilities, devices, a service-account token
or RBAC. Node-exporter receives only a read-only mount of the textfile output;
the housekeeping state and CRI socket are not mounted into the pod.

The exact host rollback is a runner run with:

```text
-e enable_node_housekeeping=true -e node_housekeeping_state=absent
```

The absent path stops and disables both timers and their services, removes the
four unit files, reloads systemd, and deletes the installed script,
`housekeeping.prom` and sampler state files. It keeps the empty
`/var/lib/node-housekeeping/state` and
`/var/lib/node-housekeeping/textfile` directories so node-sensors' `Directory`
hostPath remains valid until the DaemonSet mount is reverted. Setting the
enable flag to false is not a rollback.

## Architecture

```mermaid
flowchart LR
  subgraph node["Each node (x4): host, root"]
    TS["node-housekeeping<br/>sample 60s + daily 04:15 ET<br/>NEW"]
    CG["cgroup v2 + crictl"]
    TF["/var/lib/node-housekeeping/textfile<br/>NEW"]
    TS -->|read| CG
    TS -->|rm exited, rmi prune| CG
    TS -->|atomic .prom| TF
  end
  subgraph ns1["node-sensors (DaemonSet)"]
    NE["node-exporter<br/>CHANGED: +1 ro hostPath"]
  end
  TF -->|ro mount| NE
  subgraph ns2["resource-monitor ns (scrape=allowed)"]
    MON["resource-monitor Deployment<br/>recorder (watch) + evaluator 04:45 ET<br/>NEW"]
    PVC["history PVC<br/>journal, history, outbox<br/>NEW"]
  end
  NE -->|:9100| MON
  API["Kubernetes API<br/>read-only: list + watch"] --> MON
  MON <--> PVC
  MON -->|HMAC webhook| PC["Paperclip routine<br/>to Spock NEW"]
  subgraph ans["Ansible (runner-allowed)"]
    FL["helm-upgrade-only flags<br/>Rook, MetalLB, ArgoCD NEW"]
    LR["cluster-defaults Argo app<br/>CHANGED"]
  end
  style TS fill:#2d5016,color:#fff
  style TF fill:#2d5016,color:#fff
  style MON fill:#2d5016,color:#fff
  style PVC fill:#2d5016,color:#fff
  style PC fill:#2d5016,color:#fff
  style FL fill:#2d5016,color:#fff
  style NE fill:#1e3a5f,color:#fff
  style LR fill:#1e3a5f,color:#fff
  style CG fill:#8b4513,color:#fff
  style API fill:#8b4513,color:#fff
```

## The monitor

The monitor is the Pro application `resource-monitor`: one Deployment (one
replica, `Recreate`) in the `resource-monitor` namespace, labelled
`node-sensors-scrape=allowed`. It is a Deployment rather than a CronJob because
the evidence of a deleted Pod or an expired Event only exists while it happens.
One Python script (standard library only, from a ConfigMap) runs two parts that
share the history volume under one `flock`. Its history lives on a 1 Gi PVC at
`/history` (`ceph-block-data`, the cluster's default RBD class), which the
Velero daily schedule includes.

It is applied by the Pro Ansible task `resource_monitor_deploy.yml`, gated by
`enable_resource_monitor` (default `false`). Merging the manifests deploys
nothing by itself.

### The monitor's own access

Stated from `deployments/resource-monitor/` in the Pro repo.

- **Cluster RBAC.** The ClusterRole `resource-monitor` (`rbac.yaml`) is
  cluster-wide and read-only. It allows `get`, `list` and `watch` on `nodes`,
  `pods`, `events`, `apps/replicasets` and `batch/jobs`, and `get` and `list` on
  `metrics.k8s.io` `pods` and `nodes` (the portal API's working sets). It has no
  write verb, no Secret access and no exec. It is bound to the service account
  `resource-monitor:resource-monitor`.
- **Exporter discovery.** The Role `resource-monitor-endpointslice-reader`
  allows `get` and `list` on `discovery.k8s.io/endpointslices` in the
  `node-sensors` namespace only.
- **Network.** `networkpolicy.yaml` allows one ingress rule: the portal's pods
  (`app=portal` in `portal`) on TCP 8090, for the [Portal API](#portal-api).
  Egress goes only to
  node-sensors pods on 9100, the Kubernetes API server, `paperclip` pods on 3100
  and kube-dns on 53 (UDP and TCP).
- **The API-server rule is pinned to addresses.** It allows `10.43.0.1/32` (the
  Service, port 443) and `192.168.1.95/32` (yoda, port 6443). If the control
  plane moves, or the CNI changes whether it matches before or after the
  Service's address translation, the monitor loses the API with no policy error.
  The visible symptom is a stopped heartbeat and a failing liveness probe. The
  rule to update is the "Kubernetes API server" `ipBlock` entry in
  `networkpolicy.yaml`.

### The recorder and its gaps

The recorder watches Pods and Events in all namespaces with bookmarks and
appends to `/history/journal/YYYY-MM-DD.jsonl` (UTC day), flushing and fsyncing
each batch. It journals only a fixed field list, never a whole object:

- the first sight of each Pod UID: namespace, name, node, owner workload
  (ReplicaSet resolved to its Deployment, Job to its CronJob), QoS class, and
  every container's requests and limits, init containers included;
- every container termination: reason (`OOMKilled` included), exit code,
  started and finished times, restart count;
- Pod evictions and Pod deletions;
- Events with reason `Evicted`, `OOMKilling`, `SystemOOM` or `Preempting`, and
  their counts.

Environment, arguments, annotations and Event or termination messages are never
journaled and never appear in a report.

Every 60 seconds it writes `journal/cursor.json` atomically: each stream's last
`resourceVersion` and a heartbeat (the older of the two streams' last sign of
life). A stream's version moves only after the records up to it are fsynced to
the journal, and one lock guards every cursor change and the heartbeat's
snapshot, so a heartbeat during an evaluation can never save a version whose
records are still unwritten. If an append fails, the cursor stays and the watch
retries from the old version, and the record is journaled once. After a dropped
watch or a restart it resumes from the cursor. If the API
answers `410 Gone` it relists and journals a **gap** from the last heartbeat to
the relist. The first start opens coverage and journals a `start` record;
nothing earlier counts as observed. The liveness probe fails when the heartbeat
is more than 3 minutes old, so a stuck watch restarts the pod and its gap is
recorded.

### The evaluator

The evaluator runs at 04:45 America/New_York. If the pod was down then, it runs
at start-up as soon as today's history file is missing and it is past 04:45.
`python3 /app/monitor.py evaluate --now [--test-finding]` runs the same
evaluation by hand under the same lock. If today's history file is already
committed, a hand run with `--test-finding` is filed as a *manual* evaluation
under `/history/manual/`; it does not move the day-over-day baseline.

It scrapes `:9100/metrics` on every node-sensors endpoint (found through the
EndpointSlice), lists Nodes (allocatable) and current Pods, reads the journal
since the last evaluation, merges the host's ended containers by container ID
on first sight and joins them by Pod UID and container name to the journal's
requests, limits, QoS and owner. A Pod that is in neither the journal slice nor
the API (it ran yesterday and was deleted today) joins the last recorded
metadata instead: the newest retained history row for that Pod UID and
container, which carries its requests, limits, owner, QoS and node. The pinned image resolves `America/New_York`
through `zoneinfo`; a test asserts it.

### Findings

Each finding has the ID `<type>/<node>/<namespace>/<workload>/<pod>/<container>`
with `-` for any part that does not apply. Two containers breaching the same
metric on one node therefore are two rows.

| Type | Fires when |
|---|---|
| `exited_up`, `disk_up` | A node's exited-container count or root-disk use rose since yesterday, before cleanup. |
| `ratio_over_threshold` | A live container's limit/request is above 1.5, or it has no limit. |
| `peak_over_request` | The working-set high-water mark is above the request. Ended containers are checked once, when first merged. |
| `peak_unmeasured` | The journal shows a container that ran, but no host record overlaps its run (it lived under one sample interval). |
| `besteffort` | A live Pod has QoS BestEffort. |
| `node_overcommitted` | The sum of Pod memory limits on a node is above its allocatable memory. |
| `evicted`, `oom_killed` | From the journal (Pod status, terminations, Events) and from the host's `oom_kill` counts, ended containers included. One incident seen by several sources is one finding that lists every source (`journal`, `host`, `event`, `api`). An eviction is counted once, in the evaluation that first sees it: the finding carries the Pod UID, and a Pod that stays visible as Evicted in the API raises no new finding once an earlier history file has one for that UID, so it leaves the 7-day window with its first day. |
| `collector_stale` | A node has no scrape, its `daily` timestamp is missing or over 26 h old, or its `sample` timestamp is over 10 min old. |
| `observation_gap` | A journal gap, a rise in `node_housekeeping_sampler_gap_seconds_total`, a stale collector, or a missed evaluation day. |
| `delivery_backlog` | A report part has been pending for more than 24 h. |
| `test_finding` | Added only by `--test-finding`. |

A container that restarts gets a new container ID and a fresh peak, so a lower
peak under a new ID is reported as a restart, never as a drop. Day-over-day
change is shown only between the same container ID on consecutive days.

### Window status

Every history file records the trailing 7 days: eviction count, OOM count and
the list of observation gaps (a missing day inside the window counts as a gap).
`clean` is true only when all three are empty. A gap makes `clean` false even
with zero evictions and zero OOM kills, because nothing can be concluded about
an interval nobody watched. `days_with_history` says how much of the window
exists at all.

### Proposal rule

`ratio_over_threshold` and `peak_over_request` findings carry the 1.25x values:
request = the working-set high-water mark rounded up to the next 16 Mi, limit =
1.25 x request. A 1000 Mi high-water mark proposes request 1008Mi and limit
1260Mi. Each also names where the value lives (an ArgoCD values file, a
manifest or an Ansible task), from the static map in the
`resource-monitor-values` ConfigMap. The monitor never edits a live object;
Spock turns a proposal into a Build ticket or small task.

### History and retention

`/history/YYYY-MM-DD.json` holds, per node and per container (running, ended
and init), every metric in the host contract plus requests, limits, allocatable,
limit/request ratio, QoS and owner workload, the journal's terminations,
evictions, Events and gaps, the findings, the window status, `evaluated_through`
and the rendered report parts. Journal files, history files and delivered
report parts are kept 400 days. The history file's rename is the evaluation's
only commit (see below).

### The aggregate report and its finding IDs

An evaluation with at least one finding produces one report, keyed
`[resource-monitor/<YYYY-MM-DD>]`, that lists every finding with its ID,
numbers, day-over-day change, proposal and whether it is new since yesterday.
A report over 32 KiB is split into parts (`[resource-monitor/<date> 2/3]`);
every finding appears in exactly one part. Paperclip's webhook body limit is
10 MB, so 32 KiB is the smaller bound and is the split size.

The payload is JSON: `{"date", "key", "part", "parts", "report"}`. The routine
that receives it must declare one text variable named `report` and put
`{{report}}` in its description, because Paperclip copies top-level payload
fields into routine variables and shows them in the run issue (an
`hmac_sha256` trigger does not append the raw payload to the issue). The key
leads the report text.

### Commit, outbox and duplicates

```text
journal (fsynced) + host samples + API  ->  evaluate  ->  render parts in memory
   ->  write /history/<date>.json with the parts embedded
       (temp file, fsync, rename, fsync of /history)   <- the COMMIT
   ->  reconcile: embedded parts in neither outbox/pending nor outbox/delivered
       are written to outbox/pending from the saved bytes
   ->  deliver every pending part, oldest first, byte for byte
       2xx: rename into outbox/delivered      otherwise: stays pending
```

- **Crash before the commit:** no history file exists. Start-up catch-up
  re-evaluates from the previous file's `evaluated_through`. Its inputs are
  durable (the fsynced journal and the host's 14-day ended-container records),
  so an incident that has since resolved is found again. Stray temp files are
  deleted at start-up.
- **Crash after the commit:** the evaluation is never recomputed. Reconcile
  rebuilds any part missing from the outbox from the saved bytes, never from
  current conditions. It runs at start-up, right after each commit and before
  every delivery pass, and never rewrites a part already in either directory.
- A part moves absent, then `pending`, then `delivered`, only by atomic rename.
- Each delivery tries 3 times with backoff on a timeout or non-2xx. Only a 2xx
  acknowledges it. The recorder process retries pending parts every hour. A
  resent part is the same bytes, so a condition that resolved overnight cannot
  erase it.
- After an ambiguous timeout the same part may arrive twice (each attempt has a
  fresh timestamp, so Paperclip's replay guard does not drop it). Duplicates are
  accepted: close all but one run issue.

The request is `POST` to the trigger's `.../fire` URL with `Host: localhost`,
`X-Paperclip-Timestamp` (epoch seconds) and `X-Paperclip-Signature`, the hex
HMAC-SHA256 of `"<timestamp>." + <raw body>` under the trigger's secret. That is
exactly what Paperclip's routine webhook verifies, inside a 300 second replay
window.

### Webhook Secret: provisioning and rotation

The Secret `resource-monitor-webhook` (keys `url`, `secret`) is mounted
read-only as a volume without `subPath`, so a rotation reaches the pod. It is
not in Git. `resource_monitor_deploy.yml` creates it with both keys empty only
if it is absent and never overwrites an existing one. The monitor re-reads both
files before each delivery pass. With a key empty it logs `webhook not
configured` and leaves its parts pending. At start-up and on any change it logs
`webhook config: url len=<n> secret len=<m>`: lengths, never values.

`resource-monitor-webhook-writer` is the only write path: a Role granting
`patch` on that one Secret by name, bound to `paperclip:default` (the account the
Paperclip pod runs as). The account cannot `get`, `list`, `watch`, `create` or
`delete`. It can still read this one Secret back: a Kubernetes PATCH response
returns the whole object, so an empty merge-patch `{}` returns `data.url` and
`data.secret`. Every agent process in the Paperclip pod holds that account. This
is an accepted trade-off: the read-back reaches only principals already inside
the Paperclip pod, and the value is Paperclip's own trigger secret.
`provision-webhook-secret.sh` deliberately sends the Kubernetes response to
`/dev/null`.

**Rule:** no `kubectl patch`, MCP patch or other PATCH that prints its response
may target `resource-monitor-webhook`, because that output contains the value.

`deployments/resource-monitor/provision-webhook-secret.sh` (POSIX `sh`, `curl`,
`jq`) is the only way the value is handled:

```text
provision-webhook-secret.sh create <routineId>    # adds the hmac_sha256 trigger, replayWindowSec 300
provision-webhook-secret.sh rotate <triggerId>    # rotates the secret
```

It refuses to run with `xtrace`, sets `umask 077`, writes Paperclip's response
only to a temp file that a trap removes, and pipes a `jq`-built merge patch from
that file straight into the Kubernetes PATCH. The value is never an argument, a
variable or output. It prints only HTTP statuses, the trigger ID, key paths on a
malformed response, and the URL and secret lengths. A non-2xx or a missing or
empty field exits 1 before anything is written.

**Verify with lengths only:** the script prints two 2xx statuses and
`url len=<n> secret len=<m>`; the monitor's `webhook config` line must show the
same lengths. Then run `python3 /app/monitor.py evaluate --now --test-finding`
once in the pod. The report reaching Spock and moving to `outbox/delivered`
proves the value end to end. Never read the Secret back: no `kubectl get
secret`, no Kubernetes MCP read.

**Rotate on any exposure.** If the value ever appears in a transcript, log,
comment, tool argument or any file other than the response temp file and the
Secret, run `rotate <triggerId>` at once (Paperclip invalidates the old value
immediately), then record on the ticket that it happened, without the value.

### Sequence

```mermaid
sequenceDiagram
  participant S as sampler (60s, host)
  participant D as daily timer 04:15 ET (host)
  participant N as node-sensors
  participant R as recorder (watch)
  participant E as evaluator 04:45 ET
  participant K as Kubernetes API
  participant H as history PVC
  participant P as Paperclip routine
  loop every 60 s
    S->>S: read cgroups, update working-set/anon high-water
    S->>S: cgroup gone: mark ended, keep 14 days; count gaps over 120 s
    S->>N: rewrite housekeeping.prom (atomic, running + ended)
  end
  K-->>R: watch Pods + Events (resume from cursor)
  R->>H: append journal (specs, terminations, evictions, Events), fsync
  R->>H: cursor + heartbeat every 60 s
  alt 410 Gone or restart without a valid cursor
    R->>K: relist
    R->>H: journal gap (stream, from heartbeat, to relist)
  end
  D->>D: snapshot exited, images, disk, peaks
  D->>D: crictl rm (re-checked exited), rmi --prune
  D->>N: housekeeping.prom (snapshot + removed + timestamp)
  E->>N: GET :9100/metrics (each node)
  E->>K: list nodes, pods
  E->>H: read yesterday, journal since last run, outbox
  E->>E: merge ended containers, join specs, compute findings, window status, proposals
  E->>E: render report parts (key + exact payload bytes)
  E->>H: COMMIT: write today's history file with parts embedded (temp, fsync, rename)
  Note over E,H: crash before commit: catch-up re-evaluates from previous evaluated_through.<br/>crash after commit: never recomputed, reconcile rebuilds parts from the file.
  E->>H: reconcile (also at start-up and hourly): each embedded part in neither pending nor delivered is written to outbox/pending from the saved bytes (temp, fsync, rename)
  loop each pending part, oldest first (also hourly from the recorder)
    E->>P: POST fire (HMAC, Host: localhost), up to 3 tries
    alt 2xx
      P-->>E: run issue for Spock
      E->>H: move part to outbox/delivered
    else timeout or non-2xx
      E->>H: part stays pending, resent unchanged next time
    end
  end
```

### Rollout and rollback

```mermaid
flowchart TD
  A["Kirk approves Map"] --> B["land Pro Map branch"]
  B --> C["runner: enable_node_housekeeping (all nodes)"]
  C --> D{"textfile present on 4 nodes,<br/>node-sensors Synced"}
  D -- no --> R1["runner: enable_node_housekeeping=true,<br/>node_housekeeping_state=absent<br/>(stops timers, removes units + script);<br/>map-gh revert node-sensors"]
  D -- yes --> E["runner: enable_resource_monitor,<br/>enable_cluster_defaults (diff empty);<br/>empty placeholder Secret + patch-only Role"]
  E --> F["create routine; provision-webhook-secret.sh create<br/>(value: response file → PATCH;<br/>prints statuses + lengths only)"]
  F --> G["monitor.py evaluate --now --test-finding;<br/>history file + test report delivered"]
  G -- fail --> R2["map-gh revert monitor; disable trigger"]
  G -- ok --> H["runner: Rook/MetalLB/ArgoCD flags,<br/>no-op upgrade, helm diff empty"]
  H --> I["measurement task: 7 gap-free days"]
  I --> J["file Stage B sizing request to Kirk"]
  J --> K["Stage B lands; 7-day evidence closes OCE-369"]
  style A fill:#1e3a5f,color:#fff
  style B fill:#1e3a5f,color:#fff
  style C fill:#2d5016,color:#fff
  style E fill:#2d5016,color:#fff
  style F fill:#2d5016,color:#fff
  style G fill:#2d5016,color:#fff
  style H fill:#2d5016,color:#fff
  style I fill:#7b1fa2,color:#fff
  style J fill:#7b1fa2,color:#fff
  style K fill:#7b1fa2,color:#fff
  style R1 fill:#8b4513,color:#fff
  style R2 fill:#8b4513,color:#fff
```

Roll the monitor back by reverting its Pro commit (Argo prunes the app) and
disabling the routine's trigger. The history PVC keeps its data until it is
deleted on purpose.

### Tests

`deployments/resource-monitor/tests/` in Pro runs in CI (`python3 -m unittest
discover -s deployments/resource-monitor/tests`): fixture metrics and API JSON
against a stub receiver for findings, proposal maths, delivery, crash recovery
(a test-only environment hook exits the process at a named point), the 410
resume, secret hygiene, the rendered manifests and the provisioning script.

## Portal API

Stage P of OCE-369 gives the portal its memory tabs without any cluster access of
its own. The portal's Caddy proxies two same-origin routes to a small read-only
HTTP server inside the resource monitor, and the portal pod gains no service
account token and no RBAC. The server is `serve` in `monitor.py`, standard
library only, in the recorder's process, on `0.0.0.0:8090`.

### Stage P block

```mermaid
flowchart LR
  subgraph portalns["portal namespace"]
    UI["portal.html<br/>Memory tabs: Active, Reserved, OOM drops<br/>NEW"]
    CADDY["Caddy<br/>/api/memory, /api/oom routes<br/>CHANGED"]
  end
  subgraph rmns["resource-monitor namespace"]
    API["monitor.py serve thread :8090<br/>memory.v1; oom.v1 incidents + coverage<br/>single-flight, 4 in flight, 9-day index<br/>NEW"]
    REC["recorder<br/>+ eviction cause, occurrence time<br/>CHANGED"]
    EVAL["evaluator, daily report<br/>(Stage A, unchanged)"]
    J[("journal + history PVC<br/>(Stage A)")]
    NP["NetworkPolicy<br/>ingress portal to 8090<br/>CHANGED"]
  end
  K8S["Kubernetes API<br/>pods, nodes, events"]
  MS["metrics-server<br/>metrics.k8s.io<br/>NEW read"]
  UI --> CADDY
  CADDY -->|GET| API
  API --> K8S
  API --> MS
  API -->|copy new bytes, short lock| J
  REC -->|append| J
  REC -->|watch pods, events| K8S
  EVAL -->|read| J
  style UI fill:#1e3a5f,color:#fff
  style CADDY fill:#1e3a5f,color:#fff
  style API fill:#1e3a5f,color:#fff
  style NP fill:#1e3a5f,color:#fff
  style REC fill:#1e3a5f,color:#fff
  style EVAL fill:#2d5016,color:#fff
  style J fill:#2d5016,color:#fff
  style K8S fill:#8b4513,color:#fff
  style MS fill:#7b1fa2,color:#fff
```


### Request flow

```mermaid
sequenceDiagram
  participant B as Browser (portal)
  participant C as Caddy (portal pod)
  participant M as resource-monitor :8090
  participant K as Kubernetes API
  participant X as metrics-server
  participant J as journal (PVC)
  B->>C: GET /api/memory (30 s poll, tab visible)
  C->>M: GET /api/memory
  alt 4 requests already in flight
    M-->>C: 503 Retry-After 5 (from the accept loop)
  else cache younger than 15 s, or another request is refreshing
    M-->>C: cached or shared memory.v1
  else this request refreshes (single-flight)
    M->>K: list nodes, list pods (paged)
    M->>X: list PodMetrics, NodeMetrics
    X-->>M: working sets (or error: metrics unavailable)
    M-->>C: memory.v1
  end
  C-->>B: JSON, no-store
  B->>C: GET /api/oom?days=7
  C->>M: GET /api/oom?days=7
  Note over M: cap, cache and single-flight as for /api/memory
  M->>J: take the history lock (non-blocking, up to 5 s)
  J-->>M: new bytes since each file's offset, 9 newest days only (at most 1 MiB per hold)
  Note over M,J: lock released, then parse outside it
  Note over M: incidents by key (term key, pod UID, Event UID)<br/>merge status + event evictions, match node OOM to terminations<br/>occurredAt, cause, UID metadata join, coverage and gaps
  M-->>C: oom.v1 (incidents, counts, coverage)
  C-->>B: JSON
  Note over B: complete window - No OOM drops in 7 days<br/>partial window - No OOM drops observed since observedFrom, badge marked partial
```


### Endpoints

Every response carries `Content-Type: application/json`, `Cache-Control:
no-store` and `X-Content-Type-Options: nosniff`, and the connection is closed
after it. Only `GET` and `HEAD` are answered (any other method is 405) and only
these paths (any other path is 404):

| Path | Answer |
|---|---|
| `GET /healthz` | 200 `"ok"`: liveness of the server only. The Deployment's liveness probe stays on the recorder's heartbeat. |
| `GET /api/memory` | `memory.v1` |
| `GET /api/oom?days=N` | `oom.v1` for the last N days. N is a single digit 1 to 7 (default 7); anything else is 400. |

A 503 (`Retry-After: 5`) means busy or unavailable: the request cap is reached,
a refresh failed, or a request waited more than 10 s for a refresh.

**`memory.v1`**: `{generatedAt, nodes:[{name, allocatableBytes, requestsBytes,
limitsBytes, workingSetBytes|null}], pods:[{namespace, pod, workload, node, qos,
containers:[{name, requestBytes|null, limitBytes|null, workingSetBytes|null}]}],
metrics:"ok"|"unavailable"}`.

- Node requests and limits sum the Running and Pending Pods bound to the node. A
  Pod counts as `max(sum of its app containers, its largest init container)`, the
  scheduler's rule. It is the code path of the evaluator's `limits_sum_bytes`
  (`pod_memory_bytes`), extended to requests; a request that is absent defaults to
  the limit. The per-Pod `containers` list holds the app containers only.
- Working sets come from the Metrics API (`metrics.k8s.io/v1beta1` NodeMetrics
  and PodMetrics). A working set is an estimate of memory in use, sampled about
  every 15 s. It is not the OOM threshold: a container can be OOM-killed while
  it shows below 100 % of its limit. When the Metrics API fails, `metrics` is
  `unavailable`, every working set is `null` and the rest is still served.
- `workload` is the Pod's top owner (ReplicaSet to Deployment, Job to CronJob).

**`oom.v1`**: `{generatedAt, window:{from, to}, coverage:{observedFrom|null,
gaps:[{stream, from, to}], complete}, counts:{h24:{confirmed, unknown, complete},
d7:{confirmed, unknown, complete}}, excluded:{otherCauseEvictions},
incidents:[{id, kind, cause, occurredAt, observedAt, timeSource, count, sources,
node, namespace, workload, pod, container, limitBytes}]}`.

It lists incidents, not journal rows, newest first by `occurredAt`. `counts` is
the same for every `days`; `window`, `coverage` and `incidents` follow `days`.

### What the recorder adds

New records only; nothing already journalled is rewritten.

- `evict` records gain `cause` (`memory`, `ephemeral-storage`, `pids` or `other`)
  and `at` (the `lastTransitionTime` of the Pod's `DisruptionTarget` condition, or
  null). The kubelet's node-pressure message "The node was low on resource:
  `<name>`." maps the three names to themselves. Anything else is `other`: a
  container over its ephemeral-storage limit, an admission rejection ("The node
  had condition: ...", where the Pod never ran) or an unrecognised message.
- `event` records with reason `Evicted` gain `cause`, classified the same way from
  the Event's message. Every `event` record gains `last`: `series.lastObservedTime`,
  then `lastTimestamp`, then `eventTime`, or null.
- The message text is never journalled or served; only the closed `cause` value
  is kept. Records written before Stage P have no `cause` and read as `unknown`.
- The evaluator, preload and the daily report ignore the new fields, so their
  findings do not change, and the previous code runs unchanged on journals that
  carry them (rollback needs no rewrite).

### Incident rules

- **OOMKilled**: one `term` record with reason `OOMKilled`, keyed by (Pod UID,
  container, `finished`). A repeat of the key is the same incident.
- **Evicted**: keyed by Pod UID, merging the pod-status record (source `status`)
  with `Evicted` Events whose involved-object UID matches (source `event`).
  Repeated updates of one Event stay one incident.
- **NodeOOM**: an `OOMKilling` or `SystemOOM` Event keyed by Event UID. Each
  record adds occurrences: its count minus the previous record's count, or its
  whole count for the first record. A count that drops restarts the series.
- **Correlation**: each NodeOOM occurrence is matched one-to-one, nearest first,
  to an unmatched `OOMKilled` incident on the same node whose `finished` is within
  180 s of it. A match adds source `event` to the termination and the occurrence
  is not counted again. A NodeOOM with no unmatched occurrence is dropped; one
  left over is still a memory drop (the kernel killed a process that was not a
  container's main process).
- **Times**: `occurredAt` is the termination's `finished` (OOMKilled); the Event's
  `last`, then the status `at` (Evicted); the latest occurrence's time (NodeOOM).
  The fallback is `observedAt`, the earliest journal `ts` of the incident's
  records, with `timeSource: "observed"` instead of `"reported"`. The window, the
  order and the counts all use `occurredAt`.
- **Cause**: `OOMKilled` and `NodeOOM` incidents are `memory`. For `Evicted` the
  status cause wins over the Event's, and with neither it is `unknown`. Only
  `memory` incidents are *confirmed*. `unknown` evictions are listed and counted
  as `unknown`. An eviction with another known cause is left out of the list and
  counted in `excluded.otherCauseEvictions`.
- **Metadata** (workload and the container's memory limit) joins by Pod UID: the
  newest journal `pod` record, then the live Pod (one Pod list per refresh, only
  when some incident needs it), then the evaluator's history rows. A field still
  missing is null, never guessed. For a Pod deleted before the indexed history
  files began and with no journal `pod` record in the index, the metadata is null.
- The count is a lower bound: a container that OOM-loops faster than the pod
  watch sees can lose terminations, because the status keeps only the last one.
  A journal that cannot be read is a 503, never an empty list.

### Coverage

`observedFrom` is the later of the two streams' latest `start` record. A `start`
is written only when a stream has no cursor, so the time before a later `start`
went unobserved and left no `gap` record. When a stream has no `start` in the
indexed files but an older journal file exists, that stream was observed since
before the index began, and `observedFrom` reports the start of the index's first
day (a lower bound, earlier than `window.from`). With neither, `observedFrom` is
null and nothing is complete. `gaps` lists the `gap` records that overlap the
window. `complete` is true only when `observedFrom` is at or before `window.from`
and no gap overlaps the window. Each count carries its own `complete` for its 24 h
or 7 d window. A UI must say "observed since" when a window is not complete,
never "none in 7 days".

### Load limits

The portal has no authentication, and the API shares a process, a cgroup and
the `/history` lock with the recorder, whose liveness depends on its watch
streams. No request may block a stream on the lock, grow memory without bound or
start unbounded work.

- **Single-flight refresh.** Each endpoint keeps one cached result and one
  refresh at a time. A request within 15 s of the last refresh gets the cache;
  otherwise the first request refreshes and the ones that arrive meanwhile wait up
  to 10 s for it and share its result. `oom.v1` is built once for 7 days; `days`
  only filters it. A failed refresh is cached for 15 s too.
- **Request cap.** At most 4 requests are in flight. The accept loop takes a slot
  before it starts a handler thread; with none free it answers 503
  (`Retry-After: 5`) and closes, so a flood never starts more than 4 handler
  threads. A connection has a 5 s socket timeout and a 5 s total deadline for its
  request line and headers, and is never kept alive.
- **Short lock hold.** The API keeps a byte offset per journal file. Under the
  history lock it only copies at most 1 MiB of new bytes, cut at the last newline,
  then releases the lock and parses outside it. It takes the lock without
  blocking, retrying every 100 ms for up to 5 s. When an evaluation holds the lock
  the refresh serves the last good result with its older `generatedAt` (the UI's
  stale banner shows), or 503 with none. `journal_append` is never delayed by more
  than one 1 MiB copy.
- **Bounded index.** Only the journal files dated from `window.from` minus one day
  through today are read (at most 9 of the 400 retained days), and only the
  records `oom.v1` uses are kept: OOMKilled terminations, `evict`, the three Event
  reasons, Pod records reduced to workload and container limits, `start` and
  `gap`. A file's records are dropped when it leaves the range. The history-row
  join reads only the regular history files in the same range, outside the lock,
  skipping a file pruned mid-read, and is rebuilt only when that set of files
  changes. Pods are listed a page (50) at a time.
- **Logging.** Fixed phrases and exception type names only. Requests, paths and
  queries are never logged, and nothing returned or logged carries tokens, Secret
  data, environment, the webhook URL, labels or annotations.

### Access and resources

- **RBAC.** The ClusterRole gains `metrics.k8s.io` `pods` and `nodes`, `get` and
  `list`, and nothing else.
- **Network.** `networkpolicy.yaml` has one ingress rule: pods `app=portal` in the
  `portal` namespace, TCP 8090. Egress is unchanged (the Metrics API goes through
  the API server entry). The Service `resource-monitor` (ClusterIP, 8090) selects
  the monitor pod.
- **Resources.** Set from a measurement, not carried over. `tests/measure_resources.py`
  runs `monitor.py run` against a stub cluster of 500 Pods and 750 containers
  (about three times this cluster; each Pod padded to a real object's 11 KiB), a
  400-day journal whose last 9 days run at three times this cluster's record
  rate, the API under a burst of about 20 requests a second across both
  endpoints, and a hand-run `monitor.py evaluate` in the same cgroup. Peak RSS:
  61 MiB for the recorder and scheduler alone, 80 MiB with the API under the
  burst, 167 MiB with the hand-run evaluation (two processes). Request 192Mi,
  limit 240Mi (peak plus about 15 %, limit 1.25 x request); it was 80Mi / 100Mi,
  measured on Pods of 0.5 KiB, which a hand-run evaluation passes with real-sized
  Pods. CPU: about 5m idle, 0.9 CPU-s for the cold index build, bursts to about
  425m for a second; request 100m, limit 125m, so the cold build finishes inside
  the 10 s wait and a burst is throttled rather than refused. The API itself
  adds about 18 MiB at the 3x rate and about 42 MiB at ten times it.

### Verification and rollback

After rollout, `/api/memory` returns four nodes whose Σ requests and limits match
the evaluator's figures within 1 Mi; `/api/oom` reports `coverage.observedFrom`
equal to the journal's first `start` with `complete: false` until 7 days after
it; a new `evict` record carries `cause`; a Pod outside `portal` cannot reach
`resource-monitor:8090`; twenty concurrent `GET /api/oom` requests each get 200
or 503, and the container's working set stays below its request. Rollback is a
revert of the Pro landing PR: records written meanwhile keep their extra fields,
and the previous recorder, preload and evaluator ignore them.

## Stage B0 immediate reductions

Stage B0 of OCE-369 cuts limits (and over-sized requests) in the charts the
Ansible runner applies, plus mealie, using memory peaks that already prove
the cut is safe. **No request goes up**, so no pod can go Pending and no
node's reservation rises. Stage B (after seven clean monitor days) does the
full 1.25× sizing. The Pro half (LimitRanges and Pro manifests) is a separate
Map ticket and lands after this one.

### Per-container table

`P` is the largest cgroup v2 `memory.peak` among the containers one chart key
sets: the larger of the OCE-550 snapshot and the live re-read of 2026-11-25
19:29:53Z–19:30:24Z (OCE-600 document `peak-reread`), over each container's
lifetime. `Live P` is the re-read alone; no P changed. `memory.peak` includes page cache, so it is an upper bound on
working set. Rule: request′ = min(request, ⌈P⌉₁₆) with a 32Mi floor;
limit′ = max(⌈1.25 × request′⌉₈, ⌈1.25 × P⌉₈) with a 40Mi floor; applied only
when below today's limit. Values are Mi. CPU is unchanged. The same numbers
are the fixture `ansible/tests/b0_memory_peaks.yml`, which
`ansible/tests/test_b0_memory_reductions.py` checks against the changed files
(limit ≤ old limit, request ≤ old request, limit ≥ 1.25 × P).

| Container | Request (now → B0) | Limit (now → B0) | P | Live P | Window | Request below P |
|---|---|---|---|---|---|---|
| log-collector (x10) | 100 → 32 | 1024 → 40 | 26.5 | 26.5 | 2.22 d |  |
| ceph-exporter (x3) | 50 → 48 | 128 → 64 | 33.1 | 33.1 | 10.28 d |  |
| rook-ceph-tools | 64 → 64 | 256 → 136 | 105.6 | 105.6 | 27.68 d | yes |
| metallb speaker | 128 → 80 | 512 → 104 | 68.1 | 68.1 | 7.47 d |  |
| metallb frr | 32 → 32 | 256 → 64 | 50.2 | 50.2 | 7.48 d | yes |
| metallb reloader | 32 → 32 | 256 → 64 | 45.3 | 45.2 | 25.04 d | yes |
| metallb frr-metrics | 32 → 32 | 256 → 48 | 32.3 | 32.3 | 25.04 d | yes |
| metallb controller | 96 → 96 | 512 → 152 | 120.4 | 120.4 | 25.73 d | yes |
| argocd application-controller | 384 → 384 | 1024 → 792 | 631.5 | 631.5 | 25.23 d | yes |
| argocd repo-server | 64 → 64 | 1024 → 408 | 321 | 321.0 | 15.72 d | yes |
| argocd server | 64 → 64 | 1024 → 184 | 146.5 | 146.5 | 25.04 d | yes |
| argocd dex-server | 64 → 64 | 1024 → 160 | 124.2 | 124.2 | 25.23 d | yes |
| argocd notifications-controller | 64 → 64 | 1024 → 88 | 69.7 | 69.7 | 25.73 d | yes |
| argocd applicationset-controller | 64 → 64 | 1024 → 80 | 63.5 | 63.5 | 25.23 d |  |
| argocd redis | 64 → 32 | 1024 → 40 | 15.4 | 15.4 | 25.73 d |  |
| mealie | 320 → 320 | 1024 → 408 | 325.5 | 325.5 | 20.67 d | yes |

Notes:

- `log-collector` (10 sidecars on mon, mgr, OSD and MDS pods) and
  `ceph-exporter` are set together by one key each; the figure is the largest
  peak among them. The shortest `log-collector` window at the live read is
  2.22 d (mds-b); the key qualifies through the containers over 7 d.
- `memory.events` `max` and `oom_kill` are 0 for every container of every key
  at the live read, and none of those containers restarted since OCE-550.
- The rbd `driver-registrar` P of 24.3 is above its live 18.0 (likely the
  cephfs registrar's figure). It stays at 24.3: conservative, and the 40Mi
  limit floor applies either way.
- **CSI plugin rows are not delivered by B0.** Under `ROOK_USE_CSI_OPERATOR`,
  Rook applies `csi.csiRBDPluginResource` and `csi.csiCephFSPluginResource` to
  the Driver CRs' `controllerPlugin` only. The nodeplugin DaemonSets keep the
  plugin at 1Gi, the `driver-registrar` at 512Mi and `liveness-prometheus` at
  256Mi, so the six `csi-rbdplugin` and `csi-cephfsplugin` rows (plugin,
  driver-registrar, liveness-prometheus) moved to *Left for Stage B*. The
  controller plugin does take the new values. The CSI Driver CRs are rendered
  by the operator at runtime, so `helm template` cannot show them; read them
  after `enable_rook_ceph_resources`.
- `cmd-reporter` is a new key on the CephCluster CR at 64Mi request / 512Mi
  limit, today's effective values from the `rook-ceph` LimitRange `default`
  (512Mi). It has no measured peak: it is set explicitly so the Pro cut of
  that default cannot reach the detect-version and network Jobs.
- MetalLB `frr-metrics` is 48Mi, not the spec's indicative 40Mi: 40Mi is
  below 1.25 × its 32.3Mi peak.
- Σ over the containers B0 touches, per node (Mi, before → after;
  from the OCE-550 snapshot, not a live read): anakin requests 894 → 576,
  limits 8064 → 912; obiwan 1058 → 672, 10112 → 1136; rey 1822 → 1344,
  15232 → 2376; yoda 1440 → 1200, 10752 → 2264. B0 does not make the nodes
  fit: Σ limits stays above allocatable on every node until Stage B.

### Left for Stage B

| Containers | Reason |
|---|---|
| Ceph mon, mgr, OSD, MDS daemons | App budgets tied to the limit; the OSDs are already at their limit. Stage B sets the pins. |
| Paperclip, `oce-git-sync`, paperclip-db | Critical; windows under 2 days; no node has room. |
| Velero server and node-agents | Data-mover path; the server is at its limit. |
| Traefik | `GOMEMLIMIT` = limit; Stage B sets it Guaranteed at ≥ 256Mi. |
| company-memory, rook-ceph-operator | At their limit: they need a raise, not a cut. |
| Home Assistant | 1.25 × P is above today's 2048Mi limit. |
| pihole, cloudflared, portal, mgr `watch-active` | Windows under 7 days. |
| Nextcloud (app, cron, db, redis), Jellyfin (app, xmltv-proxy) | Values sit inline in `nextcloud_deploy.yml` / `jellyfin_deploy.yml`; whether the runner may run those stages is unverified. |
| coredns, metrics-server, local-path-provisioner | k3s-bundled manifests: the k3s path is outside the runner. |
| Nodeplugin DaemonSet containers `csi-rbdplugin`, `csi-rbdplugin driver-registrar`, `csi-rbdplugin liveness-prometheus`, `csi-cephfsplugin`, `csi-cephfsplugin driver-registrar`, `csi-cephfsplugin liveness-prometheus` (plugin 1Gi, driver-registrar 512Mi, liveness 256Mi) | Under `ROOK_USE_CSI_OPERATOR` the Driver CRs apply the plugin resource keys to the `controllerPlugin` only. The nodeplugin values need a per-container setting the operator accepts, which Stage B finds. |
| `operations-mcp` `kubernetes-mcp-server` (limit 256Mi, B0 target 80Mi) | Pinned Application revision: the `operations-mcp` Application is pinned to Pro commit `0d1938de`, so the B0 cut is not live. It lands when the pin moves. |
| Every container whose request stays below P | Needs a request raise, which needs Stage B's per-node budget table. |

### Rollout, verification and rollback

Core lands first. Argo syncs mealie from core `HEAD`. Then the runner applies
`enable_argocd_resources`, `enable_metallb_resources` and
`enable_rook_ceph_resources` (HEALTH_OK gate; all PGs `active+clean`). Before
Pro lands, the `cmd-reporter` gate must pass live: the CephCluster CR
`spec.resources.cmd-reporter` and a `rook-ceph-detect-version` Job pod both
read 64Mi request / 512Mi limit while the `rook-ceph` LimitRange `default` is
still 512Mi. Run it outside 02:00–04:45 America/New_York, with no agent build
in progress (a MetalLB speaker roll can move the Paperclip LB IP briefly).

**Rollback order.** The `cmd-reporter` key stays live for as long as the
`rook-ceph` LimitRange `default` is below 512Mi. Reverting Pro alone is always
safe, because it raises the default. Removing the key (reverting core's
landing, or any later change to `rook-ceph-cluster-values.yaml` that drops it)
waits for this sequence: (a) revert the Pro `rook-ceph` LimitRange cut and let
Argo sync; (b) read the live LimitRange and confirm the `rook-ceph` `default`
memory is 512Mi again, recording it on the task; (c) only then revert core and
re-run `enable_rook_ceph_resources`. An OOM kill or eviction of a B0-changed
container sends that key back to its previous values as a fix ticket.

```mermaid
flowchart TD
  G["B0 gate: Stage A landed, monitor live,<br/>3 no-op flag runs green"] --> B["create map/OCE-369-immediate-reductions<br/>in core and Pro"]
  B --> T["Build tickets: charts (core), manifests (Pro)"]
  T --> MR["Map review: Tuvok, Worf; Kirk approves"]
  MR --> LC["land core (master); Argo syncs mealie"]
  LC --> P2["runner: enable_argocd_resources"]
  P2 --> P3["runner: enable_metallb_resources"]
  P3 --> P4["runner: enable_rook_ceph_resources<br/>(HEALTH_OK gate, PGs active+clean)"]
  P4 --> V{"live resources = Git, no OOM / eviction,<br/>Σ per node recorded"}
  V -- no --> RBC["map-gh.sh revert core; re-run flag.<br/>Pro lands only after a fix ticket<br/>drops the rook-ceph cut"]
  V -- yes --> CR{"cmd-reporter gate: CephCluster CR and<br/>detect-version Job pod at 64Mi / 512Mi,<br/>rook-ceph default still 512Mi"}
  CR -- no --> HOLD["hold Pro; fix ticket on the charts key"]
  CR -- yes --> LP["land Pro (main); Argo syncs cluster-defaults<br/>and Pro apps; recreate pods in<br/>rook-ceph only"]
  LP --> V2{"live resources = Git, no OOM / eviction,<br/>Σ per node recorded"}
  V2 -- no --> RBP["map-gh.sh revert Pro; Argo sync;<br/>recreate pods"]
  V2 -- yes --> W["24 h: working-set peak below new limit"]
  W --> SB["Stage B: 7 clean days, then full sizing"]
  RBP -.->|core revert needed too| RL["confirm live rook-ceph default = 512Mi,<br/>then revert core and re-run<br/>enable_rook_ceph_resources"]
  style G fill:#7b1fa2,color:#fff
  style B fill:#1e3a5f,color:#fff
  style T fill:#1e3a5f,color:#fff
  style MR fill:#1e3a5f,color:#fff
  style LC fill:#1e3a5f,color:#fff
  style LP fill:#1e3a5f,color:#fff
  style P2 fill:#2d5016,color:#fff
  style P3 fill:#2d5016,color:#fff
  style P4 fill:#2d5016,color:#fff
  style W fill:#2d5016,color:#fff
  style SB fill:#7b1fa2,color:#fff
  style RBC fill:#8b4513,color:#fff
  style RBP fill:#8b4513,color:#fff
  style RL fill:#8b4513,color:#fff
  style HOLD fill:#8b4513,color:#fff
```
