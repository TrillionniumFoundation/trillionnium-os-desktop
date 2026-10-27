# Original Cargo source pairing: Hepta 4223fc7

The original Rust/Cargo 1.96.0 generated the five ordinary product locks and
the separate prepared UI lock against Hepta
`4223fc77944e9beb5651df063158b22ae1a4f701`, tree
`7c19c9903d4e82baf3a61111214ff3fe46605cef`. The independent Desktop preparation
started at `d343c35da641f86a3fa0ff6c4293d4948bbe0b2e`; the original source updater
changed three manifests and two profiles before Cargo ran. The final Desktop
commit/tree belongs to its later build receipt, not this preparation record.

The actual commands, outputs' digests, six before/after lock hashes and five
source-file hashes are in [generation.json](generation.json). Ordinary roots
used online `cargo update --workspace`, followed by locked/offline metadata.
Cargo alone generated the sixth lock in an independent Desktop worktree with
the original helper's complete SDK override. No lock source string was edited.
Three locks retain their original bytes because those roots have no Hepta Git
dependency; all six were actually resolved and checked.

[dependency-summary.json](dependency-summary.json) records the original full
dependency result, six checked roots, 219 original owner manifests and the
digest/location of the complete 1.4 MiB graph output. The ordinary UI and
prepared UI locks each contain 157 original Hepta packages; the standalone
Session lock contains 152. The original reference lock digest is
`5bd3faaf16a79eb12bcdcb89054e93da388bbd858f36439b9d6bcfb72f77d522`.

[resolved-source-verification.json](resolved-source-verification.json) adds the
original builder's actual Cargo Git-cache checks and prepared native graph
validation. Both helpers and runtime select the same clean Hepta source.
[sdk-verification.json](sdk-verification.json) retains the full original SDK
verification: upstream `337566c8b25d47f7e4fff6a202157b65bf183330`, all 102 SDK
packages, and unchanged prepared tree
`6b422b3120f5f9b5c7ada579b55f647d51bd7fcf`.

The incoming archive and every source file were SHA256-checked after transfer.
The paired Desktop callsite now asks original Fleet to validate the original
spawn through its complete lifecycle history. A later Starting transition,
missing history or invalid transition is not accepted as the old spawn.

This record qualifies source selection and actual Cargo resolution only.
It does not compile the final Desktop callsite, install a release, exercise a
physical login or Notes effect, or establish resident/cross-boot recovery.
The final package must run its existing exact-source build and runtime gates;
942/de0 and other older executions remain separate evidence.
