# Ansible runner

A manual, in-cluster way to run the Core (and optionally Pro) playbooks without an operator laptop. It is a plain Kubernetes Job in the `ansible-runner` namespace, outside ArgoCD, so a sync can never start a run.

## Design

| Item | Choice |
| --- | --- |
| Controller | One-shot Job (`deployments/ansible-runner/job.template.yaml`), ARM64, `backoffLimit: 0`, `activeDeadlineSeconds: 7200`, no service-account token, CPU/memory limits |
| Image | `ghcr.io/seadogger-tech/ansible-runner`, built by `.github/workflows/build-ansible-runner.yaml` from `deployments/ansible-runner/image/`, pinned by digest. ansible-core 2.21.4 on Python 3.14 (base image pinned by digest), matching the owner's controller, plus the pinned collections listed below. Nothing is installed at run time |
| Repository revisions | Core (public) at an explicit 40-char SHA. Optional Pro (`seadogger-tech/seadogger-homelab-pro`, private) at its own SHA via a read-only deploy key, checked out with `--recurse-submodules` (Pro pins Core at `core/`). Never a branch |
| Working directory | `/work/core/ansible` for Core. `/work/pro/ansible` for Pro (playbook `main.yml`, run with `-i hosts.ini`) |
| Inventory and configuration | `hosts.ini` and `config.yml` from Secret `ansible-runner-private` |
| Credentials | Secret `ansible-runner-private`: `config.yml`, `hosts.ini`, `id_ed25519` (SSH key for `pi`), `known_hosts` (nodes and github.com), optional `pro_deploy_key` (read-only deploy key on the Pro repo), and for Pro runs `pro_config.yml` and `pro_hosts.ini` (Pro's inventory and a runner copy of Pro's `config.yml`). A Pro run (working directory under `/work/pro`) installs the `pro_*` pair; a Core run installs `config.yml` and `hosts.ini`. Created by the owner; never in tasks, comments or git |
| Invocation | Spock creates the Job through the granted Kubernetes connection, only after the owner confirms the exact run in the task |
| Refused | `guard.py` evaluates the effective variables before every run and refuses if any destructive flag is true (below) |

### Collections in the image

The image installs exactly the collections the Core and Pro playbooks use, at the versions on the owner's controller (PR #73):

| Collection | Version |
| --- | --- |
| `kubernetes.core` | 6.5.0 |
| `community.general` | 13.4.0 |
| `community.okd` | 5.0.0 |
| `ansible.posix` | 2.2.2 |
| `ansible.utils` | 6.1.0 |

They install into the system collections path, `/usr/share/ansible/collections`. Core also vendors an old `community.kubernetes` at `ansible/ansible_collections/`. That is a different collection name, so it does not shadow `kubernetes.core` 6.5.0.

