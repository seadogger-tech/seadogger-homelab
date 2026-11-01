# Closed synthetic Mealie control source

**Draft source; not an installable or execution-ready system.** This supplies the
admission/lifecycle source prerequisite for Pro issues 108, 109 and 110. It does
not complete those slices, V01, the P0 controls, or a runtime acceptance case.
There is no production configuration, automatic service installation or deploy
hook. Do not apply the adjacent production-shaped `../candidate` overlay.

## Reviewed inputs and seams

The accepted specification is Pro issue 107 and the accepted ten-ticket plan is
OCE-25 revision `6f297b80-d29b-4331-aa0f-629f3a7c1f47`. This does not republish or
change that breakdown. Source preparation is independent of V01 execution.

Implementation inputs, read on 2026-11-01:

| Record | Revision |
| --- | --- |
| OCE-61 security-interface-contract | `4e2bb76f-71d5-49c8-80be-364522cf9085` |
| OCE-62 adapter-contract | `588fcd3a-e259-43bd-afa4-c96152d24269` |
| OCE-56 execution-packet | `97db1b09-d661-4341-9366-a04834a35d59` |
| OCE-57 command-annex | `1cb3d1d8-bb18-4c2a-b6e6-3c4741b30d7c` |
| OCE-58 configuration-annex | `1fbba1f8-ded3-48db-aab5-8595328726e3` |
| OCE-59 command-annex | `6a7a069a-9433-4110-afd7-d502f8e29a52` |
| OCE-60 evidence-annex | `7dbda507-827f-4f46-8e1b-58e5c7a61a76` |

The checked-in Pro skills and tracker/domain/triage/evidence configuration at
`ec561face84e7f99f3a3b16012fa9c6b7e9fa9df` govern this work. Core's AGENTS and
public-source conventions also apply. This directory contains no live bindings,
receipts, credentials, infrastructure identifiers or operational evidence.

| Existing seam | Source implementation and required observation |
| --- | --- |
| S1 supported UI/API | `Controller.handle` validates a broker-captured native authenticated request, exact ordinary body, one result slug and finite reads. Later observe real UI/API and controlled destination outcomes. This is not an importer seam. |
| S2 deployment/artifacts | `control.py validate`, immutable packet/route checks, compilation and existing offline Kustomize/inert Ansible tests. Shape/hash checks grant no authority. |
| S3 lifecycle/controller | `prepare`, `launch`, `tick`, `close`, `status`, broker operations and durable ledger. Later observe independent pre-exec fences, one-use forwards, host deadline, complete termination and retained state. |

Deterministic fault tests of the internal controller-to-store/clock/adapter
interface have **not** been written or run. OCE-61 explicitly distinguishes that
optional internal seam from accepted S3. The precise proposed delta must go
through Scotty and Kirk's human checkpoint before those tests are added. Source
compilation and previous S2 tests do not establish crash, forwarding or deadline
correctness. No TDD red/green result is claimed for this draft.

## Entrypoints

Python 3.12+ standard library; Linux CLOCK_BOOTTIME and SO_PEERCRED for runtime.
From a separately authorized bound checkout, using protected absolute paths:

```text
python3 useful_scripts/mealie-migration/control/control.py --help
python3 useful_scripts/mealie-migration/control/control.py validate /PROTECTED/packet.json
python3 useful_scripts/mealie-migration/control/control.py image-identity /PROTECTED/index.json /PROTECTED/arm64.json /PROTECTED/config.json --config-digest sha256:EXPECTED
```

`validate` only parses the packet. It explicitly returns `ready: false` even on
success. `image-identity` reads existing raw bytes; it performs no registry access,
layer extraction, image startup or scan. It checks E1 digest/membership/platform
and descriptor linkage. E2 layers, E3 provenance/referrers, E4 installed inventory
and scanning, E5 actual runtime binding, and source/build equivalence remain
separate verified broker prerequisites. Config reference strings are not passes.

The following are future runtime entrypoints, **not authorized commands**:

```text
python3 useful_scripts/mealie-migration/control/control.py initialize-ledger /PROTECTED/HOST-LEDGER
python3 useful_scripts/mealie-migration/control/control.py supervise --packet /PROTECTED/packet.json --ledger-directory /PROTECTED/HOST-LEDGER --broker-socket /PROTECTED/broker.sock --execute-authorized-run
```

