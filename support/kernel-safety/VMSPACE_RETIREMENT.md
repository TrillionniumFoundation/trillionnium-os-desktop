# x86 active address-space retirement

An idle task or a kernel thread without an associated VMAR must stop serving the
previous user address space. A CPU-local active `VmSpace` owns a strong `Arc`;
the processor also owns a separate physical root-page-table `Frame` reference.
Leaving both in place after a process exits can retain real charged table pages.

The frozen CPUNODE composition first exposed this in the unchanged four-CPU page
memory guest: 175 assertions passed and two failed. A workload retained 16 KiB
of page-table charge after its children exited, in addition to a retained 4 KiB
file-cache page. The guest completed without a timeout. Its failure is retained
under its original commit and must not be rewritten as a successful run.

The source contains a concrete retention mechanism. The VMAR ceiling excludes
the last reserved user page. Clearing `0..VMAR_CAP_ADDR` cannot detach the whole
highest page-table slot, and the cursor does not prune every partial empty tail.
A workload's nested fork can own a root and three high-stack table frames. An
active CPU reference can retain those four real frames after mappings are gone.
The original failed guest alone does not identify individual frame addresses.

## Transition and ownership

`VmSpace::activate_retiring_old` and `deactivate_current` run their transition
with local IRQs disabled, which also pins the CPU. For a new user space, its CPU
set is updated with `Acquire` before installing its hardware root. For a
kernel-only task, the already initialized kernel page table is installed through
the normal managed activation path. Neither path calls the boot-only first
activation function, waits for an IPI, or performs a synchronous remote flush.

The old `VmSpace` remains strongly owned throughout the hardware transition.
After the new CR3 is installed, the CPU-local slot is published and the old CPU
membership is removed with `Release`. The old root's processor reference is
released exactly once through `Frame<dyn AnyFrameMeta>` and its actual metadata
vtable. Keeping the old `Arc` alive prevents this processor-reference release
from destroying the old address space inside the critical section.

On x86, the existing primitive writes CR3 with PCID zero and the no-flush operand
bit clear. Safe user page properties have `USER` and cannot acquire the private
`GLOBAL` flag. Thus the switch invalidates old user translations and paging
structure caches locally while retaining valid shared kernel global mappings.
This follows Intel SDM Volume 3A, revision 093, section 5.10.4.1, pages 5-48–5-49:
[official Intel manual](https://cdrdv2-public.intel.com/929359/253668-093-sdm-vol-3a.pdf).

## Destruction after IRQ restoration

The opaque `RetiredVmSpace` owns only the old strong reference. It contains no
pending CPU-local cleanup and does not recreate a hardware reference. The
injected post-schedule handler returns it for both user-to-user and
user-to-kernel transitions. An associated kernel thread keeps its original VMAR
activation behavior. A task without an associated VMAR retires the old user
space.

OSTD holds the returned token on the new task's stack, preserves the existing
`complete_switch` ordering, restores IRQs, then drops the previous task and the
retirement token. Nested scheduling uses another task's stack and cannot
overwrite a per-CPU pending value. Frame-charge metadata has no blanket promise
that its destructor is nonblocking, so dropping the last `Arc` in the IRQ-off
post-schedule handler would be incorrect.

The ordinary `activate` API remains available. Its local transition guard ends
before its returned retirement is dropped. The production `exec` caller also
retains the old `VmarHandle` across its surrounding preemption-disabled scope,
so this compatibility call cannot destroy its old space as a last reference.
The other direct callers are OSTD tests and the book's example kernel.

## Validation and scope

The OSTD regressions use a real charged physical root and real active CR3. They
remove the last ordinary `Arc`, verify that switching changes the hardware root
without refunding the retained root, then exercise the scheduler's actual
IRQ-restoration release cut. A charge destructor records whether IRQs or
preemption were disabled. Both kernel-only and user-to-user retirement must
release the final frame only after that cut, and leave no active test space.

The unchanged page-memory guest remains the end-to-end acceptance test: all 177
assertions, its original bounded waits, fixture, and accounting owner rules must
pass on the new exact source. Old failure evidence, source snapshots, ordinary
ELF identity, original isolation regressions, and strict negative controls are
separate required evidence; this document reports no unexecuted success.

Kernel-only retirement is enabled only for x86 in this stage. Other architectures
retain their previous no-VMAR behavior until their local translation invalidation
and root lifetime protocol receive their own review and execution evidence.
This adds no NUMA, mobile hardware, DMA isolation, production Hepta authority, or
resource accounting exemption.
