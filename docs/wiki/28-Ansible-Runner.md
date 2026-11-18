# Ansible runner

A manual, in-cluster way to run the Core (and optionally Pro) playbooks without an operator laptop. It is a plain Kubernetes Job in the `ansible-runner` namespace, outside ArgoCD, so a sync can never start a run.

## Design

| Item | Choice |
| --- | --- |
| Controller | One-shot Job (`deployments/ansible-runner/job.template.yaml`), ARM64, `backoffLimit: 0` |
| Image | `ghcr.io/seadogger-tech/ansible-runner`, built by `.github/workflows/build-ansible-runner.yaml` from `deployments/ansible-runner/image/`, pinned by digest. ansible-core 2.21.4 on Python 3.14, matching the owner's controller. Nothing is installed at run time |
| Repository revisions | Core (public) at an explicit 40-char SHA. Optional Pro (`seadogger-tech/seadogger-homelab-pro`, private) at its own SHA via a read-only deploy key, checked out with `--recurse-submodules` (Pro pins Core at `core/`). Never a branch |
| Working directory | `/work/core/ansible` for Core. `/work/pro/ansible` for Pro (playbook `main.yml`, run with `-i hosts.ini`) |
| Inventory and configuration | `hosts.ini` and `config.yml` from Secret `ansible-runner-private` |
| Credentials | Secret `ansible-runner-private`: `config.yml`, `hosts.ini`, `id_ed25519` (SSH key for `pi`), `known_hosts` (nodes and github.com), optional `pro_deploy_key` (read-only deploy key on the Pro repo). Created by the owner; never in tasks, comments or git |
| Invocation | Spock creates the Job through the granted Kubernetes connection, only after the owner confirms the exact run in the task |
| Refused | `guard.py` evaluates the effective variables before every run and refuses if any destructive flag is true (below) |

### Who can read the Secret

Spock's Kubernetes connection has cluster-admin, so it can technically read this Secret. The control is policy, not isolation: Spock only reads it if debugging requires it, never posts its contents, and runs nothing without the owner's confirmation of the exact run.

### What it cannot run

Cold-start stage 1 wipes the cluster and stage 2 restarts k3s and Rook. Run from inside the cluster, both would kill the runner partway through, so those stay a job for the owner's controller.

The guard (`deployments/ansible-runner/guard.py` and `guard.yml`) does not look at argument text. It evaluates `config.yml` plus every `-e`/`--extra-vars` override with Ansible, and the Job exits before the real run if any of these is true:

- `cold_start_stage_1_wipe_cluster`
- `enable_wipe_k3s_cluster`
- `perform_physical_disk_wipe`
- `cold_start_stage_2_install_infrastructure`
- `run_pod_cleanup`
- `run_infrastructure_cleanup`

It fails closed: an unparseable argument string or a guard error also stops the run. Limits: it does not see variables set only inside a playbook's own `vars:`, and the Core revision you run must include `guard.py` (the Job runs it from the Core checkout).

## One-time setup (owner)

1. Run the **Build ansible-runner** workflow (or merge to master). Record the digest it reports.
2. Create the Secret from the live local files:

```bash
sh deployments/ansible-runner/refresh-secret.sh /PATH/TO/dedicated_key /PATH/TO/known_hosts [/PATH/TO/pro_deploy_key]
```

Use a dedicated SSH key authorized on the four nodes for `pi`, not a personal key. Revoke by removing it from the nodes' `authorized_keys` and deleting the Secret.

## Keeping config current

The Secret is a snapshot. **Re-run `refresh-secret.sh` after every change to `config.yml`, `hosts.ini` or the keys.** Each run prints `config.yml sha256` at the top of its log; compare it with the hash `refresh-secret.sh` printed (or `shasum -a 256 ansible/config.yml`) before trusting a run. A vault-decrypt-at-run-time design is an alternative if the owner prefers storing the vault password as its own Secret.

## Running

1. The owner confirms in the task: Core SHA (and Pro SHA), exact `ansible-playbook` arguments, whether it mutates the cluster. AGENTS.md requires this for production runs.
2. Prefer a no-change preflight first: `main.yml -i hosts.ini --syntax-check`, then `--check --diff --tags <tag>`.
3. Fill the template and create the Job. Record the exact command, SHAs and config hash in the task.
4. Read the result: `kubectl -n ansible-runner logs job/ansible-run-<id>`. The PLAY RECAP must show `failed=0 unreachable=0` for all four nodes. Post only the recap and counts to the task; keep full logs in the cluster.

## Failures

- `Permission denied (publickey)` or host key error: the Secret key or `known_hosts` is wrong. Fix the Secret; do not disable host key checking.
- Job fails partway: the playbook is idempotent but not transactional. Diagnose with [the recovery runbook](17-Runbooks#diagnose-before-recovery) before a rerun. `backoffLimit: 0` prevents automatic retries.
- `refused: <flag> is true in the effective variables`: run from the owner's controller, or set the flag false in config.yml / the `-e` overrides.
- Node unreachable (e.g. after power loss): see `node_dns_fallback` in AGENTS.md.

## Owner-run fallback

From the Core checkout at the required revision:

```bash
cd ansible
ansible-playbook main.yml -e '{"enable_internal_pki": true}'   # example: the verified PKI run
```

Post back the PLAY RECAP and the `git rev-parse HEAD`.

## Not yet verified

The route has not been exercised: no image is built, no Secret exists, and the guard has not been run against real `config.yml`. Acceptance requires one owner-approved run (`--syntax-check` or `--check` is enough) with its command, revisions and recap recorded in the Paperclip task. The owner has put the first run on hold. The Secret is created last, after merge.
