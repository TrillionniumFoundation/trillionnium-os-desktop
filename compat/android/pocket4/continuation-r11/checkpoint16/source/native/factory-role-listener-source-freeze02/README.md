# Listener successor: fail on the first OwnerLease getter error

This revision retains the explicit Registry and OwnerLease lifetime repairs and the disabled listener admission path from listener freeze01. It changes only role_session.cc and role_admission.cc. The two getters now run sequentially at every consumer. If the first getter fails, the second getter is not evaluated. Any getter failure returns its original errno before poll; DispatchOne also closes the identified grant before it can receive or publish a snapshot. The preceding Verify call does not excuse a later failed ownership proof.

The old source is retained. It could pass a negative descriptor to poll (which ignores that slot), or compare a connection to -1 and continue, or evaluate a later getter and lose the first errno. This is a concrete error-propagation defect. No runtime foreign-authority bypass is asserted. OwnerLease still performs its original held-proc ownership proof and Registry cleanup is still owner-gated.

## Actual local verification

Strict compilation of the complete candidate translation units and the unchanged nine-case listener control succeeded. Its default invocation was PLAN_ONLY; no root child, listener execution, authorization or snapshot was run.

Nine paired error-path controls compiled and ran. The two complete Wait functions, the complete admission Check function, and the exact DispatchOne prefix ending before Received were extracted byte-for-byte from each bound old/new source. Authority and getter outcomes are explicit seams. poll and its owned pipe/event/PID descriptors are actual kernel operations. The Dispatch prefix uses a test-only continuation sentinel; this is not execution of the full dispatcher. Five original swallowed/overwritten-error cases were observed. Every candidate first failure remained EMFILE or EINTR, no second getter ran after the first failed, and the Dispatch prefix called Close once. Three success controls and the previously-correct admission second-getter failure also remained correct. These controls prove bounded error handling, not production authorization.

The prior fourteen transport cases remain prior-revision evidence and were not rerun as an additional qualification claim. Their codec/receiver code is unchanged. The real nine-case root listener fixture and OwnerLease two/four root destructor comparison remain NOT RUN. Android early typed fork input, all-thread NNP, immutable base policy, exact range policy, trusted parent producer and an enabled factory service remain OPEN. No ordinary V2/zero-cap/NOFILE path is weakened.

## Correction to prior documentation

The OwnerLease freeze02 README called its arm selector a compile macro. That wording was wrong: the preimage/candidate source headers differ at compile time, and the control selects the expected behavior with runtime --expect-preimage / --expect-candidate arguments. The preserved actual compiler argv contains no arm macro. The old README and source have not been rewritten.
