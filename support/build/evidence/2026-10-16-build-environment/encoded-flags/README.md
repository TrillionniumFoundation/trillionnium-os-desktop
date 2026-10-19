# Encoded Rust flags: preserved host evidence

The exact checksum-selected input is preserved as 29 regular tar members:
28 content files plus the original checksum list, totaling 118,438 bytes.
No Cargo target, tiny executable or generated pycache is retained. Every
member was reopened and byte-compared, with sizes and hashes in `members.json`.

The independent source review found no blocking issue. The new ktest guard
rejects `CARGO_ENCODED_RUSTFLAGS` whenever present, including empty, before
output, workspace lock or external commands. Two new tests failed against
the retained pre-fix runner. Final suites passed 17 methods in each Python
mode (34 executions), with actual sessions/exits in `validation.json`.
The exact final source blobs map through `source-publication.json` to
local6b68e196 and publisher-verified remoteff040c6d with equal tree. Original
source-binding records retain the earlier observed merged base unchanged.

Three actual dependency-free tiny programs used fixed nightly Cargo/rustc
with `--locked --offline` and separate targets. The same RUSTFLAGS cfg is
active only when the encoded variable is absent. Empty encoded flags suppress
it; nonempty encoded cfg replaces it. Exact selected environment, argv, exit0,
stdout and unchanged lock hashes are retained in `cargo-precedence.json` and
the raw per-case receipts. These are host programs, not kernel/boot evidence.
The original tiny-experiment controller was not among the frozen inputs;
source/lock and all invocation/output records are retained without inventing it.

To replay the host suite, extract the raw tar into fresh scratch, copy
`original/source-snapshots/ktest-run.py` and
`original/source-snapshots/ktest-test_runner_lifecycle.py` together under
the names `run.py` and `test_runner_lifecycle.py`, then run the commands
recorded in `validation.json` with the relocated script path. The two red
tests can instead be replayed with `original/baseline-lifecycle/`. For the
tiny Cargo experiment, use `original/tiny-flags/` and adapt each retained
invocation's manifest/target paths to three fresh directories while retaining
its fixed toolchain, flags and lock. The archive itself reran no commands.

This review does not extend early rejection to debug top-level output or
OSDK-integration, and claims no new kernel compile, QEMU launch or all-phase
green result. The separately reported merged-main Clippy exit101 remains
outside this fix. Original make78 plus ktest34 are 112 executions; later
root revalidation must be counted separately, not as additional unique cases.
