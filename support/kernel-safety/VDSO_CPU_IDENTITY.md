# Linux CPUNODE observation contract

The pinned x86-64 vDSO (`27cd7bf576a92fa48a891c05988f52fac35b7374d5b9650d6b035e477c5d93a3`)
implements `__vdso_getcpu` using `LSL` on selector `0x7b`. The prebuilt bytes are
mapped unchanged. Linux assigns that selector to GDT slot 15; its limit encodes
the logical CPU in the low 12 bits and the NUMA node above them. This is public
observation data. It is not a scheduling token, permission or authority input.

The previous OSTD GDT had nine 64-bit slots and a limit of 71. Slot 15's offset
120 was outside that limit. The pinned vDSO initialized the destination register
to `0x7b`, executed LSL without checking failure and returned success after
masking that unchanged value. Real pinned samples therefore observed libc and
raw vDSO CPU 123 while `SYS_getcpu` correctly returned the selected CPU. The
original `9957cd197868b3022a7c7fabf4c5f07cf8bcbd89` ordinary ELF was
`2cec010774df75197f212cb3f2bece1c2b96699750e620f58f4bfc48b3ebaf7d`.

## Descriptor and ownership

The descriptor follows Linux v6.2.10's
[setup_getcpu](https://github.com/gregkh/linux/blob/v6.2.10/arch/x86/kernel/cpu/common.c#L2134)
and [CPUNODE definitions](https://github.com/gregkh/linux/blob/v6.2.10/arch/x86/include/asm/segment.h#L196).

| Field | Value |
| --- | --- |
| GDT slot / selector | 15 / `0x7b` |
| Base | 0 |
| Type | 5: read-only data, expand down, already accessed |
| S / DPL / present | 1 / 3 / 1 |
| D / L / granularity / available | 1 / 0 / 0 / 0 |
| Limit | logical CPU ID, with node 0 |

With node 0 the complete value is `0x0040_f500_0000_0000 | cpu`. IDs above
4095 are explicitly rejected before loading the GDT, rather than silently
aliasing another CPU or the node bits. Node 0 agrees with the existing
`sys_getcpu` contract; this change does not add NUMA support.

Slots 0 through 8 retain their exact order and values, including the two-slot
TSS at 7 and 8. Slots 9 through 14 remain null. Compile-time assertions retain
the original selector offsets and require CPUNODE at offset 120 in a 128-byte
GDT. The CPU-local GDT uses its existing kernel mapping and loading path; no
user-writable mapping or segment-register update is introduced. FS/GS thread
TLS setup and all original code/data/syscall selectors are unchanged.

## Initialization order

The statically copied `Gdt` contains a zeroed `AtomicU64` CPUNODE field; it does
not read a CPU ID while constructing static storage. Only the existing
`gdt::init_on_cpu` writes that CPU's checked descriptor, before `lgdt` and before
user execution or preemption is enabled.

- BSP assembly establishes GS.base. `cpu::init_on_bsp` prepares all CPU-local
  storage and initializes `CURRENT_CPU`; only later does
  `arch::late_init_on_bsp` enter trap/GDT initialization.
- AP assembly establishes its own GS.base and passes its known logical ID to
  `ap_early_entry`. That function calls `cpu::init_on_ap(id)` before trap/GDT
  initialization. The GDT code already used `CpuId::current_racy` at this point
  to address its CPU-local table; the descriptor reuses that established ID.

The existing boot-only safety boundary in OSTD is retained. No unsafe code is
added to a kernel crate and no new allocator, I/O, mutex or context-switch
callback is needed. This design assumes the existing fixed online CPU set.

The pinned mapped text is the LSL implementation, not a runtime-patched RDPID
alternative. This change preserves those original bytes; it does not claim
RSEQ support or provision a different vDSO/TSC_AUX ABI. A future vDSO revision
must be reviewed and rebound as a separate input.

## Development and verification

The [guest probe](../../tests/kernel/vdso-cpu/probe.c) is frozen before the kernel
change and used unchanged before and after it. It resolves only the bounded
original ELF dynamic tables inside the mapped vDSO page. CPU identity is sampled
only after a successful single-CPU affinity bind, with the mask checked again.
Each main/worker TID visits every configured CPU in ascending and descending
order. This avoids treating legitimate migration between two unbound calls as
an ABI disagreement.

Each sample records libc return/errno, raw vDSO return/errno, direct syscall
return/errno and CPU/node, LSL success/limit, TID and current user CS/SS. Success
uses actual return values and CPU/node agreement; errno is recorded without
inventing a general success-errno guarantee. Independent TLS cookies, exact
masks, thread join, original mask restoration and nondecreasing monotonic time
are mandatory. The runner requires the exact 34/58/106 case inventories and
4/8/16 sample inventories; extra or missing entries fail. The private marker
and Rust version guard prevent accidental host execution, while the outer
retained ELF/source hashes establish actual kernel identity.

The original before runs on one/two/four CPUs produced exactly 12/24/48 failed
cases: libc, raw vDSO and LSL in every pinned sample. The other mask, syscall,
TLS/selector/TID, cleanup and clock cases passed. Original failure receipts are
preserved. Candidate qualification requires a new ordinary product, complete
OSTD/core suites, all three CPU-count probes and relevant real affinity/handoff
regressions under its own exact source and artifact identities. It does not
inherit a prior kernel's native/production or physical-hardware qualification.
