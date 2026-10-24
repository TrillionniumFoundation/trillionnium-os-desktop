# Asterinas Unix MSG_DONTWAIT closure

The complete execution belongs to OS `556615fc9368c35539fbd1829f386ab55996dd47`
and tree `97ba9c49ed6c613e7255d3b7d6bc8a7e1f230a1b`. It closes the bounded Unix
per-call nonblocking defect for this source. The [publication](publication.json)
binds every original record, exact source snapshot, retained binary and log.

| Actual execution | Result |
| --- | --- |
| Original full aster-core | 365/365, all 126 required names, no filtering or skips |
| Original full frame allocator | 20/20, including real ordinary exhaustion and protected extent ownership |
| Original full MLSDisk | 15/15, experimental MemoryDisk scope |
| Original full OSTD | 230 reported pass; 3 original TCG hardware soft skips, 227 exercised |
| Same ordinary product ELF | 18 exact QueryAbi/identity/permission markers; raw QEMU 33 |
| Linux reference static ELF | 33/33 actual checks |
| Same ELF on fixed native kernel | 33/33 actual checks; raw QEMU 33 |
| Same ELF on original 74ffd05d kernel | Four exact delayed EAGAIN defects; other 29 pass; counterexample accepted, product false |

The negative oracle requires the four known calls to return EAGAIN in the
bounded old blocking interval; a timeout, arbitrary signal, incomplete log,
wrong error or unrelated failure cannot count as the counterexample. The probe
also checks persistent descriptor flags, payloads, empty receive and full send,
ordinary blocking timeout behavior, stream, seqpacket and datagram sockets.

The first build failed before kernel compilation because the reused OSDK binary
embedded a different checkout path. Its failure is retained separately. The
successful run first built OSDK from the exact test checkout in its dedicated
Cargo home, then executed all original gates. It did not change global OSDK.

Large source snapshots are gzip-compressed with unchanged decompressed bytes.
ELFs, BIOS and initramfs archives remain at their original recorded locations;
the publication records size and SHA256. The ordinary cache was later reused
for the negative source, so a later reader must use retained positive copies.

This evidence does not qualify a new Hepta pair, native durable CPU G2,
production authority, global recovery, SMP or physical-media persistence.
Earlier successful and failed qualifications remain separate historical runs.
