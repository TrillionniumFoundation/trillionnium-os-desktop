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

The normal framework-services producer applies fifteen complete upstream security
patches to the pinned `frameworks/base` originals and verifies the complete
patched files and unchanged build providers. The notification-channel correction
uses upstream commit `d01eb65a9c333d158d932f081ef2298ca789ebeb`, whose preimages
match the selected `94b4c163b7dfe5ce3607f7bb8456f9573f7de57d` source. Its
`9e7353b7d788125954eca6aaeb95f1dabb93eff2` branch equivalent is recorded as an
alias and is not applied a second time.

The focused framework-security build also requests the original `WmTests`,
`FrameworksServicesTests`, `UsbTests`, `AudioServiceTests`, and
`FrameworksUiServicesNotificationTests` modules. The last module owns the
notification regression tests; `FrameworksUiServicesTests` excludes those
sources. Successful-build records bind the actual services JAR and each
requested test APK to the owned product output and its original module
provider. Building these artifacts does not establish that the device tests
ran, that the installed binaries contain every bulletin fix, or that runtime
and production-signing checks passed.

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

## Runtime input image producer

`droidloom-runtime-inputs` builds an uninstalled runtime input image from a pinned
plan and fixed original bytes. A nonzero exit leaves any outputs unqualified;
callers must require successful completion and the complete output proof before
consuming them. This command does not install a selection or grant Android Ready.

The current `original_cat` command captures at most 4 MiB of stdout. The selected
CP3A init is 2,934,488 bytes and fits that bound. The declaration parser's larger
size limit does not establish support for reading arbitrary 32 MiB inputs through
this command. The ordinary image test uses a synthetic 32 MiB filesystem; that
filesystem size is separate from the per-command stdout limit.
