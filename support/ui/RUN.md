# A10 Linux host build/run notes

This is an executable Rust GUI prototype under the Linux host compositor.
It is NOT booted under Asterinas, NOT native HOS2, and NOT a full compositor.

The blocking A00 host workflow fixes Rust **1.88.0**, Cargo and Rustfmt.
The repository's `nightly-2026-07-21` toolchain is an additional development
environment; a pass there does not establish the 1.88.0 host gate. Required
host dependencies include network/cached crates,
Linux Wayland (or X11), OpenGL/Mesa including llvmpipe for software rendering,
libxkbcommon, a system Chinese font, and a Chinese IME such as Fcitx5.
The crates' `rust-version = "1.83"` metadata is not a demonstrated minimum
for every transitive dependency in the current lockfile.

For the Session-owned Hepta runtime observer, explicit endpoint configuration,
read-only UI behavior and its separate acceptance limits, see
[`HEPTA_OBSERVER.md`](HEPTA_OBSERVER.md). Authenticated objective submission
is not configured; Conversation remains a local draft.

The default Shell now opens Workspace / Chat with typed local draft/context
references and embedded Tasks, Context and Console tabs. See
[`CHAT_WORKSPACE.md`](CHAT_WORKSPACE.md) for the source identity model,
shared snapshot freshness rule, v2 export/legacy import and exact test limits.
Notes and Calculator remain explicit host launches; local chat actions do
not submit an objective.

For explicit host font selection, shared proportional/monospace CJK fallback,
actual Pixman screenshots and the separate live-IME gate, see
[`CJK_RENDERING.md`](CJK_RENDERING.md).

From the repository root:

~~~sh
export RUSTUP_TOOLCHAIN=1.88.0
cargo build --manifest-path ui/Cargo.toml --workspace --bins --locked
cargo test --manifest-path ui/Cargo.toml --workspace --locked
cargo test --manifest-path services/hepta-os/Cargo.toml --locked
cargo test --manifest-path support/ui/Cargo.toml --locked
cargo test --manifest-path tests/ui/Cargo.toml --locked
cargo fmt --manifest-path ui/Cargo.toml --all -- --check
~~~

These individual commands are development checks. The complete blocking host
gate is `bash tests/ui/check-host.sh`, followed by
`bash tests/ui/headless-weston.sh` for the owned compositor lifecycle gate.
The host script also requires a C compiler and GNU binutils for its explicitly
labelled fixture, Python 3, Bash, coreutils, Git, tar, and passwordless sudo
for its disposable nobody-owned Session and cross-UID negative test. The
Ubuntu package list is fixed in `.github/workflows/a10-host.yml`. All host
binary consumers and the packager honor `CARGO_TARGET_DIR`; when it is set,
replace the default `ui/target/debug` paths below with its `debug` directory.

Within an existing Linux desktop Wayland session, in terminal #1:

~~~sh
test -n "$XDG_RUNTIME_DIR" && test -n "$WAYLAND_DISPLAY"
./ui/target/debug/trill-session
~~~

In terminal #2:

~~~sh
./ui/target/debug/trill-shell
~~~

For a live Wayland-host lifecycle smoke after building run:
bash tests/ui/smoke-wayland.sh

An independent real Linux/X11 host test can be run when Xvfb, xauth,
xdpyinfo, xwininfo, xprop and the software GL stack are installed:

~~~sh
bash tests/ui/smoke-x11.sh "$PWD/ui/target/debug"
~~~

It starts its own authenticated virtual X server in a disposable runtime,
proves missing-Xauthority clients cannot connect, requires Shell and three
app windows to be X11 IsViewable, checks true Rust
egui first layouts and Shell restart with Session/app identity preservation,
and confirms actual app cancellation. With optional scrot and Python Pillow
it also captures the virtual framebuffer and checks it is not blank. A real
run against the four binaries from passing CI #39015860337 was independently
verified: 4 mapped windows, 3 live child processes, Shell restart, all 3
observed cancellations and a 1280x800 Xvfb buffer with 1532 colors. Machine
receipt: `tests/ui/evidence/2026-10-17-x11-real-host-elf.json`.
The CI host runs this as an additional **fail-if-attempted** gate when those
X11 tools are present; if absent the gate is explicitly NOT VERIFIED and
A00 must provision the host profile for mandatory X11 acceptance. None of
this proves per-trust-domain Xwayland, Wayland presentation, live IME,
physical GPU, Android or the target Rust kernel.

