# Hepta workspace dependency security debt: technical diagnosis

**Evidence date:** 19 October 2026 UTC. **Status:** diagnosis complete; dependency remediation has not been implemented. The current owner pull request remains subject to its ordinary required checks.

## 1. Decision and evidence boundary

The real `cargo-deny / cargo-deny` job failed on owner head `d32e795f0d24df89fc57745f6fae70fbd0642eba`. The preceding timeout configuration change did not modify dependency manifests, Cargo.lock, or the deny policy. Under the existing scope rules, its workflow edit selected `full_repo=true`, so the complete repository policy ran. This exposes security debt in the current locked dependency set; it is not evidence that the two timeout lines introduced those dependencies. The baseline and new-head source comparison is preserved in [local-source-comparison.json](../local-source-comparison.json).

The original remote failure is [job 117846024659 in run 39185139893](https://github.com/TrillionniumFoundation/hepta-private-ci/actions/runs/39185139893/job/117846024659), started at 01:24:19 UTC and completed with failure at 01:25:43 UTC. Its failing step was `Run cargo-deny`, which started at 01:24:42 UTC. Both job-log requests made by this reviewer returned `Transport closed`; a direct logs URL was rejected by the connector URL allowlist. The parent reviewer separately reported another unsuccessful log request. Those failures are retained in the API observation files. **The original remote log was not recovered.** Neither the exact set of errors in that job nor the cause of the transport failure is established here.

The authorized follow-up was a new, isolated local diagnosis, using the action's actual cargo-deny version and equivalent source tree. It independently produced **13 advisory errors and 85 warnings: advisories FAILED; bans, licenses, and sources all passed**. This report does not present that result as a reconstruction of the missing remote log. It also does not transfer the old `2be5fc05` timeout result to this new head, or substitute `rust-ci / CI results (required)` for the distinct repository check named `CI required`.

No dependency, lockfile, policy exception, product source, CI setting, or remote head was changed by this diagnosis. No product build, CI rerun, cancellation, manual merge, or credential-store access was performed. The next implementation should be a separate security migration that preserves the existing protection strength.

## 2. Reproducible identities and executed commands

The remote head's tree is `a3e718280a7e17b8c4a226a0232bf18c23fd3586`. The isolated local commit `1b0fedb8c2b510106848f6feaf530c9b3698399d` has exactly that tree. It remained clean before and after each diagnostic command.

| Input | Fixed identity |
|---|---|
| Cargo.lock SHA-256 | `8354b4cbdf14389db7aa5508e2ed5b524fc2d4c4ea0ecb475955c933f8bea389` |
| deny.toml SHA-256 | `3713c011667dcbeda9edf1b2644a813f2b5253ebb7b2f3e98ea60aab69407352` |
| Action | `EmbarkStudios/cargo-deny-action@82eb9f621fbc699dd0918f3ea06864c14cc84246` |
| Action-selected deny version | `cargo-deny 0.19.0` |
| Rust toolchain used locally | `1.95.0-x86_64-unknown-linux-gnu`, rustc commit `59807616e1fa2540724bfbac14d7976d7e4a3860` |
| RustSec database commit | `999ec89d5d3f10f20be14750ec8c2d8b44e0ac9b` |
| RustSec database tree | `7fab15e592b35835decefbb43f6578c70565e4d9` |

Cargo.lock and deny.toml are byte-identical to the `f8c9419df6ddeb36ff8b522a50219981fb8d9345` baseline. All Cargo manifests also remained unchanged across the pull request. Exact source copies, Git blob IDs and hashes are in [preservation.json](preservation.json); additional upstream and patch inputs are bound by [preservation-supplement.json](preservation-supplement.json).

The official, prebuilt cargo-deny 0.19.0 musl archive was verified against its official checksum and release asset digest. Its archive SHA-256 is `0e8c2aa59128612c90d9e09c02204e912f29a5b8d9a64671b94608cbe09e064f`; the extracted executable SHA-256 is `06f9d1a0ba92b201bff1215b6dc24e669b212c151ecd52cae5d38aab73931d3c`. Rustup 1.28.2 was likewise obtained from the official distribution with checksum verification and installed into isolated tool roots. Version outputs, download URLs, exact environment overrides and timestamps are in [tools-installation.json](tools-installation.json).

The fixed action uses `--all-features`, command `check`, log level `warn`, and the workflow supplies Rust 1.95.0. The local commands were:

```text
rustup run 1.95.0 cargo metadata --format-version 1 --locked --all-features --manifest-path ./codex-rs/Cargo.toml
cargo-deny --log-level warn --manifest-path ./codex-rs/Cargo.toml --all-features --locked check
```

The metadata command returned 0 at 01:36:39.498 UTC and resolved 1,517 packages. The deny command returned 1 at 01:36:52.359 UTC. Exact arguments, source snapshots, output hashes and elapsed times are in [execution.json](execution.json). The added `--locked` enforced source stability. Local GNU Linux, a new execution time, and freshly fetched registry/advisory data differ from the action's pinned Alpine container. No optional Git credentials or SSH inputs were supplied. These differences prevent claiming an exact remote-environment reproduction.

## 3. All 13 locally observed advisory errors

The following are **eight vulnerability records and five unmaintained records affecting eight distinct locked packages**. An unmaintained classification is not, by itself, a demonstrated exploitable vulnerability. Complete fixed advisory text, dates, hashes, dependency parents and workspace entry points are preserved in [error-summary.json](error-summary.json), [dependency-scope.json](dependency-scope.json), and `official-advisories/`.

| Locked package | RustSec advisory | Classification | Official patched range or migration | Principal workspace entry |
|---|---|---|---|---|
| anymap2 0.13.0 | [2026-0319](https://rustsec.org/advisories/RUSTSEC-2026-0319.html) | Unmaintained | No patched release; replacement includes anymap3 | matrix-sdk → hepta-matrix-sdk / hepta-matrixd |
| matrix-sdk-crypto 0.18.0 | [2026-0318](https://rustsec.org/advisories/RUSTSEC-2026-0318.html) | Vulnerability | >=0.19.0 | Matrix base, storage and service modules |
| rustls 0.23.45 | [2026-0346](https://rustsec.org/advisories/RUSTSEC-2026-0346.html) | Vulnerability | >=0.23.46 | HTTP, WebSocket, proxy, SQLx, Matrix |
| rustls 0.23.45 | [2026-0347](https://rustsec.org/advisories/RUSTSEC-2026-0347.html) | Vulnerability | >=0.23.46 | Same shared TLS dependency |
| rustls 0.23.45 | [2026-0348](https://rustsec.org/advisories/RUSTSEC-2026-0348.html) | Vulnerability | >=0.23.46; brotli prerequisite applies | Same dependency; selected Agentd graph lacks brotli |
| rustls 0.23.45 | [2026-0349](https://rustsec.org/advisories/RUSTSEC-2026-0349.html) | Vulnerability | >=0.23.46; session/application prerequisites apply | Same shared TLS dependency |
| unsafe-libyaml 0.2.11 | [2024-0449](https://rustsec.org/advisories/RUSTSEC-2024-0449.html) | Unmaintained | No patched release; parser migration required | serde_yaml → plugins, skills, agent migration, skills extension |
| zbus_names 3.0.0 | [2026-0371](https://rustsec.org/advisories/RUSTSEC-2026-0371.html) | Unmaintained | Standalone crate retired; functionality moves to zbus 6 | keyring → secret-service → zbus |
| zip 2.4.2 | [2026-0367](https://rustsec.org/advisories/RUSTSEC-2026-0367.html) | Vulnerability | >=9.0.0 | core-plugins curated archive processing |
| zip 2.4.2 | [2026-0368](https://rustsec.org/advisories/RUSTSEC-2026-0368.html) | Vulnerability | >=9.0.0 | Same archive processing |
| zip 2.4.2 | [2026-0369](https://rustsec.org/advisories/RUSTSEC-2026-0369.html) | Vulnerability | >=9.0.0 | Same archive processing |
| zvariant 4.2.0 | [2026-0370](https://rustsec.org/advisories/RUSTSEC-2026-0370.html) | Unmaintained | Standalone crate retired; functionality moves to zbus 6 | keyring → secret-service → zbus |
| zvariant_derive 4.2.0 | [2026-0372](https://rustsec.org/advisories/RUSTSEC-2026-0372.html) | Unmaintained | Standalone crate retired; functionality moves to zbus 6 | zvariant procedural macro dependency |

Each official RustSec page was read in addition to the fixed database text. The database TOML `date` is a reported date, not necessarily the database publication date. For example, unsafe-libyaml reports 25 March 2024 while the official page shows **Issued 12 October 2026**. The ZIP and zbus-family pages show **Issued 17 October 2026**. The original failing remote job's database SHA was not obtained; these dates do not establish that job's precise rejection set or the first failing CI run. The saved webpage response explicitly distinguishes its later save time from a retrieval time that was not individually captured.

## 4. Agentd reachability on two architectures

Two additional locked, offline graph queries returned 0 without compilation or source changes:

```text
cargo tree --locked --offline --manifest-path ./codex-rs/Cargo.toml \
  -p codex-hepta-agentd --no-default-features --edges normal \
  --target <x86_64-unknown-linux-gnu or aarch64-unknown-linux-gnu> \
  --prefix depth --format '{p} features=[{f}]' --charset ascii
```

Both root package lines show `features=[]`. Raw output and execution receipts are in [agentd-graph-execution.json](agentd-graph-execution.json); classifications, observed paths and features are in [agentd-reachability.json](agentd-reachability.json).

| Package group | Both selected Linux normal dependency graphs | Scope of the conclusion |
|---|---|---|
| anymap2, matrix-sdk-crypto | Absent | Still present in the complete workspace's Matrix graph |
| rustls | Present | Observed features lack brotli, so the 0348 feature prerequisite is not met in these configurations; other API/session prerequisites were not established |
| zip, unsafe-libyaml, zbus_names, zvariant | Present | Static dependency reachability only; no proof that a specific runtime scenario calls the affected API |
| zvariant_derive | Present as a proc-macro | A compiler-time procedural macro dependency is not proof of product runtime linkage or exploitation |

Observed paths include Agentd → app-server → axum → tokio-tungstenite → rustls, and Agentd → app-server → agent-extension → core → core-plugins → zip. They are paths printed by Cargo, not a claim that each is the globally shortest possible route. Agentd's `--no-default-features` removes its own default write flag; it does not remove its normal Codex application dependencies.

This diagnosis did not inspect the earlier five ELF files, perform dynamic call tracing, or rerun the fifteen Objective History scenarios. A workspace-wide all-features policy failure is not evidence that those scenarios are exploitable. Conversely, absence from the selected normal graph is not proof of absence from the entire workspace, every feature combination, or a deployed environment.

## 5. Minimum credible remediation and migration boundaries

There is no established, lockfile-only combination that closes all thirteen errors. The following candidates are grounded in the preserved source and official registry data; none has been implemented, resolved into a new lock, built, or accepted by post-upgrade tests.

### rustls: first candidate for a narrow patch upgrade

The workspace constraint is `0.23`. Official registry data contains non-yanked 0.23.46 with MSRV 1.71. A targeted patch update is the smallest candidate for the four rustls records. Preserve crypto providers, certificate validation and TLS configuration, inspect the resulting lock changes, and confirm the new deny output. Meaningful revalidation includes principal HTTP, WebSocket and proxy callers, relevant TLS/session failures, and Agentd qualification that depends on those paths. Version availability and semver compatibility are not test results.

### ZIP: API adaptation and extraction-boundary tests

The current [startup_sync.rs](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/d32e795f0d24df89fc57745f6fae70fbd0642eba/codex-rs/core-plugins/src/startup_sync.rs) implements its own extraction with `ZipArchive::new`, `by_index`, `enclosed_name`, `File::create`, and `io::copy`, then passes `entry.unix_mode()` to `Permissions::from_mode` without a separate application mask. It does **not** directly call `ZipArchive::extract`. The three advisory exploit mechanisms cannot simply be assigned to this custom function without examining its behavior.

The checksum-verified zip 9.0.5 release changes `ZipFile` to `ZipFile<'a, R: Read + ?Sized>`, requiring adaptation of the current `ZipFile<'_>` helper signature. The release source also shows `unix_mode()` reaching `get_unix_mode` and **`clear_specials_bits`**, which removes SUID, SGID and sticky bits. This corrects an earlier concern: the existing application call would not necessarily keep returning those bits after upgrading. An explicit application permission mask remains an implementation option, but should not be justified by pretending the inspected library fails to mask them.

Production inputs are the curated OpenAI GitHub zipball and backup export. Extraction writes a fresh staging directory, checks the marketplace manifest and activates after validation. Attacker control of production archive bytes and privileged extraction were not established. Required migration tests should exercise special permissions, path escape, symlink/existing-path behavior, malformed input, staging cleanup and failure-before-activation, while preserving legitimate executable script permissions. The patched advisory threshold is 9.0.0; the inspected 9.0.5 candidate requires Rust 1.88.

### YAML: replace the unmaintained implementation while preserving document semantics

unsafe-libyaml arrives through serde_yaml 0.9.34+deprecated. The official advisory cautions that forks such as serde_yaml_ng can retain that same implementation; renaming a direct dependency does not establish closure. Inspected serde-saphyr 1.3.0 and 2.0.0 entries require Rust 1.89, compatible with the current 1.95 toolchain, but API and semantic compatibility have not been verified.

Actual callers use `from_str`, `from_slice`, `Value` mappings and `Error`, plus skills frontmatter repair and scalar validation. Migration must cover plugins, commands, skills, external-agent migration and the skills extension with valid, invalid and boundary documents. Verify every transitive source of the unmaintained crate is removed from the resolved graph and avoid silently changing document meaning.

### Linux credentials: evaluate the existing synchronous persistent backend first

Two Linux manifests, keyring-store and rmcp-client, explicitly select `linux-native-async-persistent`. The preserved keyring 3.6.3 release also offers `linux-native-sync-persistent`, combining Linux native credentials with persistent Secret Service storage through `dbus-secret-service`, instead of the async secret-service/zbus route. Its official README explains that the keyring API itself is synchronous and recommends the synchronous backend for this use, with a libdbus requirement.

This suggests a smaller implementation migration to evaluate before a major keyring upgrade. It must preserve persistence and existing credential compatibility, not disable credential functionality to avoid a check. Verify read/write/delete behavior, service/account mapping, locked sessions, error semantics, async-caller blocking and deadlock behavior, libdbus distribution requirements, and Bazel support. Re-check the complete graph for other zbus callers; retain macOS and Windows store behavior.

Blindly upgrading keyring to 4.2.0 does not establish closure: it uses keyring-core and separate backends, so the old feature combination does not directly apply. The inspected zbus-secret-service-keyring-store 1.0.x and secret-service 5.x still depend on zbus 5, short of the consolidation in zbus 6 cited by the advisories. Backend migration and compatibility validation are necessary decisions, not a version-label fix.

### Matrix: coordinate MSRV, anymap and SQLite links

Official registry records and the checksum-verified matrix-sdk 0.19.1 manifest establish that **0.19.0 and 0.19.1 require Rust 1.96 and still directly depend on anymap2 ^0.13.0**. Moving into the crypto advisory's patched range closes only that record, leaves anymap2, and exceeds the current Rust 1.95 toolchain.

There is also a concrete native SQLite constraint conflict. Matrix sqlite 0.19.x requires rusqlite ^0.40.2, whose native dependency requires libsqlite3-sys ^0.38.2. The currently locked sqlx-sqlite 0.9.0 requires **>=0.30.1,<0.38.0**. The current libsqlite3-sys 0.37.0 declares **links=sqlite3**. The ranges do not overlap for the shared native library. The current local Matrix sqlite 0.18 patch cannot simply be reused while changing the Matrix version. The exact registry entries and locked metadata are retained in [sqlite-upgrade-constraints.json](sqlite-upgrade-constraints.json), with its original sparse-cache bytes in the preservation supplement.

Treat Matrix as a controlled migration: align Cargo, Bazel and CI toolchains for Rust 1.96; choose an upstream or maintained anymap3 replacement; agree a common SQLite links version with SQLx; review the existing sqlite and imbl patches; then validate encryption, missing cross-signing-key behavior, durable database migration, WAL/recovery and credential storage. A backport alternative would need an actual reviewed fix and verifiable version/advisory relationship. Relabeling versions or hiding dependency sources is not remediation.

## 6. Cargo, Bazel and acceptance

[MODULE.bazel](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/d32e795f0d24df89fc57745f6fae70fbd0642eba/MODULE.bazel) fixes Rust 1.95 and uses `crate.from_cargo` with the workspace Cargo.toml and Cargo.lock across Linux GNU/musl, macOS and Windows targets. The preserved `scripts/check-module-bazel-lock.sh` invokes `mod deps --lockfile_mode=error` and points to `just bazel-lock-update`. Actual dependency migrations must update and verify Cargo inputs and Bazel's derived lock as required, then satisfy the ordinary full-repository gates.

Keep the five remediation areas reviewable, but verify their combined resolution. No new lock or upgraded build exists from this diagnosis. The current active product PR should not receive recurring diagnostic-only changes that continually restart its full CI. No allowlist, advisory ignore, scope reduction, cancelled-job acceptance or required-check bypass is proposed.

## 7. Final remote observation and preservation

The bounded final observation was made at **01:56:31.362–01:56:32.629 UTC** on exact head d32. [final-status.json](../final-status.json) summarizes the complete raw [round-07-final.json](../round-07-final.json) response:

- Architecture source-head completed successfully at 01:53:04 UTC, with its native regression steps executed. Architecture required completed successfully at 01:53:09 UTC. Base-merge success is separately recorded with its conditionally skipped native scope.
- cargo-deny remains the single failing check. blocking-ci still has fifteen running SDK/Bazel jobs, and the distinct `CI required` check has not yet been created. CodeQL Rust is also running in the exact-head check set.
- Across all 47 check runs: 23 success, 6 skipped, 1 neutral, 16 in progress and 1 failure. These are observation-time counts, not a claim that blocking-ci is complete.
- PR #2815 is Ready, open, unmerged and blocked, with normal squash auto-merge enabled. The successful branches/main response reports required contexts `CI required` and `Architecture required` for non-admins. That limited branch response is not the full protection configuration; the full protection endpoint was not queried in this batch.

The original 13,717,460-byte local log is preserved losslessly as [cargo-deny.log.xz](cargo-deny.log.xz): original SHA-256 `d91f5e6d8d9961b81aebaf6873d85a1dc7ac70e1a009e5e1036e026ebc179175`; compressed size 358,668 bytes, SHA-256 `8abd8f649025c16af81d7f83c97d82bae6b2e1fd3fbbbd646b3d749de4fff44f`. Decompression was verified byte-for-byte and the original local file remains retained.

The final evidence package includes both reports, raw API observations and failed-access responses, tool/download receipts, command logs and locked metadata, both Agentd graph outputs, all thirteen fixed advisories, selected repository source, and checksum-verified public upstream sources. Its strict manifest binds every included file by relative path, size and SHA-256. Large tool roots, Cargo/Rustup caches, checkouts, credentials and compiled objects are excluded; the redundant uncompressed log is represented by its verified lossless compressed copy. The exclusion list records these decisions. Intermediate progress receipts remain identifiable as intermediate rather than replacing completed execution receipts.

