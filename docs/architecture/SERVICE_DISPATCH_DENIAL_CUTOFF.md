# Original service scope denial cutoff

The native owner's receipt-time budget must enter the original service dispatch
scope before native effects. An outer receipt clock alone cannot constrain the
completion queue, the bridge's final physical forward, or Core's ACK wait.

The real `capture_original` constructor alone creates the scope from the moved
original request binding, fixed session, original pair verifier, canonical
request, original deadlines and registration nonce. Its new private
`OnceLock<Instant>` starts empty. Registration still compares the unchanged
original context deadline; the shorter clock never replaces identity metadata.
Prepared request, scoped runtime, active bridge call and actual completion share
the same `Arc<ServiceDispatchScope>`.

`ServiceEngineCompletion::shorten_deadline_once(&mut self, cutoff)` installs
exactly one additional denial cutoff. Its Servo wrapper delegates to the same
completion. Exclusive mutable custody prevents simultaneous completion
consumption. Future caller inputs clamp to both captured ceilings. A repeated
call, including an equal or earlier value, fails closed and retires the original
scope and engine. No method can renew, replace or clear the first cutoff.

The installer checks the real creator and original Source, namespace, session,
pair, request identity and actual runtime phase before publication. It checks
again after publication and after notifying the original event-loop waker.
An expired cutoff or notification failure remains sticky denial. Local denial
does not fabricate a remote cancel, release the owning request slot or publish
a terminal receipt.

`current` reads the same effective cutoff at its initial, middle and final
checks. The next wake, immediate physical-send pre-check, existing physical-send
post-check and Core's actual post-ACK wait all use that scope. Core's old full
functions remain unchanged; their existing calls to `current` now observe the
single shortened value. An install races with readers at the OnceLock
publication point; readers that observed the old value before publication gain
no approval. Final forwarding and ACK checks reread the same published value.

A future reviewed NativeOwner adapter must sample `Instant::now()` immediately
after taking the actual command, calculate the existing five-second cutoff with
`checked_add`, and install it before admission or any Servo/WebView effect.
It must retire on installer failure. This Source slice does not add or qualify
that adapter. Existing call paths that never install retain their original
deadline; the new API alone does not prove Native5 behavior.

Physical writes and synchronous native work are not atomically reversible or
preemptible. A pre-check may pass immediately before time expires. Post-send
and post-ACK failure deny a late buffered result and preserve uncertainty; they
do not claim the write was undone. Actual native timing requires separate
legitimate original-binding runtime evidence under the unchanged budgets.

The new physical Source gate inventories all functions, types and effects in
the three actual Rust files. The combined typed runtime exposes 23 methods and
eight opaque types; Core's additional public surface is separately inventoried.
Historical gates receive only exact pinned whole-source inverses for the six
modified files. The physical gate never reads normalized views, invokes older
validators or accepts unknown changed bytes. Existing P2C tests and contracts
remain complete historical views, not descriptions of the physical 23-API
successor.

## Claim ceiling

This is a Source mechanism and correspondence gate. The two new Rust compile-
fail snippets are authored and require independent Rust verification. Default
activation and installed status remain false. No Cargo, kernel lifecycle,
Native5, Native60, installed image, hardware, G6 approval or production readiness
is claimed by this slice.


## Joint physical Source boundary

The proposed joint profile selects the genuine d979 original-request bridge and
corrected 40fd AgentPort custody validators alongside this shared cutoff. The
physical gate classifies all 694 actual files: the original six complete
inverses, 672 unchanged d933 files, twelve newly selected complete Source
objects, the existing two supplemental files, this checker and its canonical
raw contract. No normalized historical view is accepted as a current physical
object. Each twelve-file rule requires the exact full current bytes and restores
the exact full d933 parent with UTF-8 byte offsets. Rejected 8ac section padding
behavior is not an admitted current object.

