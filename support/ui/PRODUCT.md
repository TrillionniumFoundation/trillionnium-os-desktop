# Linux host installation, upgrade and recovery

The product entry point packages and runs the existing Rust `trill-session`,
`trill-shell`, `trill-app-window`, `trill-ctl` and `trill-notes-recovery`. It is a user installation for
an existing Linux desktop with a user systemd manager. It does not install an
Asterinas kernel, activate a production Hepta authority or introduce another
task/effect store. Session remains the application process owner.

## Build a source-bound installable package

First build and verify the actual Rust host programs with the pinned toolchain
and the original procedures in [RUN](RUN.md). The existing
`package-host-binaries.sh` creates the bounded five-program binary artifact.
It refuses a modified source checkout and records both its exact commit and
tree. Run it in the same clean source checkout used for the actual successful
build and retain the command logs and binary hashes alongside the package;
the commit label alone cannot prove which source produced pre-existing binaries.
It reads `debug` binaries by default. Set `TRILL_UI_BUILD_PROFILE=release` for
an actual `cargo build --release`; `CARGO_TARGET_DIR` must match the build.
Wrap that artifact with the new lifecycle entry point:

```sh
python3 support/ui/product/desktop.py pack \
  --host-archive /absolute/evidence/a10-linux-host-binaries.tar.gz \
  --expected-desktop <full-40-character-Desktop-build-commit> \
  --source-profile /absolute/verified-organ-source-profile.json \
  --output /absolute/output/trillionnium-desktop-linux.tar.gz
```

The packager checks every inner binary digest, Linux ELF signature, the exact
Desktop build commit and the full Hepta commit in the existing source profile.
It preserves that profile and `PROVENANCE.txt`, and adds a per-file manifest.
This binds package inputs; it does not claim the source profile's production
inputs have been deployed. A release id combines the Desktop commit and the
complete file manifest digest, so changed binaries, launcher or profile cannot
silently reuse one release directory.
The outer `.sha256` protects transport integrity, not publisher identity.

For a self-contained Makepad installation, first run the original-resource
preparer described in `support/ui/prepare_native_makepad.py` against the exact
Cargo metadata used for the binary build. Pass its output to `pack` with
`--makepad-resources /absolute/prepared-bundle`. The product verifies and ships
all 29 original assets, 15 notices, font source archive, inventory and source
identity. A separate `NATIVE-DEPENDENCIES.json` binds six AccessKit license and
upstream/patch provenance files under `dependency-notices/accesskit/`. Their
actual bytes are verified and included in the installed package; the original
29/15 inventory is unchanged. All four accessibility crates must use the same
Hepta source as the UI, and that source must match the binary source profile.
Rust startup independently verifies both inventories against its compiled
original constants. With `renderer: "makepad"` and `makepad_resources: null`,
the launcher uses the current installed release's resource directory.

### Explicit original SDK clipboard candidate

The baseline `trill-shell/hepta-native-makepad` feature builds with the original
337566c8 SDK and uses the original 54-file resource bundle. It requires no
external Cargo configuration. Its standard EditableText PasteText method returns
false; no native clipboard request is queued.

The separate `trill-shell/hepta-native-clipboard-sdk` feature forwards through
`trill-ui-core` to the original UI's `native-clipboard-sdk`. Only this feature
compiles the new SDK API, advertises PasteText and requires the 61-file candidate
bundle at startup. A candidate resource bundle does not enable the feature in a
baseline binary.

