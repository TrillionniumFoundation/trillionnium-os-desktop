# Compile02: qualify only the selected offline builder dependencies

Compile01 failed before Rust compilation. Its unchanged workspace-wide Cargo metadata query requested uncached adler2 2.0.1. Exact Cargo.lock traversal shows adler2 is reachable from droidloom-doctor, not droidloom-update. The original failure is retained.

Installed Cargo reports commit 083ac5135. Its primary `src/cargo/ops/cargo_output_metadata.rs` selects `Packages::All` even with filter-platform. `src/cargo/ops/tree/mod.rs` instead passes the requested package specs into `resolve_ws_with_opts`; `src/cargo/ops/resolve.rs` passes the selected member IDs to `download_accessible`. These references explain the selection difference. The precise installed behavior was then observed on Pocket4 by the offline locked selection probe.

The actual probe result SHA is 185fce9a8eba4c8edb9879da1eef282404e890ec013a8c4c41c61ccbea7023bf. Its build and test trees were identical, SHA82ad8aefece0dedb3a992db45b5de4097ebbb2c0fd02ed00ffe50c401bd4dd0d, selecting 49 unique packages: 4 exact workspace members and 45 locked crates.io packages. The actual probe preserved all 450 source files, tools and Cargo configuration observations, and recorded zero owned OOM events.

Compile02 retains offline/locked commands, the unchanged lockfile, the 450-file copied source, Go6 patch, actual Go R5 authority, compiler/library qualification, seven existing tests and all cleanup/resource gates. It replaces the broad metadata step with no-deps workspace discovery plus the two observed selected trees. Paths are normalized only for the fresh copied source root. The selected trees must remain exactly equal to the prior actual observation.

Registry qualification accepts only one existing regular cache directory for each locked package, verifies Cargo.lock package checksum and all .cargo-checksum file hashes, and records the complete held source inventory before and after compilation. Unknown registry types, directory aliases, duplicate cached sources, and newly present Cargo configuration inputs reject the attempt. Every actual compiler artifact must bind a pre-qualified manifest/package ID and source file. Cargo tree alone is not treated as proof of compilation closure.

Primary source URLs (installed Cargo commit):
- https://github.com/rust-lang/cargo/blob/083ac5135/src/cargo/ops/cargo_output_metadata.rs
- https://github.com/rust-lang/cargo/blob/083ac5135/src/cargo/ops/tree/mod.rs
- https://github.com/rust-lang/cargo/blob/083ac5135/src/cargo/ops/resolve.rs

Compile02 has not yet run. No Rust compilation, new builder ELF, full engine build, Android execution or application qualification is claimed by this source change.
