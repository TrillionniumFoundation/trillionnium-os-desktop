# Settings admission: final targeted review

## Result

The reviewed r3 source closes the specific unsafe authorization and pending-admission defects identified in the first review and the two narrow follow-up defects found while reading r2. This conclusion is bound to the eight file hashes in `REVIEW.json`; it is not approval of a running Android cohort. Settings execution remains deliberately blocked because the selected framework does not yet provide a qualified task-creation and conditional-cleanup authority. No application or release gate is accepted.

This package supplements the immutable `targeted-runtime-settings-review-r1` package. The earlier findings, first source pins, official-source URLs/version boundary, and seccomp/readiness review remain unchanged there. `evidence/SECOND-REVIEW-BEFORE-CORRECTION.json` preserves the exact r2 source identities and the two additional findings before their correction.

## What was checked

The public native Settings entry validates the fixed request shape and unconditionally returns the missing-authority error. It cannot connect to task control or run an Android command. The former task-difference/ACK/cleanup implementation is compiled only for tests. The public observation type reports `completed_partial() == false` for every value, so complete-looking serialized data cannot grant Settings progress.

The daemon originally constructed `LiveApplicationProbe` before calling the unconditional blocker. That constructor calls `android_boot_snapshot`, which reaches `timeout/nsenter /system/bin/getprop`. Although this was a read-only probe, it contradicted the promised command-before-rejection boundary. The final handler performs only user-range and host active-cell/UID checks and invokes an admission function that accepts neither a probe nor a deadline. Its unconditional error precedes any Android observation. The complete selected `require_active_cell(peer_uid, None)` path was read to verify that claim.

The dispatcher originally converted a false response carrying a structured observation into `Ok(observed)`. If its serialized `action_scope_retained` field was false, a later read-only runtime query could leave the selection fence open for Firefox. The current daemon cannot produce that observation, so this was a mixed/contradictory response boundary rather than a bypass of its own gate. The final incomplete-response branch always invalidates the sticky fence. The existing complete-looking response control now asserts no browser invocation, one initial runtime query, and all 42 rows blocked.

The daemon has eight explicitly read-only request variants. Every other current request, including all nine current mutations, passes the persistent pending check before dispatch; future variants default to that check. The check does not reacquire flock, which avoids deadlocking the external consumer that already owns it. Both staged consumer successors check the same fixed marker before `arun`, `ui`, and `dispatch`; their normal CLI dispatch remains under the existing shared flock. A marker of any inode type, a dangling symlink, an untrusted directory owner, or unavailable state blocks without clearing or retrying. The two consumers are source artifacts; their installation is not claimed.

## Selected Android evidence

The separate Native audit now supplies binary-derived methods from the selected CP3A.260905.010 / 16176746 image, SHA256 `dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4`. This review rehashed all 83 members named by that capsule's manifest and fully read seven relevant method excerpts. It did not repeat extraction, disassembly, or execution.

The actual `runStackList` prints `RootTaskInfo.toString`; that complete method omits baseIntent/identifier. Actual `WaitResult` parcel reading and writing contain result, timeout, component, total time, and launch state, without a task ID. Actual `removeTask(int)` checks permission and takes the framework lock, but accepts no expected nonce or identifier before finding the current task by numeric ID. These observations support withholding ownership from the separate launch/snapshot/numeric-ID removal sequence. They do not prove that a future typed-token or identifier design is usable or atomic.

The first package's official AOSP commit `1cdfff555f4a21f71ccc978290e2e212e2f8b168` is a 2025 source semantic counterexample. It is not authenticated CP3A source. The selected-binary crosscheck supplements that evidence without claiming a complete authenticated CP3A source manifest.

## Validation boundary

The implementation owner supplied terminal receipt `1a1c19d1019-e62c-de` and full stdout, 179290 bytes / SHA256 `e4ae476add5a795d285a79fcc16e375d65add8d7019359b494f1690aff827791`. This review read the stored terminal metadata and hash-checked the original stdout, source receipts and ordinary logs; it did not query H again or rerun tests. The observed r3 workspace groups total 70 passing tests. A portable harness compiled the same source for 58 controls; that repeats a subset of behavior, not 58 additional release gates. The six consumer controls remain tied to the unchanged r2 consumer source bytes. The four changed files and the unchanged identities are recorded explicitly.

No Android/UI invocation, installed-file mutation, owner-source modification, canonical CURRENT change, full build, runtime qualification, or production claim occurred in this review. The actual framework authority, Settings business execution, consumer deployment and all relevant release/runtime gates remain pending.
