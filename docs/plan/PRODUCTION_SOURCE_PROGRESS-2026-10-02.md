# Production blocker execution record: source candidates

Snapshot date: 2026-10-02. Accepted planning authority remains
[IMPLEMENTATION_CLOSURE_PLAN.md](IMPLEMENTATION_CLOSURE_PLAN.md), active d6 and
`manifests/project-state.v1.json`. This record changes no integrated completion,
qualification, protected review or release field. Main inspected during this
work was `1281d7ac8376bd8837fa63636420b0afc5586eda`.

The operator confirmed that fixed hardware/BOM, independent builders/reviewers
and production signing/offline-HSM facilities are not provisioned, and requested
source and CI work first. Disposable cryptographic test keys and collaborating
code-review agents provide none of those independent release identities.

## Review objects and implemented source

All review objects below are Draft candidates. PR130 supplies the shared audit
base; successors target its review branch unless their explicit dependency or
image workflow needs another base. Updating a base invalidates an
older synthetic merge. Required identity checks must reject it and rerun on a
fresh event/object; they must not be weakened to accept a stale parent.

| Work | Review object | Implemented behavior | Remaining closure |
| --- | --- | --- | --- |
| G1 foundations/CI and hostile audit | [PR130](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/130) | Runtime owner/cancellation/recovery fixes; receipt filesystem custody; strict release signature snapshots; evidence provenance; restored exact image workflows and bounded failure diagnostics | Designated independent review, protected merge, fresh exact-main gates |
| G2 request/recovery composition | [PR133](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/133) | Original AF_UNIX attestation, queue-wide deadline/cancellation, concrete engine-thread actor/coordinator, semantic preflight, durable intent/terminal facts before response, complete-chain deduplication and unresolved restart refusal | Installed native startup/owner, per-connection service handoff, approved cross-UID executable custody, principal policy and durable trusted recovery decisions |
| G3 native input/chrome | [PR131](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/131) | Actual Winit focus/content ownership, generation-bound callbacks, repeated IME context, causally bound selected-process SIGKILL evidence; actual native held-gesture withdrawal refuses further input/reconstruction and requires a fresh Servo owner | Complete owner replacement, product PageOwner integration, layout/scaling/clipboard, actual Chinese OS IME and trusted approval/handoff UX |
| G5 signed app admission | [PR134](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/134) | Actual externally pinned Ed25519 using immutable verifier inputs; complete bounded archive/index checks; immutable assets for exact synthetic HTTPS origins; current publisher-scoped trust/revocation and restrictive response headers | Installed origin interception, browser CSP/CORS/cache enforcement and protected policy/root delivery |
| G5 TaskFlow/capabilities | [PR135](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/135) | Typed proposal/resource binding; actual signed permit admission; original budgets/cancel/handoff; durable task reservation and single-use grant consumption before adapter entry; restart/fork refusal | Trusted native approval/signing surface, retained-target final native effect gate, product terminal receipts and durable recovery/revocation |
| G5 controlled observations | [PR136](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/136) | Real approved DoT, all-answer address policy, actual TCP peer and TLS identity, bounded GET/redirect observations under one deadline; ambient proxy/CA, synthetic DNS fallback, fork and clock-regression refusal | Browser network namespace plus every supported resource-class intercept; external effects and durable indeterminate reconciliation |
| G5 local app storage | [PR137](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/137), based on signed-app PR134 | Concrete private leased principal/origin partitions, verified immutable packages, stable version floor, same-schema updates, uninstall/data tombstones, durable policy pins/revocations, no-replay operation records and unresolved-owner refusal | Native engine storage binding, authenticated current time/policy delivery, schema migration, safe operator recovery/archival and protected rollback anchor |
| G6 signed update/recovery | [PR132](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/132) | Actual externally rooted signature/full-image checks, inactive private regular-file publication, issued health permits, concrete journal reconciliation, sealed verifier inputs, concrete authority types and fork/thread/lease custody | Production roots/clock/floor, installed block-slot/boot/health/recovery adapters, durable product journal wiring, QEMU update and physical cutpoint evidence |
| G6 durable update ownership | [PR140](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/140), based on PR132 | Complete durable intent before concrete inactive staging, full retained-chain/image readback, issuer-bound results, source boot policy and unclean/nonterminal restart quarantine without replay; integrated private descriptor-owner cleanup | Installed owner/service journal wiring, boot/health/commit/rollback and trusted operator recovery; protected roots/time/floor and physical power-loss evidence |

The combined branch `codex/production-source-integration-20261002` exercises
these candidates together and registers the top-level Python mechanisms with
their source-defined public signatures, technical contracts and actual test
sources. Its checks are integration of source candidates, not installation or
promotion of them into main.

## Demonstrated hostile failures and repairs

