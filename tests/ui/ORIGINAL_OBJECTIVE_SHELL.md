# One real Rust Shell across an original Objective admission

`probe-original-objective-shell.py` consumes the three private phase barriers
from [the original Objective probe](../integration/hepta/ORIGINAL_OBJECTIVE.md).
That separate probe owns the disposable test issuer, unchanged original Agentd,
original durable journal and both real Session processes. The capture controller
starts one Xvfb and one unchanged, source-bound Rust Shell. It never signs or
submits an objective, configures an Agentd endpoint in the Shell, or synthesizes
a Session response.

This is a separate qualification from `probe-original-hepta-shell.py` and its
historical six observer phases. It reuses that script's reviewed child-death,
atomic acknowledgment and read-only projection primitives, and the actual
`XGetImage` implementation in `x11-ime-client.py`. Those files remain unchanged.

## Source and environment inputs

Run from a clean, committed checkout containing this capture code. Supply the
actual UI build receipt and its matching native `trill-shell` ELF. The receipt's
`source_commit`, `source_tree`, `ui_tree`, `ui_lock_sha256`, passing
`build_commands`, and Shell byte count and SHA-256 must agree. The capture
checkout's `HEAD:ui` must equal the receipt's UI subtree; unrelated integration
changes do not claim to rebuild the UI. Every executed Python dependency is
copied from and compared against its committed Git blob before the namespace
starts. Agentd, Session, CLI and original probe ELF provenance remains in the
separate Objective runner's report.

The explicit `--host-usr /usr` input means the current host's dependencies.
Required tools are `/usr/bin/bwrap`, `Xvfb`, `xauth`, `xdpyinfo`, `xdotool`,
`xprop`, `xwininfo`, `python3`, and `ldd`. The controller records canonical paths,
byte counts, SHA-256 and bounded `ldd` results for the tools and Shell, checks
that linked libraries resolve under `/usr`, and verifies recorded files again
after capture. It binds `/usr` read-only. This is not a historical package-stage
receipt or an exhaustive manifest of dynamically loaded Mesa drivers.

The display has private Xauthority, a fresh tmpfs `/tmp`, and private user,
mount, network, IPC and UTS namespaces. PID visibility remains shared so kernel
`SO_PEERCRED` identifies the real Session process. Xvfb listens without TCP, and
the controller verifies that a client with no cookie is refused. Only the
owned test runtime is mounted as the Session endpoint. The controller has no
existing display, production endpoint or device input. A failed namespace
launch is saved as a failure; there is no automatic host-display fallback.

The visible scope is the **English Hepta Runtime card**, using the unchanged
eframe embedded fonts with software rendering requested. No extra CJK font,
IME, physical keyboard, GPU device or target-kernel GUI qualification is made.

## Coordinated invocation

Build the adapter CLIs with `--features objective-transport` when enabling the
separate `hepta-submit` executable. Use the original Objective runner with
explicit binaries, `--session-bin`, `--ctl-bin`, a **new**
`--session-phase-dir /absolute/new-phase-directory`, and
`--session-ack-seconds 120`. The runner creates the private phase directory;
do not create phase JSON or ACKs by hand. Admission and original journal
acceptance must pass independently in that runner's report.

While the original runner executes, start the capture from its frozen source:

```sh
python3 -B tests/ui/probe-original-objective-shell.py \
  --source-root /absolute/frozen-integration-checkout \
  --host-usr /usr \
  --shell-bin /absolute/built/trill-shell \
  --build-receipt /absolute/ui-build-receipt.json \
  --phase-dir /absolute/new-phase-directory \
  --startup-timeout 900 \
  --output /absolute/new-capture-directory
```

The output directory must be new and outside the source checkout. The initial
phase wait is bounded by `--startup-timeout` (1–1,200 seconds); each subsequent
phase wait, display command and child cleanup has a separate bound. The whole
capture namespace has a 480-second deadline. In environments whose execution
sandbox prevents namespace setup, run in the already authorized execution
environment and retain the actual permission failure separately.

## Exact three phases

| Phase | Original owner and Session | Required run projection |
| --- | --- | --- |
| `compiled_run_projected` | Original compiled admission, first Session | `observed`; all seven original run fields equal the original owner's direct `run_status` read; phase `admitted`, terminal false |
| `old_endpoint_run_stale` | Original owner restarted; same Session PID, instance, worker and runtime | `stale`; original run fields and retained sample remain historical, with sticky gap; failed health reads do not renew the run sample or its last attempted RPC |
| `replacement_run_projection_missing` | Same restarted owner; explicitly replaced Session at the same runtime/socket | `projection_missing`; no observation in this new Session and gap false; absence of a current projection does not negate the independently recorded original journal admission |

Each phase must be a bounded, owned, single-link 0600 file. Before and after
each actual framebuffer capture, the controller reads the live Session socket,
checks its 0600 ownership and kernel peer PID/UID, verifies the same Session
instance and named observer worker, and compares run and original owner
identities with the held phase. Successful health and run samples have separate
freshness checks. A retained run requires Session's
`sample_age_at_snapshot_ms`; a live run's source monotonic age plus the measured
UDS round trip must remain fresh. Stale samples are retained exactly, including
their original timestamps, while only this independent source age may advance.
The same Shell PID, X window ID, WM class and PID properties are
checked across all three phases. Only that verified owned window is resized
and positioned; the controller sends no task or keyboard input.

A screenshot is written as a real 1440×1000 `XGetImage` PNG, followed by the
after-snapshot and receipt, then an atomic 0600 ACK exactly matching the
original phase's `ack` object. The ACK only releases a coordination barrier.
Session replacement is performed by the original probe after stopping and
waiting for its first child; Shell reconnects through its existing polling
path without a second Shell startup.

## What a passing result requires

`capture-receipt.json` records `capture_passed` for complete process, peer,
snapshot, window, source and cleanup checks. It always retains
`visual_review_required: true` and
`visual_review_completed_by_capture: false`. The one-shot layout marker binds
only the first native Runtime layout; it does not prove the known-run pixels
or later states.

**Open and inspect all three PNG files with `view_image` before claiming pixel
pass.** Verify that each real Runtime card displays its expected live, stale
historical or missing-projection wording and that important fields are visible.
Record that manual review separately, with image hashes and phase identities.
Do not substitute fixture snapshots, generated images or the existence of ACKs
for this review. A complete result also needs the independently passing
original admission/journal/Session report. It proves this host prototype's
read-only display of an original nonterminal admission, without claiming a
model turn, resumed historical execution or device effect.

Small contract checks can run independently:

```sh
python3 -B tests/ui/test_original_objective_shell.py
```

These tests use synthetic values only for validator predicates. Their one real
kernel socket check refuses a mismatched peer before any snapshot request; it
does not serve a fake Session, run a Shell, or produce runtime/pixel evidence.
