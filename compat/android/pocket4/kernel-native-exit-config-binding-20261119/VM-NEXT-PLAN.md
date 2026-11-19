# Unexecuted VM and native-exit plan

This is a review plan. It authorizes no launch or hold removal. The complete
binding now exists, while native-exit ABI/provider and Android production
qualification remain false.

## Inputs and ownership for the legacy 160+100 regression

Use the original ordinary `qq` host `ai395` and the already built complete
`6.18.64-p4ctx6182` release. The fixed full observation is 7,978,909 bytes,
SHA-256 `047a3dcb0506a5b7c5936a9edc65a5e87a1b3b53eb199a934c8baa5ccacf23cc`.
The selected kernel is
`/home/qq/work/p4-kernel-native-exit-full-11ea-20261119-r3/out-full-r3/arch/x86/boot/bzImage`,
16,855,552 bytes, SHA-256
`a4dbd48bce8d6301a265f75f5db4e37e2a471aaa4dbf3eeee90fb23feaca4607`.
The corresponding staged module directory is the same full-r3 root's
`modules-full-r3/lib/modules/6.18.64-p4ctx6182`; select its actual needed modules
under their original full-build pins and verify each loaded signature through
the existing module qualification path.

The successful HELD binding is
`/home/qq/work/p4-native-exit-vm260-binding-evidence-5cd1-20261119-r1/HELD-BINDING.json`,
25,566 bytes, SHA-256
`b3c406e7cab11fc9eba2a213880e0a615eaaaab36b59f72c8095bb62e7bff9ea`.
This is a completed historical binding, not a future launch lease.

Preserve the original active160/inactive100 Counter catalogs and the pinned
original fixture inputs under
`/home/qq/work/p4-kernel-6.18.64-cp3a-20261118-r1/inputs/vm-fresh-r7`.
`original/KNOWN-INPUTS.json` provides their complete original byte/F9/SHA pins.
The advertised destination
`/home/qq/work/p4-kernel-native-exit-vm260-11ea-20261119-r3` was absent at this
audit. Its three held Python sources are only named/hash-referenced by the
known-input record; they must be recovered from their exact source handoff,
reviewed and deployed before any runnable command can be supplied.

A reviewed successor deployment should have separate ordinary prepare and run
units. Each phase must consume the new binding through the updated BoundPhase,
hold the original VM serial during actual work, and bookend all real kernel,
module, generated-header and Kconfig semantic inputs. Preserve the original
build serial identity and reject active full/TU/VM/binding/R12 supervisor,
build or recovery workers. Never remove or replace an existing serial inode,
claim, failed output or unit to obtain admission.

The original small-job contract is admission at 15 GiB MemAvailable and
32 GiB available disk, with a 12 GiB memory continuation floor. Keep each
sequential unit at MemoryMax 3 GiB, MemoryHigh 2.5 GiB, zero swap, CPU 22-23,
200% quota, TasksMax 128 and RuntimeMaxSec 900. Recheck real resources and
owner/unit/serial state immediately before admission. This work does not need
the separate R12 full-build 42/144 GiB admission. Whether both VM phases meet
this contract must be demonstrated by the actual preserved launcher before
launch, not inferred from the successful metadata binder.

Prepare an independent source capsule with exact input/output inventory, kernel
release binding, original QEMU/PIDFD ownership, finite deadlines and create-only
outputs. Review that concrete capsule first. The eventual two actual phases
must prove real guest boot/release, exact 160 and 100 case multisets, raw guest
output completeness, ordinary child exit/reap, cgroup/unit retirement and serial
release. This plan intentionally supplies no fabricated command for missing
launcher bytes.

## New native-exit executable fixture

The retained `history/VM-CATALOG-r3-DRAFT.json` contains 32 unimplemented rows.
Before writing the C fixture, bind the exact r3 eight-file source handoff and
its 24-byte ioctl ABI (`0x40182150`) to the complete built kernel. Freeze the
actual native guard errors, notification lifecycle, same-file rules and r3
threaded behavior. The older r2 single-thread refusal cannot satisfy the r3
threaded init cases.

Create a new standalone `native_exit_probe.c` using the actual built UAPI. Its
record protocol should identify original task/thread PIDFD, notification ID,
listener/filter, tracer TID/credential generation, request/namespace file,
epoch and guest boot nonce. Record original namespace IDs, owners and mountinfo
before and after the actual native call. Only the observed native syscall EXIT
and unchanged result after stopped detach can count as a native result.
Finish each epoch with TracerPid zero, no stale stop and original PIDFD wait/reap.
Use no SETREGSET/POKE/SET_SYSCALL_INFO/SYSEMU or unapproved resume operation and
grant no initial-user-namespace CAP_SYS_PTRACE. The fixture proves its own
operation trace; a real provider still requires its separate operation audit.

Implement and review in these finite groups, retaining every original case ID:

| Group | IDs | Required actual observations |
|---|---|---|
| Native positives/denials | N01-N07 | Three threaded init epochs, nonleader unshare, shared-files setns, actual shared-fs/native permission denials, absence of initial SYS_PTRACE, held-file fdget stability. |
| Notification/identity/ABI | I01-I10 | Real pre/post-RECV states, genuine RECV copy failure/window, original PIDFD identity, fixed ABI malformed calls, real unsupported architecture/syscall shapes, exact namespace file identity, FD replacement/close, replay, and actual ADDFD state. |
| Ptrace authority/regression | P01-P05 | Actual DAC/dumpability/Yama/enforcing-LSM denials, exact original tracer TID, credential-generation refusal, fabricated SEND refusal, unchanged ordinary ptrace behavior. |
| Lifetime and race closure | R01-R08 | Tracee/tracer/listener loss, actual attach/credential windows, mandatory guard cancellation, non-setns cleanup, finite deadline/reaping, separately configured diagnostic-kernel evidence. |
| Product integration | X01-X02 | Real provider custody/allowlist/result passthrough and real CP3A/APEX/init transitions plus all required app gates. |

Run deterministic positives and negative identity/ABI cases first under the
new production-config kernel. Race cases require observable scheduling
coordination or separately reviewed instrumentation that proves the named
kernel window was reached. A generic EFAULT, timeout or loop count does not
qualify an unobserved race. Lockdep/KASAN/KCSAN need their own actual diagnostic
build/run evidence and cannot replace the production-config run.

Keep per-case NOT_IMPLEMENTED / NOT_RUN / FAILED / PASSED results and never
turn catalog labels into test counts. P01 requires actual enforcing policies;
the older permissive diagnostic types are insufficient. X01 needs the real
sealed provider, and X02 needs the coherent Android composition and installed
app/business acceptance, so these cannot be closed by this isolated VM fixture.

## Acceptance and cleanup boundaries

Only independently verified current source/custody and exact successful
runtime results can advance their respective states. Source replay and legacy
VM results do not grant new ABI or production credit. Preserve original failed
and successful proof bytes. Any later temporary-output cleanup must be scoped
to the exact new owner, after its real children, unit/cgroup and serials have
retired, and must retain the selected kernel/module/source inputs needed by the
next approved phase.
