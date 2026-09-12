# d6 implementation closure plan after the module audit

**Plan revision:** `2026-08-29-d6`
**Status:** execution/acceptance plan, not a completion or release record
**Audit baseline:** main `854d0341eaba43408edc014297ea8af43ffcc87e`
**Candidate inspected:** `8bc2ea084c2ce69ba83ad277418aa20a7865d69b`

This plan refines the active d6 plan and PR73 decomposition ledger. It does not
merge the frozen PR73 candidate, promote unmerged successors, replace machine
truth, assign independent reviewers by assertion, or mark any product gap closed.
Every baseline above is a historical immutable source object, not a live claim.

## Completion dimensions and evidence

Report specification, implementation, integration and qualification separately.
Documentation coverage measures only specification coverage. A Cargo package
inventory does not cover every service, Python adapter, image recipe, workflow,
external facility or user-facing product function.

For each implementation change, bind requirement ID, owning module/service,
actual public API/configuration surface, exact test names, workflow, immutable
source/tree, applicable image/input digests, evidence tier, explicit non-claims
and independent review. An existing test file or digest-shaped string is not
proof that a requirement ran successfully. Failed, skipped and unobserved cases
remain distinguishable. Keep evidence outside the mutable implementation claim.

## Ordered work and acceptance

| Order | Work and owner class | Required implementation/acceptance | Closure dependency |
| --- | --- | --- | --- |
| G0 | Repository administration / security, issue #76 | Live protection/rulesets and protected environments; exact required checks, current CODEOWNER review, independent approvals, no routine admin bypass; authenticated readback and safe positive/negative probes | Administration API access and independent identities; PR110 source alone is insufficient |
| G1 | Source documentation / contract owners | Generated module index, active-plan precedence, corrected storage permissions, executable regression corpus; extend public API/schema/example correspondence during each module change | Exact-head and prospective-merge CI, independent review and protected promotion |
| G2 | Product runtime / identity / persistence, issue #86 | Installed-shape daemon path AgentPort -> browserd -> BrowserActor -> exact-pin Servo -> durable receipt -> response; execute the complete request/recovery fault matrix | Accepted S02–S08 boundaries; no fixture/mailbox substitution |
| G3 | Linux compositor / input, issue #87 | Real surface/focus/input/IME integration; trusted chrome survives crash; generations, scaling, clipboard and human preemption exercised | G2 plus actual native event-loop tests; endpoint connectivity alone is insufficient |
| G4 | Image / installation, issue #88 | Build the current product into locked Debian/QEMU; verify PID1, install inventory, explicit qualification activation, default-disabled final product, restart/no-replay and exact image binding | G2/G3 plus reproducible inputs; older D1/D2I evidence does not transfer |
| G5 | Trusted apps / TaskFlow / capability / egress | Versioned app trust and storage lifecycle; typed permits and approval UX; task cancellation/budgets; enforced resolver/TLS/peer/redirect/namespace path and bypass corpus | Relevant d5/d6 application and security requirements, separate reviewed code changes |
| G6 | Update / recovery | Externally rooted signature verification before slot write; complete-image verification; durable A/B state, boot/health commit, rollback floor, expiry and recovery tool; installed fault matrix | Accepted G4 image lineage and journal integration; source state machine alone is insufficient |
| G7 | Hardware / build / signing / release | Independent builders, fixed BOM, actual endurance and non-graceful power removal, key-custody ceremony, separated roles and protected publication | External facilities and exact immutable release candidate; verifier code creates none of these facts |

G0 gates promotion, not harmless development on isolated review branches. Work
may continue without widening activation or release authority. Successors remain
Draft until their actual prerequisites, exact-object checks and independent
review are satisfied. No self-approval or bypass substitutes for that sequence.

## G1 document-quality follow-through