The request-scoped PasteText candidate is a separate source profile. It accepts
only original SDK `337566c8b25d47f7e4fff6a202157b65bf183330` plus its two reviewed
patches and complete prepared tree `e5ae930cc6a0a528719673deff44ec2830f4bdfa`.
`native-clipboard-read.patch` retains its original bytes. The additional
`sdk-num-traits-path.patch` makes the two original `makepad-half`/`naga` path
dependencies select the same `num-traits` 0.2.20 manifest resolved by original
Git SDK discovery, at `libs/rapier/vendor/num-traits/Cargo.toml`. It does not
substitute the adjacent Vulkan 0.2.19 copy. Both patches, their exact bytes,
and the new full-tree manifest must match the fixed product contract. The
earlier clipboard-only `f9efec87` profile is retained in its historical evidence;
it is not accepted as this complete candidate profile.
Arbitrary path dependencies and mixed SDK crate sources are refused. The Hepta
helpers `prepare-native-clipboard-sdk.py` and `verify-native-clipboard-sdk.py`
generate the all-crate Cargo override and verify the actual dependency edges.
Use the same explicit clipboard feature for both metadata captures and the
actual build. The preparer/verifier checks resolved Cargo features, including
Desktop's forwarding chain. A metadata/source receipt is not a build or UI test
result.

In the independent candidate worktree, capture the original graph before the
override, then resolve and build with the generated all-crate config:

```sh
cargo metadata --manifest-path ui/Cargo.toml --format-version 1 \
  --features trill-shell/hepta-native-clipboard-sdk \
  > /absolute/original-native-metadata.json

# Run the exact Hepta prepare-native-clipboard-sdk.py helper using that metadata.
cargo --config /absolute/all-sdk-overrides.toml metadata \
  --manifest-path ui/Cargo.toml --format-version 1 \
  --features trill-shell/hepta-native-clipboard-sdk \
  > /absolute/candidate-native-metadata.json

# Verify that actual graph and commit this candidate's resulting Cargo.lock.
cargo --config /absolute/all-sdk-overrides.toml build \
  --manifest-path ui/Cargo.toml --workspace --bins --release --locked \
  --features trill-shell/hepta-native-clipboard-sdk
```

Keep the baseline's original Git-SDK `ui/Cargo.lock` on the normal branch.
Generate and commit the candidate path-SDK lock only in a separate branch and
worktree; use its exact external config on every subsequent `--locked` command.
Do not merge that lock or a global `.cargo/config` into the default product.
Both modes share the reviewed source and original owner. `--all-features`
includes this opt-in candidate and is not a baseline verification command.

Once that candidate's generated lock and source are committed, use the single
verification/build entry point to keep every Cargo command on the same inputs:

```sh
python3 -B support/ui/verify_native_sdk_candidate.py \
  --hepta-root /absolute/exact-pinned-hepta-checkout \
  --prepared-sdk /absolute/reviewed-prepared-sdk \
  --sdk-cargo-config /absolute/all-sdk-overrides.toml \
  --original-metadata /absolute/original-native-metadata.json \
  --target-dir /absolute/candidate-target \
  --profile release --jobs 2 \
  --output /absolute/new-candidate-build-evidence
```

The command requires clean Desktop and Hepta checkouts, revalidates the exact
SDK tree and all resolved dependency edges, and runs locked metadata, all-target
tests, strict all-target Clippy and the binary build. Feature, Cargo config,
toolchain, target directory and profile are fixed across those steps. The
candidate lock/config/source inputs are checked between steps; any drift or
failed command stops qualification and retains its logs. It never repairs or
regenerates a lock automatically. The output contains command argv, input hashes,
the exact candidate lock, a freshly verified SDK source profile, binary hashes
and a separate build receipt. Its source profile still says `compiled: false`;
the separate build receipt reports actual command success. Window, clipboard,
IME and accessibility qualification remains a separate run on those binaries.
The successful receipt directly supplies the existing native-window qualifier's
`--build-receipt` contract: `status`, `exit_code`, `source_commit`, `source_tree`
and `binaries` with each actual program's byte count and SHA-256. Use that exact
receipt without rewriting it. `runtime_qualified` remains false until the
separate window qualification succeeds and produces its own evidence.

