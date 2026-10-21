# Final main synchronization after the clean-build pair

After the kernel evidence was published as
`7122c9cde0b299ea1e01eb028effaf0e2ad92aa3`, actual main had advanced to
`fb135f845dcbf9026010ebbe060c004fda7f8688`. A01 incorporated it without
conflicts. The tested local merge `063d7a92de77761c2358eb6faf0abb470aba49de`
and published equivalent `e89b5e666326b0b9f8bd8355b052bbc988171bbf` have the
same tree `9ec717f096f099a3aa730db8c5f91c82c52419a7`, message and ordered
parents (7122c9cd, fb135f84). Only the A01 branch was updated normally;
main was not changed by A01. GitHub's initial mergeable=false snapshot was
transient: an independent later GET already showed mergeable=true before
this synchronization, and no conflict repair was needed.

The five inherited changes are `.github/workflows/a10-host.yml`,
`docs/STATUS.md` and three ABI test files. Each test change is exactly the
previous bytes plus one final LF. The A10 workflow adds a guarded bootstrap
path for absent UI source; its UI/Weston route was inspected, not executed.
Status entries about other owners' work are not new A01 kernel test results.

Both `kernel/asterinas` (tree `6b3cab110aa6d30d5b89f99c4389c9c3e01022da`)
and the complete `support/build` subtree before this new documentation
(tree `eddaa642d12766d25f53007a3d5f363251fb7c4a`) are identical to 7122c9cd.
The fixed-source verifier again passed all 118 checks and root README
remains zero bytes. The original clean-pair package and all its checksum
entries are unchanged. No new kernel build or VM is claimed for this sync.

Actual tool session **44972 exited 0**. In a Git-archive snapshot at the exact
merge tree, with an initially absent separate ABI target, the fixed Rust
nightly, offline registry and unchanged seeded lock:

- `cargo fmt --check --manifest-path libs/os-abi/Cargo.toml`: exit 0.
- `cargo test --locked --offline --manifest-path libs/os-abi/Cargo.toml`:
  **25 passed** (3 unit, 5 golden, 7 mutation, 10 negative), zero failed,
  ignored or filtered.
- All seven recorded source inputs and the seeded generated Cargo.lock
  remained unchanged. The lock comes from the prior ABI host run with the
  same Cargo manifest, SHA256
  `95c2616d9e61cbbb848888797f71d434d59744612fbaad5fa558754488cbffbd`.

This adds 25 host test executions to the preceding 171: **196 executions
this phase, plus 12 separately verified golden vectors**. The four real
QEMU guests, same-host/same-path identical ELF result, 362 reported kernel
passes/3 hardware soft skips/359 exercised lower bound, complete retained
serial logs and remaining limitations are unchanged; see the
[kernel build report](../2026-10-16-clean-repeatability/REPORT.md).

The raw host archive retains the actual controller, invocation receipts,
versions, source archive and blobs, command outputs, generated lock,
environment and source-invariance checks. The report's command-reference
filenames were corrected during packaging; execution receipts and original
logs were not altered. `source-diff.json` and the source-publication receipt
independently bind this merge to the remote tree and exact original changes.
The final evidence commit adds only build documentation, lock results and
this small evidence package; it does not alter the tested runtime sources.
Remote CI is read separately after publication and is not inferred from
these local tests.
