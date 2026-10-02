# TrillionniumOS Desktop adversarial audit

**Date:** 2026-10-02, Asia/Shanghai

**Baseline:** main `1281d7ac8376bd8837fa63636420b0afc5586eda`

**Active plan:** `docs/DESKTOP_PLAN-2026-08-29-d6.md`

**Scope:** repository source, development documentation, host tests, portable
evidence checks and workflow consistency. This is a source review candidate,
not an installed-image, hardware, independent approval or release record.

Detailed technical development documentation exists. All twelve Cargo packages
have registered technical READMEs, supported by architecture documents, ADRs,
versioned schemas/contracts and hostile test corpora. Structural coverage does
not establish complete public API semantics, runnable examples, product
integration or fresh qualification. The new [development guide](../DEVELOPMENT_GUIDE.md)
maps actual implementation surfaces to their remaining acceptance requirements.

## Baseline observations

The latest main source is the September integration and cleanup. September 30
automation branches add migration workflows rather than newer development
specifications. The September 12 main desktop CI stopped at Rust formatting;
subsequent check, Clippy and Rust test steps were skipped. The baseline top-level
Python discovery passed 204 tests, but separate D1 discovery failed with one
failure and six errors. Passing selected validators therefore concealed broken
image workflow and optional target integration.

An authenticated GitHub API observation on this audit date reported main
unprotected and an empty repository ruleset list. This is a dated observation,
not an administrative attestation. No source edit can establish enforced review,
independent identities, protected signing or publication.

## Corrections in the review candidate

| Area | Reproduced defect | Correction and regression boundary |
| --- | --- | --- |
| Servo supervision | Reconciliation reopened crash lockout; stable acknowledgement reset crash history while unavailable; generation exhaustion retained a dispatchable actor; caught callback panic lost uncertainty | Permanent lockout, invalidate actor before checked generation arithmetic, acknowledge only stable Ready state, latch before dispatch; four failing baseline regressions now pass |
| Session control | Navigation ignored source and owner; completion discarded human custody; recovery accepted content/focus; expired lease entered IME | Phase/source admission, preserved human lease/control on completion, recovery and expiry refusals; targeted sequences and exhaustive bounded event traversal |
| Public errors and API | Custody diagnostics and backend strings reached public errors; required supervisor policy/result types were private | Stable redacted wire messages, explicit policy/transition reexports and external API compilation |
| Rust integration | Lockfile omitted browserd actor dependency; optional D1 example used removed peer field | Preserve registry pins, add missing local graph edge, pass explicitly attested qualification peer to fixture evidence |
| Rust documentation | Simulation examples imported the old crate; six compile-fail examples passed because imports failed; doctests were disabled | Correct imports, enable doctests, verify intended E0277/E0599/E0382 failures, run workspace doctests in CI |
| Host test isolation | Private receipt fixtures inherited writable umask; Python fixtures copied live Cargo output | Explicit private test directories, preserve insecure negative cases, copy source while excluding generated output |
| D1 image construction | Removed Cargo feature/bin/path and absent permanent workflows prevented execution | Use `fixture` and the Cargo example output, restore permanent D1/D2I workflows, complete invalidation inputs |
| AgentPort custody gate | Active verifier still required the old single-item fixture feature map and failed on the reviewed D1 qualification example | Bind the exact current fixture map, optional dependencies, explicit example gate and disabled product/attestor defaults; execute full verifier with hostile source mutations |
| CI source coverage | Selected top-level Python patterns omitted D1/transport and optional Rust targets | Run all three Python discovery roots, default/all-feature Rust targets and doctests on source head and prospective merge |
| Workflow identity | Old S10 depended on a deleted base and relabelled PR execution as manual; finalizers labelled canonical procedures as actual producers | Manual S10 uses its real event; permanent gates use merge/main; record native workflow path/ref/SHA/digest separately from canonical procedure and bind them to source |
| Portable evidence | D2I expected an obsolete D1 status; files could escape paths or be omitted from digest binding; source archive and process facts were not fully cross-checked | Consume current D1 v3, exact file inventory, strict bounded descriptor reads, role/source/producer/process consistency and finalizer self-verification |
| Update state | Noninteger/NaN health passed; publication could replace coordinator lease; renamed lease or staged file broke custody; temp collisions could remove existing data | Strict health types, reserved names, retained lease/stage identity, safe collision cleanup and explicit uncertain publication handling |
| Release packet | Signature verification could reread different packet/key/signature bytes from the parsed packet; size checked after reading; exponent overflow admitted infinity | Bounded reads through pinned descriptors, private immutable OpenSSL snapshots and parse the exact signed packet; real signature replacement regressions |
| Linux and guest acceptance | NaN deadlines, ambiguous paths, root ancestor links and writable nested parents weakened admission; reconciliation omitted durability/name checks; guest numeric checks misread multiple-digit fields | Strict time/path/parent admission, retained destination custody and reconciliation sync barriers; complete numeric field boundaries, exercised with positive and negative cases |
| Development docs | Earlier qualification baseline looked like current source coverage; Debian operations text remained a placeholder; supervisor APIs omitted | Separate historical qualification from present source, concrete packaging/run commands and product-wide coverage guide |

