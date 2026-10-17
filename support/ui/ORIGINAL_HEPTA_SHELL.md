# Original Agentd → persistent Session → native Shell

This gate observes the unchanged original Hepta owner through the production
Rust Session and a continuously running Rust Shell. A07's original probe owns
the Agentd lifecycle, trusted launcher values, Session processes and phase
records. A10's capture consumer starts only its private Xvfb and one Shell.

The fixed Hepta source remains
`f8c9419df6ddeb36ff8b522a50219981fb8d9345`. This is a Linux host read-only gate.
It submits no objective, calls no model and performs no device operation.
It does not qualify Asterinas, Wayland, physical displays or mobile input.

## Execution and ownership

Build and run A07's optional persistent Session gate as described in
[ORIGINAL_AGENTD.md](../../tests/integration/hepta/ORIGINAL_AGENTD.md). Its
original Rust probe accepts `--session-bin`, `--ctl-bin`,
`--session-phase-dir` and the bounded `--session-ack-seconds` option. The
phase directory must be new. Only the original probe creates its real
Session processes; the capture consumer must not create a fixture, replace
the Session's data or write an Agentd message.

Run the capture consumer concurrently, using the same absolute phase path:

```sh
python3 -B tests/ui/probe-original-hepta-shell.py \
  --source-root "$PWD" \
  --packages "$PRIVATE_VERIFIED_X11_PACKAGES" \
  --bin-dir "$ACTUAL_UI_BINARIES" \
  --build-receipt "$ACTUAL_UI_BUILD_RECEIPT" \
  --font "$PRIVATE_CJK_FONT" \
  --phase-dir "$ORIGINAL_SESSION_PHASE_DIRECTORY" \
  --output "$NEW_SHELL_CAPTURE_DIRECTORY"
```

The package root is the already verified private 44-package R5 Ubuntu stage,
including its existing `merged/usr` view and `package-stage.json`. No package
installation or system service change occurs. This capture uses Xvfb and
the real CJK font for rendering; it starts no input method and makes no
keyboard-input claim. A different host needs its own verified environment
adapter, not a fabricated copy of the R5 stage receipt.

The capture source checkout must be clean and committed before execution.
The build receipt must identify the actual Shell, Session and ctl ELF hashes,
the production commit and complete source tree. The consumer verifies the
unchanged `ui` subtree and the Session's external path dependency
`services/hepta-os/src`, `Cargo.toml` and `Cargo.lock`. New documentation or
test code does not invalidate an unchanged production closure. An actual
change to that closure requires matching new binaries and a new receipt.

The original probe keeps the same private `ui-runtime` directory inode while
explicitly replacing the Session. The consumer binds this path read-only,
so a single Shell keeps its existing IPC address and reconnects normally.
Only the Session receives the four trusted Agentd configuration variables.
The Shell namespace contains no original Agentd control directory.

The capture shares the Session's PID namespace deliberately. Linux's
`SO_PEERCRED` returns PID zero for a peer invisible in a child PID namespace;
the existing UI IPC correctly refuses that invalid identity. Mounts,
network, IPC and UTS remain separate. This environment arrangement is not a
cross-UID security boundary or an operating-system sandbox qualification.

## Six held phases

| Sequence | Original owner / Session state | Native Shell evidence |
| --- | --- | --- |
| 1 | Same Session observes Starting, spawn generation `g` | First real Hepta-page layout marker and raw framebuffer |
| 2 | Same Session and observer worker observe Running, generation `g + 1` | Same Shell PID and window show the running observation |
| 3 | Same Session and worker observe Draining, generation `g + 2` | Same Shell shows draining health |
| 4 | Original owner has restarted; old trusted Session becomes stale | Same Shell retains the old observation and shows stale/unknown state |
| 5 | Original launcher explicitly starts a new Session for the new spawn | Existing Shell reconnects and shows the new process and generation |
| 6 | Original owner stops; replacement Session becomes stale | Same Shell shows the retained final observation as stale |

The original stop path can produce a real final Draining observation before
disconnection. Phase 6 therefore accepts a retained Running **or Draining**
sample, with its correct lifecycle generation, instead of requiring an
older running timestamp. Phase 4 retains the already observed draining
source. A07 separately verifies the first stale sample and its complete
stability on a later failed read; a timestamp frozen before a held phase
cannot stand in for the last actual successful poll.

The producer publishes `phase-1.json` through `phase-6.json` atomically as
bounded private files. Each contains the actual Session PID, observer worker
TID, Session instance, original owner record and actual ctl snapshot. Its
`ack` field is exactly:

```json
{"sequence":1,"phase":"starting","session_instance":"actual-session-instance"}
```

The capture returns that exact object as `ack-1.json` only after retaining
the phase's raw image and before/after snapshots. Linux `renameat2` with
`RENAME_NOREPLACE` publishes a single-link `0600` acknowledgment without
overwriting an existing barrier. This acknowledgment coordinates execution;
it proves neither pixels nor an original owner by itself.

## Evidence and acceptance

For every phase the capture saves the producer's original bytes, then reads
the real Session socket itself. The kernel peer PID and UID must match the
held Session. It keeps the raw bounded JSON frame before and after an actual
`XGetImage` framebuffer capture. It checks Session-instance continuity,
original process/spawn identity, lifecycle generation, current freshness or
exact stale retention, and the same Shell PID/window throughout.

The existing `TRILL_HEPTA_LAYOUT_V1` stdout line is one-shot and covers the
first observed runtime layout only. It is not reused as proof of six phase
updates. Later frames use the Shell's ordinary 800 ms snapshot polling and
100 ms repaint requests. A bounded 2.5 second dwell gives those updates time
to occur; it does not prove that a particular frame consumed a particular
snapshot. Before/after samples establish the held source context.

**All six raw PNGs must be visually reviewed** for the actual visible
connection status, AgentId, spawn/current generation, process ID and
lifecycle. For phase 4 and 6 the stale warning must be visible. For phase 5
the new PID/spawn and reconnected Session must be visible. The capture JSON
sets `visual_review_required: true`; `capture_passed: true` means the six
mechanical capture steps completed, not that human-readable pixels or
original runtime provenance have been independently accepted.

The original runtime receipt, actual ELF source bindings, capture receipt,
raw snapshots and an independent visual-review record together support the
end-to-end read-only result. Scripted-fixture evidence remains separately
labelled in [HEPTA_OBSERVER.md](HEPTA_OBSERVER.md).

On normal cleanup the owner pins each Shell/Xvfb process-group leader until
group signals and reaping finish. Each child starts through a fresh Python
exec wrapper which arms `PR_SET_PDEATHSIG(SIGKILL)` and checks the expected
parent immediately before exec. This protects the actual leaders if the
capture process dies. It avoids `preexec_fn` in a potentially threaded
parent. The focused fault test confirms actual exec, then kills the owned
parent and observes the child's kernel SIGKILL exit. It does not qualify
arbitrary descendant trees; normal process-group cleanup still covers
test-owned children.

Run the focused capture-contract checks without a display or Agentd:

```sh
python3 -B -m unittest discover -s tests/ui \
  -p test_original_hepta_shell.py -v
```

These reject substituted identities, incorrect lifecycle/freshness,
replacement outside phase 5, mutated stale data, public/symlink/oversized
phase files and acknowledgment overwrite. Their success is a harness result
and cannot substitute for the actual original-owner run or six PNG reviews.
