# Required checkout presence: complete source successor

This packet changes only `tools/droidloom-source/src/lib.rs`. It replays the
reviewable, hash-bound `SOURCE.patch` over the complete PR315 runtime producer.
It preserves the other 2,350 files, the original workspace and lockfile, and all
original tests. The existing runtime capsule, overlay and 19 release declarations
retain their original identities and qualification scope.

| Identity | Parent | Successor |
| --- | --- | --- |
| Complete Git tree | `64f57a4de88053fea58cfa5112cd089e45b20be6` | `454a50a52837f80a50d39815da91b0c8cd7a1e4c` |
| Source files | 2,351 | 2,351 |
| Source bytes | 44,223,952 | 44,237,528 |
| Changed source file SHA256 | `9f8794aff44327fbd3395f98c43d670c0930f59933daeb506b8f9e152c9e74b3` | `084a4476d1e5f98222fc1104526919f918f57147b49561a05fd01fc60866ee23` |

## Problem and behavior

`git status --porcelain` can report a clean worktree while required tracked
files are absent behind `skip-worktree` index flags. A materialization claim
therefore needs a physical-presence postcondition in addition to the original
HEAD, origin and cleanliness checks.

The patch leaves the identity precondition unchanged, so normal reconciliation
can still repair missing entries or expand a sparse selection. Verification and
the postcondition after reconciliation or a fresh checkout inspect the pinned
commit's tracked paths. Required regular files and symlinks must physically
exist with their expected entry type. A complete plan also uses normal
`git sparse-checkout disable` to restore stale skip flags even when the config
already says sparse checkout is disabled.

Cone selection includes root files and files at every selected ancestor.
A declared single-file cone includes its sibling files, matching Git's actual
`--cone --skip-checks` behavior. A dangling tracked symlink remains valid, and
an unexpanded gitlink does not assert that submodule contents were checked out.
This check proves required entry presence; it does not replace the complete
vendor source content bookend.

## Reproduction and source integrity

The reviewed workflow must pin this packet's `FILES.sha256` outside this
directory. `CI-INTEGRATION.md` gives the exact steps for the additional job.
The original runtime capsule verifier first reconstructs its complete 2,351-file
parent. This packet then verifies the original capsule's fixed inventory,
unchanged verifier, and all source rows; checks every parent file, mode and hash;
applies exact line-numbered hunks with no fuzz; and checks the complete successor.
Both old and new Git trees are derived from complete source inventories.

`PARENT-SOURCE-ROWS.json` is the unchanged 699,973-byte original tested source
inventory, SHA256 `a0cbf47867c45a388d7ccba04d4bce79bc8c20a0e15bcee5df643011076e8199`.
It must equal the rows independently reconstructed by the original capsule.
There is no replacement archive or cumulative overlay to update.

For an ordinary isolated local source audit, `--parent-packet` may be omitted
when only the full materialized parent is available. Every one of the same
2,351 path/mode/content rows and the fixed complete tree is still required.
Such a report explicitly records `parent_packet_verified: false`; it makes no
claim that the capsule archive was read on that machine. GitHub CI must supply
the original parent packet and obtains the complete archive verification chain.

## Validation and scope

Six new real-Git Rust cases exercise missing single-file-cone siblings, stale
full-plan skip flags with false sparse config, recoverable sparse expansion,
root and ancestor files, dangling symlinks and gitlinks, and fresh checkout.
The affected crate's complete expected catalog is 89 library tests, 2 CLI
tests and 9 example tests: 100 cases with no failures, ignores or filters.
The original 94 tests remain present.

The prior isolated affected-crate execution completed `cargo check --all-targets`
and all 100 actual Rust tests with Rust 1.93.0, original pinned dependency
versions and no network. That run used a narrowed workspace membership and
retained its exact evidence separately. `run_ci.py` here instead requires the
complete successor workspace and unmodified lockfile. It records real Cargo
terminals, hashes all three compiled ELF harnesses, matches every catalog name,
executes those exact harnesses and verifies the complete source again.
Historical executions do not count as a fresh run of this packet.

Formatting is **not qualified**. Both the candidate and the unchanged original
crate returned exit 1 from `cargo fmt --check`; the original has 232 existing
format-diff blocks. Those failures remain explicit in the original evidence.
This narrow fix does not reformat unrelated modules, suppress an existing gate,
or report that formatting passed. The new runner does not rerun formatting.

This packet builds and tests only the affected source tool. It claims zero
new release binaries, zero Android builds or starts, no runtime qualification,
and `production_ready: false`. Existing 19-binary validation applies only to
its original tree. The ongoing source restoration continues to use its already
pinned original tool; this successor is not installed or substituted there.
