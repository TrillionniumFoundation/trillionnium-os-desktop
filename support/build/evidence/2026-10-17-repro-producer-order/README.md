# Completed producer ordering evidence

This phase retains the schema-4 single-job scheduling mechanism, successful
native probes, expected failed controls and the read-only A3 diagnosis.
It does not claim an A4/B4 kernel boot or byte-equality pass.

Run `python3 -I verify.py` to verify all checksums, <=2MiB chunks, complete
ordered tar-member inventory and inner checksum coverage. Optional
`--output /new/path/producer-order.tar.gz` creates a new verified archive;
existing paths are refused. REPORT.md distinguishes Cargo failure exits from
an experiment CLI accepting their expected outcomes. Native ELF artifacts
are Linux host fixtures. Full kernel evidence is retained separately.