**Collections path.** Core's `ansible/ansible.cfg` sets `collections_path = ./`, which hides the image's system path. The Job template therefore sets `ANSIBLE_COLLECTIONS_PATH=./:/usr/share/ansible/collections` (PR #74). If a run fails with `couldn't resolve module/action '...'` (for example `community.general.modprobe`), check that this variable is still set in the Job and that the collection is in the table above. Pro's `ansible.cfg` may set its own path; check it before the first Pro run.

### Current image digest

Verified runs used `ghcr.io/seadogger-tech/ansible-runner@sha256:3a3da79b401c518bc3c2f8cc29f13f1597e3aa53621414b39e04d32a392c8944` (built from the PR #73 merge, `821a4af`, with the collections). This is the current digest until the image changes. When the Dockerfile or its pins change, rebuild with the workflow, record the new digest here and use it in the Job. The earlier digest `sha256:c5541f9b...` has no collections and must not be used.

### Who can read the Secret

Spock's Kubernetes connection has cluster-admin, so it can technically read this Secret. The control is policy, not isolation: Spock only reads it if debugging requires it, never posts its contents, and runs nothing without the owner's confirmation of the exact run.

### What it cannot run

Cold-start stage 1 wipes the cluster and stage 2 restarts k3s and Rook. Run from inside the cluster, both would kill the runner partway through, so those stay a job for the owner's controller.

`guard.py` is the Job's single launcher. It parses the argument string once, evaluates `guard.yml` against `config.yml` plus every `-e`/`--extra-vars` override, and only if that passes execs `ansible-playbook` with the same parsed list, so the guard and the run cannot see different arguments. Put the arguments in `REPLACE_ARGS` shell-quoted, for example `main.yml -i hosts.ini -e '{"enable_internal_pki": true}'`.

The run is refused if any of these is true in the effective variables:

- `cold_start_stage_1_wipe_cluster`
- `enable_wipe_k3s_cluster`
- `perform_physical_disk_wipe`
- `cold_start_stage_2_install_infrastructure`
- `run_pod_cleanup`
- `run_infrastructure_cleanup`
- the flags derived from stage 2 in `example.config.yml`: `enable_k3s_control_plane`, `enable_k3s_workers`, `enable_rook_ceph_part1`, `enable_metallb_native`, `enable_argocd_native`, `enable_raspberry_pi_config`

Argument rules: `--` is refused, any long option starting `--e` other than exactly `--extra-vars` is refused (optparse accepts prefixes), `-e=...` and short-option clusters containing `e` are refused. Use `-e value` or `--extra-vars value`.

**The runner's `config.yml` must set all of these false.** `example.config.yml` ships with `perform_physical_disk_wipe`, `run_pod_cleanup` and stage 2 true, so a default config is refused by design. Keep a runner copy with them false; the owner's controller keeps its own.

The guard fails closed: an unparseable argument string or a guard error also stops the run. Limits: it only sees `config.yml` and `-e` values. It does not see variables from `hosts.ini` group vars, `group_vars/`, `vars_files` or a playbook's own `vars:`. If `config.yml` is vault-encrypted the guard fails closed because no vault password is supplied; the supported path is a plaintext runner `config.yml` in the Secret. The Core revision you run must include `guard.py`.

## One-time setup (owner)

1. Merge this PR, then run the **Build ansible-runner** workflow (`workflow_dispatch` only exists once the workflow is on master). Record the digest it reports.
2. GHCR creates new packages private. In the package settings, make `ansible-runner` public (the repository is public and the image contains no secrets), otherwise the Job cannot pull it (it has no `imagePullSecrets`).
3. Create the Secret from the live local files:

```bash
PRO_CONFIG=/PATH/TO/runner-pro-config.yml PRO_HOSTS=/PATH/TO/pro/ansible/hosts.ini \\
  sh deployments/ansible-runner/refresh-secret.sh /PATH/TO/dedicated_key /PATH/TO/known_hosts /PATH/TO/pro_deploy_key

The runner copy of Pro's `config.yml` must set every destructive and stage-2 flag the guard checks to false, including `run_pod_cleanup`, and define the derived stage-2 flags as false; Pro's own `config.yml` doesn't define them, so the guard would refuse it.
```

Use a dedicated SSH key authorized on the four nodes for `pi`, not a personal key. Revoke by removing it from the nodes' `authorized_keys` and deleting the Secret.

## Keeping config current

The Secret is a snapshot. **Re-run `refresh-secret.sh` after every change to `config.yml`, `hosts.ini` or the keys.** Each run prints `config.yml sha256` at the top of its log; compare it with the hash `refresh-secret.sh` printed (or `shasum -a 256 ansible/config.yml`) before trusting a run.

## Running

1. The owner confirms in the task: Core SHA (and Pro SHA), exact `ansible-playbook` arguments, whether it mutates the cluster. AGENTS.md requires this for production runs.
2. Prefer a no-change preflight first: `main.yml -i hosts.ini --syntax-check`. `--check --diff` reaches the nodes but has a known limit (below), so read it as a connectivity and dry-run signal, not a clean pass.
3. Fill the template and create the Job. Record the exact command, SHAs and config hash in the task.
4. Read the result: `kubectl -n ansible-runner logs job/ansible-run-<id>`. The PLAY RECAP must show `failed=0 unreachable=0` for all four nodes. Post only the recap and counts to the task; keep full logs in the cluster.

### `--check` limit

Check mode skips `shell`/`command` tasks, so any later task that uses their output can fail even though nothing is wrong. Known case: with `-e '{"enable_internal_pki": true}'`, `internal_pki_deploy.yml` "Create Kubernetes Secret for Intermediate CA" fails on yoda because the earlier "Read ... CA cert and key" shell tasks were skipped and returned nothing. Treat a `--check` failure at a task that consumes skipped shell output as a check-mode artifact; confirm in the log that the failing task's inputs were skipped. Fixing it would need `check_mode: false` on those read-only tasks, which is not done.

## Failures

- `Permission denied (publickey)` or host key error: the Secret key or `known_hosts` is wrong. Fix the Secret; do not disable host key checking.
- `couldn't resolve module/action`: a collection is missing from the image, or `ANSIBLE_COLLECTIONS_PATH` is not set in the Job (see Collections path above).
- Job fails partway: the playbook is idempotent but not transactional. Diagnose with [the recovery runbook](17-Runbooks#diagnose-before-recovery) before a rerun. `backoffLimit: 0` prevents automatic retries.
- `ImagePullBackOff`: the GHCR package is still private, or the digest is wrong.
- `DeadlineExceeded`: the run hit the 2-hour limit; check the log before rerunning.
- `refused: <flag> is true in the effective variables`: run from the owner's controller, or set the flag false in the runner `config.yml` / the `-e` overrides.
- `refused: ...option...`: fix the argument spelling per the rules above.
- Node unreachable (e.g. after power loss): see `node_dns_fallback` in AGENTS.md.

## Owner-run fallback

From the Core checkout at the required revision:

```bash
cd ansible
ansible-playbook main.yml -e '{"enable_internal_pki": true}'   # example: the verified PKI run
```

Post back the PLAY RECAP and the `git rev-parse HEAD`.

## Verification record

Accepted by the owner on the Paperclip task OCE-130 (2026-11-19):

- `--syntax-check`: Job `ansible-run-20261118-syntax3`, Core `800407866fff`, passed. The first attempt (`-syntax`) failed on missing collections (bare image) and the second (`-syntax2`) on the hidden collections path; the third passed with `ANSIBLE_COLLECTIONS_PATH` set by hand, which PR #74 then made part of the Job template.
- `--check --diff`: Job `ansible-run-20261119-check1`, Core `13d3b5748d713c83d92f6c278ced2833f68b622a`, image digest `sha256:3a3da79b401c518bc3c2f8cc29f13f1597e3aa53621414b39e04d32a392c8944`, arguments `main.yml -i hosts.ini --check --diff -e '{"enable_internal_pki": true}'`. The guard passed and SSH, host-key checking and collections worked on all 4 nodes. Recap: anakin, obiwan, rey `failed=0`; yoda `failed=1` from the `--check` limit above.

## Open follow-ups

- `refresh-secret.sh` assumes a local `kubectl`, which the owner's Mac does not have. It should apply the Secret through yoda. Not done; until then, apply the Secret from a host that has cluster access.
- Pro playbooks are not exercised: the Secret still needs Pro's `config.yml`, `hosts.ini` and the `pro_deploy_key`, and Pro's `ansible.cfg` collections path needs checking.
- No real (non-check) run has gone through the runner yet.
