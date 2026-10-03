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

## Actual type-check failure and original PID representation

On frozen `ace7068730675383e6f53e4410e42fd039822d63`, the fixed released
Rust 1.93.0 window actually passed `cargo fmt --all --check`, then its peer
library check exited 101 with E0308 in the new Root transfer child. The real
transport `PeerIdentity.pid` field is `Option<u32>`, while the initializer
used `cred.pid as u32`. The sequence stopped before the new kernel no-run
command; it produced no kernel ELF or runtime result. All 667 source files
and the selected tools remained exact before and after this failed window.
Those source objects and complete actual failure facts remain retained.

This separate four-path source successor changes only that initializer to
`Some(cred.pid as u32)`, matching the actual transport type. It preserves the
prior positive `SO_PEERCRED` PID check and full equality against the original
Root admission identity, along with all original clock, pidfd, pathname,
cookie, failure-retirement and pre/post boundaries. The child whole digest
is rebound in the contract and mandatory checker, and this factual paragraph
is appended. The other 663 files, kernel source, tests, eighteen APIs, seven
opaque shapes, six restricted helpers, sixteen orders and seventeen known
legacy objects remain exact to the parent. The parent's formatter pass does
not qualify this new object: no formatter, compiler, kernel or native
command has run on this successor. Its next limited window needs a new
independent source review and explicit release.


### First actual P1 kernel failure and valid negative static-role fixture successor

The frozen `5aac2a8503c9d3b84fbb81a803edd22025d52656` object compiled in the
fixed Rust 1.93.0 default-profile limited window, then its first actual kernel
attempt (session 69687) exited 101 after 40.421912228 seconds. Two groups passed,
including the same original Source/session accepting a new real request after
its first request's asserted minimum of 21 seconds. This is a lower bound from
the unchanged runtime assertion, not a measured nanosecond duration or native
health qualification. The complete nineteen-group corpus did not pass.

The third group's fixture changed `agent.unit` to `unapproved-role.service`
while retaining the real unit's `agent.cgroup`. The production parser correctly
refused this invalid pair when `Fixture::source` opened the document
(`approved_service_request_kernel.rs:234:70`, `InvalidConfiguration`), before
that group's actual Control/Agent Trio existed. Configuration rejection does
not prove rejection of a live peer with the wrong approved role. The original
result and both raw output files remain immutable under
`work/persistent-v2-original-request-5aac2-root-kernel-facts-v1`; the result SHA is
`6ebf2802e22e3e0f202eca495000ed21c59d5e9d184cf1fe4628ea52a4bf0096`.

The separate successor changes only the negative root fixture's same selected
role to the internally consistent static pair `unapproved-role.service` and
`/system.slice/unapproved-role.service`, before any peer is created. The real
unit, executable, UID/GID, principals and Owner selection stay fixed. The
production parser and request implementations stay byte-exact; all nineteen
labels, the 20-second original request maximum, 6-second expiry negative,
21-second minimum assertion and 120-second unit bounds remain unchanged.
The source gate rebinds only the complete kernel source SHA. This successor
has source/static validation and single-file formatting evidence only until
its own compile and actual nineteen-group kernel run are separately reviewed.
The parent compile and two successful groups are not transferred to it.


### Actual seven-group kernel result and narrow private Owner composition scope

On frozen `22d43f9e60153dc40745080a8a4ab0c67ebd0033`, all three fixed limited
Rust commands completed, with the retained `unused_assignments` kernel warning.
The next actual original nineteen-group kernel run exited 101 after
105.043296887 seconds: seven groups passed and the eighth group's initial
6-second Trio admission returned `DeadlineExceeded` at the actual
`trio.receive(&f, &mut requests).unwrap()` expression, before unpacking or the
expiry stimulus. The run did not time out and does not establish which
validation phase consumed the original interval. Its complete immutable result
is `work/persistent-v2-original-request-22d43-root-kernel-facts-v1/actual-kernel-result.json`,
SHA `ef5e28a5d6ab521c6f63b23ff49e75df76114d05759d633b9ec9cca953c801ea`.
Neither the original six-second negative nor its 20-second request maximum,
21-second lower-bound assertion or 120-second unit bound is changed here.

This separate source successor adds exactly one private denial-only
`ServiceSessionState::original_owner_root_scope` and uses it at three pure
composition sites: around copying the immutable root-selected Control policy,
and immediately inside the same original Root transfer callback before the
actual Owner receiver factory. It retains original creator/namespace checks,
same Source/Owner pointer identity, root source bytes/path inspection before and
after, the original nonclone Owner custody's lease/pidfd and stored root-selected
Live `/proc` metadata, and sticky Source retirement on a direct Owner/source
failure. The stored metadata is not a fresh executable observation. This scope
returns only `Result<(), ApprovedPolicyError>`; it cannot mint action or report
permission, a new process proof or an extended deadline.