Put `--config` **after** the Cargo subcommand, especially
`cargo +1.96.0 clippy --config /absolute/all-sdk-overrides.toml ... --locked`.
Clippy is an external Cargo plugin; an outer `cargo --config ... clippy` can
consume that configuration before invoking the plugin, whose inner Cargo then
resolves a different graph. The canonical runner uses the forwarded position
for every step. This distinction is covered by Cargo's original
[external-plugin configuration issue](https://github.com/rust-lang/cargo/issues/11031)
and a regression that invokes the real Cargo frontend with a temporary plugin.

Pass the resulting SDK receipt and its inputs to the resource preparer:

```sh
python3 -B support/ui/prepare_native_makepad.py \
  --metadata /absolute/candidate-native-metadata.json \
  --sdk-source-profile /absolute/verified-sdk-source.json \
  --sdk-original-metadata /absolute/original-native-metadata.json \
  --sdk-cargo-config /absolute/all-sdk-overrides.toml \
  --liberation-source /absolute/verified-liberation-source.tar.gz \
  --output /absolute/new-prepared-resource-bundle
```

The preparer independently repeats source/tree/graph verification; it does not
trust an input `verified` flag. It rejects original SDK plus clipboard feature,
and prepared SDK without that feature. The receipt records
`native_ui_feature: "native-clipboard-sdk"`. Keep the SDK receipt unchanged as the existing
binary source profile's `makepad_sdk` object. The built binary archive's
`PROVENANCE.txt` must additionally contain `Makepad source profile SHA256: `
followed by the SHA-256 of the exact SDK receipt bytes. Packaging rejects a
missing or different profile binding. This is source provenance, with no new
runtime authority or implication of physical accessibility qualification.

After the matching successful build and checks, let the existing host archive
helper validate the fixed SDK receipt and record its exact bytes' digest:

```sh
TRILL_UI_BUILD_PROFILE=release CARGO_TARGET_DIR=/absolute/candidate-target \
  bash support/ui/package-host-binaries.sh /absolute/new-host-evidence \
  /absolute/verified-sdk-source.json
```

Commit the exact candidate source and generated Cargo lockfile before this
step; keep metadata, overrides, prepared SDK, target and evidence directories
outside that source checkout. The helper keeps its clean-source gate and does
not infer successful compilation or qualification from the receipt.

The bundle retains all original fonts and six AccessKit notices, then adds
`NATIVE-SDK-PATCH.json`, `NATIVE-SDK-SOURCE.json` and five original SDK license,
manifest, two patch and provenance files. The preparer and installer bind the
bytes and SHA256 of each patch independently, including `sdk-num-traits-path.patch`;
a self-consistent replacement notice cannot authorize a different source change.
The installer checks all 61 actual files;
startup checks the SDK notice contract against the compiled original UI
constant. The qualification harness's `--atomic-editable-text
--request-scoped-paste` additionally requires native PasteText readback and an
actual delayed clipboard response after a room change. Leave that option off
for the unchanged original SDK baseline.

## Install and start

Extract a package received from the chosen trusted build, verify its outer
checksum, then use its included installer:

```sh
python3 /absolute/extracted/trillionnium-desktop/desktop.py install
~/.local/bin/trillionnium-desktop doctor
~/.local/bin/trillionnium-desktop run
```

Installation uses `$XDG_DATA_HOME/trillionnium-desktop` (default
`~/.local/share/trillionnium-desktop`), `~/.local/bin`, the user applications
directory and the user systemd unit directory. It refuses to overwrite an
unmanaged launcher/unit or a modified managed integration. No sudo is used.
The desktop launcher and command line invoke the same entry point.

`run` starts the existing Session as a dedicated user service, verifies the
socket's kernel peer PID against that unit's MainPID, waits for the original
CLI's real Snapshot, then starts the original Shell. Closing Shell
leaves Session and its application windows alive. A new Shell observes the
same Session. `stop` deliberately stops the Session and its service-owned
application process group; save application work first. A Session crash is
reported by systemd; it is not automatically relabelled as a recovered session.

The launcher writes only this unit's private display environment file. It does
not import environment variables into the global user service manager, change
other services, auto-start at login or enable a machine service.

## Native Root deployment entry

`trusted_desktop.py` is the administrator deployment entry for a bundled native
package. Its `stage` command verifies the independently supplied manifest SHA256,
copies each file into a new Root-owned release, rechecks the copied bytes and
resources, synchronizes them, then atomically publishes one deployment record.
The program path names the immutable release, not a mutable `current` symlink.
The default prefix is `/opt/trillionnium-desktop`. Ancestors, ownership, modes,
hard links and symlinks are checked. Execute this tool from reviewed administrator
tooling; staging treats package files as data and never executes package code.

```sh
# Existing Root administrator, with a reviewed package and manifest digest:
python3 /reviewed/tools/trusted_desktop.py stage \
  --package /reviewed/trillionnium-desktop --expected-manifest REVIEWED_MANIFEST_SHA256
python3 /reviewed/tools/trusted_desktop.py describe
```

The output is a program/resource binding for the existing authenticated launcher.
It does not contain or create a principal, lease, writer or human authorization.
The original provider must supply its existing Root0600 native profile naming
that exact `program`, `program_sha256` and `TRILL_UI_MAKEPAD_RESOURCES`. A missing
or mismatched profile stops launch; changing a path in the user config does not
create one. The existing Hepta Root config, registered daemon, original owner
pidfd and App Server thread are retained.

In the intended user's graphical session, install the same verified package and
run `trillionnium-desktop prepare-session`. This performs the normal service/PID
and Snapshot readiness checks without starting another Shell. Then the existing
Root launcher invokes the following entry with its **already held original daemon
pidfd as stdin** (a shell pipe or a newly inferred PID is insufficient):

```sh
python3 /reviewed/tools/trusted_desktop.py launch \
  --authority /protected/hepta-authority-host \
  --authority-sha256 REVIEWED_ORIGINAL_ROOT_ELF_SHA256 \
  --config ORIGINAL_ROOT_CONFIG --registration ORIGINAL_DAEMON_REGISTRATION \
  --profile EXISTING_AUTHENTICATED_NATIVE_PROFILE
```

This entry hashes and executes the same open Root executable, transfers the
original daemon pidfd, and passes an exclusive deployment lock to the original
`launch-native --deployment-lock-fd` implementation. Root retains the lock for
its serving lifetime and marks every inherited fd from 3 upward close-on-exec in
the UI child. Thus the ordinary UI cannot retain a duplicate lock alias, unlock
or write the Root deployment lock. The managed release path also requires this
exact prefix lock inode when called through the generic Hepta launcher. The original Hepta
launcher still hashes/executes the installed Shell inode, drops its privileges,
retains its actual child pidfd and registers that process with the original
human/session/permission revision and App Server route.

`stage` and `rollback` refuse while that Root is active. After it ends, `rollback`
validates the complete previous package before atomically exchanging the current
and previous selection. The generation increases; old UI processes retain only
their original process/session identities. A new launch always needs a matching
existing authenticated profile and a fresh UI process. No grant or old effect is
copied during package rollback. The package filesystem tests and deployment-lock
tests establish plumbing boundaries; actual Root recognition, upgrade isolation
and original thread continuity still require the live acceptance run.

## Configuration and diagnostics

The installed, private `0600` config is
`$XDG_CONFIG_HOME/trillionnium-desktop/config.json` (default `~/.config/...`).
Its versioned fields are:

| Field | Meaning |
| --- | --- |
| `renderer` | `egui`, or `makepad` when the installed binary includes that feature |
| `makepad_resources` | Null uses this release's bundled resources; otherwise an absolute verified original resource directory |
| `cjk_font` | Optional absolute path to a real host CJK font |
| `observer` | Null, or the existing read-only observer's socket, agent id, spawn generation, peer UID and optional run id |
| `chat` | Optional `{ "socket": "/absolute/private-lane.sock", "root_pid": 123 }`; locates the original Root text lane, without providing an owner or grant |
| `draft_recovery` | Enables local draft/composer checkpointing; it never submits an Objective |
| `notes_state_dir` | Optional absolute Notes data directory; default is the stable UI state directory's `notes` child |
| `shell_page` | Existing Shell startup page, normally `conversation` |

An observer object contains exactly `socket`, `agent_id`, `spawn_generation`,
`peer_uid`, `run_id`. No grant or signing key belongs in this file. The existing
Hepta observer still validates actual kernel peer identity and original
runtime identity. A valid config is not proof the runtime is reachable.

The optional `chat` object overrides an inherited pair of `TRILL_UI_CHAT_SOCKET`
and `TRILL_UI_CHAT_ROOT_PID`. Both are required together. Without either, the
native workspace remains a local draft UI. Existing schema-1 config files
without `chat` stay valid and are not rewritten. These settings reach only
Shell; Session and its apps do not inherit them. The worker still checks the
actual Root peer UID/PID, and the original Root must independently register
this live Shell through a retained pidfd before accepting its hello. Creating
a socket path or filling a PID does not enable Send. The trusted Root launcher
owns this ordering; a manual UI Refresh can retry the same configured lane
after that registration is ready. `doctor` reports configuration, not authority
or successful registration. The native text feature uses the toolchain pinned
by the final two-repository build; the installer never changes Rust toolchains.

The launcher creates the stable UI state parent as a user-owned `0700`
directory and synchronizes each new directory entry. The original Notes store
creates its own child; a custom Notes path also requires a private owned parent.
An existing shared directory is rejected without changing its permissions.

`doctor --live` verifies installed bytes/config, private runtime directory,
the user service manager and an actual bounded read-only Session Snapshot.
Its output contains source identities, readiness, task count and errors, not
draft text or runtime payloads. Missing display or user bus is actionable;
installation cannot manufacture a graphical login. Read process diagnostics
with `journalctl --user -u trillionnium-desktop-session.service`.

Linux pathname Unix sockets allow 107 filesystem-encoded bytes before the
terminating NUL. The Session endpoint adds `/trillionnium-ui/session.sock` to
`XDG_RUNTIME_DIR`; the complete path must fit. Chat and observer socket paths
have the same limit. The launcher checks the encoded byte count before opening
the socket and reports the actual length and limit. A long installation prefix
or ordinary configuration filename does not need to become the runtime socket
directory. Use a separate short, user-owned `0700` runtime directory.

For isolated acceptance, `install` accepts `--prefix`, `--bin-dir`,
`--applications-dir`, `--unit-dir`, `--config` and a dedicated
`--unit-name trillionnium-desktop-<test-name>-session.service`. The unit must be
discoverable by the real user manager; test installations must not replace an
existing unit or use an occupied Session socket.

## Upgrade, rollback and uninstall

Close application work and run `trillionnium-desktop stop`, then run the new
package's `install` with the original installation paths. Upgrade refuses an
active service or an independently running Session. It stages and verifies a
new release before atomically selecting its `current` symlink. The previous
release remains available for `trillionnium-desktop rollback` while stopped.
This is an atomic release selection, not a live state migration between
different Session generations.

Configuration and `$XDG_STATE_HOME/trillionnium-ui` (default
`~/.local/state/trillionnium-ui`) remain outside immutable release directories.
Upgrade and rollback do not rewrite draft, composer or Notes content. Local
quotes recovered from disk remain historical; fresh owner observations are
required to present current task state. A corrupted or newer unsupported
checkpoint must be reported and preserved, never silently replaced by an
empty draft book. The former explicit v1/v2 export/import remains available
for user-requested backups.

Automatic recovery uses `workspace-checkpoint-v4.json` as private `0600`
plaintext, with a 64 MiB file bound. It contains saved local drafts, every
workspace's local composer rooms, selected room, context references and tabs.
The shared composer preserves anonymous text and up to four parked principal
partitions; startup restores the anonymous partition. A parked partition only
becomes active after the original workspace installs that authenticated owner.
No owner, thread history or delivery state comes from the checkpoint. If v4 is
absent, the old v3 file may be migrated while preserving its original bytes.
An invalid v4 file never triggers fallback to v3 or overwrites either file.
Manual v1/v2 exports retain their separate 4 MiB bound. One Shell holds the recovery file
lock; another window can still observe Session, but reports that recovery is
unavailable rather than overwriting the first window's state. Corrupt, insecure
or unsupported files disable writing for that Shell and remain untouched.
The UI queues complete snapshots to a bounded background writer; file and
directory synchronization never run in a render callback. Normal close drains
the last queued snapshot. A forced process kill can lose edits after the last
completed checkpoint. IME composition is deferred until the original composer
has a complete accepted value. Restoring a shared archive or multiroom snapshot
requires the shared presenter feature; the plain composer refuses to truncate it.

`trillionnium-desktop uninstall` refuses an active Session, removes only its
verified launcher, desktop entry, unit and release directories, and preserves
configuration and user state. Modified integration files are reported and
preserved. Uninstall never recursively deletes a user-selected data directory.
The small installation lock inode is retained to prevent concurrent-install
lock replacement races.

## Verification boundary

`python3 -m unittest discover -s support/ui/product -p 'test_*.py'` exercises
package corruption, traversal/alias refusal, installation, upgrade/rollback,
managed-file protection and user-data preservation in private temporary paths.
Its ELF fixtures test installation mechanics, not the Rust runtime.

The real acceptance harness requires two distinct real package directories,
externally supplied build-manifest SHA256 pins, the expected full source
commits, an actual user service manager and Xvfb. It
uses a random dedicated unit, fresh private runtime/state/prefix, original
Session/Notes binaries and actual Makepad windows. Both package manifests bind
all source-profile/resource/binary bytes. The upgraded package must contain its
complete original resource bundle; the first package may use an explicitly
verified external original bundle. For example:

```sh
mkdir -m 0700 /tmp/trill-install-example-UNIQUE
python3 -B support/ui/product/smoke_installed.py \
  --package /absolute/extracted-first/trillionnium-desktop \
  --upgrade-package /absolute/extracted-next/trillionnium-desktop \
  --expected-manifest-sha256 <first-build-manifest-sha256> \
  --expected-upgrade-manifest-sha256 <next-build-manifest-sha256> \
  --expected-desktop <first-full-Desktop-commit> \
  --expected-upgrade-desktop <next-full-Desktop-commit> \
  --expected-hepta <full-Hepta-commit> \
  --hepta-source /absolute/fixed-original-test-helper-checkout \
  --renderer makepad --makepad-resources /absolute/prepared-original-bundle \
  --runtime-root /tmp/trill-install-example-UNIQUE \
  --evidence /absolute/new-install-acceptance-directory
```

The product and test-helper sources have separate roles. `--expected-hepta`
checks the source pin in both real package manifests and their original resource
bundles; the pinned build manifests bind the actual product ELF bytes.
`--hepta-source` supplies the original
`apps/hepta-control-ui/test/x11_client_owner.py` used by this harness and may name
a different reviewed Hepta checkout. Its selection does not rebuild, repin or
relabel the installed product. Keep that helper checkout's complete commit/tree
with the evidence. The report records the harness SHA256 and the exact original
XRes helper path/SHA256 separately from the package and live process identities.

Window selection requires `libX11.so.6`, `libXRes.so.1` and a private X server
with XRes 1.2 `QueryClientIds` / `LocalClientPID`. The original helper maps
visible windows to the retained child PID through the server. A missing match
cannot advance startup; two visible windows belonging to the child are rejected.
Missing or ambiguous XRes ownership fails acceptance. Titles, classes and
client-written `_NET_WM_PID` do not establish ownership and are never a fallback.
These checks complement the live pidfd/executable checks below; they do not
establish product build provenance or physical input qualification. See the
[native harness contract](NATIVE_MAKEPAD.md#run-the-owned-window-qualification).

`--runtime-root` is required and must already exist as an empty, canonical,
user-owned `0700` directory. Choose a new short path for each attempt. The harness
checks the full Session endpoint and reserves space for a 32-character temporary
bus name under its private `TMPDIR`. Its temporary XDG runtime/state/config/cache/
data paths live under this root; evidence, package installation and the explicit
product configuration remain at their caller-selected paths. The original user
manager bus stays unchanged. A dedicated unit drop-in passes only these private
temporary paths to this test's Session and application children; it never imports
environment into the user manager.

The caller owns the short root. The harness records its device/inode and final
retained-state hashes, and leaves that directory and synthetic state available
after uninstall for inspection. It does not recursively remove or reuse it.
Existing owned-process, exact-unit/drop-in cleanup and cleanup-failure gates
continue to apply. Changing the runtime root's identity fails acceptance.

The two releases may share the same verified Rust binary build if the real
packaging change is adding the complete original resource bundle; their
content identities must differ. The harness never alters provenance to invent
an upgrade. It restores synthetic all-workspace local drafts through actual
Shell startup and normal WM close, checks Session and Notes survive Shell
restart, rejects active upgrade, starts a new Session after stopped-service
upgrade, rolls back, and uninstalls while checking retained data. Logs,
source/file identities and actual XGetImage screenshots stay in the evidence
directory. Seeded local recovery is not physical keyboard or IME evidence;
screenshots explicitly require visual review.

The manifest pins must come from the independently recorded real package build,
not be invented to bless fixture binaries. The harness also measures actual
Session, Shell and Notes `/proc` executable bytes/inodes under a live pidfd and
records process start ticks. It checks the Notes application incarnation and
actual process identity across Shell restart, and checks `--renderer makepad`
in the executed Shell command line. After rollback it launches a real Makepad
window and a real Notes process from the restored package, verifies a new
Session generation and preserved workspace text, then performs uninstall.

Each Shell startup must also produce nonuniform pixels from its exact XRes-owned
XID within the existing 25-second startup deadline. Mapping a window or sleeping
for a fixed delay is insufficient. The harness retains a pidfd throughout the
observation, checks its start time and executable identity, raises only that
verified window, and invokes the original native `capture.py` with the remaining
deadline. It rechecks XRes ownership after `XGetImage`. A pure black or other
single-color capture cannot satisfy the frame gate. Notes gets independent
window/first-frame evidence after its initial launch, after Shell recovery with
the same Notes process/window, and after rollback. Per-window PNGs provide that
evidence; separate root-window PNGs are context only. Nonuniform pixels do not
prove readable text, correct fonts, a completed human visual review or physical
input. The report keeps those qualification flags false.

Only this test's child environment drops inherited `TRILL_`/`HEPTA_` lane
locators. The actual HOME and original user service bus remain intact. A unique
owned unit drop-in unsets those names for its own Session; the user's manager
environment and existing services are never rewritten. The harness captures
only filtered variable names, never manager environment values. A newly added
unisolated manager lane or an actual process inheriting one fails acceptance.
The dedicated drop-in is removed with exact-byte ownership checks, and cleanup
failure cannot return a passing acceptance status.

The separate real acceptance uses the actual five built Rust programs, an
isolated installation/unit/runtime and an owned X11 or Wayland display. It must
verify the same Session identity across Shell restarts, readiness errors,
stopped-service upgrade/rollback, source readback, draft/composer recovery and
uninstall retaining state. Only executed receipts can qualify those behaviors.
Physical input, full Makepad resources, production authority, Asterinas GUI,
mobile BSP and G2 remain their existing independent implementation boundaries.
