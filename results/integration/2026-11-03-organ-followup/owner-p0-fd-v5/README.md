# Frozen fd/a39 optimized Root build, tests and installation

This record binds Desktop `fd8d56c52b971c2d5d0e6430f296803b43ef60a3`
(tree `347fbb7e9931006c749b5bef0e1550c54bc08f27`) and original Hepta
`a39a0871d9601ffccb5e0d95d8f39d54b3a63360`
(tree `e03f9b3eca364222029298496d3e4f1f5e1bf5de`). It uses the already
implemented `product-linux` profile and Rust 1.96.0. Both sources remained clean.
The earlier [dev-small size refusal](../owner-p0-fd-v4/root/build-receipt.json)
remains a separate failed execution.

## Actual stages

| Stage | Original result | Scope |
| --- | --- | --- |
| Root product build | All eight commands exited 0; original builder `status: passed` | Compiler identity, locked/offline metadata, original Hepta and Root builds, all four original strip stages |
| Session host with product-root, all targets | 53 passed, 2 ignored, zero failed or filtered | Original dev-small test groups: 8, 25, 1, 14 and 5 passed |
| Two privileged Root tests | Each actually executed and passed | The two previously ignored cases; only the original compiled test executable ran with privilege, not Cargo |
| Original packaging | Exit 0, 83.684 seconds | The verified prepared UI package and optimized original Root supplement |
| Extracted package verification | Exit 0, 2.289 seconds | Original complete manifest and package checks |
| Original installation | Exit 0, 7.186 seconds | New Root-owned release at `/opt/trill-organ-20261103/releases/fd8d56c52b97-053cc1957b40` |

The test total across those original groups is **55 distinct passed cases**.
The two privileged invocations each leave 26 other tests filtered out; these
are selections, not an additional 52 executed cases. The test profile is
`dev-small`; the installed binaries came from the separate `product-linux`
build. Test and distribution profiles are not relabelled as one another.

The original Hepta build took 1,550.565 seconds and the Root build 940.901
seconds. They preserved the selected original features and locks. The existing
128 MiB per-file and 512 MiB package bounds were not changed.

| Stripped original executable | Bytes | SHA-256 |
| --- | ---: | --- |
| codex-hepta-agentd | 117,408,600 | `f4b5115b3048f3b95a4a5e7aaa5f5a60ec41c4ed199b865705fb60fbc83b0f74` |
| hepta-desktop-root | 24,530,984 | `d22d265d8f6414342831eea7fef843212af95e08a90ca6467aca538aa15a3f0f` |
| codex-app-server | 103,411,384 | `69b08123828215500c615bf0f89e28eb5d17d4af9ba01a4f1b893115aa05afb8` |
| hepta-authority-host | 20,724,136 | `ade01e082d9026ad1c785a1a89b02b6960bdb315e13a2556ad5fdede34553074` |

The original packaging execution records product archive SHA-256
`76838c10be79708f79a0e46a89b8dbe056595a8f0fe73fe46abc9434ae6fd6e8`.
The independent reviewer retrieved and verified the complete small evidence
archives below, not this entire binary product archive. The original verify
and install commands performed their own product checks on the execution host.

## Complete retained evidence

| File | Members / bytes | SHA-256 |
| --- | --- | --- |
| [Build evidence](build/complete-raw-evidence.tar.gz) | 18 original members; 498,815 compressed bytes | `4337e3b5f1ca90d2ab88128c7d936ef8c911f787ee6ad0a538cd9c0aba712461` |
| [Tests, package and install evidence](tests-package/complete-raw-evidence.tar.gz) | 13 original members; 79,924 compressed bytes | `afc3cc18aac97a118944633cf99ee59e2e5a8932c75ee97347761b01f9de4583` |

Each archive was read with an immutable version binding. Full archive hashes
and all 31 original member sizes/hashes were independently recomputed. The
[build member index](build/original-member-index.json) includes the complete
6,760,791-byte Cargo metadata stdout; the [tests member index](tests-package/original-member-index.json)
includes the complete 1,122,246-byte all-targets stdout. These are not excerpts.
The original [build receipt](build/build-receipt.json), [later result](tests-package/result.json)
and terminal process observations remain available separately. The build job
`1a1a2ea6117-96a-7565` and tests/package job `1a1a31eeea3-96a-75da` both have
authoritative `succeeded`, exit 0, no timeout and complete output metadata.
[Independent review](independent-review.json) records the checks and limits.

## Installation is one completed gate

The original installer explicitly returned `services_started: false` and
`production_ready: false`; the build and later result keep their own false
product-qualification fields. This record does not establish an authenticated
human submission, model turn, actual Notes effect, independent application
readback, original writer terminal or full owner restart. Those later stages
must retain their own actual inputs and evidence.

The current installed composition has a finite original authority lifetime of
at most 300 seconds. Its one same-boot recovery must fit inside that same issuer
window. [D14](../../../../docs/DECISIONS.md) records why this is not a continuously
renewing production desktop, and why editing a timeout or recreating a fresh
prefix cannot stand in for original-owner continuation. A real local graphical
login, the registered live Shell, original AuthBus admission and the configured
model/provider remain required for the genuine human Notes path.
