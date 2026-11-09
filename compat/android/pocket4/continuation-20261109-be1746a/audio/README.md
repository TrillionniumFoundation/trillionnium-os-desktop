# Blueprint defaults diagnostic

This independent Rust diagnostic checks literal, direct `defaults` references in **every module found in the supplied Blueprint discovery list**, including modules outside the requested build target's dependency closure. It performs no source edits, downloads, Android operations, or Soong builds.

## Why this check exists

The normal Audio r9 build failed at `platform_testing/libraries/desktop-test-lib/tests/mobly/Android.bp`: `DesktopTestLibTestsMobly` referenced the absent `PASIT-defaults` provider. Earlier `recursive_static_unresolved_dependencies = 0` evidence belonged to a bounded, earlier source-closure review. The current source-lock validators verify immutable projects/cones and selected provider guards; they do not recompute a complete dependency graph over every module Soong discovers. That earlier result therefore did not establish that the r9 discovery surface was closed.

The regression uses the exact original r9 consumer and the exact original PASIT provider. The consumer is checked even when a separate Audio target has no edge to it. Adding the original provider resolves this one literal defaults edge. It does not qualify the provider's libraries, generated inputs, variants, or the final build.

## Build and run

From this capsule directory, with a Rust toolchain supporting edition 2024:

```bash
rustc --edition=2024 --test -C codegen-units=1 src/bin/droidloom-blueprint-defaults.rs -o /tmp/droidloom-defaults-tests
/tmp/droidloom-defaults-tests --test-threads=1
rustc --edition=2024 -C codegen-units=1 src/bin/droidloom-blueprint-defaults.rs -o /tmp/droidloom-blueprint-defaults
```

On the existing desktop work line, this is the read-only diagnostic command for the preserved r9 file list:

```bash
/tmp/droidloom-blueprint-defaults \
  /data/pocket4-audio-source316-offload-20261108-8b88-r1/work/aosp-source \
  /data/pocket4-audio-source316-offload-20261108-8b88-r1/work/android-audio-closure-out/.module_paths/Android.bp.list
```

The list must contain one normalized, relative `.bp` path per line. Empty lists, duplicate paths, parent traversal, absolute entries, unreadable files, and symlinks resolving outside the source root are rejected. The caller owns snapshot/locking policy: this tool does not acquire the production build lock or authorize a build. Do not run it against a concurrently changing projection and then treat its output as a stable observation.

Exit codes:

| Code | Meaning |
| --- | --- |
| 0 | No absent literal defaults names or unsupported parser cases were found in the supplied inputs. This is a limited diagnostic result, **not** graph qualification. |
| 1 | Invalid arguments, an invalid discovery list, an input-read failure, or an out-of-root path. No completed graph observation is claimed. |
| 2 | At least one absent literal defaults candidate or unsupported parser case needs review. JSON contains the candidates and unsupported cases. |

All reports deliberately set `graph_qualified` to `false`.

## Scope and limits

The tool strips comments, handles strings and balanced nested properties, indexes literal module names, and checks literal direct `defaults: [...]` properties in all parsed modules. It also checks defaults inherited by other defaults modules. Nonliteral `name`/`defaults` expressions and unsupported lexical forms are recorded explicitly; they are not silently counted as resolved.

It does **not** evaluate Blueprint variables, `select`, namespace visibility, provider type compatibility, architecture/product variants, load hooks, generated modules, or included Blueprint files outside the explicit list. Global symbol presence is only a literal-name observation. Duplicate names are counted, not resolved. Absence is reported as a **candidate** for review, since generated or indirectly included providers can exist outside this model. The ordinary, strict Soong build remains the authority for full graph and artifact qualification.

The retained full-list run examined restored original Blueprint bytes restricted to the r9 discovery list. It did not reconstruct the transient r9 projection. Some original modules are pruned or changed during normal projection, and some providers are generated or included separately. Consequently, the 767 candidate edges from that scan must not be described as 767 confirmed build failures.

## Observed validation

The isolated desktop test used Rust 1.95.0, one logical CPU, and a 2 GiB process limit. All seven tests passed with no ignored tests. They cover the real r9 consumer/provider pair, a module outside the selected target closure, transitive defaults, comments and string literals that must not supply providers, nonliteral expressions, malformed inputs, empty lists, trailing commas, and nested properties. The exact commands and original output are in `test-receipt.json`.

The same unmodified source and two fixtures were then compiled and tested with the CI-pinned **Rust 1.93.0** on ai395, using one independently available logical CPU, a 2 GiB process limit, and a private temporary directory. The same seven tests passed, with no ignored tests and no compiler warnings. `test-receipt-rust193.json` records the actual toolchain version, source hashes, commands, output, and removal of the resulting test executable. The toolchain and Native source tree were not modified.

The preserved discovery list SHA-256 was `ed3590368c9dbe2cf79bb7f0456678b9965383e302166bc3249e71ba97ba7a2b`. The read-only run covered 8,584 files, parsed 38,043 modules, and observed 12,053 literal defaults edges. It recovered the exact r9 PASIT edge. Four files used unsupported string escapes and remain explicitly unparsed. Before/after SHA-256 checks found no changes in any of the 8,584 inputs, the discovery list, or the materialized-source manifest; no source projection was present at the observation boundaries. These checks are bounded observations, not a transactional snapshot proof.

`r9-discovery-summary.json` contains the compact result and the PASIT input binding. `r9-discovery-receipt.json` retains the original execution receipt and all candidate rows. This work started zero full builds, performed zero shared-source writes, and granted no Android runtime or production acceptance.

`retirement-receipt.json` records removal of the two isolated desktop validation executables. It also binds the original source321/source425 closure-plan files: neither contains the PASIT consumer or provider name, and both explicitly retain false build qualification. The source425 plan carries an `unresolved_frontier_pending_strict_soong` field. The new diagnostic adds earlier visibility; it does not turn those preserved unqualified plans into build evidence.

## Fixture provenance

| Fixture | Original location | Original commit | SHA-256 |
| --- | --- | --- | --- |
| `r9-pasit-consumer.bp` | `platform_testing/libraries/desktop-test-lib/tests/mobly/Android.bp` | `6abefd291d50dee240ed2b22572d273175f070da` | `bf1647bf57fab65f5ff2fa7a82b434bb909880f1e258edebf163f8dea48672f0` |
| `r9-pasit-provider.bp` | `tools/test/desktop/mobly/tests/pasit/Android.bp` | `b77d8987bdd1d44645a015042130c8b7cba05b4b` | `01b4a9495646aa94358153832915925f15c3b35752013e9810c7b2bed4d045e2` |

Both are small original AOSP Apache-2.0 source files with their copyright notices retained. The provider Git blob is `5fe6e37402a3d4fbd1df2c9ff65987595a1f0864`. The fixture manifests and execution receipts bind their full bytes; no fake provider or dependency-suppression change was introduced.
