# Packaging internals

For installation and source builds, use the [Arch/Omarchy guide](arch/README.md).

The native package split is `droidloom-runtime` and `droidloom-image`, with
optional hardware-service packages. `droidloom-runtime` owns the supervisor,
CLI, user lifecycle service, private Android endpoint, and ordinary Wayland
presenter. Denial has no Droidloom package dependency, plugin, service drop-in,
or product-specific environment.

The development endpoint accepts a dynamic peer PID because Android Composer's
host PID is learned only after the cell starts. Kernel `SO_PEERCRED` UID and
GID remain exact. Production packaging must replace the temporary PID wildcard
with supervisor-to-presenter PID registration.

Package lifecycle tests must use a disposable root filesystem and compare
files, units, mounts, namespaces, cgroups, links, addresses, routes, nftables
objects, processes, and devices with the pre-install baseline. Normal removal
retains user Android data. Data deletion must be a separate explicit user operation.

Paths and ownership are frozen in
[`docs/contracts/runtime-layout-v1.md`](../docs/contracts/runtime-layout-v1.md).

## Lifecycle units

`systemd/system/droidloomd.service` owns the privileged, signal-aware Rust
daemon. The daemon holds the exact namespace child process and cleans its
network objects and ephemeral mount paths on normal stop. The namespace owner
also has a parent-death signal, so a daemon crash cannot leave Android running;
the next start removes only deterministically named Droidloom residue before
constructing the cell again.

`systemd/user/droidloom.service` owns the complete graphical runtime. Packaging
leaves it disabled by default. `droidloomctl start` starts the complete runtime
on demand; `droidloomctl stop` stops the presenter, catalog, and privileged
daemon. Application launches use the already-running runtime.
Its main process is `droidloom-wayland`. The service waits for the Wayland
session, connects, binds its private endpoint, and reports readiness before
`ExecStartPost` starts Android. Stopping or crashing the presenter stops the
cell as part of the same unit. The compositor remains untouched.

`systemd/user/droidloom-applications.service` is a non-privileged companion.
After the cell is ready it asks Android for enabled
`MAIN`/`LAUNCHER` activities, labels, and rendered adaptive icons, then
atomically reconciles ordinary XDG entries below
`~/.local/share/applications/` with collision-resistant `droidloom-` names. It periodically checks for package
changes while retaining the last good catalog across temporary Android
restarts. The privileged daemon never writes into a user's home directory.

The user-facing lifecycle is:

```text
droidloomctl start
droidloomctl status
droidloomctl applications
droidloomctl launch org.mozilla.firefox
droidloomctl dpi 175
droidloomctl window-mode fit-output
droidloomctl window-mode windowed --width 900 --height 1200
droidloomctl restart
droidloomctl stop
```

`droidloomctl start`, `stop`, and `restart` control the complete user service.
The internal `--cell` flag bypasses service orchestration for unit hooks and
explicit recovery. Normal application launch requires the session-managed cell,
waits for its exact PID-namespace init, and executes the packaged Android task
launcher through that namespace; it never starts Droidloom. `SO_PEERCRED`
permits only root or the exact
`host_uid` in the validated cell specification. Non-root callers can select
only root-owned, non-group/world-writable specifications below
`/etc/droidloom`; root retains an explicit development override path.

`droidloomctl dpi DPI` applies Android's standard built-in-display density
override. WindowManager persists the
value in the per-user Android data image, which the installer retains across
Droidloom upgrades and host restarts. The display's pixel canvas remains the
host output's oriented physical resolution; DPI changes UI sizing, not render
resolution.

`droidloomctl window-mode fit-output` is the default mobile policy. For a
size-less initial XDG configure, the presenter waits for the standard
`xdg_toplevel.configure_bounds` event and creates Android's first target pool
at that logical size. There is no small provisional window or visible resize.
If the compositor does not advertise bounds, the current logical `wl_output`
extent is used. The portable 480x800 fallback is used only when neither source
exists, before any buffer is published.

