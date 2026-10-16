# Read-only comparison of two prior normal-boot kernels

This package retains the five original scratch analysis files, byte for byte,
in `original/`. Their original internal checksum list remains unchanged. The
outer SHA256SUMS covers those files and these packaging records.

| Prior artifact | Raw bytes | Raw SHA256 |
| --- | ---: | --- |
| [Baseline ELF gzip](../../2026-10-16/artifacts/kernel.elf.gz) | 8,297,624 | `e884f5e50cf296833276016894a39337cd9ac13bc51f6b1f2dea3cc3a6904b63` |
| [Current comparison ELF gzip](../../2026-10-16-ktest-lifecycle/kernel-public/kernel.elf.gz) | 8,290,880 | `490ca0406593c28e64a22333ba432de6122b9a796b0f7f20352b6b2c55e7df56` |

Both existing repository gzip files were independently decompressed during
packaging and matched their original QEMU/raw hashes. No duplicate kernel
binary is included. `artifact-references.json` binds relative repository
paths, compressed/raw sizes and hashes, and the actual historical source
commits. Its packaging-source commit is separately identified and does not
claim that the old ELFs were built from that later commit.

Neither normal-boot ELF contains DWARF `.debug_*` sections; both retain symbol
tables. Five of six PT_LOAD hashes differ. `.text` shrank 928 bytes, and
`.rodata` shrank 7,520 bytes. Removing debug or symbol sections alone cannot
make those loaded bytes equal. Each `.rodata` contains 931 occurrences of its
own checkout root, plus 31 Rustup-root and 61 Cargo-root occurrences. The
original report records real file/section offsets for source and component
path strings, full section/segment hashes, and fixed Git object/SHA bindings.

The complete runtime kernel/OSTD/dependency trees and key manifests/locks are
identical between these historical source commits. Compiler/LLD comments,
initramfs, BIOS and normalized QEMU arguments also match. These observations
prove a concrete path dependency; they do not isolate the cause of every
changed byte.

Source remap flags can reduce compiler-origin path data when rendered into
the wrapper-owned manifest's `[build].rustflags`. Environment-only RUSTFLAGS
and unevaluated TOML variables are unsuitable for the current run/test route.
The fixed upstream component macro separately turns absolute Cargo metadata
paths into ordinary Rust string literals, outside source-remap coverage.
The excerpt and exact source blob binding remain in the original analysis.
No core/SDK edits or complete crosspath remedy are claimed.

Any clean-build pair at one fixed canonical workspace proves only its stated
same-host/same-path scope. A future crosspath experiment must compare loaded
segments and measure the remaining component literals. No cross-host,
full-cause, or whole-ELF crosspath identity result is claimed here.

Only saved archives, scratch analysis files and immutable Git objects were
read. No current target/manifest was read, no VM/Cargo/rustc ran, and no
production source or Git state was changed. Scratch absolute paths in the
unaltered originals identify where analysis occurred; the relative repository
references above provide the retained inputs.
