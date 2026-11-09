# Unified Droidloom installer and updater

`droidloomctl update` builds and installs a complete runtime, restarts Droidloom,
and checks Android readiness. Automatic startup remains disabled. The updater,
including source preparation, bundle verification, installation, and rollback,
is implemented in Rust. It does not invoke Droidloom's Bash deployment scripts
or its Python bundle verifier.

Bootstrap from the checkout as the desktop user:

```console
cargo run --locked --release -p droidloom-update
```

After installation, from any directory:

```console
droidloomctl update
droidloomctl start                 # desktop by default
droidloomctl start --mode mobile   # fill the available work area
droidloomctl stop
```

The checkout location and desktop owner are remembered during installation.
Updates preserve the mode selected for the current session.
The command builds the current checkout, including uncommitted changes; it does
not fetch or reset the user's Git branch. Administrator authentication is used
for system package installation when necessary and for the final activation.

```console
droidloom-update plan
droidloom-update --build-only
droidloomctl update --clean
droidloom-update verify .work/update/release-<build-id>
```

Compilation leaves two logical CPUs outside the compiler process affinity,
including nested Ninja and JVM workers. Parallel jobs are also capped at
`nproc - 2`, even if a larger `--jobs` value is requested.

Every invocation requests all host programs and the complete Android target
set, including Composer, the Java input bridge, IME, framework services, patched
native platform services, Mesa and the vendor image. Cargo, Soong, Ninja and
Meson determine which outputs need compilation. `--clean` deletes only this
updater's build outputs and compiler cache. Pinned downloaded sources and base
images are retained and verified again. Existing Android application data is
preserved.

The updater rebuilds itself first and hands off to that executable. All mutable
Android artifacts come from the updater-owned product output, after requesting
the full component set. The Git revision is recorded for information; locally
built files do not need to match predetermined checksums. Previously installed
system, system_ext and product partitions can be reused when they match the
pinned base download. Missing base images are downloaded and verified.
Compatibility APEX files are extracted from that base.

The prepared payload records required files and executable permissions. Both
copies of the input bridge must declare the input ABI matching Composer; the
framework services JAR must contain the compiled navigation policy, and ELF
components must have the expected architecture. Missing or empty components
and incompatible peers reject the update. The input launcher is collected from
Android’s executable build output; a nonexecutable launcher rejects the bundle
even if its recorded permissions agree. Compatible byte differences and
additional files do not. Checksums remain for pinned third-party inputs.

Activation makes a private administrator-owned copy and verifies it again
before stopping Droidloom. Versioned releases live under
`/usr/lib/droidloom/releases`; one `active` symlink selects the complete release.
Stable binary, image and service paths resolve through it. The configuration
is installed as a regular file below `/etc/droidloom`, as required by the
supervisor, and participates in the same rollback transaction. A
persistent transaction journal also records the pre-existing installation's
files and symlinks, so the first migration can be rolled back. A failed start or
empty application catalog restores the previous installation. Readiness also
requires Android’s input bridge service to be running. An interrupted
activation is recovered after updater bootstrap on the next update, before
compiling Android again. Rollback restores
programs/configuration; it does not undo writes Android made to application
data while starting.

Build source projections are journaled and restored on success or failure.
Interrupted projections are recovered on the next invocation. Unchanged projected
content retains its modification time, so applying patches again does not
invalidate compiled Android outputs. Build children
inherit the source lock, preventing recovery while an orphaned compiler is
still running. No command restarts the compositor, logs out the desktop user,
changes a kernel, or flashes a device.

The initial source-building implementation targets x86_64 Linux with systemd
and AMD/Intel graphics. Pure-Python build dependencies are downloaded into a private cache from
`android/manifest/build-python-lock.json`, with checksums verified. MarkupSafe
and PyYAML use their supported pure-Python implementations. Missing native
build dependencies are installed automatically on Arch-family hosts. Other distributions need equivalent build dependencies
already available. ARM64 packaging and signed public release distribution
remain separate work; this command does not claim to bootstrap every device.
Catalog readiness is a nonvisual check. It does not establish that mouse,
touchscreen, and resize behavior have passed the user's visual validation.

Run updater regression tests with:

```console
cargo test --locked -p droidloom-update
```

They exercise mixed ABI rejection, missing components, acceptance of compatible
byte changes and additional files,
architecture mismatch, source restoration and recovery, inherited build locks,
and filesystem rollback of both legacy and versioned installations.

## Stage a vendor Audio APEX candidate

The scoped staging command consumes a SHA256-pinned successful normal Audio
full-build terminal. It copies only the exact complete
`com.android.hardware.audio.droidloom.apex` under
`payload/vendor/apex/` in a new caller-owned staging directory. It emits
`CANDIDATE.json` with state `UNQUALIFIED_VENDOR_AUDIO_CANDIDATE`; it never
calls the system image assembler or updates a running installation.

```console
droidloom-update audio-apex-stage-candidate \
  --terminal /absolute/full-build/RESULT.json \
  --terminal-sha256 <exact-terminal-sha256> \
  --destination /absolute/trusted-parent/new-candidate
```

The destination parent must be a real caller-owned directory without group or
other write access. Every ancestor is opened without following symlinks;
retained directory descriptors anchor exclusive creation and are checked again
before and after publication. An existing destination is never reused. Failed
staging can leave a partial private directory, including a manifest written
before a final synchronization or identity check failed. Consume a candidate
only after the command exits successfully; inspect a failed attempt before
choosing another new destination.

The staged files are synchronized again after their final permissions are set.
New directories are synchronized from deepest child through the stage root,
then the existing parent. Final descriptor and pathname identity checks precede
successful return.

Inputs require the complete 430-project normal full-build terminal, exact
success and retirement fields, the recorded normal command, and the output
artifact's original path, file identity, byte length and SHA256. Source-only
reconcile receipts cannot stand in for a full build. The file is copied and
read back through the same held descriptor. The terminal's recorded input
references remain attached to the candidate; this command does not contact the
durable job service to independently authenticate its terminal.

ZIP metadata inspection is bounded: a container is at most 256 MiB with 4–256
members and a central directory at most 256 KiB; only stored and DEFLATE entries
are accepted. Required metadata is at most 64 KiB per member. Duplicate or
noncanonical names, inconsistent headers, overlapping members, incomplete or
oversized DEFLATE streams and an unexpected package identity reject staging.
The APEX payload must be stored, and compressed APEX containers are out of scope.
The existing workspace `flate2` dependency and lock are reused.

The declared target is the selected official QPR1 CP3A.260905.010 / 16176746
system image. It is not copied or reverified by this command. No CP2A
`system`, `system_ext`, `product`, ART, bionic, framework or Connectivity
overrides are projected. A successful candidate does **not** qualify APEX
container signing, payload AVB, the payload filesystem, compiled ELF imports,
linker namespaces, VINTF matching, Audio HAL behavior, runtime audio or
production readiness. All qualification and readiness fields remain false,
even when a supplied terminal claims otherwise. These gates must run against
the actual full artifact and the selected official base before activation.

Focused staging controls can be run without Android compilation:

```console
cargo test --locked -j2 -p droidloom-update audio_vendor -- --test-threads=2
```
