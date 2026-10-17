# A10 Linux host build/run notes

This is an executable Rust GUI prototype under the Linux host compositor.
It is NOT booted under Asterinas, NOT native HOS2, and NOT a full compositor.

Host prerequisites: Rust stable >=1.83 with Cargo, network/cached crates,
Linux Wayland (or X11), OpenGL/Mesa including llvmpipe for software rendering,
libxkbcommon, a system Chinese font, and a Chinese IME such as Fcitx5.

From the repository root:

~~~sh
cargo build --manifest-path ui/Cargo.toml --workspace --bins --locked
cargo test --manifest-path ui/Cargo.toml --workspace --locked
cargo test --manifest-path support/ui/Cargo.toml --locked
cargo test --manifest-path tests/ui/Cargo.toml --locked
cargo fmt --manifest-path ui/Cargo.toml --all -- --check
~~~

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

The A00-owned GitHub workflow uploads the A10-owned `$RUNNER_TEMP/a10/`
directory as a CI artifact. After Rust build, all three test suites and strict
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
are only packaged after the three actual Cargo suites and Rustfmt pass.
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
reattachment. For a running old app with a stale socket epoch, Inspector can
offer **Launch NEW window (not reattach)** when the Session is online. This
starts a fresh task, does not restore unsaved data and does not silently kill
the old process. Real Chinese IME, physical
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
Chinese IME preedit without discarding uncommitted text. Cancellation
sends SIGKILL and reports requested vs confirmed states separately.
For command-line cancellation, first read the session_instance from
trill-ctl snapshot; use trill-ctl cancel <task-id> <session-instance>.
A command from a previous session generation must be rejected; do not
re-resolve an old task ID into the new session.
Run an alternative X11 test only as an independent host compatibility probe.

Fail closed: missing or world-readable XDG_RUNTIME_DIR rejects startup.
Missing app executable is reported FAILED, not a successful launch.
A missing session is rendered OFFLINE and existing status is stale.
`trill-ctl launch` now exits nonzero if the session reports a failed spawn,
partial or unknown state, even when JSON transport succeeded. A zero exit
for Running acknowledges only host process creation, not a rendered window
or final AI-task completion. `cancel` may return zero when SIGKILL has
been requested but not yet observed; inspect the later session snapshot.

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
