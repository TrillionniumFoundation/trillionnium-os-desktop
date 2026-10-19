# Paired clock and scheduler handoff: exact CI contract

Historical scope: the 201-test suite and failure sets below belong to PR #203. The subsequent [CPU usage slice](CPU_USAGE_G1B.md) adds 19 core tests and one expected `clocksource-drop-fraction` failure, retaining the original seven controls and complete unfiltered gate. Its final candidate requires its own execution and source receipts.

This integrates the production slices described in [CPU_BOOTTIME_CLOCK](CPU_BOOTTIME_CLOCK.md) and [CPU_SCHEDULER_HANDOFF](CPU_SCHEDULER_HANDOFF.md), on the reviewed [retained-owner baseline](../../results/organ-backend/2026-10-19-owner-retention/README.md). The implementation preserves the original clock, scheduler, controller ancestry and accounting ownership. It adds eight paired-clock/vDSO and four actual-runqueue regressions, for an expected 201 core tests at this source handoff. BOOTTIME bandwidth conversion and coherent native usage remain the following slice.

## Execution and source identity

The A06 workflow first runs the complete unfiltered original core and OSTD gate on the clean candidate with `nightly-2026-07-21`. Each of seven separate frozen production-only patches then creates an identified local commit from that same candidate. Its full original core suite runs at the original OSDK compile-time source path, using the same OSDK ELF, compiler, lockfiles, vDSO library and QEMU/firmware profile. The runner restores the candidate in `finally` without force or discarding changes. Source files, test names, exact expected failures, raw serial, actual original-gate exit and both ELF identities are bound to each receipt. A compile error, timeout or unexpected failure set fails the workflow.

| Control | Original production path | Exact expected failed tests |
| --- | --- | --- |
| `owner-current-slot` | Original cgroup CPU owner | Three retained-incarnation failures specified in CPU_OWNER_RETENTION |
| `clocksource-drop-fraction` | Original ClockSource refresh | Three exact clock failures specified in CPU_BOOTTIME_CLOCK |
| `vdso-drop-fraction` | Original vDSO shifted base | Three exact phase/VMO failures specified in CPU_BOOTTIME_CLOCK |
| `vdso-skip-fault-mode` | Original vDSO shared data write | One mapped-VMO failure specified in CPU_BOOTTIME_CLOCK |
| `handoff-drop-tail` | Original runqueue handoff | All four handoff regressions |
| `handoff-eligibility-first` | Original runqueue eligibility ordering | One shared-ancestor window/debt failure |
| `dequeue-drop-owner` | Original runqueue dequeue | Both wait and exit retention failures |

The control catalogue hardcodes each reviewed patch SHA-256, changed production path, minimum complete suite size and exact failed-name set. No CLI option supplies arbitrary mutations, result overrides or test filters. Every negative must have the same complete test-name set as the original successful suite, with original QEMU failure exit 65 and original OSDK/gate failure.

## Preserve the actual green ELF between controls

All builds use the original OSDK-bound target path. A negative build therefore replaces the target ELF bytes. Before the first mutation, the runner archives the green ELF only after matching the original successful QEMU record. Later controls explicitly consume that retained copy with `--green-kernel`, verify the same original size and digest, and retain their own negative ELF separately. They never hash a newly rebuilt target and redefine it as green. Two host regressions reproduce shared-target replacement and reject changed/missing backups or inconsistent recorded sizes.

Each control retains source-before/source-after, its separate archive source, candidate-before/candidate-after, raw serial, real gate command and exit, environment, locks, QEMU record, patch and both ELF files. The ordinary product build and existing QueryAbi14, SCM27, RLIMIT37 and fixed CPU timing/quota lanes run only after every required control succeeds and the candidate is restored. Four HOS2 effects remain disabled.

## Status at integration

The root review read every production change and the twelve new tests. All seven frozen patches apply to the combined source; all 118 protected upstream/build inputs pass. Eleven host serial/restoration/ELF-identity tests and all 36 existing source/specification tests pass. The full original kernel type-check/build and real positive/negative QEMU execution for this new tree have not yet occurred at this document's creation. CI must supply those results before merge or qualification. Physical devices, SMP rendezvous, authorized effects, full Linux32 and Hepta W1 remain separately assessed.
