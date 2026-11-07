# Composer direct-registration transaction repair — source-only host candidate

This frozen candidate changes only `graphics/droidloom-composer-service/src/control.rs` from the fully observed builder469 source map. It does not update installed Main. The installed Main/source equivalence and the exact cause of the historical Bili launch error remain unproved.

## Production behavior

The coordinator serializes direct registration with lock order registration → operation → state. It releases operation/state while waiting for configuration, rechecks the exact object/display/task/package before binding, and reuses only a complete Bound record with matching identity and no pending retirement.

Binding failures return their original error and attempt cleanup of only the owned reservation. A complete Bound mapping survives a later activation error. Cleanup records each successful backend step; a later explicit retirement skips the endpoint already removed instead of calling an absent Denial channel again.

Reserve-stage failures now use the same checked cleanup path. Each backend invocation is recorded before crossing the I/O boundary. An endpoint never invoked can be skipped; an invoked endpoint is complete only after cleanup returns Ok. The code preserves Reserved/Removing state, direct markers and progress when cleanup is unresolved. It never treats UnknownDisplay or BadDisplay as proof that remote state is absent. In particular, the existing Denial register API can fail before inserting a local channel: this candidate preserves that uncertainty and does not claim every such failure can be recovered automatically.

## Host controls and their limit

The 27 test functions call the actual candidate TaskCoordinator methods and the actual TaskControlRegistry. The host crate uses the real, unchanged composer, task-control, denial-protocol, denial-ipc and transport path crates. Only the two Android I/O adapter types are explicit fixtures. Their before/after-effect errors exercise the API failure boundary; they are not evidence that every injected failure is reachable in installed Binder/Denial.

The build assembles `control_under_test.rs` as the exact full production bytes followed by the exact test child module. It does not replace production method bodies. The original five-second configure timeout remains in the real timeout control.

The controls cover complete binding/reuse, pending direct markers, removing-state rejection, partial sink/lifecycle/registry commit failures, foreign registration preservation, primary plus cleanup errors, monotonic cleanup checkpoints, activation failure, never-invoked endpoints, unknown remote state, exact cleanup identity, state/operation lock boundaries and independent retirement. Python parsing, Rust compilation and all these tests are still UNRUN for this candidate.

## Owned build request

`exact-request.json` is a concrete single-admission host-only request; Root alone may dispatch it. It uses a new root and key, one CPU, 1 GiB owned memory, nice 15 and a 600-second outer limit. The controller has a 450-second work window and bounded own-child retirement. Three real lifecycle negative controls run before Rust compilation; a failure prevents the compile.

Twenty-two hash/source/tool/resource helpers are byte-identical to the actual469 compiler. The OwnChildReaper class is byte-identical to Owner20 build02. Explicit deltas cover its command adapter, capture limits and fixture control environment. The request requires actual before/after immutable source, dependency, tool and configuration checks, strict child retirement and no OOM. It records the owned swap limit/usage; it does not claim a zero-swap limit.

Cargo resolves offline in the new private fixture workspace. Before compiling any Rust target, every selected registry version/checksum must match the original lock and its qualified cached archive/source; every path dependency must be one of the five exact real crates. The full original 499-leaf source copy is verified before and after, with exactly one production leaf changed. The fresh ELF must come from the exact fixture target, expose exactly 27 named tests, and pass every exact invocation with an independently held libtest logfile.

## Reproduction and evidence boundaries

Run `reproduceComposerTransactionRequest(files, H)` from `reproduce-request.js` with the frozen textual file map and the helpers from `pure_js_binary.js`. Its output must match the frozen request, stdin, stage, boundary and expected input map byte for byte. `applyUnifiedText` from `verify-inverse.js` reproduces and reverses both production deltas. The source review records the checks already executed in V8.

No device request, namespace, service, install, UI or Main mutation was made by this preparation. No branch/ref/PR is changed. This is a source/host regression candidate, not Android Binder qualification, app readiness or production acceptance. The previous Native NORMAL05 resource failure is retained; no NORMAL06 request or lower memory threshold is introduced.
