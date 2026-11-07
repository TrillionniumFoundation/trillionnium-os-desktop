# Fixed Owner16 runtime readback template

This is not an executable collection request: the actual report size and full
SHA are unset, and the reader rejects them before opening a path. Only the exact
Owner16 state/runtime-result.json will be accepted after Root supplies its
terminal-derived pin. No collector or runtime was executed by this package.

The dedicated actor has a 4 MiB hard bound; the enclosing coordinator includes
that actor and its independent Main/unit/cleanup evidence. This fixed reader
therefore allows at most 5 MiB for the complete original runtime report, not a
4 MiB claim for the enclosing report. Every byte and its external SHA must match.
An oversized report fails the collection and is never truncated into success.

The exact writer uses ASCII JSON. A worst escaping fixture of 5,242,879 bytes
round-tripped through the same JSON/gzip/base64 envelope: 10,486,146 uncompressed
bytes, below the explicit 10 MiB + 64 KiB envelope cap. The gzip cap adds another
64 KiB. Original 128 MiB, CPU1, 30s resources and protected held/named FD gates
remain. The full-prefix actor control was already run in the dedicated consumer
freeze; this package adds only a pure codec-bound check, not another lifecycle
control. All qualification flags remain false.

The producer's exact compiled control.rs sends the complete serde JSON using
write_all; its 64 KiB request bound is not a response bound. The older 256 KiB
limitation was in the Python consumer and is already repaired only for the
strict new log schema. This does not qualify the actual Android libbase cache,
KernelLogger definition, generation marker or init boot outcome.
