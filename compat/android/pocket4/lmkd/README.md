# Pocket4 LMKD candidates and isolated pressure evidence — NO-GO

The r4 Android target `b09939386d2f3e128d827701ede4da7594f9b333c92e296ddc1f7bbc50782c8f` is **not approved for Main deployment**. Its r7 pressure trial lost both the cached and foreground processes. Later diagnostics and the separately built r5 fix do not replace that failed survival result. This isolated review bundle does not replace Foundation runtime sources or change the running Android environment.

## Changes and evidence

| Layer | Change | Qualification |
| --- | --- | --- |
| Historical r3 | Read the cell's pinned cgroup2 memory budget and PSI through the fixed `/sys/fs/cgroup` contract. | Retained as the negative baseline for the no-scan early return. |
| r4 target | A new coherent `memory.events.high` increment, current usage above a stable finite high limit, and an actual critical PSI event may reach existing policy despite zero scan/refault counters. | 102 host checks and Android build passed; real foreground survival failed. Do not deploy. |
| Fixture r8 | Drain the owned log socket while waiting for ACK; retain actual pidfd exit observations before failure. | 29 temporary/mock guard checks and 24 owned IPC checks passed. Protocol passed; pressure aborted at the host PSI guard. |
| r5 candidate | Keep bounded pending high evidence across medium/poll reads, consume at the critical decision, invalidate on expiry, budget/generation changes or failed/incoherent samples. | Source controls and isolated Android incremental build passed. No protocol/pressure canary or Main deployment. |

r4 preserves existing victim selection and thresholds. Its selection controls use controlled process I/O; they do not demonstrate foreground survival under pressure. r5 preserves the pre-kill diagnostic and stock selection/threshold expressions. Its pending-evidence fix is not an established explanation or solution for r7's foreground death.

## Complete source reconstruction

