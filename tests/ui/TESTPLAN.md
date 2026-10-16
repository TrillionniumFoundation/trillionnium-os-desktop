# A10 test matrix and provenance

Automated Rust commands (from repository root):
- cargo test --manifest-path ui/Cargo.toml --workspace
- cargo build --manifest-path ui/Cargo.toml --workspace --bins
- cargo fmt --manifest-path ui/Cargo.toml --all -- --check

These are **commands to run**; command completion must be recorded separately.
On a CI host, `check-host.sh` saves `$RUNNER_TEMP/a10/rustfmt.patch` when
the strict rustfmt check fails, then exits nonzero. It never reports success
until that patch is reviewed, committed, and rerun.
Unit coverage:
- no Pending -> Completed shortcut
- distinction among pending/running/partial/unknown/cancel_requested
- Chinese UTF-8 roundtrip
- synthetic egui IME preedit/commit and focus switching (not a live Wayland IME test)
- chat workspace explicit app actions linked to observed process task cards
- oversized/truncated IPC frames and unknown statuses
- successful observed host child exit
- live host child cancellation without GUI: real /bin/sleep process receives
  SIGKILL, is reaped, and CANCEL REQUESTED never counts as final success;
  test Drop guard kills/reaps any child left alive after an assertion failure
- failed executable path and nonzero/signal exit mapping
- bounded private socket IPC and reconnection without terminating the session
- a connected but idle same-UID Unix socket peer times out in <=500ms;
  real Snapshot request resumes promptly rather than blocking task reaping
- failed host spawn, partial/unknown task and rejected IPC return nonzero
  trill-ctl process exit status; a running child means only host launch ACK
- invalid app/workspace enum, including ../path command-injection strings,
  rejected before any host process can spawn
- headless Weston + software Mesa runner: create and destroy a real Wayland
  compositor session in a private directory; require successful wayland-info
  registry round-trip (socket creation alone is insufficient), then run the two-app smoke;
  compositor-mapped surfaces/real GPU/Chinese IME are still NOT attested
- isolated Wayland smoke: shell plus two independent native app processes (Notes
  and Calculator), cross-workspace identities, both explicit first-egui-frame
  markers, and shell restart with surviving children
  and observed cancellation (requires actual host run)
- independent idle-time process reaping when no shell client is connected
- a child GUI first-update layout completion signal must match the exact
  parent-owned marker; host process spawn alone never asserts rendering
- session process restart from stale Unix socket: fresh instance ID, no fake
  reattachment or completion of previous child history
- session generation comes from 128-bit /dev/urandom (no PID/time fallback)
- stale-generation launch and cancellation targeting reused task IDs are
  rejected BEFORE any mutation; task/action responses carry source generation
- integration test cancels/reaps the restarted generation child before
  tearing down the session, even when no Wayland display is present
- GUI bridge coalesces hundreds of passive snapshot requests while preserving
  action queue capacity; user action is not starved by periodic status polling
- force a blocked transport, fill the eight-slot user action queue, and assert
  the next request is rejected rather than reported as queued
- overlong host IPC request must fail closed without creating a child
- full action queue reports NOT QUEUED and must not show a misleading
  launch-request notification or claim a PID
- no oversized outbound IPC frames; bounded process/task history, no eviction
  of unknown or in-flight tasks; explicit backpressure when full

Manual Linux Wayland test required after build:
1. Start an external Wayland compositor, confirm WAYLAND_DISPLAY and
   XDG_RUNTIME_DIR is private (0700), start trill-session separately.
2. Start trill-shell; type Chinese via a system IME into chat and Notes,
   verify candidate window, selection, composition, focus changes and no
   duplicate characters. UTF-8 unit roundtrip is NOT an IME acceptance test.
3. In each workspace launch Notes and Calculator; rearrange/focus/resize
   independent windows, switch tasks, try scaling at 100/150/200%.
4. Close app window: session should observe exit and distinguish code 0
   from failure. Try Cancel and confirm CANCEL REQUESTED before observed
   termination; never mark success from UI text.
5. Kill ONLY trill-shell then relaunch; session and independent clients
   should remain. Kill compositor separately: record actual disconnect
   and reconnection behavior, never promise Wayland client survival.
6. Exercise clipboard permission, notification, screenshots/portals, GPU
   reset, Android display/input; mark NOT IMPLEMENTED until real integration.
7. Stop session and observe shell offline state; do not show fake completion.
8. Run Linux X11 fallback independently; no claim of Xwayland isolation.

Local static evidence: the headless script Bash parser accepted its syntax,
and its missing-Weston preflight returned exit status 2; mirrored YAML and
Cargo manifest parse checks passed. This does NOT imply Rust or UI pass.
The A00 handoff workflow can retain host log/lockfile evidence even on failure.

Current host validation (A10 source checkout, 2026-10-16) is available locally:

- `cargo build --manifest-path ui/Cargo.toml --workspace --bins --locked --offline`
  passed.
- `cargo check --manifest-path ui/Cargo.toml --workspace --all-targets
  --locked --offline` passed.
- `cargo clippy --manifest-path ui/Cargo.toml --workspace --all-targets
  --locked --offline -- -D warnings` passed.
