# Derived preedit desktop release

`release_preedit.py` is the automated entry point for the explicit Linux X11
preedit package. It keeps the baseline `ui/Cargo.lock` on its existing Git SDK
and creates a separate, clean source commit containing the Cargo-generated
prepared-SDK lock. Ordinary `cargo --locked` commands in the original checkout
continue to use their original committed dependencies without a local SDK.

The default [release workflow](../../.github/workflows/hepta-native-release.yml)
runs on relevant pull requests and main updates. It builds and tests the
explicit derived package; it does not publish a branch, create a GitHub Release,
install a desktop, start an original production owner or connect to a user's
display. The existing baseline compile workflow remains a separate check.

## Exact source derivation

The caller supplies the reviewed full Desktop commit and tree. The executing
helper, original runtime and SDK preparer must all use the single Hepta
commit/tree frozen in `linux-preedit-profile.json`. Its existing source-byte,
five-lock, helper-hash and original-history-owner checks remain mandatory.
Missing original ancestry requires fetching that history, not weakening a
source check.

The materializer performs these steps:

1. Check clean original Desktop/Hepta sources and create a detached Desktop
   worktree at the exact base. This works with a complete HEAD checkout in a
   partial/promisor repository; it does not clone missing historical blobs.
2. Resolve the exact preedit feature with the original Git SDK and `--locked`.
   Verify the actual Cargo source caches. The canonical Hepta helper prepares
   a new SDK directory and all 102 crate overrides outside the source trees.
3. Let Cargo generate the candidate path lock. Compare the entire old/new lock
   graph, including package multiplicities, versions, checksums, dependency
   edges and every non-SDK source. Only the 102 reviewed SDK origins may move
   from their fixed Git source to verified local paths. No lock is hand-edited.
4. Re-verify the complete SDK source, graph and override file. Require the
   candidate diff to contain only `ui/Cargo.lock`, with no untracked source.
5. Create a deterministic local child commit with exactly the base as its
   parent. The Git identity uses a materializer identity and the base timestamp;
   it does not impersonate a maintainer or move the original branch.
6. Retain the derived commit/tree, lock and binary diff, a Git bundle, a complete
   tracked-source archive, original/prepared metadata, exact override file and
   the SDK source-verification receipt.

The bundle explicitly requires the recorded base commit. After obtaining that
exact base, `git bundle verify derived-source.bundle` and fetching its `HEAD`
reconstruct the derived Git commit. `derived-source.tar.gz` additionally retains
all tracked bytes and file modes at the derived tree without requiring the
repository's historical blobs. The SDK remains reconstructible from its fixed
upstream revision and canonical Hepta patch/helper. Its receipt records the
verified tree. Absolute SDK paths and metadata must be freshly generated when
moving to another work directory; copying a path override to another machine
does not establish a verified SDK.

`published: false` in the derived identity is intentional. A successful local
derived source is a reproducible build input and is not a claim that this new
commit exists on main or any remote branch.

## Build and qualify one package

Use clean source checkouts, installed Rust 1.96.0 with Clippy/rustfmt, and the
native build/runtime prerequisites listed in the release workflow. The Hepta
checkout must include enough history for the original ancestry verifier. Both
work/output directories below must be new, canonical, separate absolute paths
with existing parents, outside the original sources.

```sh
python3 -I -B support/ui/release_preedit.py \
  --desktop-commit REVIEWED_FULL_DESKTOP_COMMIT \
  --desktop-tree REVIEWED_FULL_DESKTOP_TREE \
  --hepta-repo /absolute/clean-original-hepta \
  --work-dir /absolute/new-preedit-source-work \
  --output /absolute/new-preedit-release-evidence \
  --jobs 2 --build-profile release
```

`--materialize-only` stops after source derivation. Its receipt says
`status: materialized`, leaves `window_qualified` false and creates no qualified
package. The default continues through the original `build_text_product.py`
and the existing `tests/ui/native-makepad/qualify.py`; there is no alternate
renderer, owner, Notes database or relaxed input implementation.

