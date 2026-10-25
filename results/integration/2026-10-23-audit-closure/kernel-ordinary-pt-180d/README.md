# Real original 4 KiB page-table allocation refusal

Frozen180d6dea passed the original complete pipeline in627.577s: core360
with all121 required cases, OSTD230 with original3 TCG VMX soft skips,
allocator20 and MLSDisk15. The same fresh ordinary ELF passed boot18,
SGID30, ownership12, proc12, memfd4, signal22, lifecycle164, stat54,
TRACEME15 and supplementary DAC6. All guest/probe exits were expected33/0,
without timeout; original source blobs remained identical.

The new original VMAR test actually held125186 physical Frames under the
original512MiB N0 fixture. The ordinary4KiB allocator returned NoMemory;
no quota denial, injection, reserve, altered memory limit or larger deadline
substituted for it. It then released0/1/2 Frames, called the original fault
and fallible page-table path at each depth, verified exact0/1/2 unpublished
node refunds, unchanged target hole and sentinel PTE/RSS/domain/refcounts,
then released pressure and successfully retried that same fault. Last-reference
accounting returned to zero. All assertions/formatting/destruction occurred
after pressure release. The kernel production allocation path is unchanged.

An ordinary per-CPU allocation refill failure is not proof that every physical
byte, all frame sizes, the global heap or all CPUs are exhausted. The receipt
explicitly retains global_recovery_guarantee=false. This qualification does
not establish general memory/OOM recovery, full Linux isolation, actual GPU,
ARM/mobile kernel support or final Root/Host/Session persistent CPU G2.

Original host inventory expectation failures01/02 and final03 are preserved.
The complete serial/build/source/strict-inventory logs are in
[the byte manifest](publication.json), alongside the
[source-bound receipt](../ordinary-pt-180d.json) and
[VMAR contract](../../../../docs/agents/VMAR_FALLIBLE_PAGE_FAULT.md).
