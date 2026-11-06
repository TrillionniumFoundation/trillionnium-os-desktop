# Static ELF interface for the bounded aapt2 provenance worker

`inspect_elf_fd(fd, size)` accepts a caller-owned, already opened and pinned regular-file descriptor and the caller's verified file size. It supports ELF64 little-endian x86-64 ET_EXEC/ET_DYN with ordinary program-header counts.

The parser's only file-descriptor operation is `os.pread`. It does not open, close, seek, mmap or execute anything. It does not find libraries, read environment variables, expand RPATH, inspect Android or infer loader success. The caller must retain the FD, validate file identity/hash before and after this call, and close it when its own operation is complete.

## Contract

The result includes:

- `format`: ELF64LE; `type`: ET_EXEC or ET_DYN; `machine`: EM_X86_64; numeric machine_id/osabi/abi_version.
- `interpreter`: exact PT_INTERP absolute UTF-8 path, or null.
- `needed`: DT_NEEDED strings in original order, preserving duplicates.
- `rpath`, `runpath`: exact raw strings. An empty value remains an empty string; only an absent tag becomes null. No token, relative path or empty search component is resolved here.
- `additional_loader_directives`: decoded DT_CONFIG, DT_DEPAUDIT, DT_AUDIT, DT_AUXILIARY and DT_FILTER strings. A narrow executor should explicitly require this list to be empty before considering its own closed dependency policy.
- `load_segments`, `dynamic`, `string_table`: bounded static segment and mapping evidence. A virtual interval is partitioned at PT_LOAD boundaries. Every subinterval must have exactly one covering file-backed mapping. Missing coverage, BSS coverage and any overlapping load mappings reject the input. Unique spans across multiple PT_LOADs are supported, including disjoint underlying file ranges.
- `string_table.offset` is null when the table's file ranges are not physically contiguous; `mappings` is authoritative. `load_segment_index` is null when a structure spans more than one load segment.
- `is_loader_resolution_proof` and `unknown_dynamic_tags_interpreted` are always false. Unknown tags are reported numerically as unexamined metadata.

Malformed, ambiguous, unsupported or over-budget forms raise ELFError, a ValueError subclass. Operating-system pread failures retain their original OSError. This is a deliberately bounded metadata parser, not a general validation or execution engine.

## Bounds and evidence

The file-size input is at most 512 MiB. There are at most 1,024 program headers and 128 load segments, 64 KiB of dynamic data, 4 MiB of string data and 5 MiB total pread data. Strings are limited to 4 KiB, DT_NEEDED to 128 entries and extra loader directives to 32. Extended program-header count encodings are rejected.

Header, program-header and dynamic entry layouts are the ELF64 forms verified against the local system's `<elf.h>`. RPATH/RUNPATH and GNU loader string tags are kept separate. No static field is treated as evidence that an actual dynamic linker resolved the same dependencies.

The first local control revision revealed that the local Python executable has a string table crossing two adjoining load segments. The initial one-segment assumption was too narrow. The original source, test and failed stdout/stderr are retained. The final code partitions the interval and proves unique mapping for every byte instead of accepting overlap or discarding the identity requirement.

The final six local control groups passed:

1. A genuine local system ELF read without executing it, with its original FD offset/stat/lifetime preserved.
2. Synthetic valid metadata with raw RPATH/RUNPATH and caller-owned FD behavior.
3. Header, architecture, program-count, file-extent and short-pread rejection.
4. Partial virtual overlap, missing mapping, oversized tables, duplicate declarations and missing terminators.
5. Invalid interpreter paths plus explicit audit directives and empty RPATH preservation.
6. A unique virtual string table backed by two noncontiguous file regions.

All fixtures were local owned temporary files. The final full-process FD identity returned from 3 descriptors to the same 3. No ELF was executed and no APK, Main namespace or target process was accessed. These controls do not certify Pocket4's candidate or its actual dependency resolution; the separate worker owns that evidence.

