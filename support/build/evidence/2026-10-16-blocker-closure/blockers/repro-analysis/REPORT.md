# A01 reproducibility closure analysis

Source inspected: `350d98d70a3d7b7c720cabd7720063849afb5a29`. This is a read-only analysis, not a new build or reproduction acceptance. No namespace, mount, chroot, container or compiler probe was executed. Exact committed input blob and SHA256 bindings are in `report.json`.

## Concrete support-only route

A reserved **real canonical build directory** can accept the same committed source from different origin checkouts through a detached Git worktree or verified snapshot. Compile only at that fixed directory, with real fixed toolchain, Cargo source/cache, VDSO and target paths. Serialize the directory, validate ownership, and capture target-absence, every input and output. This needs no change to core, OSTD, comp-sys or OSDK.

The honest result is “different origin checkouts normalized to one compiler-visible root.” The compiler still sees the same path, so that result cannot close arbitrary compiler-visible path independence. The previous same-path two-clean-build proof already establishes a related, narrower fact on its historical source.

For genuine independent-host testing, use an already permitted image or dedicated VM platform with a digest-pinned environment, fixed mount roots and a fixed embedded builder identity. Compare bytes from two independently identified hosts/jobs. This task only sees one host; it has not provisioned another execution surface.

## Why the simple alternatives do not close it

- OSDK BuildScheme has `rustflags` but no virtual Cargo metadata root. Cargo metadata and OSDK configuration discovery use real/canonical paths.
- `component-macro/src/priority.rs` emits absolute Cargo package paths as ordinary Rust literals. `init_component` emits `file!()`. The runtime uses exact map-key matching after removing the source suffix. Remapping only compiler-origin locations can separate these keys. No newly executed panic is claimed.
- The macro also reads Components.toml from the actual workspace root. A fake Cargo metadata wrapper would need to preserve those semantics and all validation; rewriting selected metadata fields is not an approved or demonstrated solution.
- `RUSTC_WORKSPACE_WRAPPER` does not virtualize filesystem access or Cargo metadata. The generated OSDK base is a separate workspace; kernel core is a path dependency. It is insufficient to reliably intercept the kernel and all dependencies.
- OSDK always overwrites child Cargo `OSDK_BUILD_USERNAME` and `OSDK_BUILD_HOSTNAME` using whoami. The cached Linux whoami implementation uses getpwuid_r/gethostname. Parent environment exports, USER and HOSTNAME cannot establish fixed compiler identity.
- An all-rustc `RUSTC_WRAPPER` could potentially normalize the embedded identity, but requires real argv-composition and incremental-fingerprint tests and does not solve component path literals. It remains an unexecuted candidate.
- Symlink aliases alone are insufficient because canonical paths and Cargo package IDs can reveal the real checkout/tool roots.

## Existing tools, with no execution-permission probe

`bwrap` exists at `/usr/bin/bwrap`, version `bubblewrap 0.9.0`. `chroot` and `unshare` exist. PRoot, Docker, Podman and Nix were not found on PATH. Tool presence does not show that managed policy permits namespaces or mounts. Chroot alone does not change the UTS hostname and requires a complete root filesystem. The upstream Docker launcher uses privileged mode, host networking and host /dev mounts; these are unnecessary for the current q35/TCG minimal profile and are not proposed here.

## Minimal coordinated source proposal

For actual different-compiler-visible-path identity, A00 and the comp-sys owner should coordinate a shared stable component identity in the registration macro, metadata macro and runtime matching. A validated unique package identity can replace absolute package path/file registration while retaining graph priority and stage semantics. Tests must cover identity uniqueness, graph ordering, registration and actual boots under two different real source roots. A separate small OSDK change can honor explicit embedded builder identity while defaulting to current whoami behavior.

Neither proposal requires a kernel version upgrade. Neither has been implemented here; A01 ownership does not authorize unsolicited component/core edits.

## Status

The support-only fixed-root route is implementable. Cross-compiler-visible-path and cross-host identity remain **unproven**, with precise technical causes and a scoped coordination path. They must not be relabeled closed from a fixed-path pair or from mere container-tool availability.
