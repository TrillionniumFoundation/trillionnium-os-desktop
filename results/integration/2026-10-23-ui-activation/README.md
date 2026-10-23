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
