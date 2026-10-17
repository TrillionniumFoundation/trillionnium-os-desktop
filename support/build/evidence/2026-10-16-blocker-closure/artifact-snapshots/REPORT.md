# Retained boot-artifact snapshots

The recorder now creates a new private `artifacts-*` directory beside `qemu.json` and exclusively writes a copy of each requested kernel, initramfs and BIOS file. QEMU's actual argv loads these retained snapshots. `artifacts[option].path` names the actual loaded snapshot; `.source` retains the original requested path, absolute source path, size, SHA256 and file stat. Original QEMU arguments are always preserved.

Each source is opened once as a read-only FD. The recorder checks regular-file type and compares FD and pathname device, inode, mode, size, mtime_ns and ctime_ns before and after chunked reading. Copy bytes are independently read back and compared with the captured size/SHA256. Snapshot files use exclusive `xb` creation, mode0400, and a private mode0700 `mkdtemp` directory. Each requested kernel/initrd/BIOS option must occur exactly once and provide a path, before any QEMU version probe. The snapshots are checked again before launch and after raw exit. Failure records retain stage/error and the actual raw result; there is no fallback to a changed source. Launch failures also retain an explicit failure record and snapshots.

| Verification | Exact result |
| --- | --- |
| Baseline recorder `071dd8ed...`, actual CLI with executable fake QEMU | Two expected assertion failures, one each under `python -I` and `python -I -O`: fake QEMU read all three original inputs, then atomically replaced their source paths; recorder raw33 but unchanged live checker exit1 |
| Final full boot-evidence host suite | 23/23 passed under `python -I`; 23/23 passed under `python -I -O` |
| Existing GDB listener ownership suite | 3/3 passed under `python -I`; 3/3 passed under `python -I -O` |
| Final accepted test-method executions | 52, including 46 boot-evidence and 6 listener executions |
| Additional intermediate suite retained | 22/22 in both modes before launch-failure hardening; its 44 executions are historical and are excluded from the final52 denominator |

The final replacement test reads the actual QEMU argv and loaded bytes from the executable fixture, replaces all three original paths, and then runs the **unchanged** production checker with `--live-artifacts`. It passes because the actual argv, recorder digest and retained snapshot bytes agree. Additional cases cover all12 missing/duplicate/valueless/empty argument variants; in-place mutation and atomic pathname replacement during source-FD reading; rejection of nonregular sources; exclusive-create collisions preserving existing bytes; distinct directories across runs; post-run snapshot tampering returning1 despite raw33; and an executable disappearing after its version probe. Existing raw-serial, timeout and panic rejection coverage remains active.

`raw.tar.gz` preserves original commands, selected environment values, source bindings, console logs, fake-tool observations and fixture files. Every regular member has a size/SHA256 entry in `archive-manifest.json`. `report.json` records exact counts and per-suite invocation paths. `sources/` retains baseline and final production/test/checker/listener bytes; two historical intermediate sources are reconstructed from the final bytes and verified against SHA256 recorded by the original invocations. Generated Python bytecode is excluded.

These are **host-only** tests using an explicitly labeled executable QEMU fixture and archived serial bytes. No real kernel was built or booted for this packet. Actual guest/GDB validation is performed separately by root A01 after publishing the code commit. The source-path replacement writer remains unidentified; this change does not attribute it or claim a sandbox, adversarial immutability, or protection from a same-user actor discovering and modifying a snapshot. Such detected snapshot changes fail closed.

Only `record-qemu.py` and `tests/test_boot_evidence.py` changed. `check-boot.py`, kernel/core, OSTD and production OSDK source remain unchanged.
