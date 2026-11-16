# Unified Audio538 Android tools

This complete producer succeeds the published AAC330 producer (1,517 files) with 1,557 authenticated files. It preserves both IntentResolver and AAC security fixes and adds only the exact same-superproject `system/libueventd-rs` project, its complete 21 originals, and explicit provenance/tests for the USB consumer and 16 existing direct Rust providers.

The actual desktop qualification passed all 334 registered source/updater/integration tests, including the original network, EROFS repack, two release-queue tests and separate original DMA layout test. Both release tools were rebuilt; 58 original PIDs and all associated units retired. Historical evidence is not counted as new CI execution.

Fresh CI runs one exact source test and three exact updater tests in their real harnesses, then builds `droidloom-source` and `droidloom-update` in a fresh external Cargo target. All 1,557 source bytes, Git blobs, modes, membership and F9 are checked before and after. The original AAC330 input is verified and replayed forward, reverse and forward with independent files and complete Git root reconstruction. Only root `.git` is skipped on copy.

The actual prior Audio9db build failed on the missing `libueventd` provider. Its original normal log, failed command and independent source/process/lease retirement remain in `history/`. This source/tool qualification does not turn that build into a success and does not qualify new Android artifacts, original C++ regression, release signing or runtime.

The qualified delivery components are only `droidloom-source`, `droidloom-update` and subsequently verified Android outputs. Current runtime D6 and its successor are integrated separately. Do not build, bundle or deploy the older supervisor or droidloomd from this producer tree.

Run `verify.py --inventory-sha256 <externally pinned FILES.sha256 digest> --parent-source <complete AAC330 producer> --output <fresh independent producer> --report <fresh report>`; then run `run_ci.py` with that producer and fresh external Cargo target/report paths. All official Git object bodies are preserved without reserialization.
