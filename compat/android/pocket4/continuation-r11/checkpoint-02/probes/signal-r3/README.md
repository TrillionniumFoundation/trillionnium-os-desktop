# Revision 3: independent mask-edit probe

This revision uses the separate package `org.droidloom.signalprobe.r3` and version code 3. It preserves the original `org.droidloom.signalprobe` r2 APK and its failing R16 evidence. Target SDK remains 33, `debuggable=false`, `testOnly=true`; there is still no Activity, network access, or dangerous permission. The native library name remains `libowned_signal_probe.so`.

New case: `smc-mask-edit` (native case ID 4). Run exactly one case with a fresh nonce:

```sh
am instrument -w -r -e case smc-mask-edit -e nonce p4-mask-edit-UNIQUE \
  org.droidloom.signalprobe.r3/org.droidloom.signalprobe.r3.SignalProbeInstrumentation
```

The new case first blocks SIGUSR1 and unblocks SIGUSR2 and SIGILL while preserving all other current kernel mask bits. The SIGILL handler verifies the complete 64-bit interrupted mask, including any preexisting runtime bits. It edits `ucontext.uc_sigmask` to unblock SIGUSR1 and block SIGUSR2, deliberately also requesting SIGKILL and SIGSTOP. It verifies that editing the saved context does not change the live handler mask. Immediately after the owned SMC assembly returns, before restoring either the original action or mask, it reads the actual kernel mask. PASS requires the edited mask to be in force and both unblockable signals to remain absent. Cleanup then restores the original action and mask and separately verifies that restoration.

The added checks are `C_CONTEXT_MASK_FULL` (bit 24), `C_MASK_EDIT_APPLIED` (bit 25), and `C_MASK_EDIT_STAGED` (bit 26). The JSON `mask_edit` object contains the entered, guest-context, requested, expected-return, live-after-edit, and immediate-post-handler masks. `sampled_before_harness_restore` is true only if that pre-cleanup query actually succeeded. All original instruction, siginfo, exact-PC, register, SP, NZCV, and cleanup checks remain required.

The original `svc`, `smc-handler`, and `smc-default` cases remain available under the r3 package. No software-pending-queue protocol is tested here, and an owned-probe result does not establish a commercial app crash's root cause. Build this revision into a separate artifact path; do not replace the frozen r2 APK or source. Java uses an explicit Runnable for the watchdog because the pinned SDK31 boot class path lacks javac21's LambdaMetafactory entry.

## Original probe contract (package names updated for r3)

# Owned ARM64 signal probe

This is a standalone diagnostic APK source tree. It has no Activity, service,
receiver, network access, or requested permission. It does not load, alter,
inspect, or impersonate a commercial App. Its package is
`org.droidloom.signalprobe.r3`; its manifest targets SDK 33 and requires API 26.
It is `debuggable=false` to preserve a normal non-debuggable App execution
context and `testOnly=true` to identify this owned diagnostic package.

## Source and build contract

| Input | Purpose |
| --- | --- |
| `native/signal_probe.c` | JNI entry, preallocated signal record, verification, owned-child watchdog, JSON |
| `native/probe_arm64.S` | Actual AArch64 SVC and SMC instructions and first-instruction recovery records |
| `native/probe_abi.h` | Only this probe's output-record offsets and sentinels; no system ABI replacement |
| `java/org/droidloom/signalprobe/SignalProbeInstrumentation.java` | Headless runner, durable nonce claim and result, outer watchdog |
| `AndroidManifest.xml` | Instrumentation and SDK declarations; no permissions or UI components |

Build the native source **as C11**, not C++, together with the `.S` source.
Use the standard NDK `jni.h`, `signal.h`, `ucontext.h`, system headers and
libraries for `aarch64-linux-android26`. The source deliberately refuses a host
ISA build. Recommended diagnostic flags are:

```
-std=c11 -O1 -g -fPIC -fno-omit-frame-pointer
-march=armv8-a -mno-outline-atomics -mbranch-protection=none
-Wall -Wextra -Werror
```

