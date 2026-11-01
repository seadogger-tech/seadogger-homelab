# Mealie ordinary web recipe check

Preparation for the ordinary-import case V01 at the accepted S1 application seam.
The fixture and oracle are synthetic; they contain no household content.
The case has not run against Mealie. No red/green result or V01 acceptance is claimed.

## Fixture and independent oracle

- `fixtures/ordinary-web.html` contains a visible recipe and complete JSON-LD.
- `fixtures/ordinary-web.expected.json` is a literal recipe oracle authored before
  application execution, not generated from an import result or HTML parser.
- `https://recipes.test/ordinary-web.html` is the synthetic provenance. This
  reserved hostname has no public fixture service. Do not substitute a real site.
- No image, note, redirect, remote script or stylesheet is supplied.

The check compares the reopened recipe's title, complete ingredient display
(including quantity/unit), yield, times, ordered instructions and provenance.
Whitespace and equivalent half-teaspoon spellings are normalized. The candidate's
public seconds fields and serving count are accepted representations of the
literal durations and yield. Unknown representations fail for review; do not
silently loosen the oracle. Added notes/images fail for review; the candidate's
`no image` placeholder is allowed. A title or HTTP success alone is insufficient.

## V01 entry command

`check.py` requires Python 3.12+ and uses only the standard library. It sends one
ordinary import and one read of the returned recipe through the supported API.
It has no fixture server, application launcher, retries, cleanup, bulk imports,
internal compiler mocks or database inspection.

Before executing, the environment owner must supply an explicitly authorized
disposable target, fresh synthetic account/data, reverified exact image identity,
reviewed configuration, and effective P0 controls/receipts. The control record
must cover fixture DNS/destination mapping, TLS trust, egress denial, admission,
finite work and termination. No provider credentials or real-provider route may
exist. AI must be disabled for this case; observe zero provider attempts/use.
Do not infer this from the ordinary endpoint: the candidate scraper can fall back
to AI. The runner does not read or change provider settings.

Serve the exact HTML at the designated URL inside that environment. Preserve
application address validation; no HTTP address exceptions, proxy/browser helper,
video cookies, production ingress/storage or uncontrolled Internet access.
Use the selected P0 budget and its independent admission/supervision boundary.
This runner is not that supervisor and does not establish enforcement.

Have the approved credential mechanism set `MEALIE_TEST_TOKEN` to the protected
synthetic-account token. Never place its value in the command, repository or
ordinary task evidence. Install the approved target CA in the test process trust
store if needed; certificate verification remains enabled. From the authorized
bound Core checkout, with placeholders replaced by verified metadata:

```bash
python3 /ABSOLUTE/CORE/useful_scripts/mealie-migration/check.py \
  --execute \
  --base-url https://APPROVED-SYNTHETIC-TARGET \
  --source-ref REVIEWED_40_HEX_CORE_COMMIT \
  --authorization-ref AUTHORIZATION_RECORD_ID \
  --controls-ref P0_ENFORCEMENT_RECEIPT_ID \
  --identity-ref EXACT_IMAGE_RECEIPT_ID \
  --config-ref CONFIGURATION_REVISION
```

These arguments record references, not grants or proof of their contents. Supply
opaque identifiers, not secrets or credential-bearing URLs. The source SHA must
identify the actual files used. The expected candidate identities are:
upstream v3.30.0, source `9552df62118224a377d9c9b0a62706a62220ab86`,
OCI index `sha256:90f83da6f3ab0a421efc827118a556168573930105f13fa3321768f42163d784`,
linux/arm64 child `sha256:8dbe3fd73896e77c797f7029201823fa8b1ddbc725059f496cf884f06c9916da`.
They still require fresh registry membership/config and running-identity receipts;
printing constants or passing `--identity-ref` does not verify the target.

The request is `POST /api/recipes/create/url` with the fixture URL and
`includeTags: false`, `includeCategories: false`, followed by
`GET /api/recipes/{returned-slug}`. There is no obsolete `useOpenAI` flag.
The contract was inspected at the candidate source above in
`mealie/routes/recipe/recipe_crud_routes.py`,
`mealie/schema/recipe/recipe_scraper.py` and the public recipe schemas.

Exit 0 means the reopened API content matched. Exit 1 means a mismatch or an
inconclusive request/read; exit 2 means invalid invocation or fixture input.
The JSON receipt reports fixed field verdicts, times, fixture hashes and supplied
references. It omits tokens, target URL, account/recipe IDs and response bodies.
Keep it with the authorized private evaluation evidence. Raw source logs may
contain sensitive URLs or exceptions and follow the private evidence policy.

After any attempted POST, preserve the disposable state. A timeout or disconnect
can leave background work or a saved recipe: do not automatically retry, delete
or rearm. The client uses 60-second socket timeouts and a 2MiB response read cap;
these are client safeguards, not total-time, download or application work limits.
The independent P0 supervisor must still enforce its selected 295s stop/300s
termination target and retain failed-run data.

Complete the same case by reopening the recipe in the actual UI, checking the
display and ordinary/AI distinction, and linking fixture-sink and zero-provider
observations plus environment receipts. API match alone leaves acceptance
`pending_ui_provider_and_environment_evidence`. Record the initial result before
changing configuration. If upstream defaults pass, retain them. An observed
failure guides the smallest supported change; no fork or fallback substitution.

