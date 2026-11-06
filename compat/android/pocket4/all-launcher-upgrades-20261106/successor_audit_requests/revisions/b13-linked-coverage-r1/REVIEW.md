# Independent linkage after the exact b13 correction

This is a local evidence validator. It contains no submission, claim, remote read,
namespace, APK-tool execution or ledger-write entry point. The original ledger
still ends in `STOP_NO_RETRY`; its b05 and b13 failed results are not rewritten.

## Actual conclusion

`COVERAGE.actual.json` was produced by the local validator from the immutable
original records. It links **45 Launcher packages, 85 complete APK files and 255
successful APK-tool commands**. The grouping remains the original 13 partitions.
The original b05 and b13 failures are retained as failed observations; the
corresponding groups use their separate, fully verified corrective jobs.

The b13 correction is actual job `1a1b2ba9875-fc05-7f80`. Its 29,446-byte original
outer stream, 79,075-byte decoded worker, successful authoritative terminal and
exact source-stage/request closure are all bound. The three APKs are the same
files as the failed job, with the same full file stat, SHA256, package UID,
codePath, CE/DE directory identity and PackageManager certificate records.
All nine commands finished normally, all three signatures match PackageManager,
the 20 complete tool-layout observations retain every directory identity and
all thirty true `ENOENT` checks, the eleven owned layout FDs close, all 7,146
observation FDs close, the original owned child's pidfd proves normal exit and
the parent's descriptors restore. The complete pre/after/final worker descriptor
identities match; the known libffi resource is retired by that child's exit.

The declared fixture version attributes remain absent: `version_code`,
`version_code_major`, and `version_name` are null. The observed raw badging
values remain empty strings. Effective long version code zero is a separate
field, supported by the exact XML absence, actual PM zero, fixed APK and fresh
normal signature. No display version name is invented.

## Existing gates and additional checks

The frozen 34,438-byte linked gate is imported only after its exact SHA256 is
checked. Its original plan loader, preserved b01–04 and b05-correction checks,
complete APK/signature/command/layout checks and result-publication projection
are reused unchanged. The b06–12 loop applies exactly the existing intent,
submitted-job, terminal, owned-lifetime and complete-APK requirements. It does
not call `inspect()` with a truncated plan, and never calls `claim()`.

The original owned gate is copied with only the function name and the newly
approved b13 source-stage schema changed. The terminal gate is an exact copy.
`owned-gate-against-frozen-linker.diff` and the controls establish this explicitly.
The original failed b13 has its own strict failure validation: its real failed
terminal, failed outer and child status, exact parse error, absent post-success
census field, actual final census and normal original pidfd retirement are
retained. Missing success-only fields are not filled in.

Every covered app is additionally checked against the fixed 47-package scope's
exact APK/UID/data/certificate projection. The 45-package set and components are
compared with the actual, fixed two-sample PackageManager MAIN/LAUNCHER resolver
reference. This does not claim a new resolver query or a new observation of all
47 packages in any one APK batch. The two helper packages are explicitly excluded.

`INPUT_CLOSURE.json` freezes 175 local inputs: old plans/source closures, original
claims/submissions/terminals/artifacts, both failures, both independent repairs,
the exact fixture raw logs, the final scope and resolver reference. The complete
closure is checked before and after validation. Authoritative JSON numbers are
read and handled by Python without a JavaScript numeric roundtrip.

## Controls and preservation

Four actual local controls passed with zero failures or skips and FD count 4→4:

- Full valid actual history plus correction produces the exact 45/85/255 set.
- The actual original failed b13 is rejected by both success paths.
- In-memory loss of original pidfd closure or complete descriptor identity is rejected.
- In-memory omission of a command, invalid signature, changed nanosecond stat or incomplete layout is rejected.

Negative mutations exist only in memory; they are never stored as actual receipts.
The first local development run exposed a missing `terminal_gate` definition
in the copied owned gate. Its draft source and failed local stdout are retained;
the fix copied the exact original terminal function. No Main or remote process
was run during that local development failure. The subsequent actual validation
and controls passed. Old device failures, ledger and source remain untouched.

## Reproduce locally

```sh
python3 -I -B successor_audit_requests/revisions/b13-linked-coverage-r1/verify_linked_coverage.py
python3 -I -B successor_audit_requests/revisions/b13-linked-coverage-r1/check_linkage.py
```

Run from the project root. Both commands only read local evidence and write their
result to stdout. They do not rewrite `COVERAGE.actual.json` or any ledger.

This conclusion covers APK bytes, manifests, declared permissions and normal
signature/PM agreement. It does not establish complete resource-table health,
effective grants/AppOps/roles, login or core workflows, soak/restart recovery,
production readiness, or permission to remove old builds.
