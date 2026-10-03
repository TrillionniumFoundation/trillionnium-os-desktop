# Persistent Source / original request bridge v2

This additive source profile consumes the existing nineteen-field `ApprovedServiceOwnerBinding`. It gives one original service a sequence of separate original Control/Agent requests. It does not implement an Actor, PageOwner, coordinator, journal, native health check or installed daemon. The default browserd entry remains unchanged and production activation remains disabled.

`ApprovedServiceRequests` directly owns the non-cloneable original Owner binding. Its readonly session verifier retains exactly the same Source and Owner verifier, and cannot keep the original custody alive after Requests drops. There is no Source reopen, policy generated from observed process data, supplied procfs root, constructor from a principal or snapshot, or constructor from a future absolute Instant.

Each `bind_control` consumes one existing `RootPathControlConnection`. Its original deadline, root pathname custody and actual endpoint move into the private service factory. The factory derives the Control policy from the same root-selected Source, performs real default `/proc` Live attestation, and checks Source/Owner and current Control before and after the actual challenge. All five observable role fields (UID, GID, unit, cgroup and full ELF digest) must agree with the selected root entry. `principal_id` is root-selected logical metadata; it is not a kernel measurement or an action grant.

`receive_request` checks the original Control scope and Source/Owner before the first SCM receive. The explicit transport profile checks the original Control dev/inode/SO_COOKIE captured by `ControlChannel::new`, delegates once to the unchanged raw retained receive, checks the actual returned Pending channel, and privately enables the same identity checks for every subsequent transaction message and detached report send. It never captures an identity at the first idle poll, verifies a moved-empty receiver, or treats an Agent cookie as a Control cookie. The bounded wait comes only from the original Control remaining time and cannot exceed the original maximum twenty seconds. The received Agent clock remains independently enforced; the effective request deadline is the minimum of the original Control and SCM ceilings.

The Agent is attested through the real default procfs source against the same Source's Agent role. The binding owns the original Agent pidfd custody, the actual original Control verifier, the fixed effective Instant and the exact session Arc. A verifier for a different session is refused even if all nineteen policy fields are byte-identical. A readonly request verifier has no owning mechanism slot and cannot extend the original request. At most one pending/admitted slot exists; caller data cannot release it. The final receiver/binding/report owners must drop before another original connection can occupy the slot. Product active/prepared/uncertain journal quarantine is a later coordinator responsibility and is not implemented by this slot.

`consume_with_request_binding` moves the original stream, deadline, unique Control custody, independent reporter, attested peer and non-cloneable binding into its callback. It performs full original pair and report checks before the callback and checks Source/Owner and the original Instant afterwards. The callback may legitimately retire the request, so request retirement is not a prerequisite of persistent Owner continuity. Returning a principal, snapshot, bool or successful callback value does not create an action or durable-report permit.

`ApprovedServiceRetainedReporter` checks the original Source/Owner, original Control identity and original request clock. It remains independent of the revoked action lease. A real Cancel may therefore revoke action while one terminal remote report is still legal. Its remote report is transport data only; it is not a fact about a local journal, delivered response, native success, Page state or production readiness. Repeated cancellation, EOF, malformed packets, substitution or expiry retire the original request. Only direct Source/Owner continuity failure retires the service; legal request EOF does not retire the persistent Owner.

The two low-level `service_control` APIs provide mechanism/cookie continuity only. The sender API has no Source-approved product sender factory in this package. It cannot be treated as root policy approval. Legacy receive/send/raw poll (including absent packets), send-report and wait-report methods keep their complete original bodies and guarantees. The new bridge initially uses full raw checks, including idle polling; it introduces no executable cache, stale snapshot proof or relaxed no-message semantics.

Cookie substitution tests use isolated actual syscall faults and prove refusal before packet parsing or report publication. They do not establish absence of all cleanup effects under arbitrary unsafe concurrent same-process FD replacement: inherited cleanup may close a replacement FD, and identity-query-to-close remains a race. Fork checks reject before request FD/root access and close only the child's descriptor copies, without shutdown or parent mutation. Namespace-local root custody does not establish host root trust or installed cross-UID procfs access.

The required actual host corpus is separate from source correspondence and compilation. Its positive case must finish the first actual Control/Agent request, retain only an old readonly verifier, wait beyond the first original twenty-second Instant, then accept a second actual Control/Agent pair through the same Requests/session/Source with a new original bounded request. Old proof must refuse while the persistent Source/Owner remains current. Source continuity after twenty-one or sixty-one seconds is not a native sixty-second health observation. Self-exec destroys the original in-process proof; tests must not claim that an old Rust object was verified after its address space was replaced.

