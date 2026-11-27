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

### Settings pages and one reversible value

The normal payload stages `droidloom-native-settings@.service` with profile
`settings-pages`. It accepts only `com.android.settings` and the
`settings_supported_pages` route, from its independently adopted index-13
source. The existing unit, CPU/memory limits and original business/cleanup lease
remain required.

The r2 cohort's v3 source performs five fixed page routes, nine UI observations,
two owned launches and normal closes, and one reversible user-0
`system/font_scale` transaction. It records the original provider string or
absence, checks the actual resource configuration, observes the changed value
after close and reopen, and restores only its own still-current value. An unknown
dispatch or a third-party change cannot authorize another write. The parser must
verify the exact v3 facts together with actual Main, held runtime/data custody,
execution and complete retirement before evaluating `settings.pages` or
`settings.roundtrip`. Permission/account interfaces and whole-app acceptance
remain outside this result. Neither a saved result nor installation grants credit.

### Separate immutable native leaf cohort

`cp3a-20261126-apps-r2` is a distinct, reproducible cohort. It preserves the
historical r1 commitments as history; it does not claim to reconstruct the four
missing later r1 entrypoints. The compiled recipe explicitly describes every
recovered source, path and dependency-pin change, the seven reviewed Settings
sources, the real held-user-namespace argv repair, and the admitted IHG input.
The selected helper is the recovered original 3,972,024-byte ELF with SHA-256
`67cfd1c212e9f40ce3f0ff7be856a05f8189c674cbfa270757a672ea596a6c3f`.
Its historical normal build and mechanism evidence remain distinct from the
fresh Main/namespace/retirement checks required on every actual invocation.

Using the normally built CLI from the same source release, the ordinary producer
runs:

```sh
droidloom-update materialize-native-leaf-cohort \
  --input RECOVERED_PUBLIC_PACKET \
  --helper EXACT_ORIGINAL_HELPER \
  --output FRESH_STAGING_DIRECTORY
```

It verifies all 477 fixed inputs and generates 478 cohort members, 14 preparations
and ten entrypoints, plus the source manifest, exact compiled recipe and
`COHORT.tar`. The canonical ustar package has only the ordered regular
members authorized by that recipe. It is a separate release artifact; it is not
added to the 63-member host archive.

The privileged normal importer and installer is the same CLI:

```sh
droidloom-update install-native-leaf-cohort --package PUBLIC_COHORT_TAR
```

The public archive supplies bytes, not authority: no caller member/digest table is
accepted. Its held FD, complete SHA and full inode bookends are recorded. Every
header, member name, order, count, mode, length, payload digest, padding and exact
EOF must match the compiled recipe; links and extension records are rejected.
The importer creates a fresh root-owned directory under the fixed cohort parent,
writes and fully reads back all members, then atomically publishes with
`RENAME_NOREPLACE`. Failure cleanup is limited to the invocation's unpublished
files. Existing cohorts are never overwritten. The directory-input alternative,
`--input`, still requires already protected root-owned sources; ordinary
user staging is not passed directly to that route.

The only production destination is
`/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2`.
Directories are root:root 0755, ordinary members 0444 and the fixed helper 0755.
The matching source catalog and selection are compiled into the App consumer;
publication never changes a runtime plan, starts a service or creates Main or
application authority. The normal release must bind the package/materialization
receipt and actual installation result separately. The new Rust modules,
compiled recipes and embedded sources belong to the actual Cargo dependency
closure, even though the existing host install-layout names are unchanged.

### Kernel-first baseline capture

The same normal release provides a fixed capture operation:

```sh
droidloom-update capture-native-leaf-business-baseline --package PACKAGE_NAME
```

This operation requires the already running kernel-first owner and the protected
r2 cohort. The Rust producer obtains actual PackageManager and Main observations
from the authenticated normal peer, holds the target working-data directories,
and checks the selected manager and presenter against the same private release.
It runs the fixed cohort collector under one absolute deadline and the existing
owned child-retirement boundary. The collector retains the original three
read-only namespace diagnostics. The final Rust bookend obtains new PM/Main
observations, rechecks the complete installed source set and every recorded
output, and creates new baseline and qualification documents in its own private
qualification directory. There is no caller-provided result, command or hash map.