`droidloomctl window-mode windowed --width WIDTH --height HEIGHT` selects a
persistent desktop-style default. Add `--package PACKAGE` to set an explicit
per-application override. Stable compositor-assigned sizes are remembered for
windowed applications and constrained to later XDG bounds. Policy is read at
application creation, never from a render or input loop. Configuration lives
at `$XDG_CONFIG_HOME/droidloom/window-policy-v1.json`; automatically remembered
sizes live at `$XDG_STATE_HOME/droidloom/window-sizes-v1.json`.

## Bounded application qualification units

The normal runtime payload also contains `droidloom-native-calendar@.service`
and `droidloom-native-gallery@.service`. They are explicit root qualification
entries, have no automatic enable target, and do not start Android. Calendar
reminder retains its half-CPU, 512 MiB budget; Gallery retains its two-CPU,
2 GiB budget. Both forbid swap and core dumps and cap the complete unit at
64 tasks. The unchanged native leaf runs in a child of this exact unit, so
unit cancellation and the original child retirement cover the same tree.

An instance is the lowercase SHA-256 of one root-owned complete native runtime
plan at `/etc/droidloom/native-application-leaves/plans/calendar-reminder/`
or `/etc/droidloom/native-application-leaves/plans/gallery/`, with a `.json`
suffix. The native entry accepts exactly one matching package and route,
requires the adopted current native/source release, and calls the existing
runtime-plan dispatcher. It does not create a Main qualification, change the
control peer policy, extend the foreground owner lease, or grant acceptance
from a resource observation.

Before and after dispatch it authenticates the actual PID 1 private socket,
uses the held controller PIDFD to query its actual systemd invocation, and
checks the effective command, namespace identities, CPU affinity, resource
limits and complete-unit stop behavior. Transient units, extra lifecycle
commands, different invocations and expanded budgets are rejected. The full
controller budgets are 1,200 seconds for Calendar and 2,400 seconds for Gallery;
the original leaf business and cleanup timeouts remain unchanged.

Only an operator with an already prepared and adopted release should start
an exact instance. Preserve its native report and independently read back the
same invocation's final unit result, empty cgroup and descendant retirement.
The emitted report remains partial evidence and explicitly marks whole-app
acceptance false. Installing these unit files, a successful source build, or
a rejected precondition does not establish a working production resource path.

The component package builder already freezes all packaging inputs against
its complete baseline. Adding or changing these templates therefore requires
a complete package build; a component rebuild cannot silently reuse a payload
that lacks the corresponding unit bytes. The separate developer installation
using release symlinks does not meet this entry's canonical regular-file
contract. The ordinary package owner or the direct runtime installer must
place the actual current executable and templates at their canonical paths.

### Settings read-only page scope

The same normal payload also stages `droidloom-native-settings@.service` with
profile `settings-pages`. It accepts only `com.android.settings` and the
`settings_supported_pages` route, from its independently adopted index-13 source.
Its exact root plan lives under the `settings-pages` directory beside the other
fixed plans. The two-CPU, 2-GiB, zero-swap, 64-task scope uses CPU 20/21 and a
1,500-second controller ceiling. The nested native leaf has a 900-second outer
ceiling; its original business and cleanup lease remains 600 plus 120 seconds.

The result may credit only `settings.pages` after five page observations, two
owned launches, two normal closes and complete original cleanup. Settings value
round trips, permission UI and all whole-app gates remain pending. No template is
automatically enabled, and no source or resource observation creates acceptance.

The current canonical application source bundle is rooted at
`/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1`.
New Main and business qualifications use the v2 protocol and
`/var/lib/droidloom/qualification/pocket4`; old home-directory receipts cannot
qualify the new mapped Main or its held guest-entry helper.

## Immutable APK input

The installed `/usr/bin/droidloomctl` public client uses `install APK --user 0`
or `install-multiple BASE SPLIT... --user 0`. Keep the reviewed source, signer,
version and complete split-set pins alongside the original APKs. Root-owned
qualification copies remain below `/var/lib/droidloom-qualification/NAME/inputs`
and require the existing administrative authorization to read them. The public
control domain gains no access to home directories or temporary disk files.

