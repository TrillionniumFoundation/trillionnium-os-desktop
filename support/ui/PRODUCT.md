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
python3 -B support/ui/product/smoke_installed.py \
  --package /absolute/extracted-first/trillionnium-desktop \
  --upgrade-package /absolute/extracted-next/trillionnium-desktop \
  --expected-manifest-sha256 <first-build-manifest-sha256> \
  --expected-upgrade-manifest-sha256 <next-build-manifest-sha256> \
  --expected-desktop <first-full-Desktop-commit> \
  --expected-upgrade-desktop <next-full-Desktop-commit> \
  --expected-hepta <full-Hepta-commit> \
  --renderer makepad --makepad-resources /absolute/prepared-original-bundle \
  --evidence /absolute/new-install-acceptance-directory
```

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
