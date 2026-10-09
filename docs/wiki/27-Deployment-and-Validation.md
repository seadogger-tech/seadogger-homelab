# Deployment and validation

## Find the owning deployment

Core is the public repository. In the Pro checkout it is the `core/` submodule; Pro-only applications live outside it. Find the existing application task and ArgoCD source before adding deployment logic. The playbook imports are the authoritative execution order.

| Concern | Core location | Pro location |
| --- | --- | --- |
| Entry point and ordering | `ansible/main.yml` | Pro `ansible/main.yml` |
| Public switch/credential template | `ansible/example.config.yml` | Pro `ansible/example.config.yml` |
| Private configuration/inventory | `ansible/config.yml`, `ansible/hosts.ini` | Pro files with the same relative names |
| Shared application tasks | `ansible/tasks/` | Pro `ansible/tasks/` |
| GitOps source | `deployments/<app>/` and the Application source in its task | Pro `deployments/<app>/` and its task |

Read the actual `enable_*` expressions and `when` conditions for the application. Core's application switches commonly combine `cold_start_stage_3_install_applications` and `manual_install_*`; older private configurations may lack newer switches. A flag's name or a template comment is not enough to establish its behavior. Infrastructure and destructive cleanup switches are separate concerns. Publishing a commit can cause live changes when an existing ArgoCD Application tracks that source; inspect ownership before publishing workload changes.

Ansible is the operator entry point and provisions protected Secrets and ArgoCD Applications. ArgoCD reconciles the application's Helm chart or Kustomize source. Reuse shared Ansible tasks for explicit staging commands. Keep conversion, teardown and recovery as separately authorized operations. Existing legacy task exceptions are not a reason to create another deployment path.

## Nextcloud PostgreSQL path

`ansible/main.yml` imports `tasks/nextcloud_postgresql_deploy.yml` before `tasks/nextcloud_deploy.yml`. The dedicated database defaults disabled and uses `enable_nextcloud_postgresql`, derived in the example configuration from stage 3 and `manual_install_nextcloud_postgresql`.

`ansible/nextcloud_postgresql.yml` requires explicit staging selection and imports those same database tasks. Its `nextcloud-db` ArgoCD Application points to `deployments/nextcloud/postgresql` at a reviewed immutable Core revision. ArgoCD renders the Kustomize StatefulSet, retained PVC, Services, backup CronJob and monitoring rules. Nextcloud itself still uses its Helm chart.

Staging provisions a target; the separate `ansible/nextcloud_migration.yml` phase runner controls conversion. Read [the migration runbook](26-Nextcloud-PostgreSQL-Migration) for prerequisite evidence, credential custody, the private deployment marker and both reopening boundaries. For failed pods, begin with [diagnosis before recovery](17-Runbooks#diagnose-before-recovery).

## Local and CI validation

From any directory, run this command with the path to your Core checkout:

```bash
python3 /ABSOLUTE/CORE/useful_scripts/nextcloud-migration/check.py
```

Prerequisites: Python 3.12 or newer with `venv`/pip, PHP 8.1 or newer with SQLite3 and PDO SQLite extensions, Bash, Helm 3 and kubectl on `PATH`. CI declares Ubuntu 24.04, Python 3.12, Helm 3.19.0 and kubectl 1.34.1. On macOS, these tools can be supplied by Homebrew; on Ubuntu install `python3-venv`, `php-cli` and `php-sqlite3`, plus the declared Helm/kubectl releases. Only kubectl's local Kustomize renderer is used.

The runner builds a private development virtual environment in Core's ignored `.cache/nextcloud-check/`, installs the versions in `checks/requirements.txt`, and downloads public artifacts using committed SHA-256 pins. The Ansible community distribution includes the collections needed to parse the existing playbooks; this validation environment does not rely on the older deployment collection file. It never reads the operator's `config.yml` or inventory: syntax checks use copies of the public examples and a localhost inventory. Ansible integration tests substitute recording Kubernetes modules, and CLI tests simulate Kubernetes/AWS at the subprocess boundary.

The command checks:

- The verified upstream converter's saved configuration contract and agreement with the production source pin.
- The local workflow suite, including real temporary SQLite WAL tests and simulated Ansible/Kubernetes/AWS behavior.
- Main/staging/phase Ansible syntax, migration-related YAML and the CI workflow, Python compilation, PHP and shell syntax.
- Pinned chart rendering: replicas zero, captured application image format, external PostgreSQL Secret references, and absence of the bundled database/wait container.
- Kustomize rendering: seven namespaced resources, explicit retained 10Gi RWO storage and the suspended nightly schedule.

This is a scoped guardrail for the migration and its deployment integration, not a claim that every historic repository YAML file is lint-clean. It does not deploy, contact a cluster or AWS, retrieve user backups, or start a restored Nextcloud.

After one successful online preparation, add `--offline` to require cached dependencies/artifacts. Use `--cache-dir /ABSOLUTE/CACHE` for a separate cache. A checksum mismatch stops the command; inspect the artifact before removing it and retrying. A changed requirements file requires online preparation again. Concurrent runs should use separate caches.

Ansible needs a local RPC socket for the localhost tests. If a sandbox denies that socket, allow this local test process rather than changing cluster permissions. DNS/download failures require restoring public package access or using a prepared offline cache; they are not evidence that GitHub or AWS credentials need reauthentication.

Core's `Nextcloud migration checks` workflow runs the same command on pull requests and master pushes and exposes it as a reusable workflow. Pro calls a pinned version against its checked-out Core submodule. Neither workflow receives deployment credentials. Review the reusable workflow pin when changing the CI wrapper; Core's submodule pointer selects the scripts and tests being validated.

## Updating converter or chart pins

`useful_scripts/nextcloud-migration/tests/fixtures/converter-contract.json` records the upstream source URL/hash, reviewed arguments and expected persisted host. `checks/artifacts.json` records the chart download and the official index used to establish its digest. These are durable review inputs, not files recovered from an earlier agent's temporary directory.

When updating the converter, inspect the pinned upstream changes, especially `saveDBInfo`, omission prompts and credential handling. Update the fixture, production `convert.php` hash guard and affected version checks together. The check command downloads and verifies the full source, then calls only its configuration-saving method with inert interfaces and an in-memory config. The same fixture supplies the CLI validation regression. This tests the cross-component contract without bootstrapping Nextcloud or connecting to a database; it does not prove that the full conversion will succeed.

For chart updates, obtain the digest from the [official Nextcloud chart index](https://nextcloud.github.io/helm/index.yaml), update the artifact pin and review the render assertions. Preserve the independent standards/spec review for migration changes; automated checks supplement that review.