Before connecting, the client holds each original regular file, checks its APK
header and unchanged inode metadata, and copies at most 32 inputs and 2 GiB into
one anonymous payload within a fixed preparation deadline. It creates the payload
with `MFD_NOEXEC_SEAL`, fixes its mode to 0400, and seals writes, growth, shrinkage,
executable-mode changes and further seal changes. It then reopens that same held
inode read-only and sends only this description through `SCM_RIGHTS`. Both single
APK and split installation use this path; source files are never passed to or
opened by the broker. Unsupported kernel APIs fail before a package session.

The early-owner server checks the received inode, exact byte count, anonymous
`tmpfs` backing, complete seals, read-only access and close-on-exec flag before
using its existing typed Android package-session authority. The policy permits
the broker to use the public client's descriptor and read only the dedicated
payload type; opening, modifying, mapping and executing the payload remain
denied. Source-copying and immutable transport do not authenticate an APK:
Android still verifies package signatures and installed signer continuity. The
normal install sequence retains its owner/epoch checks, complete split writes,
atomic commit and explicit abandonment on failure. It does not uninstall an old
package or erase application data to work around an incompatible signature.

## Explicit launch observations in runtime plans

The existing `droidloom-applications --runtime-plan PLAN
--expect-runtime-plan-sha256 SHA256 --expect-app-count COUNT` dispatcher accepts
schema 3 for an explicit launch-only route. Keep the complete selected application
set, including blocked applications, and obtain `expected_epoch` from the actual
current runtime. The existing Main receipt, gate registry, source receipt and
runtime-plan pins remain required. A material inventory or an APK manifest cannot
supply a runtime epoch or qualify Main.

An application row selects this route with `launch.specification`, a `FilePin`
containing the absolute cell-specification `path`, exact `bytes` and `sha256`, and
`launch.component`, the exact package/activity component. It also requires the
complete `expected_input`: version code, every APK name/length/digest and the
independently reviewed source/signature receipt. A component extracted from the
selected APK is only a candidate: its current enabled state and installed identity
must still be observed. A row cannot select both `launch` and a business `leaf`,
or combine this route with the separate Firefox public-browser invocation.

The route executes through the existing typed supervisor control API. It first
reads the current enabled `MAIN`/`LAUNCHER` catalog and requires one matching
normalized component from the selected package. It checks the actual running
owner, then inspects PackageManager identity, APK bytes, Android user/UID and
runtime epoch against the selected input. Gallery retains its existing whole-image
custody requirement. After rechecking its pinned inputs, it sends one typed
`Launch` request and validates the returned inspection and the original owned task
binding. A final inspection must still agree with the same owner and epoch.
There is no shell command, task-ID authority, automatic retry, or replacement of
signature, version, selector or source validation.

A successful observation has status `launch_only_business_pending`, increments
`launch_only_invocations`, and records `launch_observation` with the exact catalog
component and the supervisor's observed object, composer-display, Android-display
and task binding. Those numeric values describe the observed result; they grant
no independent authority over a task. This route does not close an application,
prove that an existing activity was replaced by a fresh task, or reopen it.
`close_observed`, `reopen_observed` and `fresh_task_proven` remain false.

Launch-only observations leave every business/common gate pending, contribute no
accepted application, and remain included in `unsupported_business_flows` until
a dedicated business route is available and qualified. The report keeps
`accepted_applications` at zero and `runtime_qualified` and `production_ready`
false; the CLI prints the partial report and exits with its existing incomplete
acceptance error. Preparing route JSON, compiling the dispatcher or observing one
owned launch does not establish application production readiness. A failure after
a launch preserves any observed binding for reconciliation and must not trigger
an automatic replay.

## Original-window observation and interaction

The kernel-first production broker also exposes a separate, finite qualification
interface over its existing presenter channel. Start from an actual
`droidloom-applications --inspect-package PACKAGE --user 0` observation, review
its PackageManager identity against the selected APK and source/signature pins,
and save only that command's `observation` object as a pinned
`ApplicationInspection` JSON file. The saved file cannot supply authority: the
broker checks the current installed identity, Android UID/user, runtime epoch,
enabled launcher catalog and admitted cell selection again.

