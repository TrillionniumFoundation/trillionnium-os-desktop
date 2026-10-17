# A10 test matrix and provenance

Automated Rust commands (from repository root; the blocking CI
`tests/ui/check-host.sh` now runs all three A10-owned Cargo test suites):
- cargo test --manifest-path ui/Cargo.toml --workspace --lib --bins --locked --offline
- cargo test --manifest-path support/ui/Cargo.toml --locked --offline
- cargo test --manifest-path tests/ui/Cargo.toml --locked --offline
- cargo build --manifest-path ui/Cargo.toml --workspace --bins --locked --offline
- cargo check --manifest-path ui/Cargo.toml --workspace --all-targets --locked --offline
- cargo clippy --manifest-path ui/Cargo.toml --workspace --all-targets --locked --offline -- -D warnings
- cargo fmt --manifest-path ui/Cargo.toml --all -- --check
- cargo fmt --manifest-path support/ui/Cargo.toml --all -- --check
- cargo fmt --manifest-path tests/ui/Cargo.toml --all -- --check

The UI `--all-targets` test command is also attempted in host validation, but
the sandbox denies AF_UNIX socket creation (`EPERM`) in
`ui/session/tests/ipc_reconnect.rs`; that limitation is recorded below.
The host script prefetches every locked package before its post-test offline
metadata gate, so target-specific lock entries cannot fail reproducibility
after a successful Linux build. These commands never claim a Wayland
compositor, live IME, GPU, or target kernel pass.
On a CI host, `check-host.sh` saves `$RUNNER_TEMP/a10/rustfmt.patch` when
the strict rustfmt check fails, then exits nonzero. It never reports success
until that patch is reviewed, committed, and rerun.
The same blocking host gate stages an actual Linux ELF binary archive only
after all three Cargo tests and strict Rustfmt pass. The archive and its
SHA256 contain four built Rust programs and their build/source provenance,
not a Weston, Chinese IME, GPU or new-kernel acceptance certificate.
Unit coverage:
- A10-owned `tests/ui/test-package-host-binaries.sh`: independent C ELF fixture
  actually executes Linux packager; verifies 4 files, source provenance,
  inner/outer SHA256, preservation of prior archive on missing executable,
  and rejection of relative destinations (NOT Rust or Wayland success)
- strict HOS2 read-only UI adapter: opcode/payload pairing, request-id
  correlation, response opcode matching, and hidden mutating payload refusal
- shared A02 `Request::encode` preflight before any transport exchange and
  `Response::validate_for` for boot ID, revision, timing, delivery sequence;
  negative fixtures must never be reported as owner observations
- read-only adapter pins the first successful *observed* boot and rejects
  subsequent cross-boot results; a rejected response never pins the boot
- bounded (1024) permission observation cache, disconnected-owner invalidation
  with revision tombstones, scope-local invalidation, revoke-at-capacity and
  SAME-revision conflicting grant poisoning to Unknown (including replay)
  fail-closed regressions
- no Pending -> Completed shortcut
- distinction among pending/running/partial/unknown/cancel_requested
- Chinese UTF-8 roundtrip
- a pure Rust IME preedit/commit and focus ownership model (not an egui
  backend or live Wayland IME test)
- oversized restricted-terminal UTF-8 paste refused before it reaches the
  rendered command log; no auto-execution on Enter
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
  registry round-trip (socket creation alone is insufficient), then run the multi-app smoke;
  compositor-mapped surfaces/real GPU/Chinese IME are still NOT attested
- metadata-only Wayland socket observation with fail-closed missing/non-socket
  status and monotone per-Session observation epoch; each app records its
  launch socket epoch. The Shell explicitly distinguishes old-client socket
  change from new-client launch without ever claiming surface reattachment
- real headless Weston crash/restart while the independently supervised Session
  retains its generation and child identity; a newly launched Wayland app must
  complete its egui layout and be explicitly reaped. A pre-crash client is NOT
  assumed to reattach, and this is not a physical GPU reset.
- shell first egui layout marker before and after Shell restart (exactly once
  per Shell process; not a compositor-presented frame)
- isolated Wayland smoke: shell plus independent native app processes (Notes,
  Calculator, and Restricted Terminal), cross-workspace identities, explicit
  first-egui-frame markers, an externally killed child observed as FAILED with
  exit detail, and shell restart with surviving children plus observed
  cancellation (requires actual host run)
- independent idle-time process reaping when no shell client is connected
- a child GUI first-update layout completion signal must match the exact
  parent-owned marker; host process spawn alone never asserts rendering
- a broken Shell stdout leaves UI/session running without repeated writes;
  readiness polling treats genuinely pending frames as normal, not exceptions
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
   duplicate characters. Verify Notes and Calculator visibly report the active
   keyboard-focus target. In Restricted Terminal, type "echo 你好" via Chinese
   preedit, press Enter to select a candidate: command MUST NOT execute merely
   because Enter moved focus; only clicking Run can execute the committed text.
   Test a >512-byte pasted command: error should be short and no pasted content
   may enter the scrollback. UTF-8 unit roundtrip is NOT IME acceptance.
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
- UI unit/binary tests passed (45 tests), `support/ui` contract tests passed
  (26 tests), and `tests/ui` contract tests passed (8 tests).
- Rustfmt checks, `git diff --check`, and Bash syntax checks passed.

The full UI all-targets test command is not green in this sandbox because
`ui/session/tests/ipc_reconnect.rs` cannot create an AF_UNIX socket here
(`EPERM`); an independent Python probe confirms the same kernel restriction.
This is an environment limitation, not evidence of a UI lifecycle failure.
No target Rust kernel boot, physical GPU, compositor restart, or live Chinese
IME test was run or claimed.

A10 host preflight evidence is recorded in
[2026-10-16-host-preflight.json](evidence/2026-10-16-host-preflight.json).
That file is the historical pre-Cargo preflight record. The exact-head Rust
validation is recorded separately in
[2026-10-16-rust-validation.json](evidence/2026-10-16-rust-validation.json).
The checked Bash scripts remain byte-for-byte confirmed using Git blob hashes;
live Wayland/IME/GPU tests remain environment-gated and are not reported as
passed.

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
  data recovery or a trusted A05 portal. Rust unit/contract tests are executed
  locally; the AF_UNIX reconnect integration remains blocked by this sandbox's
  socket restriction and is not counted as passed.
