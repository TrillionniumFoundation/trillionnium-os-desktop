# Cargo adapter host evidence

These are host-only Cargo boundary tests and a small x86_64 host `cfg-if` program. They are not Rust kernel or QEMU acceptance.

Code: [4976b571b1d01c069254252a03b74aaa4f51af93](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/4976b571b1d01c069254252a03b74aaa4f51af93). Original source: [b5030737451cd7b57813fc4e3c39665a6bb66cfc](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/b5030737451cd7b57813fc4e3c39665a6bb66cfc). `source-provenance.json` verifies exact committed bytes; production source is referenced rather than copied.

The unmodified `baseline-bypasses.json` records four fixture-Cargo requests accepted without generating validation reports by the old adapter: value-bearing global color options, `b`, `r -- --locked --offline`, and an unfixed `+nightly`. These controls use a fixture executable to inspect adapter dispatch; they are not real dependency builds.

Final host tests are **13/13** under `python3 -I` and `python3 -I -O`, logged as `tests-clippy-closed.log` and `tests-clippy-closed-optimized.log`. Exact command arrays, source hashes and limitations are retained in unmodified `REPORT.json`.

`real-smoke-final.json` records four actual fixed-nightly Cargo invocations: metadata, fixed-selector build alias, run alias with application arguments resembling lock flags, and version. All return 0. The host program prints `A01_FIXED_CARGO_DEPENDENCY_OK`; its binary SHA256 is recorded, but its binary is excluded. The selected inherited environment intentionally supplied incorrect Rust selectors; actual command reports identify the pinned compiler and Cargo used.

`records/` exposes the three original final request JSON files unchanged. `normalization.json` indexes actual command arrays, normalization commands, lock hashes and empty external drift. Full normalization metadata, derived Cargo.lock bytes, initial smoke records and raw stdout/stderr remain in `logs.tar.gz` (43 members). Every member is indexed by SHA256 in `logs.members.json`.

The real smoke used `cargo.py` SHA256 `cfbe5ff30e5ae88f4f1b4316184bc40cec6848187d5db7697c9685cb6c910658` and test SHA256 `c2db5dfac97129de605eb613ca019c0f73f06092dd1c409293e97e6290ccf05e`. The later final code removes `clippy` from permitted resolving commands and adds its explicit pre-execution rejection test. Final hashes are in `REPORT.json`; the **13/13 × 2** tests cover that delta. `post-smoke-delta.patch` preserves these exact two changed lines. Reversing them recovers full-file SHA256 values identical to the original smoke snapshot; no production source copy is included. The four real smoke commands were not rerun after it. Their original hashes are preserved, and they do not call clippy. Arbitrary external Cargo commands, configuration redirection, custom aliases and lockfile redirection remain unsupported.

`real-smoke.json` and its raw records are an earlier real run and are not relabeled as the final freeze. `fixture.patch` packages the tiny smoke manifest/program and a baseline-caller recipe; it contains no production adapter copy. In a separate empty directory apply it with `git apply`; `python3 -I fixtures/reproduce-cargo-baseline.py /absolute/repository` reconstructs baseline code from the verified Git object and invokes the committed fixture tests. The packaged recipe has not been counted as an additional executed test. To repeat the real smoke, use the exact command arrays and environment in `real-smoke-final.json`, adjusting scratch paths and allowed roots to a new owned directory; the repository seed lock and toolchain must retain their recorded hashes.

`SHA256SUMS` covers every delivered regular file except itself. No target, registry, dependency cache or compiled program is included.
