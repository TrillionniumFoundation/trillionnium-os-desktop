# 2026-10-23 store compatibility validation

The original Hepta libraries were built from clean
`b3d3f2d4b01f123d7ac17575c27fb54d00094f7f`, tree
`b035a577969cb503d7c09620694a6b6c54178c97`. The external Rust fixture binary is
31,108,672 bytes, SHA256
`246dbd2a690453ad0e700d3fced91ae426a3ab96823f64528ba86e28414f7a05`.
It directly links the original API; no owner source or dependency identity was
changed. Offline resolution, locked metadata, locked dev-small build and
Clippy with warnings denied passed on Rust 1.95.0. All 704 retained shared
package identities match the original lock (name, version, source, checksum).

| Actual validation | Result | Qualification |
| --- | --- | --- |
| Linux host `host-1` | 10/10 fixture checks | Original legacy WAL/process-crash reopen and process CAS |
| Ordinary Asterinas `native-3` | 10/10 fixture checks, fixture exit 0, QEMU exit 33 | The same original store on a fresh writable ext2 guest disk |
| New host oracle/C-emitter regressions | 18/18 | Includes real C multi-read output and forced 127-byte short writes |
| Same tests under Python `-O` | 18/18 repeated | No additional unique tests or guest evidence |
| Existing runtime staging/receipt regressions | 42/42 | Reused staging/initramfs/boot protocol regression coverage |
| Rustfmt, staged diff checks, static C launcher compilation | Passed | Static checks only |

Both actual store runs observed 1,244,272 WAL bytes while the seed pool stayed
open, an actual SIGKILL wait status, exact original logical cut/full-memory
reopen, an idempotent source retry, and one process CAS commit plus one original
conflict. The host's winning contender was `b`; the guest's was `a`. Both
verified the losing source insert rolled back and awaited the original pool
close before their final exact reopen. No simulated store result was used.

The guest used the actual clean ordinary kernel built from Desktop
`7d8906ef9fbb5f3af4e6bb0843b79ac666394833`, tree
`ca4b875cdb553291a99f4a550eb0b2bd6649de8c`, kernel SHA256
`8bee0769b1cbf5217b396294ccbcfdc31bb7ba90b52be53bba03364b7fe0e186`.
Its receipt SHA256 is
`a2554b5651d377b32c1c8f08dd911b414d4a7f81421892e7c34b2aea2932d37f`.
This validates the store workload on that exact kernel only; it does not
qualify subsequent kernel changes or the complete kernel test suite. The
payload stayed read-only. The state image changed from SHA256
`053b7333121bb719bc137c9a93a782620d7e8aefc1d1b38e5b0558c0c8d3d626`
to `ff4b7a6871439107c3cb9b35e0c1e1c216fc3b9a73e6fd717c359574e0e76758`.
The guest used one CPU, 4 GiB memory, no network and a 900-second outer limit;
it finished without timeout or excessive output, retaining 25,984 serial bytes.

The local audit workspace retains the raw inputs and receipts under
`work/f1-store-validation/`. Receipt identities:

| Retained file | SHA256 |
| --- | --- |
| `build-2/build.json` | `6cc1ccbff13211c3d33a713feaac28d7e54f999708e0685dadcf4623e17232de` |
| `host-1/result.json` | `bf8b2a666a91886e3eb4922f6593fcc57339add945e3b036d9ef249a9f6b2b24` |
| `native-3/result.json` | `05ae78003701bb037718bf10a3614f3a94f2fe607ef7c908214ceba2bb0e2ec3` |
| `native-3/fixture.stdout` | `7f8230f95f846cc32dfc063f704b50f736351aa4262a2f226400fe1c9ae726a0` |
| `native-3/serial.log` | `e75fd1830bba7e0a5df545841088cd72a9f9777d157fbba44c25d3483f786d66` |

These are caller-retained local evidence identities, not remote attestation.
The raw binary/disk images are not copied into this source module.

Earlier failed attempts remain failures: `build-1` exposed and corrected three
adapter return-type mistakes; `native-1` rejected INFO syscall logs splitting a
buffered hex stream; `native-2` rejected the launcher's assumption that one TTY
write must be complete. `native-3` used the corrected bounded write loop and
warning log filter, with the same strict receipt oracle, original Rust binary,
Hepta owner source and ordinary kernel. The two earlier native attempts are
not counted as passes.

Every receipt retains `production_authority=false`,
`production_writer_lock=false`, `authenticated_recovery=false`,
`power_loss_durability=false`, `f1_completed=false`, `model_turn=false` and
`device_effect=false`. See the [module contract](README.md#qualification-boundary)
for the actual external authorization/current-witness work still required.
