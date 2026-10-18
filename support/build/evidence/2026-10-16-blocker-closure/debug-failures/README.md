# Debug failures retained during blocker closure

Both debug controller attempts failed on source `071dd8edcd2a3cf9b33dbbeab713428317b9b76c`, tree `5268494bc732e2f39b319248ec4a4dc1705d8d75`. The complete denominator is **2 attempts, 0 complete debug passes, 2 failures**. Only the second attempt launched QEMU.

| Attempt | Actual completion | Observed result |
| --- | --- | --- |
| debug1 | Immediate outer exec exit 1; no standalone session | Preparation failed because GDB was absent from the selected PATH. No QEMU guest ran. |
| debug2 | Tool session 47050 completed exit 1 | Release compilation completed; GDB hit `__ostd_main`, compared 32 live bytes and detached with exit 0; QEMU exited raw33. The live boot checker rejected the recorded `-kernel` pathname size/SHA256 mismatch, and driver/overall exits remained 1. |

The immediate outer call for debug1 included cache cleanup and controller execution. Its separate debug tool session ID does not exist. Root supplied these actual-tool completion observations; the original controller subprocess argv, environment, timestamps and exit 1 records are retained under `raw/`.

The debug2 original boot metadata records **5,975,720 bytes**, SHA256 `fbe81c0e2deae705d61d77ccaaf604e2bf1ca30e4541de71d263af6ecc62ec1b`. **Its complete bytes were already unavailable and are not retained or reconstructed.** Recorded matching entry bytes, a GDB hit, and raw33 do not change the failed overall verdict.

The actual debug2 symbol ELF was still present and was captured through a stable, nonsymlink file descriptor: **111,689,912 bytes**, SHA256 `06c320f0799d4f8afcb610046dceae64b3cc9885aa64537bc24ce0219c67eaf3`. `artifacts/debug2-symbol.elf.gz` retains it; gzip decompression, full SHA256, length and its entry bytes were independently checked. Before/after FD stat and public pathname identity records are retained.

A later read-only observation found the boot pathname occupied by a different **8,266,576-byte** file, SHA256 `d90ebc3210e74271252a6d1f75ca22a16a569a8b48a99805d30d3d99124b9306`. Only its stat/hash observation is retained. The post-failure untracked `kernel/OSDK.toml` bytes and stat/hash are copied under `artifacts/`; its inode differs from the owned inode that the cleanup receipt reports removed. The writer and exact replacement/reappearance timing are unknown. Neither observation is attributed to another agent or process.

`raw/` retains every file in both completed controller/run directories, including full serial logs, QEMU command/exit/profile/firmware hashes, initramfs bytes, GDB/control scripts, environment, symbol listing, build log, and cleanup results. `raw-members.json` binds each original file to its copied member, size and SHA256. Original byte streams are unchanged, including terminal escapes and line endings.

`controllers/` retains attempt1 and the corrected PATH/LD_LIBRARY_PATH controller source. `source/git-source-controls.tar.gz` retains 68 exact committed source/control files with Git modes/blob IDs/SHA256. All 63 source hashes recorded by debug2 environment match that Git revision. The archive is a source/control subset; the complete project remains identified by the exact commit/tree.

`result.json` provides the explicit per-attempt denominator and limitations. `SHA256SUMS` covers every retained file except itself. This archive is immutable failure evidence; any successful later retry belongs in its own evidence directory.

## Symbol storage migration before publication

The original `artifacts/debug2-symbol.elf.gz` packaging path above is historical. Its exact gzip stream is now retained losslessly as **13 ordered chunks** described by `artifacts/symbol-storage.json`; no symbol capture facts or bytes changed. The old SHA256SUMS and storage migration receipt are retained under `artifacts/`. The full original gzip is also preserved outside the repository in scratch as recorded by that receipt. The gzip SHA256 remains `4a8d2ea94b3237d211adf14e9230984a1ab80a0de824fe43a76d179193e54b70`.

Use `python3 -I artifacts/reassemble-symbol.py --output /new/path/debug2-symbol.elf.gz` from this directory. The helper verifies every ordered chunk, total gzip hash/size, and decompressed ELF hash/size before publishing a new output path; it refuses an existing output.
