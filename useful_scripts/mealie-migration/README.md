# Mealie ordinary web recipe fixture

This is inert preparation for the ordinary-import case V01 at the accepted S1
application seam. It contains no importer, server, deployment change or credentials.
The fixture and oracle are synthetic; they contain no household content.

## Fixture and independent oracle

- `fixtures/ordinary-web.html` contains a visible recipe and complete JSON-LD.
- `fixtures/ordinary-web.expected.json` is a literal recipe oracle authored before
  application execution. It is not generated from an import result or from parsing
  the HTML. A later test must compare the reopened saved recipe with these literals.
- `https://recipes.test/ordinary-web.html` is the designated synthetic provenance.
  The reserved test hostname has no public fixture service. Do not use a real
  recipe website as a substitute.
- There is deliberately no image, note, redirect, remote script or stylesheet.
  Image/helper retrieval and additional workflows need their own approved cases.

Formatting normalization is acceptable when meaning survives: for example, a
fraction may display as 0.5, and a duration may display in minutes. Require every
ingredient's quantity, unit and identity, the supplied yield and times, and the
three instructions in order. The saved recipe's provenance must equal the fixture
URL. The title alone, a successful HTTP response, or an importer log is insufficient.
No source image or note is supplied; record any added content for review rather
than treating invention as fixture truth.

## Pending application test

Once an isolated evaluation target and execution are authorized:

1. Record the test-source commit, SHA-256 hashes of both fixture files, candidate
   OCI index/ARM64 identities, configuration revision and authorization reference.
2. Have the environment owner serve the exact HTML at the designated URL inside
   the closed evaluation environment. DNS, destination mapping, certificate trust
   and egress denial must follow the approved control design. Do not add HTTP
   address exceptions or weaken application address checks to make it reachable.
   The environment must have no Internet or real-provider route.
3. Through the actual candidate UI and its supported authenticated API, perform
   exactly one ordinary import with AI disabled. Use a synthetic account and a
   disposable synthetic data target. Observe the controlled fixture destination
   and confirm no provider use.
4. Reopen the saved recipe through the UI/API and compare its content with the
   independent oracle above. Record missing, changed or invented fields and the
   actual import mode. Do not inspect database rows as a substitute for this check.
5. Record the outcome and evidence limits in the private evaluation record.
   Public Core holds this reusable fixture, not raw logs or account metadata.

Do not run a local server or start the candidate merely because this fixture
exists. The environment owner must establish the approved closed-network controls,
and the existing finite-work profile applies. No runtime permission is conveyed by
this document.

## Validation state and next development step

The application case has not run. No red/green result, deployment render,
registry identity verification, image scan or migration/recovery result is claimed.
The ordinary-import case cannot be marked complete from fixture review.

The next development step is one executable V01 test at S1 using the authorized
target. Record the initial result before changing configuration. If it already
passes with upstream defaults, retain those defaults. If a change is needed, use
an observed failing result and the smallest supported change needed to pass.
Record the exact entry command and protected credential reference with that test.
A test runner is not yet provided; do not report the proposed `check.py` command as
runnable.

Local syntax and fixture checks have not run; the current workspace has no bound
Core checkout. Once a bound checkout is available, inspect the JSON/HTML and run
the repository's applicable checks. These checks cannot pass V01.

Candidate identity inherited from the accepted specification: upstream v3.30.0,
source `9552df62118224a377d9c9b0a62706a62220ab86`, OCI index
`sha256:90f83da6f3ab0a421efc827118a556168573930105f13fa3321768f42163d784`,
expected linux/arm64 child
`sha256:8dbe3fd73896e77c797f7029201823fa8b1ddbc725059f496cf884f06c9916da`.
These are expected identities to reverify, not newly obtained registry receipts.

Closed synthetic success would not establish real web origin assurance, automatic
YouTube transcript acceptance, image security, upgrade safety or homelab recovery.
Those acceptance and release gates remain separate.