Link `libowned_signal_probe.so` as a shared library with a Build ID, RELRO,
immediate binding and a non-executable stack. There is no C++ or third-party
runtime dependency. Keep unstripped symbols as evidence. `probe_arm64.S`
includes the NDK's architecture-specific `asm/unistd.h`; its syscall number
must come from the AArch64 sysroot.

Package **only** `lib/arm64-v8a/libowned_signal_probe.so`. Do not add an x86_64
fallback. This makes the actual Android native bridge load part of the test.
The manifest requires native extraction. Java compilation uses framework APIs
available by API 26, so the pinned SDK 31 `android.jar` can compile it; the
manifest target remains 33. Use Java 8 bytecode (for example, `javac -source 8
-target 8`) and D8 with `--min-api 26`.

The root task owns the pinned Android toolchain, signing, installation and
device execution. A local syntax/build check is not evidence that an ARM64
payload has run through ART or the installed bridge.

## One invocation, one case, one nonce

The exact instrumentation component is:

```
org.droidloom.signalprobe.r3/org.droidloom.signalprobe.r3.SignalProbeInstrumentation
```

The CLI shape is:

```
am instrument -w -r \
  -e case smc-handler \
  -e nonce UNIQUE_RUN_NONCE \
  org.droidloom.signalprobe.r3/org.droidloom.signalprobe.r3.SignalProbeInstrumentation
```

Accepted cases are `svc`, `smc-handler`, and `smc-default`. A nonce contains
8–96 ASCII letters, digits, underscores or hyphens; its first character must be
a letter or digit. The operator chooses a fresh nonce explicitly for each
intended execution. There is no automatic retry.

Before `System.loadLibrary`, the runner atomically creates:

```
files/signal-probe/UNIQUE_RUN_NONCE.claim
```

`File.createNewFile()` must succeed. The claim is retained even on failure.
Any framework or operator duplicate using the same nonce returns
`DUPLICATE_NONCE` without loading or invoking the native payload and without
overwriting the first result. A successful run first persists `STARTED`, then
atomically replaces its JSON result with the final phase:

```
files/signal-probe/UNIQUE_RUN_NONCE.json
```

Instrumentation emits `evidence_json` and the absolute `result_path`. The
authorized device operator can retain that output and retrieve the exact
owned private result path through its existing device access; no `run-as`
access is required or assumed.
Do not interpret the CLI process's exit code by itself: require JSON
`phase == "PASS"`, native `status == "PASS"`, the expected case and nonce,
and the matching source/binary Build ID receipt.

## What each case establishes

### `svc`

The assembly loads `x0=UINT64_MAX` (which cannot be a successful PID) and
`x8=__NR_getpid`, then executes the literal instruction
`0xd4000001`. It must return the native call's actual process PID without any
SIGILL delivery. The instruction before and after execution, resume label,
first result stores, cookie and restored signal policy are checked.

The recording handler is installed even for this negative signal control.
If this exact owned SVC incorrectly causes SIGILL, it records the unexpected
delivery and resumes only this owned instruction; the case fails. It does not
perform a substituted syscall.

### `smc-handler`

The assembly executes the literal `0xd4000003`. A real registered
`SA_SIGINFO` guest handler records the actual signal, `si_code`, `si_addr`,
guest PC, SP, PSTATE and all 31 general registers from the standard NDK
`ucontext_t`. It checks the pre-fault sentinels:

| Field | Expected value |
| --- | --- |
| x0, x1 | `0x1111`, `0x2222` |
| x8 | AArch64 `__NR_getpid` |
| x9, x10 | `0x9999`, `0xaaaa` |
| NZCV | `0x80000000` |
| Signal and code | SIGILL, ILL_ILLOPC |
| `si_addr` and guest PC | Exact SMC fault label |

The handler captures its live kernel mask through `rt_sigprocmask` and the
saved context mask. It must run with SIGILL and its explicit `sa_mask`
SIGUSR1 blocked. It then changes **only the owned probe's context**: x0/x1/x8/
x9/x10 become `0x5a01/0x5a02/0x5a08/0x5a09/0x5a0a`, NZCV becomes
`0x60000000`, and PC becomes the exact resume label. SP remains unchanged.

The first instruction at that resume label stores x0/x1. The rest of the
assembly records the other registers, SP, NZCV, resume address and `0x4f4b`
cookie. Thus a bridge that silently treats SMC as SVC, loses context changes,
or advances an extra instruction cannot satisfy the checks.