The full patch starts at [AOSP LMKD](https://android.googlesource.com/platform/system/memory/lmkd), commit `c3601e823bd07c9c190f67e2f9bc7486e4978328`. It changes `Android.bp` and `lmkd.cpp`, and adds `memory_cgroup.cpp` and `memory_cgroup.h`. Original Apache-2.0 copyright notices remain intact.

Each manifest covers all 31 regular source files. The unchanged upstream `.clang-format` symlink points outside this small repository into AOSP `build/soong`; `manifests/upstream-symlinks.json` separately pins its exact target. The verifier checks that archive metadata without following or materializing the external formatter target. The verifier exports the public commit, applies upstream-to-r4, reconstructs r3 by reversing its recorded delta, and applies the separate r4-to-r5 patch. It verifies every regular path/hash/size at all stages and all eight supplied r4/r5 source files. Run from this directory with an existing clone:

```sh
python3 tools/verify_source_series.py \
  --upstream-repo /path/to/aosp-lmkd \
  --out-dir /tmp/pocket4-lmkd-new-source-trees \
  --receipt /tmp/pocket4-lmkd-new-source-verification.json
```

Both output paths must be new. This command writes only source/evidence directories, without compilation, Android or pressure execution.

## Host controls

r4 records 57 adapter assertions, 20 actual Reader checks with controlled descriptor substitutions, 10 extracted production-guard cases, and 15 stock-selection controls. The old guard fails the critical high-throttled case; other negative controls remain. Exact tests and normalized original receipts are included.

A later negative control combines the actual r4 Reader and extracted production guard. An intermediate medium or poll read consumes the high event before the critical decision. Both sequences fail as expected. This source-level defect is separate from r7's still-unresolved double death.

r5 records **326 state assertions including setup assertions**, 57 adapter assertions, 20 Reader assertions, 15 stock-selection controls, and two actual Reader/guard sequences with 18 assertions per candidate arm. Do not call these 326 independent cases. Optional source-only controls on reconstructed trees:

```sh
python3 tests/r5/run_controls.py \
  --source-dir /tmp/pocket4-lmkd-new-source-trees/r5 \
  --baseline-dir /tmp/pocket4-lmkd-new-source-trees/r4 \
  --r4-tests-dir tests/r4 \
  --out-dir /tmp/pocket4-lmkd-new-host-controls
```

Use r4 as the baseline. These controls do not touch Android or run pressure. Original failed trials and prepared r5 evidence remain separate.

## Conditional Android build provenance

The recorded r4 build freshly compiled two translation units and linked four reused support objects. The compiler entry, actual compile/link argv, actual object inputs, shared libraries and dynamic loader are pinned.

The six dependency files contain **803 distinct emitted records**. They were produced with **`-MMD`**, which omits system headers. They are not a complete preprocessor/system-header closure. The older 797-record inventory also includes source files and must not be described as 797 headers.

`manifests/recorded-mmd-dependencies.json` gives each recorded path, hash, size, using translation units and provenance. The actual object list distinguishes fresh objects, reused support objects and CRT/compiler-runtime inputs. Historical `support_inputs` also pinned preserved older objects that were not r4 link inputs; the actual link argv is authoritative.

A clean hermetic Android rebuild is **not established**. The materialized AOSP/generated workspace, omitted system/builtin headers, reused object production, CRT outputs, DSOs and loader remain external or incompletely closed. No binary/APK/DSO/signing material is distributed. The separate r5 build is recorded in `evidence/r5-build/`: target `c6d49d95c16d1ce6d94293313ae9f6f683a079ebd4cc821338a701dfe5b2cf6f`, two new objects and the same four pinned reused objects. Its new translation units use `-MD`: all 976 emitted records were covered by 3,586 prep pins and remained unchanged. That does not close the reused objects' historical system-header gap. The published argv arrays are explicitly reconstructed from saved r3 records and frozen r4/r5 transformations, not directly copied from the latest remote command logs. The earlier source-only control receipt retains its historical scope.

## Retained real pressure outcomes

| Trial | Actual result | Limit |
| --- | --- | --- |
| Fixture r5 / original target | Boundary probe and protocol passed; pressure guard aborted. | Old diagnostic path did not retain the precise rejected health frame. Do not invent a threshold value or external cause. |
| Fixture r6 / original target | Durable health frame: host full PSI 11.4% against `< 10%`; own current exceeded high, high events increased, scan/refault zero, cached process alive, allocator D state. | No positive kill qualification. Owned work contributes host PSI; the error label does not prove an external workload cause. |
| Fixture r7 / r4 | Probe/protocol passed; cached and foreground processes both disappeared, protected/sentinel survived, OOM counters zero, Main/framework preserved. | **Real foreground-survival failure.** Neither a fixture false positive nor positive pressure acceptance. |
| Fixture r8 / same r4 | Protocol passed; regular cached kill logged, then host full PSI 15.17% tripped the unchanged guard. | Aborted; does not override r7 or establish final survival. |

r7's helper passed its cached SIGKILL check before failing the foreground pidfd check. The “Resource temporarily unavailable” suffix came from a stale errno in the failure formatter, not a proven syscall cause. Its ACK wait did not drain the private log socket, leaving a decision-log gap. r8's socket controls reproduce that diagnostic boundary; they do not prove Android logging caused the double death.

## Fixture relocation and boundaries

The public r8 runner has one disclosed relocation: its fixed input root is `/srv/pocket4-lmkd-inputs` instead of the private preparation directory. Other source is retained. The original runner hash and prepared manifest are separate from the relocated public source. The old manifest cannot authorize the public runner.

The Python boundary suite uses temporary files/mock guards, without systemd, Main, LMKD or cgroup execution:

```sh
python3 fixture-r8/test_runner.py
```

Actual fixture execution requires reviewed exact binary inputs, a fresh manifest binding the current runner, a fresh Main/framework fence and an explicit window. This bundle does not supply a ready-to-run live fence or execution permission.

The fixed contract remains `DROIDLOOM_CELL=1` and `DROIDLOOM_LMKD_CGROUP=/sys/fs/cgroup`. Only a verified owned child domain is projected there. The namespace root's PSI-write denial remains required. Six namespace bindings, domain inode checks and pidfds restrict ownership.

Bounds remain: memory max 512 MiB; high initially unlimited then 384 MiB; zero swap; one CPU; 64 tasks; 90-second phase bound. Admission requires host available memory ≥ 8 GiB, swap free ≥ 2 GiB, Main memory/pids < 80%, Main and host full PSI < 10%, and no Main event increments. Host/init and each framework process generation, namespace, configuration and resource identity are pinned.

Only the minimal pidfd signaling route was exercised. PID-reuse behavior and production cgroup-group kill remain unqualified. Do not loosen these boundaries to obtain a pass.

## Current Main integration boundary

A separate read-only observation after presenter/native activation found that Main still selects `/vendor/bin/droidloom-lmkd-compat`, a service that drains and acknowledges commands and never kills. `/system/bin/lmkd` has the same binary hash. `DROIDLOOM_CELL=1` is present and the LMKD cgroup variable is absent. A file hash alone cannot prove real LMKD integration. The observed cgroup-root/`nsdelegate` layout and source-level PSI denial condition are distinguished from an actual trigger-write test: no Main write was attempted. A scoped monitor-access design, explicit service/environment verification and successful survival canaries remain prerequisites. See `evidence/r5-build/main-integration-summary.json`.