The audit used actual cryptographic operations, live sockets, ordinary files,
faulted fsync/replacement boundaries, service/image CI and real fork probes.
These were reproduced defects, not fabricated hashes or pass-status inputs:

- D1's distinct-UID qualification server could not read the peer's live
  `/proc/<pid>/exe` under kernel ptrace policy. Its explicitly separate fixture
  now binds a root-owned qualification path while retaining live peer checks.
  The production attestor still requires live executable observation; broad
  ptrace capability or loss of UID separation is not accepted closure.
- Chrome motion left a stale content pointer, and old native callbacks could
  affect a replacement generation. The ownership/callback checks were repaired
  and the real Servo compiler caught an event constructor mismatch, subsequently
  fixed using the immutable upstream API.
- The pinned engine offers no mouse cancellation primitive. A synthetic Up can
  click, and blur/leave/drop do not prove its global pressed-button mask reset.
  Actual matching Up remains unsettled until its current input acknowledgment;
  ownership withdrawal with an unsettled gesture fails closed, drops the owned
  content handle and refuses automatic reconstruction in that Servo instance.
  The earlier native passing runs do not qualify this new withdrawal behavior.
- Pre-dispatch cancelled/expired TaskFlow IDs could reopen and renew budgets;
  fork copied the parent's approval and cancellation state. Durable reservations
  and creator-PID authority checks now refuse both reproduced paths.
- Mutable update-verifier files allowed a real wrong signer to produce an
  admission claiming the approved key. Sealed memfds bind all verifier inputs.
  Callback subclasses cannot substitute a shaped admission or persistence fact.
- A fork child could unlock an update parent's flock lease and commit its
  copied health permit after the parent observed a failed boot. Descriptor-only
  cleanup and creating-process/thread authority checks reject those paths.
- Real interrupted update directory closes could close a foreign reused FD and
  leak the successor; acquired leases and private helper/scan handoffs also leaked
  on observed Python interruptions. Detach-first cleanup, empty-before-open
  private owners, descriptor-only GC and three wrapper owner-protocol consumers
  repair those paths. Post-attempt cleanup keeps the original pending transaction
  and typed recovery state. Joint 78 core and 41 wrapper tests pass, including real
  close/reuse, constructor/return and double-interruption cases. These specific
  tests do not prove every raw C-return-to-bytecode window.
- A forked Rust managed journal could mint durable child facts while the parent
  writer stayed live. The G2 successor binds live journal/coordinator/fact
  authority to its creating process and preserves the parent's lease on child
  descriptor cleanup.
- Update publication/reconciliation and app-storage mutation interruptions need
  durable uncertainty boundaries. They must preserve evidence and refuse replay.
  A callee cannot prove its caller received a returned value: an already known
  durable local commit with a lost response instead retains deduplication and
  version authority. No caller acknowledgement boolean mints a durable fact.
- Downloaded S08 checksum output included the checksum file itself and absolute
  runner paths. All other actual members verified, but the empty self-digest
  made complete portable verification fail. The collector now excludes itself,
  writes relative paths and verifies them. Actual shell packaging regressions
  exercise repeat collection, relocation and tamper rejection.
- The D1 fixture forwarded raw attestation errors into journald, and its
  successful stdout also carried raw peer identity JSON. The actual CodeQL UID
  finding was at the latter sink. Operational stdout/stderr now take payload-free
  enums and emit fixed summaries/categories. Explicit no-follow, exclusive
  mode-0600 qualification output retains the required PID/UID/GID facts; the
  host collector uses that file. Actual CLI and output-sink regressions check
  identity preservation, public redaction and overwrite/link refusal. Fresh
  CodeQL is required for this successor.
- The offline D2I verifier accepted false chrome survival and insufficient or
  wrongly typed input counts even after all artifact hashes were rebound.
  It now independently requires typed true chrome recovery, exactly fifteen
  sent inputs (twelve ordinary plus three IME events) and a strict integer floor
  of three handled callbacks. Twenty
  complete rewritten negative packets fail the actual verifier.

## Actual lower-tier evidence

D1 run [36994844511](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/36994844511)
passed for candidate head `6b73ae48b01fe49ff9748c96a668c61bccaf3164`, tested merge
`3471b98d098102e03f5e4108481cb2fe46d028ec`, tree
`c6194d3441e1cd733ce2e3cdfd53957f4ab1332b`, base main above. The downloaded
portable packet independently verified 67 outputs and 419 source inputs. Its
`promotion_authoritative=false`, fixture handler and `servo_started=false`
limits remain intact. Later source changes require fresh appropriate evidence.