The A00-owned GitHub workflow uploads the A10-owned `$RUNNER_TEMP/a10/`
directory as a CI artifact. After Rust build, all host test suites and strict
Rustfmt pass, `support/ui/package-host-binaries.sh` adds
`a10-linux-host-binaries.tar.gz` and an outer SHA256 file. The archive contains
`trill-session`, `trill-shell`, `trill-app-window`, `trill-ctl`, per-binary
SHA256 sums and `PROVENANCE.txt` with exact source HEAD and toolchain.
The copies are debug builds stripped of debug symbols to limit artifact size;
they depend on compatible Linux system libraries. An independent committed
`tests/ui/test-package-host-binaries.sh` exercise runs first on the CI host:
it compiles four disposable C ELF fixtures (NOT A10 Rust binaries), verifies
the provenance and both SHA256 layers, and proves failure cannot replace an
existing archive when one source executable is missing. Real Rust executables
are only packaged after all four Cargo suites and Rustfmt pass.
The blocking host job then independently replays that newly built archive
through `tests/ui/replay-packaged-host.sh`, refusing a wrong source SHA or
unsafe tar contents before extraction. The replay launches *actual packaged
Rust executables* to check Session/CLI ownership, private IPC, singleton
flock, stale-generation rejection, observed FAILED headless GUI, and clean
restart in a private runtime without a display. Weston, live Chinese IME,
GPU, and Asterinas acceptance remain separate gates. The artifact is NOT an
Asterinas boot image, compositor, IME, native GPU gate or proof Weston passed.
Never publish it as a release simply because the binary build succeeded.

For CI/a Linux host without a physical desktop but WITH Weston, Mesa
software GL and the Rust toolchain:
bash tests/ui/headless-weston.sh
It creates a private runtime directory and targets the existing compositor
socket by absolute path. It terminates only processes started by the script.
No completion is claimed until it finishes with exit code 0. It checks
three distinct child PIDs and their first egui layout events, as well as
one completed Shell egui layout before AND after restarting the Shell.
These are process-local Rust layout observations, not compositor surface
mapping or actual GPU-buffer presentation. It also launches a separately owned Weston, kills and restarts that test-only
compositor while the same Session stays alive, and verifies that a new
Wayland client reaches its first Rust layout. The Session separately observes
the test socket disappear and reappear with a monotonically increasing
host-only observation epoch. Every successfully launched host process
records its observed socket epoch; the Shell identifies when a process predates
a compositor socket replacement but never claims a mapped or reattached surface.
The original client is recorded without any claim of lossless window
reattachment. Inspector can offer **Launch NEW window (not reattach)** only
when the old task remains RUNNING, has an observed PID and first egui layout,
the observed compositor socket epoch is strictly NEWER than launch and
Session is online; equal or older/out-of-order samples never authorize replay. Unknown/partial/cancelling
tasks are explicitly NOT eligible for this recovery shortcut. An opted-in
new task cannot restore unsaved data and never silently kills the old process.
Host process launch, NEW window and termination controls require an explicit
primary pointer click; Enter/Space on a focused button cannot activate them.
 Real Chinese IME, physical
GPU reset and target kernel boot remain separate gates.

