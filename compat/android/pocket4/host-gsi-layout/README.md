# Explicit GSI system-as-root host support

The QPR1 x86_64 GSI places product and system_ext inside its system image.
The previous host always required and mounted separate images. This patch
updates the actual runtime and its operation plan together, including reverse
unmount ordering. Existing cells keep the default `split_partitions` layout.
An explicitly configured `gsi_system_as_root` cell uses `images/system.img`
and its separately pinned vendor image. A missing split image never silently
selects another layout, and split GApps add-ons are rejected for a GSI cell.

The private synthetic root translates only the two verified GSI partition
aliases to equivalent relative links. File override targets are normalized
to those internal directories before the existing private parent projection
is applied. Aliased duplicate targets and unexpected root link destinations
are rejected. Read-only ext4 image mounts use `noload` so preparation does
not replay the image journal.

The same change preserves an already valid selected Android input method
when the IME setup service restarts. A new, absent, or invalid choice still
falls back to the packaged HostInputMethod.

## Source and verification

Apply `host-gsi-layout.patch` to the exact Droidloom host base
`5957addac279b11110c6cdd406e32ef871a7c511`. The resulting source was committed
as `ce2150070260a660a4f634d5bb43085fd6df541b`, tree
`5ef17a4d859c510b39804774e4dae0464922a9cb`. The patch carries all nine changed
files, including the new layout type and meaningful runtime tests. The
[source and host proof](source-and-host-proof.json) binds every changed file,
the four actual release executables, and the original observations by SHA-256.

On Pocket4, normal UID1000 execution of `cargo test --offline --locked -j1
-p droidloom-supervisor --lib -- --test-threads=2` passed 127 tests. Three
environment-specific tests were ignored by that ordinary invocation. The
normal offline release build of both the supervisor and application packages
also succeeded.

The new ignored GSI test then ran separately as root in a fresh bounded
private mount namespace against the actual official QPR1 system image and
the current vendor image. It exercised the compiled mount, alias, private
projection and bind functions, verified read-only behavior, and passed.
The unit, cgroup, image loops and namespace mounts were retired; the temporary
fixture was removed. Full image hashes and protected user-data metadata were
unchanged. This control did not start Android or access the accounts.

## Remaining release gates

These results qualify the host layout change. The binaries have not been
installed by this qualification. The final QPR1 compatibility payload, actual
Android/Main runtime, original application workflows and cleanup remain
separate gates. Older CP2A framework or ART results cannot qualify QPR1.
The existing development runner's production UID mapping and seccomp
limitations also remain unresolved by this layout patch.
