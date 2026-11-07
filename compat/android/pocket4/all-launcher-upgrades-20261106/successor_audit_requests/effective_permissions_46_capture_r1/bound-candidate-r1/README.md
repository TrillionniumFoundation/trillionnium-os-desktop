# Actual 49 package binding, 46 Launcher permission capture, 14 serial batches

This is a new source candidate. No new capture has been submitted or claimed by its author. It preserves the original 45-target series, its failed batch 03 and its STOP, plus the separate successful microG correction. Those records do not count as results of this new series.

## Actual input and scope

The normal `.r2` helper installation succeeded in job `1a1b34fadf6-fc05-81f2`; the independently read original scope succeeded in job `1a1b3539bb5-fc05-821a`. `bind_actual_scope49.py` verifies the original stdout/terminal of both jobs, exact source and request, child normal exit and held-pidfd retirement, all observer FDs, and the complete 60,614 byte scope with SHA-256 `7187bc544cf6812ad47efdf141cd111897a1124b9532f84b7cf599b0c0fee1e3`. It calls the original installer `validate_scope_transition` using the real prior48, actual installed helper and actual49, rather than replacing that validator with a shape check.

The scope contains 49 packages and 89 APKs. It adds `.r2` / UID 10167 while retaining every prior48 row. Launcher membership comes from actual discovery job `1a1b307f521-fc05-807a`: 46 packages, including `com.example.ndk_tests`. Every batch freshly re-reads the native catalog and requires exact component membership, then verifies all 49 package identities before and after the fixed queries. The original 13 partitions are preserved; NDK is batch 14. A capture does not rerun the complete framework resolver and does not newly verify APK signatures. These limitations are explicit in each result.

The current protected scope is immutable input. A later legitimate installation, framework change, component change or helper change must produce a new reviewed binding; this candidate will not adopt it automatically.

## Capture behavior

Each batch uses the existing sidecar and frozen R5 namespace/classpath transport. It makes three native reads (`status`, `applications`, `status`), then `cmd package help` and the following two reads for each fixed target:

```text
/system/bin/cmd package dump-package PACKAGE
/system/bin/cmd appops get --user 0 PACKAGE
```

There are 106 fixed Android reads across all 14 batches. Package dump itself has no user filter; the later literal parser selects only the unique matching package and User 0 block. No launch, UI action, lifecycle command, permission change, ADB, business-file read or cleanup is authorized by this series. Bili's original UNKNOWN and the saved Meituan location state are checked and retained. Bili Accept remains restricted to its separately authorized historical test cell.

The original command deadlines, process ownership, joined-child rules, poisoned-unjoined handling, namespace cleanup, locks, FD lifecycle and libffi bootstrap remain intact. The original 11 owned-lifetime functions are unchanged; only the capture-specific result predicate is new. The worker functions exactly match the frozen normal/microG templates, and transport functions are unchanged. Some inherited module documentation still names the historical explicit47 source; the executable constants and predicates require exact actual49 and actual46 membership.

All streams retain the original 256 KiB cap except **batch 02, command 02, exact microG `dump-package` stdout**, which reuses the separately proved 2 MiB implementation. Its stderr, help, AppOps, native streams and every other target retain 256 KiB. Command timeout remains 30 seconds, Android timeout 25 seconds, worker deadline 900 seconds, owned process 1000 seconds, external process request 1100 seconds / CPU 100% / memory 1 GiB / nice 10. No automatic retry is present.

## Entry points for the root coordinator

Run from this directory. Validation and status are local reads. The author has only run validation/status and controls against its own temporary test ledger.

```sh
python3 -B -I permission_capture_gate.py validate
python3 -B -I permission_capture_gate.py status
```

`REQUEST_INDEX.json` lists all 14 exact process-request files, target identities, keys, stage roots and output roots. `CAPTURE_PLAN.json` is the authoritative frozen plan. Each request already includes its five source/input files and exact stager. The root coordinator can use the existing process-start tool with that object; no new backend is required.

For a batch number N that `status` reports as `NEXT_READY`:

```sh
python3 -B -I root_local_coordinator.py claim N > request-to-submit.original.json
```

This creates only a new immutable **local** intent, then prints the already fixed request. Submit that same request/key once through the existing process tool. Preserve the actual start, then write `submitted-job.json` into the claimed ledger folder with exactly `job_id`, `idempotency_key`, `request_sha256`, `process_request_sha256`, and `plan_sha256`. These values must come from the actual launch and the frozen plan, not an anticipated job.

