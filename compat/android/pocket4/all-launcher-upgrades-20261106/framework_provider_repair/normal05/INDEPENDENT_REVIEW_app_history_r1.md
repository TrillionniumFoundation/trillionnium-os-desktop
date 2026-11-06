# normal05 independent source review — source-r1

Reviewer: `app_history`. Scope: local source and actual saved receipt inspection only. No Pocket4 command, Main observation, build, deployment, UI, permission change, or Git write was executed by this review.

## Finding

No blocking defect was found in the reviewed normal04 → normal05 source delta, typed current-runtime checks, preserved resource admission, or owned-child retirement paths. **This is not approval to execute the current unsealed source-r1.** Its final App scope and transport wire are deliberately unset. A final source revision must bind the actual post-upgrade complete App scope, recompute the affected source/manifest/transport pins, and be checked against that concrete input before execution.

## Exact reviewed inputs

- `source-r1/SOURCE_PINS.json`: SHA-256 `b22f52ab12bfd5dc190e6b75a9085881d3852c2607ca57ad4bfd135ee51cb130`. All 25 file rows matched actual local bytes.
- `framework_build.py`: 60,970 bytes, `f4ab5e09fc22b759811bfa9480c2de555dbc5096bc1258a984dbd33809db734b`.
- `main_snapshot.py`: 23,127 bytes, `8c8c4d8d8480edd3c48308634cee79ac04e6933cf8ad27409f31dc465ed41e5b`.
- `capture_lifecycle.py`: 25,240 bytes, `7fe6569f6665d6b710d2207c53e631261d6eb922d37e24ddfe5de15b841f0126`.
- `root_snapshot_supervisor.py`: 12,041 bytes, `69a65925a6716eb180bd42f41506fa1be6e0438ddc945bc907448765b6595bdc`.
- `fenced_build.py`: 25,681 bytes, `ef1a6b7b26b7318dd67977b45015305dfec3bd0ef685a24cbc6fb4968cac316b`.
- Generator: `generate_sources.py`, 17,927 bytes, `c33f0d1641ac771e0958167ddad676aa748af5ade22fdb4baa78407b0ea79903`.

The unchanged builder body was checked directly against the restored normal04 source `16e1e03e466c946dcb4c72f5fc900f2552bba919fdcf49ba136c41d0e544cdc1`. Replacing its single fixed `...build-04-20261106` ROOT occurrence with `...build-05-20261106` yields the new file byte for byte. The original strict build/resource implementation was not relaxed.

## Runtime and App identity binding

The new fixed identities are derived from the saved actual R2 baseline, not selected from current PIDs or accepted by changing an old guard. `expected_from_baseline` cross-checks the binding and held-process records for exactly eight roles, including composer. `qualify_baseline` verifies the canonical runtime digest, actual framework digest, boot, all eight identities, cell configuration and the five Main resource limits.

The snapshot loads only the exact new guard source `d84df98d55352ef9ae66753ee15f3746d9d9a64c35fddf392a08f10ba4105cb3` and requires its full authority PINS. It calls the existing `current_baseline`, `current_guard(candidate, action_attempted=False)` and `check_app_scope` APIs. Their actual saved/frozen implementations and returned key shapes match the new caller. As an additional local interface check, the actual JD02 saved `guard_before` receipt was accepted by the pure `qualify_typed_guard` function; no live guard was invoked.

`check_app_scope` performs its own current runtime checks before and after exact App path/file identity comparisons. It does not claim a new APK signature verification. The builder's pre/post fence compares runtime, framework, qualification, current guard, protected roles, scope digest and the exact package list. The current R2 baseline remains an identity qualification, and the source cannot produce a new Android QA qualification or production-ready claim.

`APP_SCOPE_PIN` and `APP_SCOPE_PACKAGES` are still `None` in source-r1. The generator's final mode requires the supplied raw App-scope SHA, the same runtime epoch, and inclusion of every initial scope member; it derives the package list from every key in the actual scope, with no caller-selected subset parameter. The final reviewed input must be the complete post-upgrade 46-member scope (45 historical launcher targets plus `local.pocket4.actions.v2`), retaining all upgraded package identities. This is not a claim of a new complete Android launcher resolver.

## Resources, child ownership and failure handling

The actual build remains UID1000 in its exact owned runtime job unit. It requires 10 GiB MemoryMax, CPU quota `200000 100000`, zero owned swap limit/current, and a freshly read MemAvailable of at least 15 GiB. Global swap does not count as the build budget. The unmodified resource admission writes the bounded raw observation before deciding. A low-memory rejection does not invoke Soong or automatically retry.

The Main snapshot requires its unchanged five resource limits and zero pre/post OOM deltas. It records pressure/resource deltas without claiming continuous noninterference or attributing changes causally to this build.

Both outer and root capture supervisors use owned-child subreapers. A spawned leader has a new session/group, and the leader is kept unreaped while its group is retired. Adopted descendants are taken only from this supervisor's kernel-listed children and signalled by pidfd where available; PID fallback is restricted to a still-unreaped direct/adopted child. The eight protected Main PIDs are explicitly excluded from capture signalling. This is not the previous Android wrapper's shared-PGID retirement path.

Allocation failure, timeout, escaped descendant, EPERM, incomplete wait, leaked FD, or missed deadline remains a failure. Cleanup is not converted into successful observation/build. The existing real host lifecycle controls are still required inside the eventual run, before the first Main snapshot. The saved 59-case result is a local pure-control result and is not a new actual host lifecycle or Main PASS.

The root snapshot retains its 15-second observation budget with a bounded retirement phase; the outer transport retains its separate 25+5-second limit. The added typedguard and App-scope reads must finish inside these original budgets. If they do not, the before-fence must fail and no build may be inferred to have run; this review did not measure their current host latency or change a timeout.

## Execution conditions still outstanding

1. Obtain and pin the final post-upgrade App-scope original bytes, then generate a new source revision with the full member set. Do not edit a previous qualification or inherit a previous gate PASS.
2. Recompute the changed snapshot, root supervisor, fenced wrapper, stager and wire pins. The current transport has `WIRE_BYTES = None` and `WIRE_SHA256 = None` and rejects `--execute-once`.
3. Check the actual final packet and its UID1000 execution limits. The stage writes only a fresh normal05 host root and never installs a framework or App.
4. Preserve actual normal04/earlier failures and normal05 pre/post/child/resource receipts. Successful compilation, if later observed, will still not authorize Android deployment, UI, App permission changes, or production cleanup.

No historical Bili UNKNOWN, Main Accept boundary, Meituan location boundary, integrity constraint, original guard, or application data was changed by this review.
