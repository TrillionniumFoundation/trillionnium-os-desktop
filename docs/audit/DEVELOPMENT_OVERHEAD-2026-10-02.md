# Development overhead audit

Baseline: PR #130 source head `bb6e4a66ba06de3c25ed95a83cb76a13936aae0d`.
This is a source optimization candidate, not integrated-main or installed-image
qualification. PRs #131–136 remain separate; their changes are not absorbed here.

## Coverage and decisions

The baseline inventory contains 419 files (3,458,197 bytes). Review covered the
12-package Cargo graph, daemon/runtime and receipt paths, all 21 workflow files,
58 tool files, Python tests and discovery roots, packaging/Linux/update surfaces,
39 contracts, 29 manifests, and documentation obligations. This is inventory,
call-site and targeted semantic review, not a claim of exhaustive proof over
all source lines or absence of defects.

- Aggregate validation ran 113 root tests twice: the focused validation/truth
  subsets were repeated by full Python discovery. `make check` now uses the
  complete discovery once. Standalone `make validate` and `make truth` retain
  their focused regressions. Tests cover combined goals, parallel dry-run plans,
  every original validator, and the complete Rust feature/target/doc matrix.
- Journal rotation consumed its writer but cloned its full receipt-progress map.
  It now transfers that owned map, retaining all custody, sealing, chain, quota,
  and duplicate-admission checks. A regression observes retained allocation
  identity; another checks failed rotation preserves both journal and collision
  bytes and allows explicit reopen without readmission.
- Receipt envelope export and authoritative validation deep-cloned every
  lifecycle record merely to group them. They now group immutable references:
  N full-record copies per grouping pass become zero. The existing public
  slice API remains unchanged. Frozen canonical bytes, interleaved admission
  order, malformed lifecycle and privacy/identity mutation tests cover the path.
- Twelve module change-protocol paragraphs required metadata/contract/README
  rewrites even when unchanged. They now require corresponding updates when an
  interface, behavior, inventory or claim changes. Security review, hostile
  regressions, exact-head checks and exact-main qualification remain mandatory.

## Measurement and verification boundaries

On the same checkout, one paired execution of all Python commands from each
Makefile graph took 17.396 seconds before and 10.014 seconds after (42.4% less).
The benchmark ran every discovery root even after failures, so it measured the
same scope. It is a local orchestration measurement, not a product performance
SLO or statistically generalizable benchmark. The deterministic saving is 113
duplicate test executions; the removed subset took approximately 7 seconds.

The local environment prohibits Unix sockets. Three unchanged Linux Wayland
custody tests fail with EPERM, including when execution escalation is requested.
They are not skipped or relaxed. D1 and transport discovery pass. Exact Rust
1.93 formatting, Clippy, default/all-feature tests and doctests must be checked
on this candidate's hosted CI head; local syntax formatting used an available
newer formatter and is not locked-toolchain qualification.

## Retained safeguards and remaining scope

Prospective-merge testing is not redundant exact-head testing. Historical
qualification validators, closed-source inventory, compatibility facades and
legacy reference implementations have active callers or historical evidence
roles; they are retained. CI command duplication is not removed without proving
its required context and diagnostic coverage remain represented. No workflow,
source-admission check, signature/update/custody rule, schema, dependency, or
historical evidence record is changed.

The baseline's integrated-image run failed because the guest recovery screenshot
`servo-content-recovered.png` was missing. Its CodeQL check also reported a high
alert whose location was unavailable through the connector's annotations API.
These baseline findings remain blockers, not grounds to remove qualification.
The optimization needs independent immutable-head review and does not establish
installed Servo, QEMU, hardware, signing, release readiness or stack integration.
