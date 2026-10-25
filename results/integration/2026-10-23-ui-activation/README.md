# Accessible activation and IME lifecycle repair

Source base: `1f4a252c22adf3bc4e1de1ce655e42387070f503`.
The [execution record](execution.json) binds six changed files by SHA-256,
toolchain, commands and failure boundary.

The renderer-independent policy passed 12 actual tests under Rust 1.95.0
with warnings denied; see [policy-tests.log](policy-tests.log). Modified Rust
files passed rustfmt. The patch applied in a dry run to verified Git blob
preimages. These checks do not qualify a graphical backend.

The full Shell/app-window cargo test build was attempted with --locked
--offline and stopped before compilation because eframe was not cached.
The real egui widget tests and pinned Rust 1.88 host/Wayland gates still
require execution on this new source. Historical XIM and compositor receipts
do not qualify it.

No Cargo manifest or lock was changed. AccessKit is not enabled and no
assistive-technology, Wayland IME, mobile or physical-device success is claimed.
Chat remains a local draft, and original Hepta authority is unchanged.

## Follow-up: renderer-independent held-key handling

The [follow-up execution record](repeat-execution.json) binds the initial and
updated policy hashes. The same [independent regression](repeat-regression.rs)
failed on the initial policy and passed after the fix. It rejects a second
keydown without keyup even when a backend omits its repeat flag, then restores
activation after release. All 13 updated policy tests passed with warnings
denied under Rust 1.95.0. The initial 12-test record above remains historical;
full egui and native gates still need to run on the latest commit.

The archived regression adjusts only its module-relative path for this directory.
Its original execution layout is retained in repeat-execution.json; the archived
copy was also compiled and executed against the unchanged updated policy, as
recorded in [archived-regression-execution.json](archived-regression-execution.json).
From the repository root, compile this file with `rustc --edition=2021 --crate-name
archived_input_repeat --test results/integration/2026-10-23-ui-activation/repeat-regression.rs`
and run the resulting binary with `--exact repeated_unmarked_keydown_does_not_repeat_an_effect`.
