# Same-file CI commands

When this capsule is published as `compat/android/pocket4/continuation-20261109-2840/apps-settings-page`, append these commands to the existing A08 workflow after its source-pin/replay check:

```sh
cargo test --locked -j 1 --manifest-path compat/android/pocket4/continuation-20261109-2840/apps-settings-page/harness/Cargo.toml -p pocket4-settings-admission-tests --lib application_settings -- --test-threads=1
cargo test --locked -j 1 --manifest-path compat/android/pocket4/continuation-20261109-2840/apps-settings-page/harness/Cargo.toml -p droidloom-task-launcher -- --test-threads=1
python3 -I -B compat/android/pocket4/continuation-20261109-2840/apps-settings-page/consumer/test_pending_marker.py
```

Expected execution is respectively **23**, **30 library + 5 CLI**, and **6** passing controls. The Settings filter intentionally excludes the eight unchanged package-observation tests in that small crate. The native dependency crates are compiled from their exact unchanged sources; their own test suites are not independently rerun. There is no ignored or privileged test in these selected groups, no Android start, and no app runtime credit.

The two Cargo commands already passed on ordinary Pocket4 with the exact small lock and `--offline` added. `--offline` is omitted above so a fresh CI runner can fetch the locked dependencies. Python evaluates the exact selected function ASTs from both pinned full consumer sources and uses temporary files; no extra Python packages are needed.

The final actual daemon/dispatcher workspace execution is separately recorded as r3 70 in `evidence/r3/RESULT.json`. This harness deliberately does not pretend to compile the full daemon or dispatcher. Reuse the existing A08 Rust source replay verifier for the eight changes listed in `source-binding.json`; the four preimages are under `preimage/`, all eight postimages under `source/`, and the exact patch is `settings-failclosed.patch`.

The exact 34 external package tuples can be checked against `reference/source-workspace-Cargo.lock`; the observed equality and successful lock SHA are recorded in `evidence/r3/HARNESS.json`. No dependency update is authorized by these commands.
