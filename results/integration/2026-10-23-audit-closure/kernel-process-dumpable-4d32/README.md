# Image-owned dumpability and controlled native isolation

Frozen4d32d94f passed the original complete pipeline in577.893s: core359 with
all120 required cases, OSTD230 retaining its original3 TCG VMX soft skips,
allocator20 and MLSDisk15. The same ordinary kernel ELF passed boot18, SGID30,
Unix ownership12, proc privileges12, memfd4 and signal22, followed by actual
lifecycle164, sensitive stat54 and unprivileged TRACEME15. All complete probes
exited0/rawQEMU33 with no timeout; all owned probe children were reaped.

The original MM owns dumpability, shared by CLONE_VM and copied by fork. Exec
and live credential changes use the same original synchronization boundary.
Proc sensitive reads/readlinks, pidfd_getfd and established debugger reads use
that policy; old environment/auxv descriptors retain only their original image.
Unprivileged TRACEME releases the parent mutex before original Yama admission.
A tracer's actual relationship capability is captured at attachment, and
PEEK/POKE checks the recorded caller and shared MM while retaining the locks.

Original host84, source118,6 new kernel owner cases, cfg-ktest Clippy113 existing
warnings, strict lifecycle/stat checker5 and TRACEME checker3 are source-bound.
Their original red baselines remain separate publications, including Linux
fixture-policy failure,43 native lifecycle failures,20 sensitive stat disclosures
and the old0252 TRACEME original120s timeout. That timeout did not reproduce an
established PEEK bypass. Intermediate sparse-fixture and borrow-check failures
also remain in the qualified receipt, without rewriting original bytes.

This qualifies the stated image/process isolation scope, not complete Linux
ptrace or capability parity. PTRACE_ATTACH/user namespaces remain unsupported.
Supplementary-group DAC, original small physical page-table NoMemory, general
heap/accounting recovery, final Host loader/Session isolation, protected writer,
physical checkpoint recovery and persistent CPU G2 remain separate acceptance.
No executable, disk image, compiler target, key or private state is published.

See [the manifest](publication.json),
[the qualified source receipt](../process-dumpable-4d32.json), and
[the module contract](../../../../docs/agents/PROCESS_DUMPABILITY.md).