## Offline candidate render preparation

`candidate/kustomization.yaml` is an offline S2 contract overlay. It references
the existing Mealie base and changes only the image to the expected upstream
tag/index. Nothing under the watched `deployments/mealie` path is edited.

**Never apply this overlay.** It retains production-shaped names, routing and PVC
references to inspect preservation; it is neither a safe isolated target nor a
P0 implementation. It also preserves the legacy prompt input mount/environment
for later verified migration disposition. It does not retire prompts, the custom
build, or select per-group overrides for the initial defaults test.

Once a bound checkout and tools are available:

```bash
kubectl kustomize /ABSOLUTE/CORE/useful_scripts/mealie-migration/candidate
yamllint -c /ABSOLUTE/CORE/.yamllint /ABSOLUTE/CORE/useful_scripts/mealie-migration/candidate
```

Inspect the rendered contract: one replica/Recreate, ARM64 scheduling, original
`mealie-data` RWO claim with `ceph-block-data`/10Gi, `/app/data`, PUID/PGID 911,
50m/320Mi requests and 1000m/1Gi limits, existing probes, Service port 9000 and
Certificate/IngressRoute/TLS linkage. Effective capacity and writer fencing are
runtime evidence, not conclusions from these fields.

## Offline S2 checks

With Python 3.12+, kubectl 1.34.1, and the pinned validation requirements installed
in an approved development environment, run from any directory:

```bash
python3 -m pip install -r /ABSOLUTE/CORE/useful_scripts/nextcloud-migration/checks/requirements.txt
python3 -m unittest discover -s /ABSOLUTE/CORE/useful_scripts/mealie-migration/tests -p 'test_*.py' -v
```

The dependency file reuses Core's existing validation toolchain, including
Ansible 14.4.0 / ansible-core 2.21.4, PyYAML and yamllint. Installation retrieves
public packages; the checks themselves contact no application, registry or cluster.

The render suite invokes only local `kubectl kustomize` with an empty kubeconfig.
It checks literal contract requirements against actual rendered resources:
candidate image/index, ARM64 selector, one replica/Recreate, original RWO claim,
mounts, PUID/PGID, resources, probes, Service, Certificate, ingress and TLS.
It checks that the four retained prompt inputs reach the generated ConfigMap
unchanged. Sixteen focused mutations of rendered output must be rejected,
including a second writer, missing digest, wrong architecture, replaced storage,
changed ownership/probes/resources/routing/TLS and a removed prompt input.
This proves assertion sensitivity, not application execution or image membership.

The Ansible suite reads only public examples and source. It copies the actual
`ansible/main.yml`, adds a test selection tag to its one Mealie import, and uses
the original condition and imported task body. It never rewrites the enable
expression. A temporary localhost inventory, no privilege escalation and
recording `k8s`/`k8s_info` modules replace the external Kubernetes boundary.
Other tags and fact gathering are skipped. Parse-only sentinels for unselected
Helm/patch modules fail if invoked. An allowlist rejects new task actions,
includes, loops or delegation before execution. Operator configuration,
inventory and credential environment are not used. The recorded healthy
Application response is a test double, not a readiness observation.

Checks assert the actual emitted Application source repository/path, `HEAD`,
destination, `prune: true`, `selfHeal: true` and namespace creation policy.
That is existing source behavior, not a new deployment selection or approval.
The pinned Ansible execution established these existing behaviors:

| Configuration | Recorded Application |
| --- | --- |
| Stage 3 false, manual false or true | None |
| Stage 3 true, manual false | None |
| Stage 3 true, manual true | Existing Application contract |
| Explicit enable false or true | Follows explicit enable |
| Enable absent, even with both stage/manual false | Existing Application contract |
| Manual absent, stage 3 false | None |
| Manual absent, stage 3 true | Existing Application contract |

The last case does **not** raise an undefined-variable error with ansible-core
2.21.4: the outer `enable_mealie | default(true)` also defaults the undefined
derived configuration to true. This is characterization, not a hardening change.
A different Ansible version must recheck these cases. A syntax result or template
comment alone does not establish switch behavior.

## Validation state

The credential-free `Mealie preparation checks` workflow compiles Python,
checks CLI help/fixture JSON, lints preparation YAML and runs the full S2 suite.
Relevant Mealie, Ansible entrypoint/example/task and validation dependency changes
trigger it. It never invokes `check.py --execute`. Exact-head CI evidence is
recorded on the PR; passing S2 does not pass V01.

No local checkout or local test execution is claimed for the connector authoring
workspace. Actual import/reopen/UI and zero-provider observations, registry and
running-image identities, effective capacity/writer fencing and environment
enforcement remain separately gated.

Requested non-runtime checks after local capability is bound:

```bash
python3 -m py_compile /ABSOLUTE/CORE/useful_scripts/mealie-migration/check.py
python3 /ABSOLUTE/CORE/useful_scripts/mealie-migration/check.py --help
python3 -m json.tool /ABSOLUTE/CORE/useful_scripts/mealie-migration/fixtures/ordinary-web.expected.json
```

Closed synthetic success cannot establish real web origin assurance, automatic
YouTube transcript acceptance, image security, upgrade safety or homelab recovery.
Those acceptance and release gates remain separate.