The handler only writes preallocated storage. It performs no formatting,
allocation, JNI operation or logging. An unrelated PC, null context or second
delivery terminates the owned probe with exit 124, leaving an incomplete or
watchdog result rather than a false PASS. JSON formatting/JNI allocation occur
after the old SIGILL action and original thread mask have been restored.
Restoring an action is not judged by a zero return code alone: the probe
queries it again and compares the original handler, flags and signal mask.

### `smc-default`

Only this case forks, and it forks exactly one child owned by this probe.
It requires an initially default SIGCHLD disposition without SA_NOCLDWAIT;
it fails setup rather than modifying a process-wide reaper policy.

The child installs `PR_SET_PDEATHSIG=SIGKILL`, rechecks its actual parent,
sets its own core limit to zero, selects SIG_DFL for SIGILL, unblocks SIGILL,
marks its shared record ready, then executes the same SMC assembly. No
recording SIGILL handler is installed in this child. The expected observation
is `WIFSIGNALED && WTERMSIG == SIGILL`, an entirely untouched post-SMC result
record (including the very first stores), and an actual reap
of the exact PID returned by this probe's `fork()`.

The parent polls only that child with `waitpid(..., WNOHANG)`. The normal
deadline is 2 seconds. On expiry it signals only its still-unreaped child with
SIGKILL and allows at most 1 further second to observe cleanup. ECHILD or other
wait errors are failures; the code never uses a name lookup or signals a PID
after losing wait ownership. Timeout, SIGKILL, incomplete cleanup and a
return from the SMC path can never pass. All of these outcomes are returned
explicitly in the child record.

Because SIG_DFL remains in place, this case reports
`precise_siginfo_observed=false`. `waitpid` does not provide the original fault
address or ILL_ILLOPC code; those fields remain unobserved. It does not invent
them or install a handler that re-raises a replacement signal. The precise
signal/context proof is provided by `smc-handler`.

## Evidence and guard boundaries

Addresses and registers are fixed-width hexadecimal strings, avoiding loss
through JSON number conversion. The result includes actual process/thread
IDs, raw instruction words, check masks, signal/context records, post-return
registers, restored action/mask results and child cleanup state. `checks` must
contain every bit in `required_checks`; any setup or cleanup reason vetoes
PASS.

The Java envelope also records this process's actual `Seccomp` and
`NoNewPrivs` fields from `/proc/self/status`, and its SELinux context from
`/proc/self/attr/current`. Each read is bounded. Missing fields or read errors
are recorded under `self_security` without preventing the native case.

The Java watchdog uses a 10-second absolute elapsed-time deadline, persists a
timeout result, finishes instrumentation, then kills only this probe process.
The child has its own shorter watchdog and parent-death protection. The
operator should retain an outer CLI bound and preserve incomplete evidence
if the Android framework itself cannot finish. A cleanup failure is a failed
trial, never a successful result.

Initial delivery contains only the three cases above. It does not yet test
self-modifying code, concurrent guest threads, SA_NODEFER/SA_RESETHAND,
alternate stacks or the commercial App's actual installed action. Passing
these three cases therefore establishes the owned basic SVC/SMC and context
restoration behavior, not the cause or resolution of the East China Airlines
failure.

## Check mask

Bits 0–23, respectively:

```
no_signal, one_signal, signo, code, address, pc,
registers_before, nzcv_before, context_mask, handler_mask,
registers_restored, sp_restored, nzcv_restored, resume_pc,
cookie, return_value, mask_restored, action_restored, opcode_stable,
child_ready, child_reaped, child_sigill, child_no_return, within_deadline
```

Reason codes 0–19, respectively:

```
none, bad_case, busy, clock, mask_query, action_query, action_install,
mask_set, action_restore, mask_restore, checks, child_policy, mmap, fork,
wait, child_setup, child_returned, child_signal, child_timeout, child_cleanup
```

The `child.setup_reason` values 1–6 are parent-death setup, parent identity,
core limit, SIGILL default action, mask query, and mask update. Child phases
0–4 are initial, started, ready, returned, and setup error.
