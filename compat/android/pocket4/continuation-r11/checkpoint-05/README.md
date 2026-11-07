# Pocket4 Android continuation — checkpoint 05

**Status: NO-GO for production activation; 0 of 45 launcher apps have whole-app production acceptance.** This checkpoint adds measured source fixes and preserves failed runs. It does not deploy a new Main engine or qualify an entire commercial app.

Main remains on engine `c8b9bae4466d4f66525fdef6bcec140b29612581efeb6ceb621f96e17277d26d`, presenter `47f34d5f68783a372283cb63a42034d5899e270524cca40122bf28fd5e903f24`, framework epoch `48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f`. Every owned metadata cycle returned the package set from 183 to the original 182 entries and removed only its verified test package.

## Metadata: one real Android discrepancy fixed

R18 exercised the actual fixed metadata owner and ordinary metadata wrappers in an owned nondebuggable x86_64 APK. Ten cases returned at a metadata-consistency guard. They had not reached the wrapper checks; unfilled UID fields were not evidence of a credential mismatch. R19 kept the original comparisons and added bounded field diagnostics.

All ten failed cases identified the same discrepancy: native Bionic `fstatfs` returned `f_flags=0`, while the raw syscall snapshot retained `0x20`. All compared stat fields and other statfs fields matched. The exact Bionic source clears kernel-private `ST_VALID` after a successful call.

R20 adds that conversion only at the successful **host-libc** publication boundary under `__BIONIC__`. It preserves error returns, errno restoration, every other flag, and the original test comparisons. The actual Android ELF was audited for its fixed raw-worker closure. Independent root review inspected the sole Worker/null clone entry and the successful-result branch, byte AND, and complete Snapshot copy in that ELF.

| Actual Android cycle | Result | Cleanup and scope |
| --- | --- | --- |
| R18 | FAIL; expected-behavior mask `0x840` | Twelve direct and two nested children reaped; UID 10160 removed. Ten wrapper paths were not reached. |
| R19 diagnostic | FAIL; mask `0x840`; ten identical `f_flags` discrepancies | Twelve direct and two nested children reaped; UID 10161 removed. Original guards retained. |
| R20 | All twelve expected observations; mask `0xfff` | Twelve direct and two nested children reaped; UID 10162 removed; no timeout; Main unchanged. |

R20 includes actual ordinary Fstat/Fstatfs/QueryOrigin behavior, O_PATH, full caller FD table, low address-space limits, private fork, twelve clear-TID restart rounds, invalid-FD atomicity, quiescence, and caller-thread private FD tables. Quiescence deliberately rejects restart; it is not a successful restart case.

The twelve expected observations **include the known NOFILE=0 EMFILE red**. The updated core is compiled into the owned test APK; this is not an installed native-bridge engine update or an ARM64 commercial-app qualification. Guest raw-syscall statfs representation must retain the raw contract separately; these host-libc results do not qualify that adapter. Trusted-factory positives, trusted O_PATH reopening, pathname alias admission, arbitrary native credential/root/mount transitions, and full runtime lifecycle remain open.

Primary results: [R18](native-runtime-r18/summary.json), [R19](native-runtime-r19/summary.json), [R20](native-runtime-r20/summary.json). Exact source, Bionic reference, host reproduction, build receipts and actual ELF audits are in [native-repair](native-repair/README.md). Primary runtime exports preserve the original phase receipts and owned instrumentation output.

## Signal canary: a03 diagnosed; r4 admission blocked

The a03 private Android cell booted and passed its first strict framework capture. Its first instrumentation command exited 134 before a native signal verdict. Its exact nonce matched a tombstone reporting missing BOOTCLASSPATH and DEX2OATBOOTCLASSPATH. The subsequent missing claim was secondary. The original failed run and exact cleanup are retained.

R4 adds held namespace/root entry, private-zygote classpath admission, and bounded failure diagnostics. Its actual host controls passed: 35 owned-host controls, 13 original admission/loader controls, and an AST comparison of 18 retained functions. Four additional external-qualification controls read the real r1 verifier, host-suite and helper receipts; they used retired a03 inputs for static qualification only and **did not call validate_inputs or prepare**.

Independent review blocked a new Android run on three concrete paths:

- A resource-evidence write can throw before every cell/unit stop; recording FAIL alone does not retire those services.
- MainPID and root cgroup.procs do not prove that nested cgroups and descendants have retired.
- Pinning zygote identity while hashing jars only through init's root does not establish the correspondence between their different mount views.

