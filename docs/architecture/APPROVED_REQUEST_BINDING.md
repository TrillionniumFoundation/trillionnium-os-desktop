# Approved request replacement inside one bounded actor

G2's approved native startup expects Health, Create, Observe and Snapshot to
arrive from separate actual Agent connections. The original connection's
process exits after its durable terminal response. A fixed PID/start-time
`PrincipalBinding` then rejects the next otherwise root-approved Agent. Keeping
the old Agent alive would conceal this lifecycle defect.

The additive implementation supplies a private binding proof while consuming
the same `ApprovedAgentReceivedStream`. It does not change the existing fourteen
approved-policy APIs or the fixed-PID legacy/raw actor path. No caller principal,
snapshot, UID, executable digest, table or boolean can substitute for the opaque
`ApprovedAgentRequestBinding`. The [versioned API contract](../../contracts/approved-request-binding.v1.json)
describes the additional source API. The source validator is finite correspondence,
not execution or approval.

The proof retains the actual stream's SO_PEERCRED identity, initial attestation,
a duplicate of that original pidfd, original Control verifier and source guard.
Actual default `/proc` refresh checks identity and executable on that retained
incarnation. The Control verifier retains the original root path, socket cookie,
Control process and paired approval. Dropping the proof retires every read-only
verifier of its request; retaining a verifier cannot reset that retirement.

`ApprovedAgentSession` retains the first selected root document and first
absolute Instant. It deliberately holds no old request's Agent or Control lease.
A completed request's death gives it no remaining execution authority and is
not a precondition for a later valid replacement. Both old and new retained
documents must remain current. All two-role fields compare exactly: UID, GID,
unit, cgroup, executable SHA256 and semantic principal for each role, under the
closed thirteen-field schema. A separately valid different Control principal
also refuses, even if the Agent principal matches. Observed document drift
permanently retires that document; restoring bytes does not revive it.

The approved actor constructor derives its principal solely from this proof.
A legacy actor has no approved session and cannot gain one retroactively.
Replacement checks creator PID, current own original pair and both selected
sources before changing only the mechanism PID/start binding. PageOwner,
incarnation, SessionMachine, session/WebView counters, shared observer and
durable receipt history stay in the same actor. The coordinator additionally
requires Ready, no storage failure, no pending reconciliation and no unresolved
journal. The actor refuses pending preparation/cancellation registrations,
active Agent/Control authority and poisoned runtime. Rust's exclusive mutable
borrow and the coordinator's existing Rc thread confinement serialize replacement
with dispatch. Every external observation precedes the single binding assignment;
subsequent preflight repeats the original request checks before receipt admission.

Every controlled production actor entrance also checks the current opaque
request's pair liveness, root source and first ceiling. The existing controlled
dispatcher then performs full executable/identity refresh before admission and
effect. It borrows only its private original AttestedPeer and Control verifier
through `with_original_pair`, with fixed default procfs and an effective deadline
no later than that original scope. Caller-supplied attestor, snapshot and
custodian parameters apply only to legacy actors and supply no approved
authority. The cheap gate does not claim full attestation. An approved actor refuses
uncontrolled `handle_attested` and `preflight_attested` entrances; a bare call
cannot reuse a retired request or renew its first ceiling. Native callbacks continue
to carry their original request/control verifiers and must recheck immediately
before effect. No global relaxation of `verify_dispatch_attestation` occurs.

`consume_with_request_binding` consumes the original stream and invokes its
callback once after current source, pair and retained checks. Its callback data
are composition values, not action permits. `start_session` takes only the proof
and captures its existing ceiling. `verify_for_session` compares both sources
and returns actual admitted identity data only after current-pair verification.
`verifier_for_session` returns a read-only, non-cloneable wrapper after the
same sources, ceiling and original pair-liveness checks. Its `verify_for_session`
performs full readback; `ensure_pair_alive_for_session` is the cheaper controlled
entrance gate. `with_original_pair` borrows the actual retained original sources
for one callback, with scope checks before and after; its data do not authorize
an action, and dispatch must refresh those same sources. `start_session` produces only root-source metadata after original
pair-liveness checks; constructing or rebinding an actor separately requires
full current-pair readback. Refusal preserves the original `ApprovedPolicyError` distinction:
expired original scope, changed creating process, changed root source or refused
peer. Actor methods map failures to `AgentPortError::Handler`; product composition
maps them to `PeerRefused`, `DeadlineExceeded`, `StorageUnavailable` or
`RecoveryRequired` at its existing entrance. Failed replacement performs no
runtime command, receipt admission or PageOwner mutation.

The actual host test is executable with:

```sh
CARGO_PROFILE_TEST_DEBUG=0 CARGO_PROFILE_TEST_OPT_LEVEL=1 CARGO_BUILD_JOBS=2 \
  cargo test --locked -p hepta-browserd --test approved_request_binding_kernel
cargo test --locked --release -p hepta-browserd --test approved_request_binding_kernel
python3 tools/verify_approved_request_binding.py
python3 -m unittest discover -s tests -p test_approved_request_binding.py -v
```

Its source callback backend is synthetic. Its prelaunch fixture selects a real
root transient unit and known owned ELF before launching actual Control and
Agent processes. It uses default procfs and actual socket/pidfd custody. It
finishes and reaps every completed Agent before creating the next request, then
checks the same session and own managed receipt history. Negative cases cover
independently preselected principal differences, both policy sources' irreversible
drift, new original pair death, real exec, fork, prepared conflicts, raw actor
retrofit, retired proof/old handle and later or caller-renewed deadlines. The
real exec case also supplies attacker procfs still claiming the old ELF and a
different live original custodian; approved controlled preflight refuses it
using its privately retained actual pair. The
unchanged original native six-case target still requires actual exact-PIN Servo
execution on this source; host callbacks cannot qualify it.

The first Instant is an upper bound of twenty seconds, never a renewable budget.
Synchronous root/procfs/hash operations can consume it and refuse. This API does
not implement a persistent installed owner, a 60-second health window, desktop
startup, firmware/root approval, signing or production readiness. Default
activation stays disabled. Original kernel/native fixture budgets and historical
qualification records retain their existing boundaries.

The first command uses the repository's already declared CI test build profile;
the release command uses its existing optimized release profile. Unoptimized
debug with debug symbols can consume the unchanged twenty-second scope hashing
its larger ELF. Such a timeout is an actual failed object, not a skipped case or
qualification for another build profile. No build profile or fixture budget is
changed by this package.
