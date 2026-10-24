# Notes process recovery: executed Linux application scope

Source: `87f1dea1ca28bf6e75c0e54cc2468cd8f8b87aac`.
Tree: `7ec817444dbc9766a0207e39806f9c3202563c55`.
Base: `774e3a55ced564dc554ba546da8a219281fcdc14`.

All fourteen executable/test source files in `source-bindings.json` were
compared byte for byte with the remote build copy. Evidence additions do not
change that source tree's implementation. The UI retained Rust 1.88.0 and its
existing Cargo.lock. The source was built in an isolated Linux checkout and
target directory, with two Cargo build jobs.

## Executed results

- Core: 34 unit tests and 6 legacy transport tests passed.
- Notes store: 6 test entries passed, including the child-process fixture used
  by the real SIGKILL test. This is five behavior cases, not six independent
  product scenarios.
- App window: 33 tests passed. Its original real-font test was initially
  ignored; the final run separately executed and passed it using the actual
  Noto Sans CJK font, including glyph coverage and rasterized ink.
- Strict Clippy, warnings denied, passed for Core and App. The final helper's
  diagnostic-only follow-up also passed App strict Clippy and rebuilt.
- Session, App and recovery binaries built with locked dependencies.
- A real isolated Xvfb Session/Notes application received one complete effect
  frame. Its effect reply was deliberately not read. After actual document
  persistence, the Notes process was killed, the original Session observed its
  reap, and a separate recovery process returned the exact saved receipt.
- A mutation sent to the recovery-only process was rejected. Exact retirement
  was persisted, and a second recovery-process instance returned
  `already_released`. The document text remained unchanged at revision 1.

See `result.json` for the scope flags and
`final-helper-font-recovery.stdout.log` for final executable SHA256 values and
the actual process result.

## Retained failure and correction

`v2-step-4.log` is the original recovery query timeout. The following
`early-owner-*.log` records identify the independent helper's exact lock refusal
(`EAGAIN`). The probe had treated disappearance of `/proc/<pid>/exe` after
SIGKILL as complete process reap. That observation can precede release of the
process's final descriptors.

The corrected probe waits for the **same original Session** to report its
child's terminal state. It does not unlink a live lock, retry an effect, change
the target generation, enlarge the deadline, or ignore the refusal. The next
run and final frozen-source run pass. The exclusive storage lock's refusal was
correct; the premature transition was in the qualification probe.

## What these results do not claim

The parent is an explicit isolated transport fixture. It is not a production
Root issuer or original Hepta durable writer. `production_authority`,
`original_writer_terminal`, `compositor_pixels`, `asterinas_native` and
`root_or_machine_reboot` remain false. A deployed original owner must attach
the exact recovery channel and reconcile its retained operation before this
can count as the production Notes effect closure. New application instances
are not automatically rebound to old document incarnations.

The implementation contract and development commands are in
[`NOTES_DURABILITY.md`](../../../../support/ui/NOTES_DURABILITY.md).
