# Ansible runner

A manual, in-cluster way to run the Core playbooks without an operator laptop. It is a plain Kubernetes Job in the `ansible-runner` namespace, outside ArgoCD, so a sync can never start a run.

## Design

| Item | Choice |
| --- | --- |
| Controller | One-shot Job (`deployments/ansible-runner/job.template.yaml`), ARM64, `backoffLimit: 0` |
| Repository revision | Public Core repo, checked out by an init container at an explicit 40-char commit SHA, never a branch |
| Working directory | `/work/core/ansible` |
| Inventory and configuration | `hosts.ini` and `config.yml` from Secret `ansible-runner-private` (the gitignored private files) |
| Dependencies | `ansible-core` 2.17/2.18 plus `kubernetes` installed at start; collections are vendored under `ansible/ansible_collections` |
| Credentials | Secret `ansible-runner-private` holds `config.yml`, `hosts.ini`, `id_ed25519` (SSH key for user `pi`) and `known_hosts`. The owner creates it; it never appears in tasks, comments or git |
| Invocation | Spock creates the Job through the granted Kubernetes connection, only after the owner confirms the exact run in the task |

## One-time setup (owner)

```bash
kubectl apply -f deployments/ansible-runner/namespace.yaml
kubectl -n ansible-runner create secret generic ansible-runner-private \
  --from-file=config.yml=ansible/config.yml \
  --from-file=hosts.ini=ansible/hosts.ini \
  --from-file=id_ed25519=/PATH/TO/dedicated_key \
  --from-file=known_hosts=/PATH/TO/known_hosts
```

Use a dedicated SSH key authorized on the four nodes for `pi`, not a personal key. Revoke it by removing it from the nodes' `authorized_keys` and deleting the Secret.

## Running

1. The owner confirms in the task: revision SHA, exact `ansible-playbook` arguments, whether it mutates the cluster. AGENTS.md requires this for production runs; never run `cleanup.yml` unless asked in that session.
2. Prefer a no-change preflight first: `main.yml --check --diff --tags <tag>` or `--syntax-check`.
3. Fill the template and create the Job. Record the exact command and SHA in the task.
4. Read the result: `kubectl -n ansible-runner logs job/ansible-run-<id>`. The PLAY RECAP must show `failed=0 unreachable=0` for all four nodes. Post only the recap and counts to the task; keep full logs in the cluster.

## Failures

- `Permission denied (publickey)` or host key error: the Secret key or `known_hosts` is wrong. Fix the Secret; do not disable host key checking.
- Job fails partway: the playbook is idempotent but not transactional. Diagnose with [the recovery runbook](17-Runbooks#diagnose-before-recovery) before a rerun. `backoffLimit: 0` prevents automatic retries.
- Node unreachable (e.g. after power loss): see `node_dns_fallback` in AGENTS.md.

## Owner-run fallback

From the Core checkout at the required revision:

```bash
cd ansible
ansible-playbook main.yml -e '{"enable_internal_pki": true}'   # example: the verified PKI run
```

Post back the PLAY RECAP and the `git rev-parse HEAD`.

## Not yet verified

The route has not been exercised. Acceptance requires one authorized run (a `--check` or `--syntax-check` is enough to prove the path) with its command, revision and recap recorded in the Paperclip task.