Workflow provenance follows GitHub's distinct native workflow ref and commit
variables. See the [GitHub variable reference](https://docs.github.com/en/actions/reference/workflows-and-actions/variables)
and [workflow source selection](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflows).

## Verification and interpretation

Rust 1.93.0, the repository's locked toolchain, passed formatting, locked
workspace checks, Clippy with warnings denied, 382 default tests, 392 tests with
all features and twelve doctests. The separate D1 fixture built in release mode
and passed its self-check; product daemon self-checks and dependency separation
also passed. Host umask 0002 works without weakening receipt custody.

Run all Python discovery roots and the source validators in `make check`.
Adversarial tests exercise actual finalizer subprocesses, detached signatures,
real filesystem custody and workflow graph identities. Synthetic evidence is
test input only. No test fixture is an actual image, hardware or release result.
All three Python discovery roots passed: 250 top-level, 41 D1 and fifteen
transport tests, for 306 total. Fourteen active source validators passed. The
historical D0C-04 seven-package snapshot validator correctly rejects the later
twelve-package workspace; its purpose and diagnostic are now explicit. YAML
parsing, changed shell syntax and `git diff --check` passed. The PR and
user-facing report record any subsequent CI limitations.

Iterations continued after initial fixes: independent review exposed signature
snapshot inconsistency, coordinator lease replacement, staging-file replacement,
workflow producer ambiguity and false-positive compile-fail examples. Each new
reproduced defect received a regression and another review. The first remote PR
run then exposed the stale active AgentPort fixture feature check; it was fixed
without enabling qualification features in the default product graph and added
to local aggregate validation. This establishes a
bounded review of these surfaces; it cannot prove that the complete project has
no remaining defect or possible improvement.

## Product completion and remaining acceptance

| Dimension | Assessment |
| --- | --- |
| Specification | Detailed foundation/module/architecture contracts exist; complete executable API/example and end-to-end requirement correspondence remains partial |
| Implementation | Twelve source packages and host/image/update mechanisms exist; services, workers and several product functions remain planned or scaffolded |
| Product integration | The executable browserd still runs scaffold/self-check commands; product AgentPort remains fail-closed without its promoted handler; the installed daemon to Servo to durable response path is incomplete |
| Qualification | Current local source tests pass; historical headed/host evidence does not qualify the new source, installed image, hardware or release |

Do not assign an overall percentage without a defined denominator and weighting.
Twelve of twelve module READMEs measures Cargo documentation coverage only.

The remaining ordered work is the installed AgentPort/BrowserActor/Servo/receipt
vertical slice and recovery UI; native compositor/input/IME; signed-app lifecycle;
trusted consent, typed capabilities, TaskFlow cancellation/budgets and actual
resolver/TLS/namespace egress enforcement; fresh exact image qualification;
externally rooted installed A/B update and recovery; and independent hardware,
performance, endurance, power-loss, key-custody and protected release evidence.

Receipt recovery has explicit segment/chain bounds, but streaming recovery,
archival/quota policy, resource growth and independently protected rollback
anchors still need product acceptance. A proposed async architecture is not a
substitute for measuring capacity and implementing bounded concurrency in the
actual service. No accepted full-product performance SLO is demonstrated here.

Preserve the existing machine qualification ceiling and default-disabled
production state. Independent review, protected promotion and exact-main/image
reruns remain prerequisites under [CONTRIBUTING](../../CONTRIBUTING.md) and the
[closure plan](../plan/IMPLEMENTATION_CLOSURE_PLAN.md).
