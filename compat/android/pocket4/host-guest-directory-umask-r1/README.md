# Android guest directory modes and first-stage umask

The bounded host daemon uses umask `0077` for its control and state files.
The development cell bypasses Android first stage after assembling the guest
mounts, then executes init's second stage. That also bypassed first stage's
`umask(0)`. Host-created guest directories and later Android-created property
directories consequently inherited restrictive host permissions.

An actual QPR1 attempt observed `0700` on `/dev/socket`, `/dev/__properties__`,
graphics device directories, and the synthetic CPU directory chain. The
property socket itself was `0666` and `property_info` was `0444`, so their
parent directories still denied ordinary Android service access. This capsule
repairs that concrete host-to-guest boundary; it does not disable critical
services or grant production acceptance to a boot attempt.

## Source change

`host-guest-directory-modes.patch` is the exact committed delta from
`ecf986b7afe7a2c24e537e765ee600c0256b2096` to
`fcb5afd7347b13f32c96daa073a63a048e95ecb2`, tree
`bb8f2f3bc689da9f3441ea7d6c818f52d812896f`. It changes three Rust files:

- `development.rs` calls the private-directory helper for the device,
  synthetic sysfs, and mount staging directories. At the final Android exec
  boundary, a pre-exec hook requires namespace PID 1 and clears only that
  guest process's umask. Host preparation keeps its original umask.
- `development_guest_dirs.rs` creates missing directory components using
  held directory descriptors and sets only newly created directories to
  `0755`. It rejects relative escapes, symlinks, non-directories and descent
  onto another filesystem. Existing directory modes remain unchanged.
- `development_guest_dirs_tests.rs` exercises the real helper and exec hook,
  including root-only namespace controls with ordinary UID 1000 clients.

The umask behavior comes from the pinned AOSP first-stage source. Bionic's
serialized property area uses `mkdir(..., 0711)`; it must remain `0711`, not be
indiscriminately changed to `0755`. The source identities are recorded in
`source-pins.json`. They document this boot contract and do not assert an
unproven source-tag correspondence for the complete QPR1 binary release.

## Validation

The normal locked, offline Rust suite passed **130 tests**. Thirteen private
fixtures or root controls are ignored by the ordinary suite. The new actual
root namespace control was separately selected and passed without skips.
It verifies all of the following on actual kernel objects:

- With umask `0077`, the old directory creation behavior causes UID 1000 to
  receive `EACCES` for both the socket and property metadata despite readable
  leaf modes.
- The production helper permits UID 1000 to connect to a Unix socket, traverse
  the intended guest directories, and read all three projected CPU files.
- A real PID 1 exec through the production hook inherits umask `0000`.
  A subsequent unmodified `mkdir(..., 0711)` produces `0711`; UID 1000 reads
  `property_info` and connects to a newly created property-service socket.
- Host control directories and files remain `0700` and `0600`. An existing
  host directory bound into the private tree is neither chmodded nor modified.
- Mount, PID, cgroup, IPC and UTS namespaces are private. The owned outer
  child is reaped, the bound init pidfd reports exit, and the host namespace
  identities and original directories remain unchanged.

The final normal release build succeeded. Exact source, release and sanitized
control identities are in the adjacent JSON files. The original qualified
parent source and binaries remained unchanged. No Android image or account
data is used by these controls.

To reproduce in the source repository, apply the patch to its exact parent,
use the repository's locked toolchain, and run:

```sh
cargo test --locked --offline -j1 -p droidloom-supervisor --lib
```

Then select this exact test in the resulting libtest binary as root in a
bounded Linux environment with namespace privileges:

```text
--exact development::guest_dirs::tests::actual_restrictive_umask_namespace_directory_access --ignored --nocapture --test-threads=1
```

The source patch preserves the already qualified unshare ownership and
retirement path. It does not add the still-missing production UID map,
seccomp enforcement or production resource executor. The controlled QPR1
probe continues to depend on its explicit external systemd resource boundary.

The first directory-only control is retained as partial earlier evidence.
One subsequent preparation attempt failed before source mutation because a
normal user tried to read its root-owned receipt; the corrected attempt used
the already authorized read-only sudo path. The root-owned evidence file's
permissions were not loosened. Complete private records remain outside this
public capsule.