This source package must be compiled in both existing feature graphs and run with real default-proc processes on its final frozen tuple before any runtime acceptance. Prior Foundation, readiness, native or supplier-attestation facts do not transfer to this new object. The old native six cases, original twenty/five-second budgets, Foundation source-continuity budget, Cargo/PIN and CI profile remain intact.

## Frozen parent and execution boundary

The source parent is `db9cb5399a16f794407be2c3561255e8d69fa537`, the separately reviewed Foundation/readiness SOURCE composition. Its donor Foundation kernel results, prior readiness results, supplier signature verification and prior native cases are not runtime evidence for this bridge. The new kernel source is authored but has not been compiled or executed in this package. No elapsed speedup is claimed.

`python3 tools/verify_approved_service_request.py` independently reads every current complete parent insertion, all five production children, all eighteen public methods, seven opaque field shapes and six restricted helpers. It requires the attached profile and preserves the exact original source by finite inverse. Foundation's four input-reader normalization boundaries accept only exact complete current or enumerated old whole objects. They do not supply request authority or qualify the new profile. The original Foundation test/checker rules, readiness guarantees, raw message/report methods and every old test body remain intact. The first author old-source test run had 69 passes and two errors before normalization at the Foundation reader; those failed raw facts are retained independently of the corrected 71-test run.

The new `approved_service_request_kernel` target has `harness = false` and a separate root-selected oneshot maximum of 120 seconds. It is automatically part of both existing workspace feature graphs. Its individual requests remain at most twenty seconds and it changes none of the old native twenty/five-second, sixty-second health or Foundation sixty-one-second continuity budgets. Root preparation copies and fully hashes the selected ELF and writes nineteen fixed role fields before the Owner unit and the Control/Agent children start. Each child retains its actual original connection; no observed process data generates successful policy. Namespace-local same-UID default-proc behavior does not qualify cross-UID installed operation.

| Group | Actual planned stimulus and bounded assertion |
| --- | --- |
| 1 | Complete a first request; after its original ceiling plus one second and at least 21 seconds, the same Source/session admits two fresh actual Control/Agent PIDs. Old proof refuses. |
| 2 | Drop unique persistent Owner custody; issued readonly session refuses. |
| 3–4 | Before launching peers, choose an explicitly wrong static Agent or Control role; real default-proc admission refuses. |
| 5 | Separate Source/session with identical policy bytes refuses the first Source's proof; both original services stay current. This is adversarial test setup, not product recovery. |
| 6–7 | Real Agent exit or Control EOF retires the original request while direct Source/Owner remains current. |
| 8 | A separate original six-second request expires; neither proof nor report gets a new ceiling. |
| 9 | Actual Cancel revokes action while one terminal remote transport report remains legal. |
| 10 | Peek and replay the real authenticated Cancel packet over the original actual Control endpoint; repeated cancellation refuses. This is explicit protocol fault injection, not a fabricated nonce authority. |
| 11 | Root policy mode drifts and is restored; Source stays retired. |
| 12 | Execute a copied ELF with different bytes; its new Owner admission refuses. Exec destroys the prior address space, so this does not claim a surviving old Rust proof. |
| 13 | Single-thread fork rejects inherited proofs before FD/root access; parent original proofs remain current. |
| 14–15 | In separate single-thread raw transport cases, replace original Control FD using another actual endpoint of the same actual Control PID. Cookie refusal precedes SCM parsing or detached report publication. This is mechanism-only unsafe syscall fault injection, not a Source-approved caller-FD factory or a guarantee against cleanup close races. |

The root harness reads back the original policy/ELF and their metadata, checks per-group FD cleanup, and bounds its actual child pipes and termination. Missing root/systemd prerequisites return 77 as UNAVAILABLE and are neither PASS nor skip. Runtime acceptance requires new actual compiler/kernel facts bound to the final complete source object.

## Historical seventeen-method draft, retained independently

The independently frozen seventeen-method draft `93a73c063a6b19e0bb36f438e74465f2190524ca` does not close replacement of the Root connection's actual moved FD before Handoff channel creation: the legacy Root connection validates a retained descriptor clone, and the later channel cookie can initially capture a replacement endpoint. Its groups 14–15 prove only the planned post-channel-creation refusal. The current eighteen-method successor adds the explicitly versioned Root transfer API and additional failure/unwind/escape test source to address this boundary. It still requires new actual compilation and kernel evidence. The seventeen-method draft's source checks do not supply this missing guarantee.