The explicit flag is intent only. The enforcing broker must verify actual
authority, custody, target and all readbacks. The CLI never auto-initializes a
missing ledger or reuses an old run. A protected socket is not a grant to use it.
No systemd unit, shell stop command or speculative Kubernetes runtime hook is
supplied as an installed enforcement mechanism.

## Durable state and crash handling

The journal is a host-controlled SQLite rollback journal, outside the app/guest
restorable volume, protected by a 0700 directory and 0600 regular single-link
file. Ancestors cannot be writable by other identities. An exclusive process
lock and BEGIN IMMEDIATE serialize state; synchronous=EXTRA and journal DELETE
require a supported host filesystem with verified fsync/directory-fsync behavior.
There is no schema migration, cleanup, pruning, retry or automatic reinitialization.
The 24MiB database page ceiling leaves rollback-journal/headroom inside the
contract's separate 64MiB host-state quota. The host quota, filesystem metadata,
bounded evidence reserve and full 20GiB aggregate layout still require Operations
enforcement and readbacks; SQLite settings alone cannot prove the allocation.

Run ID and epoch are unique. Launch and import consumption are distinct. Import
SPENT and request attempt commit before `forward_once`; result slug commits before
`release_response`; runner GET allowance commits before its forward. A crash
after commit and before send spends the attempt without replay. Concurrent or
ambiguous outcomes cannot refund it. State recovery burns active runs and requests
closure; stale/missing/unknown host tombstones prohibit a new launch. Host reboot,
snapshot rollback and power-loss behavior remain unexecuted integration cases.

The broker must atomically enforce the host tombstone and current generation
with each forward capability, including withdrawal on close. This is required
to prevent a delayed handler forwarding after the controller's commit but after
closure. It must never retry a POST, follow a redirect, queue work or reconstruct
an outbox after reconnect. The controller cannot revoke a network packet itself.

## Operations broker contract

Ro/Tom, through Spock, must implement and bind the actual privileged broker.
`adapter.py` is the concrete local transport client, **not that implementation**.
Only an expected root-owned Unix peer in a protected path is accepted. Four-byte
big-endian length framing carries bounded UTF-8 JSON (4MiB transport maximum for
base64 HTTP envelopes). One connection carries one request. The absolute
CLOCK_BOOTTIME deadline bounds each exchange; no reconnect retry exists.

Every request/receipt binds protocol version, operation, random request ID, run,
epoch, canonical binding hash, host/target boot IDs, configuration digest and
journal sequence. Receipts also bind adapter digest and fresh host monotonic
observation time. `VERIFIED_TRUE`, `VERIFIED_FALSE` and `UNKNOWN` are distinct;
`ACKNOWLEDGED` is not verification. The broker resolves authority/evidence handles
in protected custody and verifies actual implementations/readbacks. It cannot
accept caller strings as proof. Its authority includes only the prebound target.

The socket protocol implements these existing OCE-62 operations:
`inspect_binding`, `claim_writer`, `arm_once`, `read_run_state`, `close_and_stop`,
`force_fence`, `observe_quiescence`, `describe_retained_set`. It adds the concrete
transport forms of OCE-61 admission operations: `capture_request`, `forward_once`,
`release_response`, `deny_request`, `next_request`. These are source interfaces,
not assertions that corresponding Operations commands already exist.

Broker integration requirements:

- Cover host backend writer exclusion and **every** guest mount/start/restore
  path before exposing writable storage or executing app/init/helpers. No API
  token, runtime socket, fsGroup repair, second writer or auto-restart bypass.
- Install/read back sealed workload, sink and guest network controls before exec;
  bind netns handles, all helper subtrees, quota generation and offload policy.
  Shared packet accounting and all bounded writable paths remain real enforcement.
- Arm the independent host watchdog at the original outer VM launch time before
  launch consumption. Never reset time at app readiness, client connection,
  daemon restart, pause/resume or reboot. Require host suspend/resume fencing.
- Close admission/network/start fences at 295s or earlier failure. The contract's
  proposed TERM295/KILL297/exact-VM-fallback298 schedule must be bound and measured
  by Operations. The Python polling interval is 50ms and ordinary broker calls
  have 200ms transport budgets; these are source parameters, not measured maximum
  closure latencies or hard real-time guarantees. Broker/runtime latency and
  scheduling must fit the absolute 300s target. A missing observer fails the case.
- Execute only the protected-map stop/fallback for the exact dedicated target,
  never a caller shell string, PID/name search, broad shutdown, detach or deletion.
  Repeated close is idempotent; close remains allowed even if journal sequence is
  unavailable. Force-fence acknowledgement alone never yields quiescence.