Every actual challenge/SCM boundary retains its original full Source, Owner and
Control checks before and after. All eighteen public methods, seven opaque
shapes, old six restricted helper declarations, original raw poll/send bodies,
seventeen known legacy normalization objects, nineteen kernel groups and old
107 static tests retain their exact bodies. The mandatory gate merges the
unchanged closed six-helper table with one separately closed scope helper and
checks all seven actual restricted declarations, signatures and full tokens in
all five production children. It also binds all actual function tokens and
allows exactly the three listed scope calls. New mutation cases rebind token
correspondence in memory before testing missing creator/pointer/lease/root
checks and a scope substituted for a real challenge check; these cases must
still fail the independent route/order inventory.

This successor has source/static and two-child formatter evidence only. Its
compiler, actual kernel and performance results are pending new independent
review and separately released runs. The parent compile and seven successful
groups do not qualify this new object; no speed improvement, installed service,
native health or production readiness is claimed.


### Actual unchanged six-second refusal and full Control guard composition

The frozen `0c94d5e66d35cd575028f51961c40af36c7f19cc` source passed the three
fixed Rust 1.93.0 limited commands, retaining one `unused_assignments` warning.
Its separately released original nineteen-group kernel run exited 101 after
88.842089882 seconds with the same seven completed groups. The eighth group's
initial original six-second `trio.receive(&f, &mut requests).unwrap()` still
returned `DeadlineExceeded`, before unpacking and before the expiry stimulus.
The unchanged kernel source is `6f099409079351f5793a669e43f71cd9f0441befaec20f3003e910156ed5c8fa`;
the complete actual result is
`work/persistent-v2-original-request-0c94d-root-kernel-facts-v1/actual-kernel-result.json`,
SHA `ee391173a29f66a96bc242dd365cb515b28d97a6d12f42a0a002027a42639a38`.
The observations identify process CPU use, not validation call counts. They
do not locate the failing phase inside binding or SCM or establish a speedup.

This separate Source successor composes each adjacent legacy Control-current
and complete selected service verification into one private full boundary.
`ControlPeerOwner::current_for_service` requires the original creator and
remaining deadline, default `/proc`, Live executable source, an empty legacy
approval list and the original retained Root path. It checks that path before
and after the unchanged full `ServiceSessionState::verify_control`, which
checks Source/Owner before and after one actual complete Control snapshot
through the same original live pidfd. It finally checks the same deadline.
No Source/Owner full check is removed. The original single protocol challenge
and actual SCM operation remain surrounded by these complete guards.

`AttestedHandoffReceiver::ensure_service_current` preserves original creator,
cancelled/absent-owner refusal, error retirement and the exact receiver
deadline. Its method is placed in the original sole receiver impl. All public
eighteen method bodies, seven opaque types, three pure denial-scope calls,
seventeen legacy normalization objects and nineteen kernel groups remain
whole. The mandatory finite inventory independently keeps old six helpers,
denial-scope one and composition two: all nine actual restricted declarations,
signatures and complete function tokens are closed across five children.
Additional semantic rules preserve the two complete original Session guard
bodies and both actual `/proc` literals even when test digests, signatures and
configurable effect orders are rebound.

Four previous test methods require finite adaptation: the old challenge
location mutation, the old seven-helper total, the old challenge-to-denial-scope
mutation and the rebinding utility's complete helper set. Each retains its
original mutant strength, with an independently applied whole method inverse;
the other original test methods remain byte-exact. New actual finite mutations
remove or replace creator, each deadline and Root path, full selected Control,
default-proc/Live/empty-approval state, cancellation and error retirement, or
weaken/move either challenge and SCM boundary. They must refuse after complete
token/whole-object rebinding; these are Source tests, not a runtime authority.

The successful bind/receive call graph has four fewer consecutive duplicate
Control refresh calls. That static count is neither an observed invocation
count nor six-second qualification. The original 6/20/21/120-second budgets,
Rust profiles, actual ingress boundary and negative expiry assertions remain
unchanged. This candidate has two-child formatter and Python Source evidence
only; its compiler and original nineteen-group run require new independent
review and separately released execution. No latency improvement, native
health, installed behavior or production readiness is claimed.


### Actual E0425 and explicit private helper Duration import

On frozen `bb50ded3e30881e96d78c97c50e2ee0cbbeb62de`, the separately released
fixed Rust 1.93.0 sequence passed `cargo fmt --all --check` and then the peer
library check exited 101 with E0425 at the new private Root helper's
`Result<Duration, ControlOwnerError>` return type. Its module lacked the
explicit `std::time::Duration` import; the inherited glob did not introduce
that name. The previous 139 Python Source tests and fourteen validators did
not perform Rust name resolution. The sequence stopped before kernel no-run,
produced no new ELF and executed no kernel group. All 667 Source identities,
bytes, modes and Git blobs remained exact through the failed window.

The actual result under
`work/persistent-v2-original-request-service-control-composition-successor-root-limited-compile-facts-v1/actual-limited-result.json`
has SHA `8e5d543a065ee663fca09086410240c514057a606f63cafc7a1372cfb85c0297`.
Its complete stderr has SHA
`c5631127245cc927315b31a7ab0947e7507d9bd6031a9ab798b3cb5b965cb321`.
Those original failed compiler facts, the frozen Source and independent
Source review are retained separately and are not successful compilation.