The compiled recipe includes the kernel-first comparisons and the fixed IHG
preparation inputs, binding 35 embedded source assets to 36 members. Its comparison channel is inherited only
by the five reviewed host entrypoints and their exact argument shapes. Android
commands, the namespace helper and independent monitor/display observers do not
receive it. Saved comparison documents cannot construct opaque Main authority.

Business checkpoints send a single E only after the target is actually running
and the original cleanup owner is registered. The parent uses its opaque Main
and package observations to obtain the normal native-x86_64 or Berberis mapping
fact within the same original deadline. The child receives only an acknowledgement;
the opaque facts remain in Rust. Failed observations cannot be retried or confer
identity credit; local G checks remain available for original cleanup only while
custody and the original deadline still hold. Documents picker/provider pending
state is preserved on failure. Read-only Gallery identity and preparation/capture
operations do not produce running-engine credit. These checkpoints do not claim
continuous process custody after sampling or whole-application business acceptance.

The baseline distinguishes original-to-working image lineage from the current
target package's working CE/DE directory identities. For IHG only, the normal
owner also observes the complete installed user-0 package/UID table through the
fixed `cmd package list packages -U --user 0` query. It retains shared UIDs and
every package, rejects duplicate or truncated output, and checks actual query
retirement. This table is a separate comparison projection; it does not replace
the actual target-directory or original-to-working lineage checks. Fresh query
receipts have different process identities, so the full same-epoch table is
compared while each receipt is independently validated.

### Fixed IHG preparation

After normal baseline capture, the same normal CLI exposes six fixed preparation
modes:

```sh
droidloom-update prepare-native-ihg \
  --mode MODE --request ROOT_OWNED_REQUEST_JSON --request-sha256 REQUEST_SHA256
```

| Mode | Exact request fields | Normal output |
| --- | --- | --- |
| `target-identity` | `baseline`, `qualification` | Actual IHG target identity |
| `helper-source` | `baseline`, `qualification` | Fixed helper source inputs |
| `helper-build` | `source` | Normal signed helper APK and build result |
| `helper-install` | `build`, `target_identity` | The original 13-command installation chain |
| `helper-identity` | `baseline`, `qualification`, `build`, `install`, `target_identity` | Actual installed helper identity |
| `plan` | `baseline`, `qualification`, `target_identity`, `helper_identity`, `helper_build`, `helper_install` | Fixed `ihg_london` plan |

Each request value is the actual normal artifact's `path`, `bytes` and
`sha256`. The caller cannot select an executable, argument vector, helper
package, Android user or output directory. The Rust adapter constructs the
canonical cohort entry, generates a fresh mode-specific output directory, holds
the entire installed cohort, and supplies the current opaque Main/PM and working
data context under one original deadline. Preparation is distinct from business
execution and cannot issue a business Engine checkpoint.

Helper source, build and installation require the helper to be absent from the
complete current user-0 table. Installation preserves the original 13 commands,
its single mutation and state-only instrumentation. The normal postchecks require
the target PM/Main to remain unchanged, the actual helper APK bytes to match the
normal signed build, and the complete table to differ by exactly that helper and
one previously unused UID. Subsequent helper identity and plan operations compare
that installed helper to the preserved pre-install table; they do not discard it
from the inventory or replace the baseline embedded in the helper source. The
ordinary business invocation still requires its complete actual before/after
tables to agree. The preparation CLI's private live execution object is not a
cross-process installation credential, and saved JSON cannot reconstruct it. An ambiguous dispatch or failed retirement never triggers an
automatic installation retry or uninstall.

The adapter preserves the actual child exit, stdout, stderr and held output
references. All preparation/capture/materialization results keep business
acceptance and production qualification false. The normal App owner must still
execute the actual qualified business invocation, observe any required Engine
checkpoint and complete its final custody checks. Building or installing this
software does not establish that the fixed helper toolchain or Android operation
has run.

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