```sh
droidloomctl --json launch-owned PACKAGE/ACTIVITY \
  --expected /absolute/reviewed/inspection.json --expect-sha256 SHA256 \
  --spec /etc/droidloom/cell.json
droidloomctl --json window LEASE_HEX observe
droidloomctl --json window LEASE_HEX capture
droidloomctl --json window LEASE_HEX tap X Y
droidloomctl --json window LEASE_HEX back
droidloomctl --json window LEASE_HEX stop-capture
droidloomctl --json window LEASE_HEX close
```

`LEASE_HEX` encodes the returned `window.lease` byte array as exactly 32
lowercase hexadecimal digits. It selects an already retained original lease;
it is not a task identifier or a transferable process capability. The broker
holds the original presenter's live PIDFD and registration nonce before issuing
the normal typed launch. Binding requires a new real `CreateTask` event after
arming and the matching real `BindTask` event for that package. The presenter
also holds the original Wayland surface and toplevel objects and rejects
replacement objects even if they reuse a numeric task/object value.

`capture` copies pixels from an actual composed submitted frame after waiting
for its original acquire fence and using normal DMA-BUF CPU synchronization.
The response's `window_image` contains the complete bounded PNG as base64, its
SHA-256 and the original frame metadata. Bounded parts must agree on the same
snapshot, object, task birth and live presenter session; mixed or incomplete
parts fail. Inspect the decoded image to determine what the application
actually displayed. Frame counts and `host_last_input_serial` describe host
submission/transmission; they do not acknowledge Android input processing or
prove a business result. Active direct-layer streams are explicitly unsupported
by this capture path and cannot be represented by an old composed frame.

Tap and the finite text/navigation key operations require the original focused,
mapped window, valid bounds, and no conflicting physical input. They use the
existing input transport. They neither authorize transactions or communications
nor establish that an application completed an action. Stop capture before
ordinary stability or performance measurements: the explicit qualification
lease initially captures composed frames and therefore adds fence waits and PNG
encoding. `stop-capture` releases copied image state and disables further
acquisition while retaining the same lease for observation, input and normal
close. Ordinary production launches do not enable this qualification capture.

Close uses the normal task-close path and waits for both the real original
`DestroyTask` event and removal of the original native window. Closing a control
socket or merely requesting a close is not completion. A reopen requires a
separate successful `launch-owned` with fresh current inspection after the prior
original task was destroyed. If a launch or bind fails or times out, the broker
keeps its armed original lease: it does not replay the launch, clear ownership
or infer destruction from elapsed time. Reconcile the real task/owner state;
when the task cannot be reconciled, retire and restart through the normal
original-owner lifecycle and obtain a new inspection and runtime epoch.

This interface adds execution and observation primitives. It does not change
the schema-3 launch-only report, grant any common or business gate, or accept
an application. All six common gates and the complete application's business
profile still require actual runtime evidence, including data continuity and
authorized account/dependency coverage.

## Build and installation ownership

The Rust package builder produces `droidloom-runtime` and `droidloom-image`.
Pacman owns their system files. Rust package support handles first-user setup,
service permissions and transaction hooks. Upgrades stop Droidloom and leave it
stopped; removal retains application data. See the [package guide](arch/README.md)
for commands and exact administrator requirements.

The [Rust updater](../tools/droidloom-update/README.md) also supports a separate
developer installation with versioned releases, transactional activation and
rollback. It refuses to overwrite pacman-managed files. Moving an older developer
installation to pacman needs an explicit migration, not blanket overwrite flags.

## Component installation helpers

`install-runtime`, the component installers and `verify-bundle` support focused
developer installation workflows. The `ime/setup` and `home/setup` scripts run
inside Android and are also used by the Rust assembly.

## Component compatibility

The Rust builder checks required components, executable permissions, architecture
and compiled input ABI metadata, including alternate input-bridge copies. It
accepts compatible byte differences and extra files; pinned upstream inputs
retain their integrity checks. The pacman workflow uses this builder to produce
a matched runtime/image pair.

The retained ARM64 installer uses a sealed manifest with file hashes, modes,
symlinks and input ABI checks. This is specific to that installer, not an added
gate for the private pacman preview. Its Python regressions run from the Rust
repository-contract suite.

Compiled input markers do not cover every private ABI. Package lifecycle checks
must be complemented by live input and resize validation; successful Android boot
or catalog enumeration alone does not establish interaction compatibility.
