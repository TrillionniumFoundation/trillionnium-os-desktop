# Public entry guards for encoded Rust flags

Both public runners now reject the **presence** of `CARGO_ENCODED_RUSTFLAGS`, including an empty value, with exit 2 immediately after argument parsing. The diagnostic is identical to the existing normal and kernel-test entry guards. Callers must unset the variable rather than bypass the mandatory kernel flags.

The baseline is commit `350d98d70a3d7b7c720cabd7720063849afb5a29`. Baseline and fixed snapshots, a patch, exact commands, source SHA256 values, environment selections, outputs and exit codes are retained here. The fixed code commit is published separately by A01; the snapshots are bound by SHA256 in `report.json`.

| Verification | Exact result |
| --- | --- |
| Old entry guard regression, two runners × empty/nonempty × normal/optimized Python | 8 expected assertion failures; each old entry consumed output and reached the host work fixture; unset retry at the same argv/path failed with FileExistsError |
| Full integration lifecycle host suite | 16/16 passed under `python -I`; 16/16 passed under `python -I -O` |
| Full debug host suite | 12/12 passed under `python -I`; 12/12 passed under `python -I -O` |
| Fixed entry test cases within those 56 executions | 8/8 rejected with exit 2, no output parent/work marker; integration also created no lock. Unset retries with identical argv/path reached explicit successful host fixtures |
| Direct, unwrapped CLI probes on the old scripts | 8/8 invoked a deliberately exit-19 executable host tool and consumed output; integration also created its lock. Outer CLI exits were 1 |
| Direct, unwrapped CLI probes on the fixed scripts | 8/8 exited 2 before any output parent, integration lock, or host-tool marker |

Raw fixture files are preserved without byte changes inside `raw.tar.gz`; `archive-manifest.json` lists and verifies every regular member by size and SHA256. All following `raw/` paths refer to members of that archive.

The full suite commands are recorded individually under `raw/green/*/invocation.json`. The targeted red commands are under `raw/red/*/invocation.json`; their fixture observations preserve both the initial invocation and exact-argv retry. `raw/direct-cli-probes.py` is the retained direct probe controller and `raw/direct-cli-results.json` summarizes all 16 probes. Its fixture paths are historical absolute paths from the actual run.

This is **host-only** entry-ordering, ownership and lifecycle evidence. The integration positive retry replaces `run_locked` with a host marker; the debug positive retry uses explicitly labeled host substitutes for tool sessions, ELF/GDB acceptance and boot acceptance. These substitutes test retryability only. The separate direct probes invoke real executable fixture tools through the unmodified runner paths, and deliberately stop before Cargo or QEMU. None of the fixtures represents a Rust kernel build, a guest boot, a real GDB breakpoint or a full OSDK 22-case guest pass. Root A01 performs those guest validations separately.

Only the two public runners and their existing test suites changed. Mandatory Rust flags, production OSDK, kernel/core and OSTD implementations are untouched. Generated Python bytecode is excluded from the copied raw fixture tree; retained logs, invocation records and observations are copied without rewriting.
