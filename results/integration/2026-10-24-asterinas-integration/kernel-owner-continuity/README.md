# Retained CPU owner continuity execution

The actual execution belongs to OS `824720ea64e25a40c3bef6e338193910ce12912c` and tree `7dcb141abf6f66f047913e15b66cba3e49023e20`. Its original
pipeline took 1062.465 seconds. This publication reads
existing results and raw logs; it runs no kernel, userspace owner or test suite.
The [publication](publication.json) binds every copied record and retained
binary by actual SHA-256 and byte count.

| Actual historical execution | Recorded result |
| --- | --- |
| G2 feature, complete aster-core | 371: complete ordinary 368 plus the original 3 Root Process tests; all 129 ordinary required names |
| Ordinary complete aster-core | 368: original 365 plus 3 CPU-owner continuity tests; 129 required names, no filtering or soft skips |
| Ordinary frame allocator | 20, including actual original exhaustion/ownership checks |
| Ordinary MLSDisk | 15, experimental MemoryDisk scope |
| Ordinary OSTD | 230 reported; 3 original TCG hardware soft skips; 227 exercised |
| Same ordinary product ELF | 18 QueryAbi markers and 33 positive Unix MSG_DONTWAIT checks |
| Original G1d watchdog | Six independent boots, each complete and raw QEMU exit 33 |
| Previously executed Linux reference | Same original static probe SHA; reused reference, not rerun here |

All original successful QEMU exits are raw 33. The G2 input is exactly
799744 bytes with SHA `178f67705b0bd4450733e92eaed5a5febd2e4d7279d071660e64a8819409d2ec`. It is a **compilation input only**;
these Process ktests do not execute or qualify the original Hepta owner.
The independently retained OSDK has SHA `fe5878d7602927c45fd98a9b2119e5ebd720710422a609c4fe20bfccdd8b20ee` and was built from the
same exact original checkout path.

The three CPU-owner regressions verify old-image revocation isolation, delayed
watchdog-cut isolation and bounded callback registration across policy replacement.
Each required name appears once with its own terminal result in both the ordinary
and G2 core logs. This extends the original 126-name gate to 129; it does not
substitute a smaller filtered suite.

The watchdog is the original C probe under the three-role G1d profile, with
SHA `1d95dc45b3ed1a78a541d030d9b167f82d73ce0634859d1a34a22c30b893b588` and 1100568 bytes. Its separate kernel
has SHA `b8dd04f0b9ec74cb31d7c865fb7cf8b6a8edbaa164c386219283060a8b67ffb8`. The G2 compile input, the ordinary product ELF,
and this watchdog kernel retain their separate identities.

| Original watchdog boot | Original verified outcome |
| --- | --- |
| restore | Manager close leads to the independent timer restoring the cap; saved receipt and revision remain stable on later ticks |
| healthy | Live manager retains its policy without watchdog recovery |
| zero | Zero cap is preserved, then fatal cleanup and reap complete |
| zerothread | Zero-cap workload with another thread preserves the cap and completes fatal cleanup/reap |
| stopped | Watchdog preserves the original job stop; explicit continue is separate |
| recovered | Recovery has already consumed its one-effect allowance; watchdog does not apply another recovery effect |

Each case retains its original result, raw QEMU record, exact raw serial SHA/size,
elapsed time, kernel/BIOS/initramfs bindings and observed original markers.
Publication validates those existing records; it runs neither the watchdog nor
its evaluator again. These are N0 emulated timer results, without a physical-clock
fault-injection or hardware claim. They do not execute a Hepta production writer.

Every `.log` is gzip-compressed directly from its original bytes. Decompression
must reproduce its original SHA and size, including original CRLF. Larger
text/JSON records may also be compressed; `records` specifies every path and
both original/published digests. No raw log is decoded and written back as
text. Binary ELFs, BIOS, OSDK and initramfs archives remain at their actual
retained paths; only their verified SHA/size manifest is committed. Mutable
Cargo target paths in original QEMU argv are provenance and are never read
or rewritten during this archival pass.

This evidence does not include later bounded-successor or launcher additions.
It does not qualify an original native daemon/writer/FinalUse
cycle, lost reply or crash after effect, cross-boot Unknown preservation,
300-second grant renewal, repeated role recovery, long-term persistent CPU
control, host power loss, SMP, physical media or production readiness. The
independent G2-complete and product flags stay false. Earlier success and
failure records remain separate; no later source inherits this qualification.
The earlier 0f6300e4 initial-Process archive remains intact at
`../kernel-g2-initial/publication.json` and retains its own older inventory.