Only C's private `_read` applies the separate twelve-file historical inverse.
Its existing `parent_source` remains whole, so the Native/B/A/C parent chain
still presents actual d979 original-request modules to P1's independent guard.
The new reader never grants process identity, request custody or runtime proof.
The existing mandatory physical checker remains in Makefile exactly once;
historical C/A/B/Native correspondence cannot replace that physical stage.

The mandatory P3 physical reader opens an absolute directory chain with
`O_NOFOLLOW` and directory descriptors. Relative input components must be
nonempty and cannot be `.` or `..`. It rejects absolute input names, symbolic
parent directories and symbolic, hardlinked,
unbounded or nonregular leaves. It checks the captured leaf's full descriptor
identity before and after reading and checks the directory lineage before
closing every descriptor in `finally`. No `resolve()` masks a link under test.
Directory content timestamps are not process or Source authority.

C keeps its original independent leaf FD9 reader, including nonblocking FIFO
race refusal, and applies only the new twelve-file inverse before the existing
six-file inverse. This historical reader does not claim directory-lineage
hardening. Only the mandatory P3 physical 694-file stage supplies that guard;
a historical C result cannot replace the physical stage. The exact earlier
88d C checker is a registered historical whole object, never an admitted
current physical substitute.

Raw contract serialization must match the canonical closed object exactly,
including its one final newline. The checker removes only its exact canonical
one-line `EXPECTED = json.loads(...)` literal after checking the complete AST
assignment offsets and full physical line. Extra same-line statements,
comments, nonliteral/multiline assignments or appended EOF bytes are refused.
The independent whole rules remain outside the mutable contract envelope.

This joint proposal does not reuse any individual branch's execution result.
It still requires Root review of every complete file and inverse, actual joint
Source checks, fresh joint Rust builds/tests/docs/Clippy and the original
Kernel corpus under unchanged clocks. Installed cross-UID attestation, a
Native service entry, default activation, image/recovery/HW/HSM and independent
human approval remain unqualified.


## Current physical ingress and historical P1 input

This joint profile keeps the independently reviewed d979 P1 checker and all
200 P1 methods whole. Its existing Native/B/A/C input chain deliberately
presents the exact historical transport Source: `accepted_handoff.rs` has
36790 bytes with SHA256
`988ab3003afd3f4c4381b989b7581376c970e30af958470e0f47561cb4eea84f`.
C's already registered complete inverse removes exactly two reviewed lines:
`mod connected_denial;` and the `OriginalConnectedDenial` reexport. That whole
historical object is an input view, and never a current physical substitute.

The mandatory P3 physical gate requires the actual 36863-byte module with
SHA256 `9d689df4fa59601e39b4598771fa2cad55d83d1733f137593e017e2b2cd11e23`.
A separate private pure Source guard fixes this current module and fifteen
whole d979 ingress modules independently of mutable contract hashes. It
performs no file IO, historical normalization, process admission or runtime
authorization. P3.check calls it once after the existing exact 694-name/count
checks and before other implementation/inverse checks. The original P1
nine complete ingress bodies, headers, sole sealed receive route and seven
consume guard modules remain unchanged and independently reviewed. P1's
sixteen historical input checks are not relabeled as current physical proof.

New full-gate negative cases replace the actual module with whole history,
remove both export lines or remove the Rooted receiver's final session guard.
They synchronize all mutable classification/whole identity metadata and
both the complete canonical contract and EXPECTED assignment. All sixteen
unknown physical modules and catalog-only rebinding are also checked. The
original P3 tests and their seventeen precise rejection targets stay whole.
These methods are authored here; execution qualification requires fresh
joint Source windows and independent Root review. Rust, the original Kernel
corpus, installed cross-UID attestation and production readiness remain
unqualified by this Source proposal.


## Current independently observed branch results

Root independently verified the d979 original three build commands and both
required strict workspace Clippy commands, with all five actual exit codes
zero and no compiler warnings. These close that branch's local compile/lint
blocker; they are not fresh joint Rust execution or a production approval.