Native run [36998181245](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/36998181245)
passed for head `6b0b41f8af300db90201906faaba5029abae375a`, tested merge
`484ab5757b20bb1f57fd8474c639209e56eb1424`, tree
`786952a03c9a9a8edd463cbdbf78c5c0da3d057e`, base
`bb6e4a66ba06de3c25ed95a83cb76a13936aae0d`. Downloaded pixels, content input and
selected PID/start-time fault records were rechecked. This is
`PASS_HEADED_LOCAL_FIXTURE_ONLY`, with product/BrowserActor/AgentPort activation
false. Fresh-base native run
[36998950853](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/36998950853)
also passed; the separate general prospective-merge checks accepted its fresh
object. Neither run qualifies actual Chinese OS IME or an installed desktop.

The integrated source head `22b59aa39012f8b5ba4052797ef110ff9a13172f` passed
S08 run [37001916912](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/37001916912)
and native run [37001917005](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/37001917005).
The downloaded evidence binds tested merge
`002f3c00844bcf132a36203fadae8226bb2838a5`, tree
`566ad38bb37666ff92295731bb968616e1cb69f8`, base `bb6e4a66ba06de3c25ed95a83cb76a13936aae0d`.
Independent rechecking matched five native PNG hashes/sizes and both causal
fault-record hashes. S08 reported ten AgentPort requests, nine actual Servo
commands and thirty committed receipt records, with zero unresolved receipts.
Its checksum self-inclusion defect above remains a packet limitation of that
specific run. These earlier passing source objects do not qualify later fixes.

Native run [37005158637](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/37005158637)
passed the full positive/requested-SIGKILL corpus and all three new held Down
withdrawals at head `f9b1ae7f51010c7237a72c9f1179cacc53b44107`, tested merge
`616b7c8106f2cdcc9222e05be95d0aae10ae8a81`, tree
`b038bd2474b00bc534c694a3ed02076978bfa2b6`, base `bb6e4a66ba06de3c25ed95a83cb76a13936aae0d`.
Independent packet rechecking matched five PNGs, two fault hashes and twenty-one
raw negative-fact hashes. All three cases observed actual Button1 held, exactly
one admitted Down, exit 1 and no synthetic Up, plus removed owned WebView handle
and false engine-reset/automatic-reconstruction claims. Cleanup identity and
listener-disappearance facts also passed. This is native X11/XTest candidate
evidence; it establishes no physical input hardware, safe mouse cancellation,
full owner replacement or installed product UI.

D2I run [36994844517](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/36994844517)
built the integrated image but failed guest acceptance. Earlier diagnostics
omitted guest failure facts because extraction followed the PASS-only branch.
The repaired guest/host failure path keeps bounded journal and runtime records;
run [36997938015](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/36997938015)
failed with `TRILLIONNIUM_D2I_ACCEPTANCE_FAIL:missing_servo-content-recovered.png`.
The newly retained diagnostics showed generation one timed out after twelve
sent events and only two handled callbacks, before fault injection. Readiness
and paced exact-ID acknowledgments now sequence those same original inputs;
generation replacement resets its controls, and chrome survival is derived
from an actual presented replacement frame. [PR139](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/139)
targets main to run its image workflow. Its actual QEMU result and fresh exact
source proof remain required for each later change; the acceptance criteria
were preserved. Candidate run
[37002984433](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/37002984433)
passed actual integrated QEMU acceptance at head
`bfe2664a52191ff6327e2cbd253ab02ce1527401`, tested merge
`3037319e595ee1dab7b6eec432ab39278b2c09d2`, tree
`66801d4a60523ad01df77c653773f91d44dbf30f`, base main above. Independent selected
fact checking matched eight output hashes and observed fifteen sent/handled
events, three IME events, actual SIGKILL, zero processes and a distinct replacement.
Complete portable checking now independently verifies ninety outputs and 419
source inputs, with image digest
`dac7dcf3826c3f3cbae40695268af87ad13814673764b1bbf5a411fe71850e72`.
That candidate's separate stdout CodeQL finding still blocked promotion.
The logging and fifteen-event offline-verifier successor is head
`cc210cb051ec179c022cd814cca41af94f91925f`; its actual CodeQL check passed, while
fresh image workflow
[37008295707](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/37008295707)
remains pending at this snapshot.

The intermediate `3c3f20b` image run
[37005677335](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/37005677335)
failed with runtime exit 101, dependent acceptance not started and host timeout.
Its bounded packet confirmed absent persistent runtime/acceptance logs; the
specific panic cause remains unobserved. Startup-handshake and independent
failure-diagnosis/clean-poweroff source work is a separate follow-up; this
document does not turn that failed run into a passing image.

## Conditions still blocking production

G0 independent protected promotion and G7 facilities remain unconfigured. Pure
source work also remains for installed G2–G6 integration: native product startup,
trusted policy/approval/recovery surfaces, complete renderer/network confinement,
device/portal/storage adapters and actual boot/update orchestration. The product
executable and AgentPort remain default disabled until those boundaries and
their independent acceptance are satisfied. No `all_gaps_closed` or production
readiness flag is advanced by this work.