The new ledger is `successor_audit_requests/actual/permissions-fixed46-r1/batch-NN`. Save the actual terminal JSON and each complete process-read page as `read-OFFSET.original.txt`, with offsets 0, 16384, 32768, and so forth, preserving the original bytes. The inherited coordinator reconstructs stdout from these hex-backed pages and requires complete/durable terminal output and empty stderr:

```sh
python3 -B -I root_local_coordinator.py settle N status-01.original.json
```

Settlement checks stage, source pins, normal child exit, original held pidfd, complete parent FD identity restoration, actual worker raw, all 49 identities, exact target/service streams, and zero mutation counters. Only `NEXT_READY` permits a later claim. Failed, incomplete, absent or unknown outputs stop the series. For a failed/unknown launch, reconcile the original submission; never change keys or claim the next batch. A malformed failure stream may cause the inherited coordinator to exit after preserving its original stdout and terminal; `permission_capture_gate.py status` then remains stopped.

## Readback and literal interpretation after an actual successful capture

The subsequent pipeline is prepared, but no future log pin, job or permission value is prefilled.

```sh
python3 -B -I prepare_completed_readback.py --batch N
```

This first runs the complete new serial gate and requires N to be in its actual successful `completed` list. It selects only the two real service stdout files per target from that receipt. It then calls the **unchanged proven `render_reader`** to generate a bounded host-only reader under `readbacks/batch-NN`. Its exact request can be reviewed and submitted once by root. It never enters Main or takes the action lock. The original five per-file reader functions retain no-follow opens, file/path stat and hash rechecks, and their original whole-process FD count check.

The reader keeps the original 2 MiB total service-body bound and 1 MiB compressed stdout bound. A full-limit microG PM plus AppOps that exceeds the total bound is rejected, never truncated. Log pin generation happens only after actual capture success, including exact microG PM size/hash/path. The generated readback plan binds the new49 capture job, artifact, terminal and targets. It does not inherit an old correction result as new proof.

Store complete reader stdout **outside this repository** at `p4_private_ui/fixed46-permissions-compressed-readback-r1/batch-NN/stdout.original.jsonl`. Keep only `start.original.txt` and `terminal.original.json` in `readbacks/batch-NN/actual-public/`, along with later safe derived receipts. Then:

```sh
python3 -B -I decode_completed_readback.py --batch N --plan-sha256 ACTUAL_REVIEWED_PLAN_SHA
python3 -B -I interpret_completed_readback.py --batch N --plan-sha256 ACTUAL_REVIEWED_PLAN_SHA
```

The decoder changes only local destinations and the 1–14 range of the proven decoder. Its seven helper functions, including full envelope/decompression/body hash validation, are unchanged. It requires the actual exact reader start and durable success before decoding all bodies. Raw and decoded original logs remain private; only safe pins and resource metadata are published.

The interpreter independently revalidates capture, readback source/start/terminal/receipt and the complete private envelope, then reads the private files with their actual pins. It imports the original eight literal functions (`need`, `sha`, `unknown`, `lines`, `section`, `parse_package`, `parse_appops`, `derive`) unchanged. Its original exact-path-and-pin microG exception is bound to the new actual batch02 PM log; no other input acquires a larger limit. It does not normalize permission whitespace or infer absent grants, merge ambiguous sections, attribute other users, or infer unprefixed AppOps UID scope. Unexpected grammar remains UNKNOWN. PM true is only a reported grant, false is not proof of a user denial, AppOps mode is not authorization, and roles/core operation/permission denial recovery remain untested.

## Local evidence and privacy

`closure-attempt1.stdout.original.json` records full source/actual49 binding PASS with zero claims and zero new observations. `controls-attempt1.stdout.original.json` records seven boundary controls, including a real temporary O_EXCL intent, unsettled stop, rejection of an actual failed terminal, old microG result not qualifying the new49 scope, actual 1,478,016 byte stream budget comparison, and full local FD identities 3→3. `readback-controls-attempt1.stdout.original.json` records refusal of unobserved batches 01 and 14 before any reader directory is created, plus unchanged decoder/parser source. These are local controls, not Main permission results.

The first two assembly attempts failed locally while resolving the `GUARD` expression and distinguishing `PACKAGES` from `TARGET_PACKAGES`. Their original stderr is retained. The final assembler uses exact top-level AST assignment spans and the already pinned original guard value; it did not alter any frozen input or submit a process.

No raw PM/AppOps body, private window/UI content, APK, key material or private log bundle belongs in Git. Source, exact requests, public pins, original metadata receipts and literal permission summaries may be retained. New semantic results remain unavailable until the complete actual capture/readback/interpretation chain succeeds. **Production-ready count and cleanup count remain zero.**