This four-path successor adds only `use std::time::Duration;`, rebinds that
complete module's SHA in the contract and mandatory checker, and appends this
factual record. All production function bodies and signatures, nine private
helpers, eighteen public bodies, seven opaque types, three denial-scope calls,
complete original 139 tests, seventeen legacy objects and the exact nineteen
kernel groups remain whole. The original 6/20/21/120-second budgets and Rust
profiles are unchanged. One-child formatting and Source checks do not qualify
the repaired object: new independent Source review and separately released
original three-command and nineteen-group runs are still required. No latency,
native health, installed behavior or production readiness is claimed.


### Source consume composition after the preserved original Kernel failure

The import successor `6a77c27676f629ea24651957d7f54a73db0b9dd8` passed its
separately released original three-command Rust sequence with the fixed
default development profile. The original nineteen-group Kernel then ran once
with the unchanged 6/20/21/120-second budgets and exited 101 after seven PASS
groups. Case eight's initial `trio.receive` returned before `unpack` called
`consume_with_request_binding`; the latter returned `DeadlineExceeded`, which
the original Kernel unwrapped at line 394. There are no internal stage markers:
whether the consumer executed, or a pre/post check reached expiry, is unknown.
The preserved actual result SHA is
`2f9f6f8a6712c64f93dddf6715890d95fc5ff7715c45640c0286ff27d5feb886`.
The complete terminal readback SHA is
`5f2cc8132be01cca6f112f755ee989d444b12a095103a4c72c856bdb0801eace`.
Neither failure location nor seven PASS groups qualify the six-second deadline
or establish a measured performance improvement.

This Source successor changes one public method body and keeps all eighteen
signatures, seven opaque types, nine restricted helpers and every other public
body whole. In `consume_with_request_binding`, the initial duplicate complete
request-current call becomes the original slot/Creator check plus the same
captured absolute Instant check. Moving the private fields is pure composition.
The complete independent reporter check still brackets its real channel identity
and clock access with Source/Owner checks and refreshes the original Control.
Immediately before the actual consumer, the unchanged request-current method
still performs complete original Agent/Control pair verification surrounded by
complete Source/Owner and original deadline checks. After the callback, the
unchanged complete persistent Source/Owner and original deadline checks remain.
The callback may legitimately retire action/report custody, so the original
post-callback rule still does not demand live request custody after retirement.
No earlier result or snapshot is cached or treated as current authority.

An expired request can now fail at the original cheap clock before an Owner
hash. An already-retired action can undergo independent report-channel identity
inspection before the final pair refuses it. Neither path executes a consumer,
SCM transfer, cancellation poll or report submission. Original custody cleanup,
error retirement, selected roles, live proc attestors, pins and deadlines remain.
The static removal is one duplicate `ServiceRequestState::current` path; its two
Owner, one Agent and one Control refresh calls are not measured runtime counts.

The checker independently fixes the complete consume signature/body, the original
slot/current/reporter/session bodies and the seven complete actual Guard modules.
Rebinding the contract hashes, API, private shapes and order table cannot replace
those guards with cached or caller values. All 139 original Source tests remain
whole, with additional complete-rebinding refusal cases. This is Source evidence;
separate independent review, original three-command compilation and the unchanged
nineteen-group Kernel must qualify this new object. Native health, installation,
activation, latency and production readiness remain unqualified.


### Adjacent Reporter / original-pair Source boundary candidate

The b655 original 19-group execution remains failed: actual exit 101, seven
ordered groups passed, and case eight returned `DeadlineExceeded` from consume
at the unchanged Kernel line 394 after receive succeeded. Its internal phase
is unknown. The complete original run and all Source/ELF/identity facts are
retained; no same-object retry or deadline change qualifies it.

The reviewed successor changes only the consume body and adds one plain private
Received helper. It verifies its own creating process, same original session
and slot Arcs, and exact captured deadline equality, then runs the complete
unchanged independent Reporter guard. The Reporter's last full Source/Owner
check supplies the immediately adjacent pre boundary of the original pair.
The entire original pair checked tail still verifies the same Agent and actual
Control, keeps original clocks and sticky retirement, and performs full
Source/Owner post checks before the actual callback. The original complete
Source/Owner and deadline checks after callback remain unchanged; legitimate
callback action/report retirement remains allowed.

Both real Control refreshes and the retained original channel identity, nonce,
sequence, boot/time namespace and monotonic/Instant proof remain unchanged.
The helper accepts no caller proof and exports no reusable authority or cache.
One adjacent full Owner refresh is removed on the static success path. Actual
invocation counts, bottleneck, latency and six-second runtime qualification are
unmeasured. Removing one observation does not claim identical sampling times
for temporary external drift restored between complete boundaries.

Independent fixed whole helper/consume/guard bodies, sole call, exact copied
pair tail, seven whole Guard modules and opaque fields reject complete catalog
hash/API/order rebinding. All original 139 tests remain whole; four of the 15
earlier consume tests adapt moved guard locations with complete method inverses.
The original Kernel, 19 groups, 6/20/21/120 seconds and owned 5+5 cleanup budgets
remain unchanged. Cargo, Kernel, Native and production readiness remain pending.