A10 independently downloaded the successful exact-source Linux-host
[#39015860337](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39015860337)
artifact, verified the outer tarball SHA256 and all four actual ELF hashes, and
executed its **real** `trill-session` and `trill-ctl` binaries in a separate
Linux container with DISPLAY and WAYLAND_DISPLAY absent. Five checks passed:
private 0600 IPC, exclusive process lock, stale-generation cancellation
rejection, a missing-display GUI child observed FAILED (never Hepta success),
and a fresh Session instance that does not adopt old tasks. Machine-readable
host-only results and exact executable SHA256 are stored at
`tests/ui/evidence/2026-10-17-native-elf-replay.json`; it references source
`fcc57bd2`, CI artifact ID `12096301139` and archive SHA256.
**This does not prove a Wayland window, CJK candidate, GPU, A05 effect, or
Asterinas kernel boot.** Later A10 commits need separate exact-HEAD CI.

The session MUST be independently supervised or kept running in terminal #1.
Stopping/restarting the shell should not kill its owned app processes.
Use the conversation's explicit local action cards or the Apps view to
launch Notes/Calculator. Chat drafts remain disconnected from Hepta; no
language-model result can mark a task successful. Click the windows to test
compositor focus and manually test Chinese text composition. Restricted
Terminal does not run host shell commands, refuses log-forgery control,
newline and bidi formatting characters, and disables Run during an active
Chinese IME preedit without discarding uncommitted text.
Terminal Clear output and Shell draft Save / Export / Restore also require
explicit primary pointer clicks: a focused Enter/Space key while confirming
an IME candidate must not erase local output, persist incomplete text, or
overwrite a draft backup. Pure navigation remains keyboard-accessible. Restricted Terminal
executes only after an explicit primary pointer click on Run; keyboard
Enter/Space cannot activate that button, even if it has keyboard focus. Cancellation
sends SIGKILL and reports requested vs confirmed states separately.
For command-line cancellation, first read the session_instance from
trill-ctl snapshot; use trill-ctl cancel <task-id> <session-instance>.
A command from a previous session generation must be rejected; do not
re-resolve an old task ID into the new session.
Run an alternative X11 test only as an independent host compatibility probe.

Fail closed: missing or world-readable XDG_RUNTIME_DIR rejects startup.
Session host IPC also uses a single strict bounded JSON request parser;
Snapshot, Launch, and Cancel reject unknown or duplicate top-level fields
before task dispatch. An older built Rust Session was observed to accept
an unknown Snapshot field; this is a schema/validation correction rather
than a new privileged protocol. The CI now runs tests/ui/test-strict-request-ipc.py
against its newly compiled real Session binary. The identical test was
independently run against older source fcc57bd2 and correctly FAILED
on case 0 (the old process returned an unauthorized Snapshot rather than
rejecting a request with extra data). Fix acceptance requires that exact
new binary to reject all eight malformed raw requests without side effects.
A host Session must verify the effective UID owns `XDG_RUNTIME_DIR`,
its existing `trillionnium-ui` subdirectory and `session.lock`, in
addition to 0700/0600 modes: root bypasses mode bits and must not
accidentally install a privileged Session inside another user's runtime.
The strict isolated native gate `tests/ui/test-runtime-owner.sh` checks
three foreign-owner denials and a valid same-owner Session socket. The older
`fcc57bd2` CI-built ELF was independently observed to bind in all THREE
foreign-owner scenarios, each returning timeout status 124; this is
explicitly baseline failure evidence, not new-code success. See
`tests/ui/evidence/2026-10-17-runtime-owner-three-path-baseline.json`.
The upgraded exact HEAD still needs its own real CI acceptance.
Both Linux host Session and Shell/CLI connect calls use the same shared
`trill-ui-core::host_peer` SO_PEERCRED identity check. Session refuses
unknown-UID clients before parsing requests; clients refuse cross-UID
servers before sending a request or trusting a host task snapshot. These
checks compare effective UID and cannot authenticate different programs
sharing a UID. This supplements private 0700 runtime / 0600 socket
permissions, but is **not** a cryptographic user identity, same-UID sandbox,
Hepta authority, production portal or A05 trusted CapSpace. The blocking
Linux-host CI now also starts an isolated nobody-owned Session with passwordless
sudo and verifies a root client's cross-UID access is actually rejected by
the server (not merely by filesystem permissions), while nobody's own CLI
continues to work. This test's nobody-owned runtime is 0700, so an ordinary
Runner cannot directly read the PID marker. Cleanup uses scoped sudo with
kernel /proc cmdline, process name and effective UID verification to kill the
exact disposable Session even on ptrace-restricted hosts. PASS is emitted
only after teardown; an inaccessible/unverified Session is a test failure.
No production processes or files are targeted; only private /tmp paths.
Missing app executable is reported FAILED, not a successful launch.
A missing session is rendered OFFLINE and existing status is stale.
`trill-ctl launch` now exits nonzero if the session reports a failed spawn,
partial or unknown state, even when JSON transport succeeded. A zero exit
for Running acknowledges only host process creation, not a rendered window
or final AI-task completion. `cancel` may return zero when SIGKILL has
been requested but not yet observed; inspect the later session snapshot.
A headless GUI can exit between Launch returning RUNNING and a later Cancel
IPC request. In 50/50 independent real Rust ELF attempts on source fcc57bd2,
Session returned "No owned live child; no cancellation claimed". Strict host
acceptance now requires a fresh FAILED Snapshot in that race, and never
records a fake cancellation or inferred Hepta success.

A previous GitHub Actions host run (38932065166) completed the Rust build,
unit-test and Weston lifecycle steps; its overall result was FAILED because
the final offline Cargo metadata gate lacked a target-only Android crate.
The host script now prefetches all locked target packages; current-head CI
must independently prove the fix. No live Chinese candidate/focus acceptance
was performed: in Restricted Terminal Enter cannot run a command, so IME
candidate confirmation requires an explicit Run click afterward.

Still missing: current-head green CI, automated live IME, real display-driver
attestation, native HOS2/Hepta bridge, trusted portal, owned compositor,
per-domain Xwayland, Android buffer/fence runtime, and target kernel boot.

`support/ui/src/android.rs` contains only the pure consumer state model and
contract tests; it is not Android runtime evidence.
Do not extrapolate host process exit code 0 to successful Hepta operations.

Optional **user-triggered** draft backup: click “Export drafts to local file”
to write unencrypted JSON at `$XDG_STATE_HOME/trillionnium-ui/local-drafts-v1.json`
(or `$HOME/.local/state/trillionnium-ui/` if XDG_STATE_HOME is unset).
The application-specific directory is 0700 and the regular file is 0600.
Nothing is autosaved or uploaded to Hepta. Restore is accepted only with an
empty local chat/composer, never overwriting active unsent input. These are
host-user files, NOT an A05 portal or cross-workspace secure storage service.

Export is deliberately rejected while the conversation composer contains
unsaved text. Use “Save local draft” first; there is no implicit text loss
or automatic conversion to a Hepta execution request.

The separate “Console / Logs” tab shows read-only, last-observed host process
status and volatile local shell notices. It does NOT execute arbitrary shell
commands or claim authenticated Hepta audit logs. All displayed status is
host-only and may be stale when the Session is offline.

Local draft import validates the *opened* 0600 regular file using Linux
O_NOFOLLOW, and refuses symlinks rather than trusting a prior path-only check.
This is a host safety guard, not an authenticated A05 portal or same-UID
adversarial isolation guarantee.

A single XDG_RUNTIME_DIR can run only one `trill-session` supervisor. A
second starter fails fast on the held `session.lock` flock rather than
touching the active service Socket. After abnormal Session termination,
the kernel automatically releases flock and the next startup may recover
the stale Socket. The lock file remains 0600 and never stores secrets.

For a second export, an existing backup must still be a regular file with
0600 permissions; an insecure/missing-permissions check fails instead of
silently overwriting it. Successful atomic rename is followed by an fsync of
the containing directory. If that fsync fails after rename, export reports
that **durability is unconfirmed**; inspect the local file rather than
assuming the older backup survived. Plaintext data has no encryption or
same-UID protection.
