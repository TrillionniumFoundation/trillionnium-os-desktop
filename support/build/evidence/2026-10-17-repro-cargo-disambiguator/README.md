# Cargo crate disambiguator mechanism evidence

Native fixture evidence and the retained real A2/B2 inequality diagnosis.
This phase does not claim a profile-3 full-kernel boot or byte comparison.
See REPORT.md and source-bindings.json for exact published candidate bytes.

Run `python3 -I verify.py` to verify all outer files, chunks, the complete
ordered tar-member manifest and inner SHA256SUMS. Optionally pass
`--output /new/path/cargo-disambiguator.tar.gz` to create a new verified archive.
Existing output paths are refused. All pieces are at most 2 MiB.

The complete native sources, compiler/producer ledgers, actual failures and
independent review are retained inside the archive; target caches are omitted.
Native binaries in native-artifacts/ are host test programs, never kernel
boot evidence. The separate full-kernel phases retain real QEMU evidence.
