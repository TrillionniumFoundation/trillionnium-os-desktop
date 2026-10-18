# f092 A10 completed CI evidence

The A10 Linux-host workflow for exact commit `f0924a6e48c68101ec09b01ef2f69aec330a3da7` completed successfully. Run **39073273425**, source job **117515138978**, native job **117518904862** are preserved here with raw job output, API snapshots, artifact metadata and executable verification. The native job ran 22:44:10–22:47:10 UTC on 2026-10-17.

This append-only completion record preserves the earlier f092 archive, whose A10 snapshot was still queued when retrieved. The f092 ARM original-Agentd run remains failed in its separate earlier archive. This success is not assigned to a later source head.

The actual host-check log contains 145 Rust tests passed, zero failed and two explicitly ignored CJK-font tests: UI workspace 81, observer 17, support/ui 39, tests/ui 8. Six separate Python owned-process guard tests passed. The new original-Hepta Shell capture Python contract tests are not invoked by this workflow. The actual Session fixture, egui layout, Weston Shell/app/cancellation and compositor-restart, IPC refusal and packaged-ELF replay passed.

The Session and Hepta-page runtime records explicitly use a scripted socket fixture, report original Agentd absent, and do not claim compositor-pixel verification. No original-Hepta → persistent Session → six-phase native Shell pass is inferred from this CI; the separate local original runs carry that evidence. No model, objective, physical input/display, device or mobile qualification is inferred.

Artifact 12117635274 ZIP bytes and SHA256 were matched to GitHub's published digest. The inner tar was independently streamed and hashed; all four packaged executables were streamed without extraction or execution, checked as ELF64 little-endian x86_64 and matched to their SHA256 manifest. The large ZIP/tar and ELF bytes are omitted from this Git archive. Runtime Session/Shell hashes are preserved separately because packaging stripped the files and changed their bytes.

`artifact-members.json` maps every ZIP member to its original byte count/hash and curated copy; `.log.gz` files decompress to the original raw log bytes. `package/verified-executables.json` records measured sizes and ELF/hash checks. `summary.json` states exact scope and limits. `SHA256SUMS` verifies every curated file.
