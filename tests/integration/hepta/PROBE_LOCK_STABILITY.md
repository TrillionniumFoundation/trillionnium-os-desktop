# External original-library probe lock stability

The 2026-10-17 fix changes the generated external test manifest and its lock
validation. It does not edit `hepta-private-ci`, change the original Agentd
build, replace dependencies, or relax `--locked`. The original eight CLI
process assertions and the optional persistent Session assertions retain their
existing qualification requirements.

## Actual failure and cause

[ARM run 39073273434](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39073273434)
and the local staged consumer attempt `r6-original-runtime/build-01` both built
the observer and resolved the external probe, then failed its `--locked` build
with Cargo exit 101. Neither attempt compiled the new probe module or ran its
Session acceptance. The local original Agentd build had separately passed;
its source remained the clean fixed original
`f8c9419df6ddeb36ff8b522a50219981fb8d9345`.

The original manifest provides the same tungstenite git/revision target under
two patch origins: `crates-io` and
`ssh://git@github.com/openai-oss-forks/tungstenite-rs.git`. That package is unused
by this external probe. Cargo wrote two identical `[[patch.unused]]` records.
An independent diagnostic reproduced a successful `--locked` metadata command,
then an unlocked metadata command that moved one unused record from the end
of the list to its beginning, then a failed `--locked` metadata command. All
733 package entries stayed identical.

Cargo 1.95's pinned sources explain this behavior:
[Resolve equality](https://github.com/rust-lang/cargo/blob/rust-1.95.0/src/cargo/core/resolver/resolve.rs)
compares the `unused_patches` vector, and
[lock encoding](https://github.com/rust-lang/cargo/blob/rust-1.95.0/src/cargo/core/resolver/encode.rs)
serializes that vector in its existing order. The
[lock writer](https://github.com/rust-lang/cargo/blob/rust-1.95.0/src/cargo/ops/lockfile.rs)
rejects a changed resolution when updates are disabled. The observed ordering
change therefore caused a real locked-build rejection without dependency drift.

| Observed lock | SHA256 | Package count |
| --- | --- | --- |
| Original external manifest, first unused ordering | `9d1de5fab85aa6400a1d178e1791b3b01453b1b2b37e2b986bbe97cad55ceec1` | 733 |
| Same manifest, moved unused record | `a69c778be383103bf49dac0148964ca871e78527abb6cff5eeff7ea2549c7dc1` | 733 |
| External manifest with the one guarded omission | `72cb7346158f4c3514922cc7b9020f9b9d290aec78e047264a738d52afe6ed68` | 733 |

## Narrow manifest rule and fail-closed checks

`prepare_runner` omits only the named SSH origin, and only when its complete
mapping is exactly the tungstenite target retained under `crates-io`, with a
fixed git revision. Additional entries, a changed target or a missing origin
cause rejection. Every other original patch mapping and rebased path remains
unchanged. The returned omission origin, target and reason are recorded in the
gate report.

After resolution, `verify_runner_lock` still requires every shared package's
name, version, source and checksum to occur in the original seed lock. It also
rejects an active omitted target, any package from the omitted SSH origin, or
an unused list that does not contain exactly one copy of the retained fixed
target. This exception is specific to this external probe. It must not be
applied to the full original workspace, where the fork is an active package.

Two consecutive `--locked` metadata commands must then succeed without changing
the resolved lock bytes or the validation result. Compilation continues with
`--locked`, and the lock bytes are checked again afterward. The gate records
the stable lock hash and the count of successful locked metadata checks.

## Completed verification and its limit

The source change passed 17 focused Python tests, including actual owned-child
cleanup tests, the existing Session receipt rejection tests, and new negative
cases for the patch omission. The latter are deliberately minimal lock
fixtures; they do not qualify Cargo compilation or Agentd runtime.

The separate actual Cargo diagnostic used the clean original source, Rust
1.95.0 and its populated offline cache. Resolution followed by two consecutive
`--locked` metadata commands passed with the stable hash above. All 733 package
entries were identical to the failed manifest's resolved lock. Cargo's actual
`resolve` graph was also identical after substituting only the external probe
root path; its canonical JSON SHA256 was
`1dd8dc978f55fbdd2b8c90551eaadcfe6a5b3709a82fc108de7cdc5d355e04bd`.
The only unused-patch membership change was six records becoming five.

The failed build and both diagnostics remain separately preserved as
`r6-original-runtime/build-01`, `lock-diagnostic-01` and `lock-diagnostic-02`,
with logs, manifest/lock inputs, hashes and receipts. The actual Rust probe
build, its two Rust tests and persistent Session runtime are separate checks;
the metadata result alone grants none of those qualifications.