The builder uses the actual selected Cargo, Rustc, Rustdoc, cargo-clippy and
clippy-driver executables, verifies their versions and hashes, and checks the
driver's embedded compiler. Clippy and fmt execute their selected adjacent
programs directly. A different custom-subcommand proxy in `CARGO_HOME/bin`
cannot silently take over a qualified build. The original full workspace
tests, standalone host/observer/support tests, 4 focus and 35 TextInput SDK
regressions, strict native Clippy, resource licensing and package checks all
remain part of the builder.

The final window gate runs the actual stripped **packaged** ELF and all 61
packaged resources on an owned Xvfb display, private D-Bus, real IBus libpinyin
and original AT-SPI interfaces. The materializer additionally requires the
exact named 7 AT-SPI, 5 atomic EditableText and 5 IBus checks in their original
receipts, same derived source/package identity and successful owned-process
cleanup. A boolean `passed`, a build-only result, a raw Cargo ELF or fewer
checks cannot produce `status: qualified`.

For an offline run, add:

```sh
  --offline \
  --asset-cache /absolute/previous-verified-product/resources \
  --liberation-source /absolute/previous-verified-product/resources/sources/liberation-fonts-1.04.93.devel.src.tar.gz
```

The asset cache is checked against the original inventory. Liberation's source
archive is a separate explicit input. Missing resources fail the offline build;
the materializer does not silently switch it to an online build. Cargo caches
must already contain all required original graphs for an offline run.

## Receipts and result boundaries

`release-receipt.json` binds the base and derived sources, complete lock
transition, source closure, tool identities, command logs, package SHA256,
packaged Shell SHA256 and exact build/window receipt hashes. `stages.junit.xml`
reports orchestration stages; it is not presented as a count of Rust tests.
The original build logs and 17 named runtime checks remain separate. Failed
stages and failed source postchecks retain failed receipts and return nonzero.
Neither a partial run nor `--materialize-only` can write a qualified result.

The source worktree, SDK and compile target remain task-owned intermediates.
The CI artifact uploads logs, receipts, source closure and the distribution
archive, excluding build targets and live/private display credentials. No
global Cargo configuration, SDK source cache, source-clean exception or original
baseline lock is changed.

Every result retains `production_authority_qualified: false` and
`physical_device_qualified: false`. The input gate does not prove authenticated
Root operations, arbitrary streaming interruption, physical keyboard/display,
Wayland IME, Orca human use, font pixels or candidate-window placement. Those
retain their existing separate acceptance gates.

### Preserved comparison from 2026-10-26

The original Git-SDK package at Desktop
`f36664310b7bb0074a16846f2c1c600e90844f05` with Hepta
`760363e06c5f4a115de039ffa7bd7e7767bd1fd9` passed its 7 supported AT-SPI and
5 atomic EditableText checks, but failed the real IBus composition guard:
the editor stayed empty and New Draft remained enabled during attempted
preedit. That baseline failure remains a failure; its acceptance condition is
not changed by this release helper.

The separately frozen prepared-profile evaluation at Desktop
`9ae442075f5aaec4c2e913e30305e2c1188f76eb` and the same Hepta source passed
all 17 packaged-window checks. Its exact packaged Shell SHA256 was
`049eeada5efe1d3f479ed81e2a68465e1a7e2ffb0185fb0557795d478c85bd49`;
the original qualification receipt SHA256 was
`7b7e80013953dc21a6c0e0e240d8276c0aac5c6b4d9453d76fe95ae303449762`.
This measured result justifies using the explicit prepared profile. It does
not qualify a later Desktop runtime commit: the default workflow must rebuild
and re-run the same gates on that new base's derived package.

## Guard regression tests

```sh
python3 -I -B support/ui/test_preedit_release.py
python3 -I -B -O support/ui/test_preedit_release.py
```

These tests reject lock version/checksum/edge/source changes, partial SDK
coverage, altered tracked/untracked source, attached branches, duplicate or
missing window checks, cleanup failures and substituted package identities.
A real temporary Git worktree/bundle round trip verifies that the baseline
branch/lock remain unchanged and the same input produces the same derived
commit. They validate the release boundary; they do not simulate a successful
real input or production run.