The structural README validator and the new coherence checks are necessary but
not sufficient. Each affected public API needs a versioned signature inventory
and argument/precondition/error semantics. Each machine schema needs executable
positive/negative vectors and domain/wire conversion tests. Compile runnable
examples and test operational permission/configuration examples against the
actual API. Avoid filling a minimum word count with repeated non-claims.

Use the generated Cargo index for package coverage. Track non-Cargo subsystems
in their own source contracts and this acceptance table until a reviewed common
inventory exists; do not label unimplemented services as documented-and-complete.
The older `WORK_PACKAGES_AND_GATES.d5-historical.md` is a d5 planning input wherever d6 or the
S01–S12 decomposition supersedes it, not a competing current schedule.

## G2–G4 integration details

Use [Request execution and recovery](../architecture/REQUEST_EXECUTION_AND_RECOVERY.md)
as the cross-module fault and ownership checklist. Capture actual product entry
points and IPC, not isolated library aliases. Define one engine-thread owner,
one PageOwner, bounded queueing, cancellation and exactly-one completion cleanup.
Prove old session/WebView/frame/node references are rejected after reconstruction.

Preserve default-disabled production activation. A test-only profile may enable
the reviewed test path, but its marker, fixture binaries, debug endpoints and
qualification-only units must not remain in the final product install map.
Repeat the path after service crash and system reboot on the same accepted image.

## G5 authority and network details

A syntax-only HTTPS validator does not enforce actual egress. The implementation
must bind approved DNS answers, connected peer, TLS identity, redirects, session,
origin, permit and receipt in one operation. Test direct-socket/proxy bypass,
private/link-local/metadata addresses, IPv6/rebinding, workers/service workers,
iframes, prefetch, downloads, WebSocket and other supported protocols. Disable
unsupported protocols explicitly rather than silently relying on a proxy setting.

Define signed-app bundle/manifest format, trust-root rotation and revocation,
offline verification, origin interception, CSP/CORS, storage partitioning,
upgrade/downgrade, data migration and uninstall. Define TaskFlow proposal,
approval, execution, cancellation and human-handoff states. Untrusted page or
model output must never mint or broaden a permit. Implement and test the trusted
approval surface, not merely the policy data types.

## G6 recovery and operational usability

Pair each fail-closed condition with bounded diagnosis and a safe operator path.
Disk full, corrupt history, sync uncertainty, indeterminate operations, identity
loss and crash-loop lockout must preserve evidence and present actionable trusted
UI. Specify who may authorize reconciliation and which exact facts clear a latch.
Do not automatically replay, delete history, recursively repair authority paths
or mistake clearing a latch for restarting an operation.

Design receipt archival/checkpointing before capacity exhaustion becomes routine.
Retain authoritative deduplication and reconciliation facts. Whole-directory
rollback resistance requires an independently protected monotonic anchor; an
unkeyed local chain alone does not provide it. Test each change in the installed
filesystem and separately on the qualified physical hardware.

## G7 facilities and frozen qualification objects

Freeze an immutable release-candidate source/image/input/BOM tuple for expensive
qualification. A moved main or changed relevant input invalidates evidence under
the current policy; do not relabel old artifacts to avoid reruns. Provision real
independent builders, test hardware, power control and approved signing custody.
Record actual observations. Never manufacture distinct people, elapsed endurance,
physical cuts, production signatures or protected-environment readback in JSON.

Collect performance baselines early: trusted first-frame, input, observe/act,
receipt-sync and recovery latency, RSS/FD/PID, queue depth and resource growth.
Review measurement method, samples and percentiles before approving hardware
thresholds. CI runtime is not user-experience latency or hardware endurance.

## Closure record required per gap

A gap closes only after its implementation and hostile tests exist, exact head
and prospective merge pass, the bounded digest-bound evidence is verified, fresh
independent review accepts the object, protected merge succeeds and exact-main
regression passes. Installed/hardware/release gates additionally require their
own evidence and external authority. Until then use the actual blocked/candidate
state and name the missing prerequisite. Never set `all_gaps_closed=true` merely
because this plan, a validator or a pull request exists.
