# Linux Notes destination evidence

This evidence records the destination-only run on isolated Linux host `main`;
it is not a production FinalUse, Agentd writer, or Asterinas run.

Source was `9f3f26d6` (scope patch over archive `5d5fd314`), then formatted by
Rust 1.95.0 and its UI lock updated for sha2. `tested-source-sha256.json`
records the actual tested file contents. The containing source commit imports
those same formatted files and the updated lock; it does not claim a second
run under the later commit id. Remote job: `1a15eef82ab-1b6abb-2a1a`, exit 0.

- `cargo +1.95.0 test --manifest-path ui/Cargo.toml --workspace --all-targets --locked`:
  172 passed, 0 failed, 2 ignored across 13 test binaries. The two ignored
  tests require `TRILL_UI_TEST_CJK_FONT` to select a real host font; this
  workspace run did not opt into those font qualification tests.
- Workspace binary build and Notes probe example build completed. The runner
  scripts retain the exact commands; full log locations remain with the task.
- Strict host IPC test rejected 10 forged frames; legitimate Launch retained
  task id 1; exit/cancel observations remained separate.
- Isolated Xvfb rejected a missing-cookie client. The actual Notes process
  produced a matching document mutation acknowledgement, changed egui layout
  marker and independent read-only receipt query. X11 reported its window
  viewable and the separately captured PNG was nonblank. The PNG visibly shows
  the requested two-line text, Chinese text and document revision 1.

`target-receipt.json` intentionally keeps compositor-pixel verification false
because that Rust transport probe does not inspect pixels. `summary.json` and
`notes.png` add the independent window/screenshot evidence. Neither establishes
physical hardware/GPU qualification, user-display operation or a durable
original-owner terminal outcome. No live user display was used.

The standalone Session still has no original-owner bootstrap in this tested
source. Follow-on bootstrap code requires its own test and compilation result.