R4 remains frozen and unrun. R5 work is separate and is not qualified by this checkpoint. No a04 input, nonce, image or service was created for r4. See the [root admission review](signal-runtime-r4/reviews/root-r4-admission-blocked.json), [independent baseline review](signal-runtime-r4/reviews/native-peer-r4-baseline-review.json), and [frozen source](signal-runtime-r4/source/REVISION.md).

## LMKD: real critical pressure and a narrower stale-event result

Revision09's positive run passed. Its stale run failed because pressure totals increased during strict quiet aging; that original failure is retained unchanged.

Revision10 releases only the owned allocator before aging queued critical events. Its actual matching build passed 20 Rust tests, seven ordinary IPC controls, strict native actor compilation and 28 Python qualifier controls. The coordinator controls passed eight checks.

The same revision then completed two unique owned invocations:

- The positive run observed fresh medium and critical events, a native critical cached-target kill, preserved foreground/protected targets, complete outer/inner resource checks, exact cleanup and Main fences.
- The relief-stale run observed an actual critical queue, allocator release, the original strict quiet aging, zero kills on resume, and normal exit of all five targets. Cleanup and Main fences passed.

Only `stale_relief_critical_qualified` is true for the latter, with scope `relieved-domain-aged-critical-queue`. The original stale gates, independent native stale-drop observation and above-high stale zero-kill qualification remain false. Below-high pressure after relief can independently suppress an effect; zero kills alone does not prove the native expiry branch executed.

Thresholds and bounds were not weakened: some 70000 / full 700000 microseconds in a 1000000-microsecond window, eight-second allocation ramp, 512 MiB outer maximum, 384 MiB measured-domain high, swap zero, one CPU, TasksMax 64 and 60-second runtime bound. These are owned-fixture limits, not guessed production defaults.

See the [complete pressure checkpoint](../pressure10-checkpoint05/README.md), including all four original results, source/matching pins and read-only archive audits. The route remains PIDFD-only in a minimal root. Installed supervisor integration, production cgroup.kill, PID reuse and daemon-loss recovery remain unqualified.

## Runtime lifecycle and paired update work

The native R8 source connects a private versioned protocol to ART/engine initialization, specialization, fork, exec failure and retirement. Its first host attempt failed on a real inherited capability bit. The test setup then cleared capabilities only in its own child and verified the result; production gates were not weakened. Eleven host controls passed. The Android translation-unit record retains both failures and three passing exec translation units; no full ART or engine link is claimed.

The updater pair gate has four changed source files and nine passing tests, including owned ext4 APEX and EROFS fixtures. It checks component versions/hashes and preserves whole-APEX metadata. It has not built a candidate ART APEX, verified its signature or qualified an installed paired update. Its patch must be integrated into the current project; the older complete updater files must not overwrite unrelated newer work.

The original full R7 freeze was not recovered. This checkpoint identifies available exact source subsets and the four missing production adapter deltas. A new complete candidate must have a new manifest. Factory server/build/service closure, raw guest ABI, full paired builds and actual app acceptance remain separate requirements. See [overlay gaps](native-repair/overlay-gaps.json).

## Held namespace entry

The shared Rust helper consumes held namespace/root descriptors and reasserts CLOEXEC before the final exec. It does not perform numeric target lookup at action entry. Its actual qualification includes 14 host controls, six-namespace host entry and a read-only Main entry. It was then used in the three exact metadata APK cycles.

Its qualification covers namespace entry and the direct launcher relationship. PDEATHSIG can be cleared by credential changes and does not establish whole-process-tree cleanup. Exact package, unit and cgroup retirement are still required. Source, controls and the scoped qualification are in [namespace-entry-r4](namespace-entry-r4/qualification.json).

## Integrity and reproduction

All inherited checkpoint04 payloads remain byte-identical. The previous delivery manifest is retained in [previous-delivery-manifest.json](previous-delivery-manifest.json); its original Git commit is `4af46935a44ecb5e19ddc65fa39558ddf1f0b733`.

New transport archives and individual UTF-8 payloads were independently SHA-256 checked after complete version-bound reads. The active delivery manifest records the exact repository bytes, including original failures and separate later evidence. No APK, ELF, image, signing key, commercial application log or broad runtime journal is added.

Executed once-only coordinator scripts retain their original roots, nonces and fixed inputs for audit. They are not recipes for replaying a retired invocation or silently substituting a new baseline. Main activation and whole-app production acceptance remain closed.
