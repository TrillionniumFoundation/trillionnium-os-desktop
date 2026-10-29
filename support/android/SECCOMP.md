# Native seccomp: development and technical contract

This stage implements a bounded syscall filter in the actual Asterinas
core. It is an x86-64 kernel feature, not an Android compatibility certificate.
Binder, Android MAC, framework boot, ARM64 filtering and phone hardware remain
separate work. The original A08 Linux-host probe is a reference comparison;
`tests/kernel/seccomp/` runs real syscalls in an ordinary Asterinas guest.

## Interface and ownership

`seccomp` (native syscall 317) supports SET_MODE_STRICT, SET_MODE_FILTER and
GET_ACTION_AVAIL. `prctl(PR_SET_SECCOMP)` and `PR_GET_SECCOMP` use the same
policy owner. Every thread owns a mutex-protected immutable policy snapshot.
Both process and thread clone paths inherit that snapshot; exec retains it.
There is no interface to disable a filter or replace a strict policy.

TSYNC is flag 1 of SET_MODE_FILTER. It admits disabled peers or peers whose
actual immutable filter chain is an ancestor of the caller's chain. Identical
looking independently installed programs are not ancestry. An incompatible
peer returns its positive TID, before any policy or no_new_privs mutation.
Success installs the same new chain on every live original TaskSet member,
and monotonically propagates the caller's no_new_privs flag if set.

All installations share `Process::seccomp_update` with clone inheritance and
exec credential preparation. Lock order is update mutex, TaskSet, thread
policy. Clone holds the update mutex from the credential/policy cut through
TaskSet insertion; a later TSYNC cannot miss the new sibling. Fork takes a
coherent credential/filter cut for its independent process. Exec takes the
mutex before preparing credentials and keeps it until in_execve and sibling
SIGKILL are published, then releases it **before** waiting for siblings.
Publication interrupted by admitted exec/exit returns EINTR without mutation.
Thus an installer blocked on this mutex can return and process SIGKILL; exec
does not wait while holding a mutex needed by that sibling. A successful NNP
sync cannot be followed by a stale pre-NNP privileged exec publication.

Filter installation requires the calling thread's `no_new_privs` or effective
`CAP_SYS_ADMIN`. The complete `sock_fprog` is copied from user memory before
validation. No user pointer survives publication. A failed installation leaves
the prior policy unchanged. Adding an ALLOW filter cannot relax an earlier
restriction. Equal-priority action data comes from the most recently installed
filter; KILL_PROCESS precedes KILL_THREAD, then TRAP, then ERRNO, then ALLOW.

The syscall entry hook runs before dispatch, including unrecognized syscall
numbers. ERRNO returns directly without entering the handler. ERRNO data is
clamped to 4095; data zero returns zero without executing the syscall. KILL
actions use the kernel's thread/group exit path with SIGSYS and cannot be
turned into permission by ignoring SIGSYS. Strict mode permits native read,
write, rt_sigreturn and exit only. In particular exit_group is not allowed.

TRAP does not dispatch the syscall. It records a kernel-created synchronous
thread fault separately from coalescing user-signal queues, then delivers it
after the ptrace syscall-exit stop and before returning to userspace. SIGKILL
keeps priority. The native 128-byte siginfo contains SYS_SECCOMP, filter data
in si_errno, the original syscall number, audit architecture and saved return
instruction pointer. The handler can change the return register via ucontext;
signal return continues after the trapped instruction without restarting the
call. If SIGSYS is blocked or ignored, its mask/disposition is forced to the
default action. A default forced fault also applies to init. User-supplied
siginfo cannot opt into this kernel-only behavior. Ptrace signal replacement
still follows the existing signal path; a full ptrace compatibility suite is
not implied by this stage.

The process filter module contains the pure verifier, interpreter and policy;
the syscall module owns user-memory copies, credential admission and effects.
Locks are released before interpretation, user I/O or termination. There is
no second authorization service, external execution helper or JIT.

## Verifier and execution bounds

The classic BPF instruction is an independent 8-byte UAPI layout. Input is the
64-byte native `seccomp_data` register snapshot: syscall number, audit
architecture, instruction pointer and six 64-bit arguments. Argument pointers
are never dereferenced by a filter. Native audit architecture is 0xc000003e.

A program has 1..4096 instructions, forward jumps entirely within the program
and a final RET. The verifier checks instruction classes, aligned in-range
absolute word loads, 16 scratch words, definite initialization on every
incoming path, nonzero constant division/modulo and constant shifts below 32.
Supported arithmetic uses unsigned 32-bit wrapping BPF semantics. Register
division or modulo by zero terminates the thread. Register shifts are rejected
pending compatibility qualification. All instructions are structurally checked,
including unreachable instructions.

The whole inherited chain costs at most 32768 instructions, with four extra
units per preceding filter. Policies use a flat vector of shared immutable
programs so destroying a long chain cannot recursively exhaust the kernel
stack. Interpreter execution is bounded by verified forward-only programs.
This does not provide a complete kernel-heap resource budget.

## Explicitly incomplete interfaces

