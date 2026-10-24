# Inline signal ownership, typed fault reasons and detached memfd

Frozen `6c26e3aeefde05c120944e278299b4925612f3c8` passed the complete original
pipeline in 545.818s: core353 with all114 required tests, OSTD230 retaining its
three original TCG VMX soft skips, allocator20 and MLSDisk15. All four guests
returned raw33. The ordinary ELF passed18 boot/QueryAbi assertions, then the
same ELF passed SGID30, Unix ownership12, process privilege12, memfd4 and
signal14. Every probe exited0 and raw33; complete tracked source snapshots match.

The retained failures include both original d5 protection-fault classifications,
the errno-only unmapped negative, the standalone console initialization failure,
and 1d2's missing rt_sigqueueinfo after seven successful signal cases. They are
not converted to success by a raw QEMU33. The final typed fault reason comes from
the original locked VMAR lookup. Original standard signal owners remain inline
through pending, ptrace/requeue, timed wait and signalfd; dynamic and RT owners
retain their original allocation and FIFO contracts. The new syscall uses real
target credentials and accepts an actual nonleader TID for the shared queue.

The same frozen Root C binary passed the controlled Linux reference, failed on
the old d5 native ELF because its memfd reported nlink1, and passed on this new
ordinary ELF in 0.818s. Actual Root-owned regular nlink0/mode0400/four-seal state
and a dropped UID60001/caps0/NoNewPrivs child were checked. The child read the
complete bytes and could not write, grow, shrink or change ownership. This is
an independent kernel handoff component test, not the production bootstrap DTO
producer/Host loader or a complete native Root authority service.

Original host84, source118, checker6+6, Clippy106 warnings and Linux14+memfd4
records are included. The final combined checker invocations displayed tool
output without a separate redirected file; the individual original checker logs
are retained without inventing another log. All original ELF/disk artifacts stay
at their retained local paths; only text records are published here.

The separately identified kill/tkill/tgkill/pidfd full signed-argument boundary
remains a next-phase defect. No ordinary small physical page-table NoMemory,
RT quota, global heap recovery, complete memory accounting, persistent CPU G2,
whole-writer crash recovery or production loader qualification is claimed.

See [the complete manifest](publication.json) and
[the module contract](../../../../docs/agents/INLINE_STANDARD_SIGNAL_OWNERSHIP.md).
