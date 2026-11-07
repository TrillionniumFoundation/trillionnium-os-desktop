# Final action-window consistency correction

This isolated source candidate fixes one missing comparison in the Pocket4 R3
owned QA helper. It has not been built as an Android APK, installed, or used to
operate a device. It is a test-tool correctness correction and does not qualify
an App for production.

## Defect and change

The first `action_target` inspection checks both `tree_sha256` and
`window_sha256` against the earlier inspection. Immediately before dispatch,
the second `action_final_window` inspection checked only the window ID and tree
digest. `inspect()` obtains the window bounds from `AccessibilityWindowInfo` and
hashes them separately from the node tree. Equal node-tree digests therefore do
not establish equal window envelopes at that last check.

The candidate adds the missing final `window_sha256` equality to the existing
`need(..., "FOCUS_CHANGED_BEFORE_ACTION")`. The error code, exact one-inspection
behavior, `finally { finalWindow.close(); }`, deadline check, action-attempt
assignment, subsequent node action, and outer cleanup are unchanged. No
predicate is weakened and no retry is added. This check still does not make an
Android inspection and action atomic.

The reviewable change is `final-window-sha256.patch`. The complete preimage and
candidate Java files are retained under their respective directories, at
`src/org/droidloom/qa/bili/r3/ActionRunner.java`.

## Source identity

The preimage is copied from the existing frozen R3 source at
`/workspace/scratch/94990735b266/owned-bili-qa-r3-search-01/source`.

| Input | Identity |
| --- | --- |
| Preimage Java | 37,812 bytes; SHA-256 `374c4b3ba1d83a97a376613b2ab2e015006019a61dd36970b27c64693d5bcef5` |
| Candidate Java | 37,949 bytes; SHA-256 `d43660d0a3ccfd4226ed8619a52e8d7cf160cf84ec11450a35a03af768a0eb97` |
| Original nine-file R3 source manifest | SHA-256 `91af9446dc2e749ecf3ef75967bfa2154eae8a94a73d9b4149e0574789a5d422` |
| Historical R3 APK bound by that build review | SHA-256 `a32348c8d4615872aa2ec04b9253cd89826aca31d92d6c208365745ff522d3c8` |

The historical APK identifies the unmodified preimage lineage. It is not an APK
for this changed candidate. The original source manifest and actual-build review
are copied unchanged under `references/`; `SOURCE_PINS.json` inventories this
isolated correction. Nothing in the original workspace was modified.

## Executed regression

Run:

```sh
python test_final_window.py
```

The regression extracts the exact production final-window guard, its immediate
`try/finally`, deadline call, action-attempt assignment, and exception helper from
each pinned Java source. Java 17.0.20 compiles and executes both extracted
fragments. The predicate is not reimplemented in the test. Controlled capture
objects, string-field storage, an inspection result, a deadline, and a dispatch
marker are the explicit test seams.

Both arms use the same acceptance expectations:

| Case | Original | Candidate |
| --- | --- | --- |
| Window ID, tree and window digest unchanged | Permits dispatch marker | Permits dispatch marker |
| Same ID and tree; window bounds expand from `[0,0,800,600]` to `[0,0,1000,600]` | Incorrectly permits dispatch marker | Rejects before action-attempt assignment |
| Window ID changes | Rejects | Rejects |
| Tree digest changes | Rejects | Rejects |
| Final window digest is missing, as a malformed-input control | Incorrectly permits dispatch marker | Field access fails before dispatch |
| Final tree digest is missing | Field access fails | Field access fails |
| Final inspection fails | Fails without dispatch | Fails without dispatch |
| Deadline fails after a matching window | Fails without dispatch | Fails without dispatch |

Original: **6/8, expected test exit 1**. Candidate: **8/8, test exit 0**. Both
fragment compilations exit 0. All eight cases also check inspection count, final
capture close count, deadline order and whether the action-attempt/dispatch
markers were reached. Obtained final captures close once, including on the new
rejection path. A failed inspection produces no capture to close. The outer
current-capture lifecycle is outside this fragment and is not claimed tested.

`evidence/result.json` preserves all rows, source and fragment hashes, compiler
and execution return codes, and qualification limits. The generated Java
harnesses, stdout and stderr are retained beside it. The test also verifies that
the complete candidate is exactly the one intended replacement in the pinned
preimage.

This controlled window-envelope input proves the source predicate omission. It
does not prove that Pocket4 has exhibited that geometry timing, that this is the
cause of Bilibili buffering, or that an installed Android helper runs correctly.
Those remain separate validations before any deployment.

## Complete Java compilation with Pocket4's actual SDK

A later isolated compile used the original Pocket4 JDK21 `javac` and API31
`android.jar`, with the original `-source 8 -target 8 -proc:none` flags. The
remote root is `/home/alex/work/pocket4-qa-window-fix-20261105-r12`; no original
source or build directory was changed.

The complete original nine-file source was copied into both fresh source
directories. Only the reviewed `ActionRunner.java` differs in the candidate.
Two sequential `javac` commands compile the full original and candidate Java
source. The new preimage classes match all six currently observed historical
class files byte for byte, providing a direct comparison under the actual SDK.

| Complete compile | Result |
| --- | --- |
| Preimage `javac` | Exit 0, child joined, 1,227 ms |
| Candidate `javac` | Exit 0, child joined, 1,171 ms |
| Output classes per arm | Six, all Java class version 52 |
| Changed class | `org/droidloom/qa/bili/r3/ActionRunner.class` |
| Identical classes | `$1`, `$2`, `$Capture`, `$Rejected`, `$SelectedWindows` |
| Original and copied source verification | All hashes unchanged after compile |
| Compiler, SDK and selected JVM inputs | Eleven pinned inputs unchanged before/after |

Both compiles emit the same three existing JDK warnings about obsolete Java 8
source/target options. Their full stderr is retained; it is not reported empty.

The actual job has one-CPU quota, CPU affinity `[0]`, nice level 10, a 512 MiB
memory ceiling, zero swap allowance and 128-task ceiling. Observed owned memory
peak is **311,328,768 bytes**; swap peak is zero; all recorded memory-event
counters remain zero. These are measurements of this compile job, not a claim
about every concurrent host workload.

The runtime confirmed job `1a1aa25cc73-fc05-3e25` succeeded with exit 0 and complete,
durable logs. `evidence/sdk-build-result.json` is the exact 23,095-byte remote
receipt, SHA-256
`13bbebccc31f90f831edaa8641dc4adb3e4f6e3048018e9ee632d07617f9b338`.
`evidence/sdk-job-status.json` records the authoritative job terminal. The compile
driver is `sdk_compile.py`; it only invokes `javac`.

No D8, APK packaging, signing, installation, helper execution, Android command,
UI action or App qualification occurred. Full Java compilation is now verified;
APK and runtime validation remain open.