The latest d979 original nineteen-case Kernel run executed once and exited
101 after 82.72360858198954 seconds. Its first seven cases passed, and the
initial receive in the eighth expiry case returned successfully. The failure
occurred at line 394 while unpacking the actual received request through
`consume_with_request_binding`: the Result unwrap reported `DeadlineExceeded`.
The internal pre-callback/callback/post-callback phase remains unknown because
that run has no stage markers. No causal performance improvement was measured,
case18 was not reached and the nineteen-case corpus did not pass. The original
six-second expiry budget was unchanged. The older initial-receive line572
failure remains historical evidence, and is not the latest d979 failure.

These branch facts are frozen in Root's original-three/strict-two readback
(SHA256 `729feb730b972f43f4e43adf7dcac0b7dbc504d8849c6a6db9228fa0701933cd`)
and original19 readback
(SHA256 `b001459a83f5a3c984e41f0c0bbec33223e6aafdd8aaaf13e2f5d7d5793b465e`).
The present ten-path joint profile remains an external proposal. The already
qualified joint945 Source profile still contains f243. No branch Rust, Kernel,
Native or installed result is transferred to the proposed d979 combination.


## Current CI composition candidate and earlier qualifications

The new composition has 699 tracked Source files. It combines the complete
23-path c700 CI closure with the de44 service closure, including all ten actual
workflow files, both CI contexts/identity catalogs, the AppArmor profile, the
complete cleanup helper and its 64 original namespace tests. The common Git ancestor is
99c4eb9ff6f11b5075487c7e9fc4b4f0ca794320 (650 files). Fifteen CI leaves remain
c700 whole after the necessary reader/filter and actual SHA binding adapters; the module catalog preserves every de44 service registration
and adds only the five CI references to browser-codec. The retained-control
checker preserves both de44 detach functions and binds the actual new workflow
SHA. CI checker.inputs alone changes to the bounded P3 physical reader.

P3 checks the current16 production modules with the unchanged independent
function, then independently fixes all 23 current CI physical leaves. It
requires all 699 actual physical files and canonical metadata. Eighteen CI
whole inverses restore exact de44 objects only through C._read historical views;
new CI files have no historical parent. The module's finite six-file inverse
restores both registration additions as a complete current-to-original object.
The other five finite rules, twelve P1 rules, implementation semantics and
original API/effect inventories remain unchanged. P3.parent_source stays whole;
Native/B/A/readiness retain current CI workflow views. Both G2 workflows add
the six actual service checker imports to push and pull_request filters; their
complete jobs, action pins, timeout/clock budgets and steps remain whole.
Only actual context digests, workflow SHA bindings and the literal CI inverse
filter inventory change accordingly. Current CI.inputs bypasses
the Native historical chain and verifies actual workflows/contexts/helper/
profile; replacing those inputs with historical views is rejected.

The old 694-name positive test changes only its name and count assertion to
699. The other 39 original P3 method bodies and every original test helper remain
whole, including all seventeen precise independent mutant rejection targets.
Four new methods exercise the actual positive CI route, all 23 changed current
objects, all 18 historical substitutions and catalog-only rebinding. They bind
the complete mutable contract/checker envelopes before testing the independent
physical guard. The original 64 CI namespace methods and their helper implementation
remain whole. The earlier c700 five Source suites ran 131 tests in total;
those branch results do not qualify this candidate. These tests are authored; independent execution is pending.

Earlier 693/694 Source and separate c700 Source/Make results remain historical
branch evidence. This 699 candidate begins with no Source, Rust or Kernel
execution qualification. The original nineteen-case corpus, observation clocks,
Kernel/Native budgets and default activation remain unchanged. No Hosted
AppArmor cleanup, Native5/20/60, installed image, hardware, HSM, independent
human approval or production readiness follows from this Source composition.
