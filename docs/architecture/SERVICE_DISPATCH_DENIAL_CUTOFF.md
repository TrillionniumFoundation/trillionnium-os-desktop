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

The proposed joint profile selects the genuine f243 original-request bridge and
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
still presents actual f243 original-request modules to P1's independent guard.
The new reader never grants process identity, request custody or runtime proof.
The existing mandatory physical checker remains in Makefile exactly once;
historical C/A/B/Native correspondence cannot replace that physical stage.

The physical reader opens an absolute directory chain with
`O_NOFOLLOW` and directory descriptors. Relative input components must be
nonempty and cannot be `.` or `..`. It rejects absolute input names, symbolic
parent directories and symbolic, hardlinked,
unbounded or nonregular leaves. It checks the captured leaf's full descriptor
identity before and after reading and checks the directory lineage before
closing every descriptor in `finally`. No `resolve()` masks a link under test.
Directory content timestamps are not process or Source authority.

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