- Observe all descendant cgroups, runtime tasks, helpers/sockets, no replacement
  writer, network/start fences and settled backend I/O independently. A vanished
  cgroup, scale0, empty Pod list or command exit is insufficient.
- Keep DB/WAL/SHM/journal/assets/settings and independent evidence under hold.
  `inspectionAllowed` stays false; no copy, mount, checkpoint, repair, cleanup,
  temporary-data preservation extension or automatic fresh volume allocation.
- Verify the complete raw HTTP envelope and native principal/group/session
  before capture. No reverse-proxy identity invention. Serialize captured request
  handle, digest and one-use forward capability with the same closing generation.
  Reconstruct only reviewed upstream headers; no smuggling or normalization gap.
  Hold bounded responses until source validation and explicit single release.
- Keep the gateway/browser/runner inside the no-NIC guest. Host/guest transport
  and console custody remain unbound: this local socket interface does **not**
  authorize vsock, host shares, NICs, port forwards or another network channel.

## Finite UI manifest: missing input, closed by default

No complete packaged asset manifest is claimed. `Binding.parse` refuses a missing
or incomplete manifest, an incorrect candidate/package digest, wildcards,
duplicate routes, unknown placeholders, excessive responses and forbidden routes.
The exact method/target/query is matched without prefix permissions. HEAD needs
its own reviewed entry. Only the bound group and returned slug can be substituted.
Observer native session validity must cover the entire remaining run. Auth
refresh/logout, alternate imports, provider management/Test and unknown reads
are denied. A denied request conservatively closes the evaluation.

The four known seed routes are insufficient: the candidate's Nuxt build uses
hashed chunks, locale/font assets, a generated backend manifest and PWA behavior.
At source `9552df62118224a377d9c9b0a62706a62220ab86`,
`frontend/nuxt.config.ts` configures `ssr: false`, lazy locale assets, auto-updating
PWA registration and generated build assets. It cannot supply installed asset
filenames/hashes. Source inspection is not package inspection. One expression in
that config is connector-redacted; no alternate-byte bypass was attempted.

Operations must supply the authorized offline inventory of the exact unmodified
ARM64 package, its E1/E2 linkage and file hashes, plus ordinary observer locale,
group/household/session conditions and approved browser policy. Wesley then
enumerates **all** required page/component/API/asset requests, hashes each packaged
asset, checks the 2MiB response cap and no-remote-resource/PWA behavior, and routes
the finite artifact for review. No wildcard, auto-learning, app rebuild or route
relaxation is selected. This missing source input must not become a dependency
on OCE-56 being execution-ready or V01 completing.

## Validation and limits

The preparation workflow compiles these files and checks CLI help. Its existing
seven S2 cases remain deployment/configuration coverage, not controller coverage.
Three new offline packet checks use the public `validate` command: reject boolean
numeric limits, reject shared runner/observer identity, and accept a valid
synthetic shape while explicitly withholding authority/readiness. The first
regression was committed before its fix: preparation CI failed at `db4350bb` and
passed at `184ea2fb`. Check-run status was observed through the developer
connector; step logs were not available through that tool. The other two checks
characterize existing behavior and prevent an always-reject implementation from
passing the rejection cases. No internal clock/store/adapter is replaced.

`fixtures/packet.synthetic.json` is a shape-only test artifact: its fake references
and synthetic asset entry cannot authorize a run or represent the candidate UI.
Record actual workflow links and current head separately. No local checkout, local test,
control simulation, image/host/VM/cluster/import/provider probe or enforcement
test was run while authoring this draft. The new deterministic test seam is
pending the precise checkpoint described above; there is no passing controller
test suite yet. Review must report this as missing evidence.

Keep the V01 behavioral runner separate. Its two connector-redacted credential
expressions remain an existing review gap; this source does not touch or bypass
them. Closed synthetic/source checks do not resolve recipe-origin TLS, real
automatic YouTube, decoded-size/cooperative cancellation/no-partial-write claims,
image security, production Ceph recovery, capacity, custody or retention authority.

Branch `feat/oce-63-mealie-run-controls` starts at Core PR63 head
`8eda938d88a79e6327b7081f1383c36d141c93f0`; PR63 is unchanged. The new PR is stacked
on its contributor branch solely for an isolated diff. Eventual order: separately
approved PR63 first, then retarget/review this PR against master and obtain human
approval of its exact new current head. No contributor merge or deploy is allowed.
Native Tuvok then Worf source gates and Scotty/CCB routing remain required.
