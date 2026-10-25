# Native seccomp: development and technical contract

This first stage implements a bounded syscall filter in the actual Asterinas
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

Filter installation requires the calling thread's `no_new_privs` or effective
`CAP_SYS_ADMIN`. The complete `sock_fprog` is copied from user memory before
validation. No user pointer survives publication. A failed installation leaves
the prior policy unchanged. Adding an ALLOW filter cannot relax an earlier
restriction. Equal-priority action data comes from the most recently installed
filter; KILL_PROCESS precedes KILL_THREAD, then ERRNO, then ALLOW.

The syscall entry hook runs before dispatch, including unrecognized syscall
numbers. ERRNO returns directly without entering the handler. ERRNO data is
clamped to 4095; data zero returns zero without executing the syscall. KILL
actions use the kernel's thread/group exit path with SIGSYS and cannot be
turned into permission by ignoring SIGSYS. Strict mode permits native read,
write, rt_sigreturn and exit only. In particular exit_group is not allowed.

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

Only ALLOW, ERRNO, KILL_THREAD and KILL_PROCESS are advertised. Static TRAP,
TRACE, USER_NOTIF and LOG results are rejected with EOPNOTSUPP. An unknown or
unsupported dynamic result terminates the process. All nonzero install flags,
including TSYNC and NEW_LISTENER, are rejected with EINVAL. GET_NOTIF_SIZES and
other unsupported operations are rejected. Installation on other architectures
returns ENOSYS. These refusals must remain explicit until the corresponding
semantics and race tests exist.

TSYNC needs atomic group publication coordinated with clone and exec; applying
a filter only to the caller must never return TSYNC success. SIGSYS trap needs
the correct siginfo syscall/architecture/address fields and signal return
semantics. Neither can be replaced by a symbol or a successful no-op. AOSP
seccomp policy compatibility, ptrace interactions and Android's required action
set must be measured on its pinned workloads before changing the Android gate.

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
cases. The guest has no host disk or network. Raw serial, nonce, ELF/initramfs
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
