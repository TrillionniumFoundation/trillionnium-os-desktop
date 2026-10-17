# A02 review blocker closure — 2026-10-17

Host: `343e40cfefc1`. This is the current project cloud execution node; the
previous report's node `29609d47ba8e` and tool paths are historical. The current
checkout was restored independently on branch `agents/A02-hos2-wire`, parent
`606244b6109b1060b4916baa76e3fdd14dcc5240`. Actual Git fetch found newer main
`acd9ee30d51c405b32a36ff02ce25a9272b65834`, which is incorporated as a merge
parent. Its A00 workflow and A03 owner files are imported byte-for-byte from
main. The tested A02 executable inputs remained identical after that merge.

## Closed review findings

| Finding | Reproduction | Fix and verification |
| --- | --- | --- |
| [Compiler wrappers bypass direct identity probes](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/76#discussion_r4296957185) | With the real pinned compiler, the old runner reported all three baseline identities matching, yet Cargo invoked an injected wrapper three times and compilation failed | Every suite binds RUSTC explicitly, overrides both wrappers with empty strings (including Cargo configuration), and removes CARGO_BUILD compiler overrides. Standalone and unified real compiler runs pass with the same poisoned environment/configuration and zero wrapper calls |
| [Whole mutation batch limited to one command timeout](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/76#discussion_r4296957198) | Deterministic subprocess-boundary test models a 75-second batch: the old 60-second total budget times out even though individual commands fit | Independent --mutation-timeout defaults to 900 seconds; nested Cargo commands retain --timeout=60. Reports record both budgets. Tests reject nonfinite/invalid budgets and still reject a timed-out batch even if a success report exists |

The timeout regression uses virtual process timing, not an assertion that this
cloud run actually took 75 seconds. Actual standalone runtime was 15.94 seconds;
the complete unified acceptance took 23.61 seconds. The unified compiled batch
took 15.40 seconds and recorded a 900-second outer budget versus 60 seconds per
nested command. No timeout is counted as a mutation kill.

## Actual fixed-nightly execution

Existing tools were read from
`/workspace/scratch/629ae4947f18/toolchains/{cargo,rustup}`. No tools or
dependencies were installed and no other agent's source checkout was changed.
The selected version is the unchanged upstream-lock pin `nightly-2026-07-21`:
rustc `1.99.0-nightly (87e5904f5 2026-07-20)`, Cargo
`1.99.0-nightly (3efb1f477 2026-07-17)`.

Both actual runs inherited deliberately poisoned RUSTC_WRAPPER,
RUSTC_WORKSPACE_WRAPPER and three CARGO_BUILD compiler variables. A task-owned
CARGO_HOME/config.toml also set build.rustc and both compiler wrappers to a
marker-producing executable that exits 97. The old runner called it; both fixed
runs did not. Exact argv, cwd, configuration, trap script, versions and hashes
are retained in the JSON evidence listed below.

The normal fixed-toolchain reproduction command, without the adversarial
configuration, is:

```sh
CARGO_HOME=/workspace/scratch/629ae4947f18/toolchains/cargo \
RUSTUP_HOME=/workspace/scratch/629ae4947f18/toolchains/rustup \
python3 -B tests/abi/run_acceptance.py \
  --rustup /workspace/scratch/629ae4947f18/toolchains/cargo/bin/rustup \
  --timeout 60 --mutation-timeout 900 \
  --output-dir /tmp/a02-review-reproduce-new-directory
```

| Check | Actual result |
| --- | --- |
| Unified acceptance | 13/13, success=true, no unexecuted checks |
| Rust codec | 69/69 unit/integration + 1/1 doctest; zero failed, ignored or filtered |
| Python ABI | 52/52 normal and 52/52 under -O; zero errors/failures/skips |
| Independent Python canonical mutations | 9/9 (included in the 52, not added again) |
| Independent golden generators | 12/12 original + 24/24 edge + 1/1 transport |
| fmt, strict all-target Clippy, bare-target no_std | All passed |
| Real compiled mutation baselines | 8/8 + 12/12 + 7/7 in both executions |
| Real compiled mutants | 12/12 killed in both executions; all compile and run their complete designated suite |
| Expected mutant assertions | 17 expected failures per execution; no production failure |
| Wrapper regressions | Fixed runner 10/10 normal and -O; old runner fails both new marker tests in each mode, with zero test errors |
| Source hashes and root README | All tested inputs unchanged; README remains 0 bytes |

The old-runner negative control's three compilation failures are intentional,
retained before evidence. It reports success=false and zero mutant kills.
The old-runner marker regression's two assertion failures per mode are also
expected. No tests were skipped or unexplained failures hidden. Six new Python
regressions account for the increase from 46 to 52.

## Evidence, CI and consumer handoff

- `results/cloud-review-before-2026-10-17.json`: actual old-runner poisoned-wrapper failure.
- `results/cloud-review-mutations-2026-10-17.json`: complete standalone real compiler mutation results.
- `results/cloud-review-acceptance-2026-10-17.json`: complete 13-check report and nested mutation output.
- `results/cloud-review-regressions-2026-10-17.json`: normal/-O regression commands and old-runner assertion failures.
- `results/cloud-review-execution-2026-10-17.json`: host, parent SHAs, invocation metadata, configuration and report hashes.

The predecessor HEAD's G0 queue blocker is now closed: [run 38932550749](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/38932550749),
job `117079887722`, completed successfully. It used stable rustc 1.99.0, ran
69+1 Rust and 46 Python ABI tests, fmt/Clippy and A05 Linux host smoke. It did
not run the full fixed-nightly entry, compiled mutants or bare target.
The A00 workflow added by PR #83 is now on main; its earlier success was
explicitly bootstrap-only, not fixed-nightly acceptance. New-HEAD CI must be
reported separately when it actually completes; predecessor success is not
relabeled as a test of this commit.

No production Rust codec, golden bytes, dependencies or shared ABI changed in
this increment. Production source SHA256 remains
`b7cc442a3bd0b5fcf5dddbd8f3557e036daf6912d0ca54e38acaee9b2f235725`.
The original single-CPU samples still satisfy 35ms <= 50ms and 33ms <= 40ms;
the lowered-cap case still has 35ms > 20ms.

A03/A05 continue using Request/Response, Transport snapshot/preflight,
decode_response_for, decode_response_prefix_for, Response::validate_for and
install_budget_request_id/install_budget_sequence. matches_request only checks
opcode and ID; semantic correlation requires validate_for or the correlated
decode helpers. These public interfaces remain unchanged.

No unresolved A02 Wire-field contradiction was found. Public ioctl assignment
remains an A00/A05 decision. Real kernel copyin/copyout, CapSpace permissions,
A06 scheduler enforcement and original A07 durable Hepta owner recovery remain
their owners' integration work; this host closure does not mark G1/G2 complete.
Final integration into main remains A00's responsibility. HOS2 remains an
experimental ABI, major=2/minor=0.