## Original Root connection transfer boundary

`RootPathControlConnection::consume_service_control_before<T>(self, consumer: impl FnOnce(OwnedFd, Instant, RootControlPathCustody) -> T) -> Result<T, RootControlPathError>` checks the actual moved endpoint against the original Root admission identity before and after the callback. Creator and the original remaining clock precede FD reads; the held original peer pidfd/path scope remains current as well. Actual endpoint dev/inode/uid/gid/mode, SO_COOKIE, SO_PEERCRED, domain, type and CLOEXEC must match. No new identity capture, duplicate FD or future Instant is created. The complete old `consume_before` method is delegated exactly once and its body remains intact.

A private guard starts uncompleted and owns the exact original connection scope. Error, mismatch or callback unwind retires that scope even if the consumer leaks its custody or retains its verifier. The guard performs no FD access, shutdown, lock acquisition, service Source retirement or extra shared pathname retirement. The normal original path checks retain their existing sticky response to a real pathname drift. Only successful actual-FD and held-scope post-proof disarms the guard. Callback side effects do not receive any authorization from this transport method; the P1 product factory only constructs a receiver still holding the same actual FD.

The current corpus has 19 source-authored groups. New group 16 replaces the actual Root FD using another endpoint of the same actual Control PID and requires the old clone-only deadline check to remain current, then requires the explicit transfer to refuse before its callback. Group 17 replaces the actual FD inside the callback and proves denial of an escaped original verifier, while the same listener admits a separate new connection and the existing service Source remains current. Group 18 unwinds with escaped custody/verifier and requires refusal afterwards. Group 19 proves a successful ordinary transfer retains its original Instant and exact scope. Groups 16–17 are explicit isolated syscall faults, not a same-process arbitrary concurrency guarantee. The new groups and the previous fifteen have not been executed on this source object.

## Source-only import correction after independent review

Independent review of frozen `02fbd28f4fca8583a694c20638fcc4c19f8aa26f`
found that the new `PostFailureDropProbe.verifier` field names
`RootControlPathVerifier` without importing its public transport reexport.
The prior 107 Python source checks and fourteen source validators did not
perform Rust name resolution and therefore did not detect this omission.
Those original results and the original frozen source remain retained; they
do not establish successful Rust compilation.

This narrow source successor adds that one explicit kernel import and rebinds
the contract and mandatory checker to the new whole kernel digest. The five
production children, eighteen APIs, seven opaque types, original parent
insertions, old raw methods and all old test bodies remain byte-exact. A
manual source import review is bounded inspection, not a compiler result.
This successor has not been formatted, compiled, run with the real kernel or
used by native/installed qualification; its nineteen groups remain source only.

## Actual formatter failure and finite source successor

On frozen `e0fb9a554f2c3f53dfcd445fa5b9b84cb8d17094`, the released
Rust 1.93.0 `cargo fmt --all --check` actually exited 1 after 0.817604 seconds.
Its complete stdout contains seventeen format hunks in four Rust source files.
All 667 physical source identities, Git blobs, modes and bytes remained exact
before and after the check. The fixed execution sequence stopped there: the
peer library check and new kernel no-run compilation were not launched, and
no new kernel ELF or runtime result was produced. Those original failure facts
and source bytes remain independently retained.

This separate source successor applies only the emitted four-file formatting
hunks: whitespace and optional trailing commas, plus the fixed ordering of the
two newly inserted `ServiceSessionState` reexports relative to public reexports.
The complete old parent bodies still restore exactly; eighteen API semantics,
seven opaque shapes, six restricted helper signatures, original effect order
and all old budgets remain unchanged. The contract and mandatory checker bind
the actual formatted whole child/kernel and insertion bytes. Its repeated
source checks are not a new formatter, compiler, native or kernel qualification.
New heavy checks and all nineteen kernel groups still require a separate
released window bound to the new final source tuple.

The first formatted-source Python run actually completed 107 cases with
106 passes and one failure. The new P1 peer-identity operator mutation had a
single-line literal that no longer matched rustfmt's line break, so its
`assertIn` failed before either inventory rejection was exercised. This
separate approved one-line test adapter matches the actual whitespace and
still changes only `!=` to `==`; the original `mutate_order`, `assertIn`,
independent `inventory_and_orders` refusal and full gate refusal remain intact.
The original seventy-one cases and the other thirty-five new cases retain
their entire bytes. The initial failed run is retained, and a corrected run
must actually enter the operator mutation before static acceptance. This
is neither a compiler result nor detection merely through a whole-file hash.