Only ALLOW, ERRNO, TRAP, KILL_THREAD and KILL_PROCESS are advertised. Static
TRACE, USER_NOTIF and LOG results are rejected with EOPNOTSUPP. An unknown or
unsupported dynamic result terminates the process. All nonzero install flags,
except TSYNC are rejected with EINVAL, including NEW_LISTENER, LOG and
TSYNC_ESRCH. GET_NOTIF_SIZES and
other unsupported operations are rejected. Installation on other architectures
returns ENOSYS. These refusals must remain explicit until the corresponding
semantics and race tests exist.

AOSP
seccomp policy compatibility, ptrace interactions and Android's required action
set must be measured on its pinned workloads before changing the Android gate.
The pinned [Android 15 Bionic policy builder](https://android.googlesource.com/platform/bionic/+/refs/tags/android-15.0.0_r36/libc/seccomp/seccomp_policy.cpp)
uses TRAP for rejected calls; implementing it here does not establish that
the whole generated policy or mixed 32/64-bit ABI works. Native i386/x32 syscall
compatibility remains unqualified.

## Reproduction and evidence

Use the repository's pinned nightly and source-built OSDK for this checkout;
an OSDK built with OSDK_LOCAL_DEV can embed its original source directory and
must not silently select another worktree. Follow `support/build/README.md`
for the VDSO and host prerequisites. Keep each evidence directory new.

```sh
python3 -I -B support/build/ktest/run.py --crate aster-core --output /scratch/seccomp-native
python3 -I -B tests/kernel/seccomp/run.py --smp 2 --output /scratch/seccomp-smp2
```

The first command runs the entire core native suite, including malformed
program, control-flow/scratch, immutable inheritance, chain exhaustion, action
precedence, strict transition, arithmetic and UAPI layout tests. The second
builds and boots an ordinary kernel and runs a static C probe in its guest.
It requires real filtering, syscall/prctl installation, fork/thread/exec
inheritance, unchanged installed bytes after user mutation, stacking, privilege
admission, malformed/faulting inputs, no file creation on a denied openat,
SIGSYS termination including a live sibling, and strict-mode positive/negative
cases. It also checks actual TRAP siginfo against libc's UAPI, handler-controlled
return, action precedence, absence of file effects and blocked/ignored traps.
The guest has no host disk or network. Raw serial, nonce, ELF/initramfs
hashes and before/after source snapshots are retained; any failed assertion,
timeout or source mutation fails the run.

For comparison only, compile the same probe on a disposable Linux reference
host and run it with `--linux-reference`. It deliberately omits strict-mode
and unsupported-action assertions that a pre-existing container policy can
alter. The privilege-drop case requires root; an unprivileged reference run
labels it NOT_RUN. A reference pass cannot replace the Asterinas guest run.

The 2026-10-25 development native run passed 302/302 with no skips; its 3517
relevant source/build/test inputs were unchanged across the build and guest.
The ordinary double-CPU guest then passed all 60 assertions, including a real
pthread clone and group termination with a live sibling, and powered off with
QEMU exit 33. Its ELF SHA256 is
`187b96200a89a8606774c0eeac3a1e92b1c3c4c0a3ddd44f9885f7c0eb677707`.
The guest's source and retained artifacts were unchanged throughout the run.
Host tooling separately passed all 184 tests and Java/JNI loading; Binder open
remained BLOCKED/77. Neither result qualifies an Android guest.
The first compile failure (missing trait imports) remains in the evidence.
The selected-commit Android source report remains independently bound to its
commit and always leaves runtime verification false. Android host tooling,
JNI tests and Binder-device absence must also retain their own actual results.

The subsequent TRAP stage passed 304/304 native tests, including a full
independent siginfo byte-layout check. Its 3518 relevant inputs matched from
the recorded compilation snapshot through the completed guest. The actual
double-CPU ordinary guest passed every filtering and trap assertion on ELF
`95055dc36f386cae9e0209fe67bc635e9dc89010ce4813130d1e6816ef8cade2`,
with unchanged source/artifacts and QEMU exit 33. Initial non-TRAP evidence
above remains historical.

The TSYNC stage passed 305/305 native tests and a first four-CPU ordinary guest
with 119 assertions. The added privilege-race workload then passed 201/201
assertions on the same ELF
`99436891ca66961c068950a05876924b1670bae93b970bc7ffc823c54ff14fdf`.
It exercises disabled peers, inherited ancestry, atomic refusal of a divergent
peer, NNP propagation, 16 concurrently created threads and exec against a live
filter installer. Sixteen actual setuid-exec/TSYNC races observed both valid
outcomes: exec before synchronization retained its legitimate setuid effect
with NNP=0; successful synchronization preserved NNP=1 and the unprivileged
effective UID. No NNP=1 privileged result was accepted. The setuid fixture is
created only inside the disposable guest; `--linux-reference` never creates
one on the host. The source and artifacts remained unchanged throughout each
run. A separate static lock-order review found no blocking issue; it is not
additional runtime evidence. These bounded races do not prove every possible
scheduling interleaving or qualify AOSP/CTS/ARM64.
