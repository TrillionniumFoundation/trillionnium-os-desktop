# Preserved OS qualification evidence

This evidence-only followup is based on actual main `2d2eb42d6d897edf6316e5ad326dcea04e8aa75d`. It changes no production or test source, workflow, dependency manifest, lock, or permission.

The sibling `2026-10-21-a07-cpu-history-native` directory contains the unchanged seven-file native proof from the original PR #229 followup: 11 CPU history tests, the complete 28-test service suite, strict Clippy on Rust 1.88, and the original sandbox socket-bind refusal. It records the actual source/version and original logs. #229 was subsequently merged by ProfHepta as `2d2eb42d6d897edf6316e5ad326dcea04e8aa75d`; this packet does not recreate or attribute that merge to the reviewing agents. Its 11 original PR file changes were independently verified against the actual merge without any changed source blob.

The sibling `2026-10-21-exfat-qualified` directory contains the original #231 A06 job, all exact-head check results, complete artifact byte-check receipt, the complete ZIP member index, and original small host evidence in deterministic compression. The complete 206,241,233-byte artifact remains referenced by its GitHub artifact identity and its reusable file identity; every byte was streamed and matched to the original SHA-256. The large ELF/ZIP payload is deliberately outside this Git tree. The actual successful runner was 7.0.0-1017-azure and already had its matching ExFAT module, so the conditional module installation fallback was not exercised by that run.

`main2d-candidate-validation.json` is the unchanged independent root source review of the ordinary, conflict-free #228/#230 merge candidates. It establishes exact tree and blob preservation only. It is not a CI result or a human approval.

Original evidence remains tied to its own source head and scope. None of these records confers success on this evidence commit, on later main source combinations, on the pending #228/#230/#232 checks, or on physical desktop/device qualification. No tests were rerun to assemble this packet.
