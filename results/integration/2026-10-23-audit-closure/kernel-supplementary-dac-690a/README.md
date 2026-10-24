# Supplementary membership in original DAC group permission

Frozen690a7bb3 passed the original complete pipeline in594.206s: core359 with
all120 required cases, OSTD230 retaining the original3 TCG VMX soft skips,
allocator20 and MLSDisk15. A fresh ordinary ELF passed boot18, SGID30, Unix
ownership12, proc privileges12, memfd4, signal22, lifecycle164, stat54, TRACEME15
and the same original supplementary-group6 cases. Every probe exited0/raw33
without timeout; all owned probe children were reaped.

The production change is one condition in the existing DAC group branch:
match the inode group against the caller's fsgid or its actual supplementary
groups. Owner priority, other-class denial, capability override and mask logic
are preserved. The original Linux/static executable cc6a20ff is unchanged.
Its two formerly refused legitimate group operations now pass in0.768s while
member write and all three nonmember accesses remain denied. The original
0252 probe42/raw33 failure remains a separate published counterexample.

The complete native logs, source snapshots, actual ELF/receipts, host84,
source118, Clippy113 existing warnings and strict checker3 rejecting21
mutations are retained. No executable, compiler target, disk, key or private
state is published. All qualifications bind the actual frozen690 source;
4d32's earlier successes are not transferred to it without execution.

Ordinary physical page-table NoMemory, general heap/accounting/global recovery,
complete Linux isolation parity, final Root/Host/Session deployment, native
persistent CPU G2, GPU and native ARM/mobile acceptance remain separate work.

See [the manifest](publication.json),
[the source-bound receipt](../supplementary-dac-690a.json), and
[the module contract](../../../../docs/agents/SUPPLEMENTARY_GROUP_DAC.md).
