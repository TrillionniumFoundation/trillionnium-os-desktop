# Immutable normal-boot ELF comparison

The baseline e884f5e5… (8,297,624 B) and current 490ca040… (8,290,880 B)
differ in loaded code/data. Neither contains DWARF .debug_* sections; both
retain symbol tables. Five of six PT_LOAD hashes differ; .text shrank 928 B
and .rodata shrank 7,520 B. Stripping metadata alone cannot equate them.

Each .rodata contains 931 occurrences of its own absolute checkout root,
plus Rustup/Cargo roots. Full runtime kernel/OSTD/dependency trees, key
manifests/locks, compiler/LLD comments, initramfs, BIOS and normalized QEMU
arguments match. This proves a concrete path dependency, not the cause of
every changed byte or cross-host reproducibility.

A possible A01-only partial remedy is rendering source remaps into the owned
generated manifest [build].rustflags. Environment-only RUSTFLAGS and literal
TOML variables do not reach the current run/test route correctly. Absolute
component metadata paths are ordinary generated string literals and remain
outside source-remap coverage. No core or SDK edits are proposed.

Root's next A/B experiment is scoped to clean targets at the same canonical
path and host/environment. Later crosspath tests must compare loaded segments
and measure residual literals before claiming whole-ELF equality.

report.json records exact Git/source/config hashes, section and segment
comparisons, immutable artifact hashes, byte-offset path samples and limits.
elf-structure.json records full section data. Extracted scratch ELF copies
remain in ../next8-elf-comparison; original archives/current targets were
untouched. No Cargo, rustc invocation, VM, production source or Git writes.