- UI unit/binary tests passed (43 tests), `support/ui` contract tests passed
  (17 tests), and `tests/ui` contract tests passed (8 tests).
- Rustfmt checks, `git diff --check`, and Bash syntax checks passed.

The full UI all-targets test command is not green in this sandbox because
`ui/session/tests/ipc_reconnect.rs` cannot create an AF_UNIX socket here
(`EPERM`); an independent Python probe confirms the same kernel restriction.
This is an environment limitation, not evidence of a UI lifecycle failure.
No target Rust kernel boot, physical GPU, compositor restart, or live Chinese
IME test was run or claimed.

A10 host preflight evidence is recorded in
[2026-10-16-host-preflight.json](evidence/2026-10-16-host-preflight.json).
The three checked Bash scripts were byte-for-byte confirmed using Git blob
hashes; Cargo/Wayland tests remain blocked and were NOT reported as passed.

- private socket directory created atomically with 0700, never 0755 then chmod;
  symlink redirection remains rejected (Linux-host-only invariant)

- XDG_RUNTIME_DIR and existing UI socket directory must be exactly 0700,
  rejecting unreadable or non-writable modes such as 0500 in addition to 0755

- malformed/invalid JSON socket peer must still cause completed host child
  reaping; invalid-request flooding cannot indefinitely defer process cleanup

- executable Linux /proc cleanup regression runs before Cargo: two sibling
  processes from different private runtimes; only the owned one is terminated

Host-only execution evidence: [process cleanup regression](evidence/2026-10-16-process-cleanup.json)
ran 25/25 on the isolated Linux container with exact blob hashes. This
validates *only* PID/runtime-scoped cleanup; no Cargo/Wayland pass is claimed.

- Scoping helper must exit promptly with observed SIGTERM (status 143), not
  succeed after sleep exits normally. Also preserve a same-binary/different
  runtime process and a different-binary/same-runtime process (host-only).

- Reproduce a REAL zombie via controlled fork/waitpid: kill -0 reports PID
  present but host_process_alive MUST reject the Z state before reaping; the
  supervised child is always reaped (Linux host only, no GPU/Cargo involved).

- shell draft memory is fail-closed: full history preserves oldest user text
  and unsubmitted composer; >16 KiB UTF-8 entries reject without truncation,
  valid Chinese drafts are stored exactly once (no Hepta request implied)

- Opt-in local-only draft export/import: XDG state directory exactly 0700,
  private 0600 JSON file, bounded 4 MiB and <=127 entries, no automatic
  persistence or Hepta calls; import refuses a nonempty chat/composer.
  Atomic save must preserve prior snapshot on rejected invalid input,
  including a zero-draft export; malformed/schema-mismatch files and
  symlinks are rejected. PLAIN TEXT.

- Host validation still checks rustfmt on the exact source checkout after
  any Cargo failure; the non-green job preserves rustfmt-check.log and
  rustfmt.patch in the A00 CI artifact without hiding compiler diagnostics.

- Explicit export refuses while the composer contains unsaved text, so a
  seemingly successful backup can never silently omit the current input.

- CI entrypoint control flow validated on an exact-Git-blob shell mirror:
  compiler exit 53 is preserved even if formatter fails; format-only failure
  exits 1; missing Cargo exits 127. Mock-Cargo cases are explicitly NOT
  Rust compilation. See evidence/2026-10-16-ci-control-path.json.

- Linux local draft import opens O_NOFOLLOW and validates the actual
  opened file's mode/size, not only an earlier path stat; rejects raced final
  symlink swaps (not a same-UID security boundary).
- private draft import rejects world-readable (0644) or truncated snapshot;
  import is refused if the existing conversation or composer has any content

- Console/Logs is a real read-only native UI view of observed host task
  PID/state/first-egui-layout + volatile shell notices; no fake shell command
  execution, Hepta success, privileged audit-trail or persistent task ledger.
  Rust tests assert UNKNOWN stays UNKNOWN and exit 0 isn't a Hepta result.

- Linux session service startup obtains advisory nonblocking exclusive flock
  before inspecting or deleting a stale Socket; a competing supervisor must
  fail with WouldBlock. Lock survives as a safe on-disk file and releases at
  process death; symlink lock paths are rejected without modifying targets.

- spawn two REAL Linux trill-session executables in the same private runtime:
  the second must exit specifically on kernel flock EWOULDBLOCK, without
  unlinking the original live session socket, and the first still serves the
  same generation ID (headless Cargo integration test; NOT run locally).

- Linux-host-only subprocess flock gate (no Cargo): separate process blocked
  by nonblocking LOCK_EX, kernel releases lock after SIGKILL of owner, and
  O_NOFOLLOW rejects a symlink without changing its target. This is Linux
  syscall behavior, not proof that the Rust supervisor compiles or ran.

- User-opt-in local draft exporter rejects preexisting backup files whose
  permissions are not exactly 0600 and propagates metadata errors other than
  NotFound; private atomic rename now synchronizes the containing directory.
  This is a Linux host filesystem durability hardening step, not crash-proof
  data recovery or a trusted A05 portal. Rust tests remain unexecuted until CI.
