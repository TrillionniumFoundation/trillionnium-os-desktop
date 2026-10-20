# Private host-tool selection: host regressions

The OSDK integration recorder now applies the normal recorder's `select_bios` and `select_data_directory` **after** its unchanged fixed guest-profile transform. Explicit `A01_QEMU_BIOS` and `A01_QEMU_DATA_DIR` values support private tools and paths containing spaces. Invalid selections fail before any QEMU version probe or execution. BIOS artifacts are hashed from the selected actual argv path, rather than the hardcoded default constant.

Each guest retains its original OSDK arguments, fixed arguments before host selection, both selection records, and the exact shared selector source hash. The shared module is created with importlib and compiled from the same bytes that are hashed, so this binding does not depend on a Python bytecode cache. The integration runner input table and copied lifecycle-test closure now include the shared parent recorder dependency.

| Verification | Exact result |
| --- | --- |
| Baseline production CLI in this cloud environment | One expected failure per Python mode: private BIOS/data environment was ignored, default `/usr/share/seabios/bios-256k.bin` was absent, recorder exit125 before QEMU's version/execute |
| New private-tool CLI preflight suite | 6/6 passed with `python -I`; 6/6 with `python -I -O` |
| Complete integration host suite | 131/131 passed in each mode;262 test-method executions, no failed or skipped tests |
| Actual private selection positive within full suite | Unmodified production CLI plus executable fake QEMU exited33 in both modes; private paths contained spaces, requested BIOS was absent, host default BIOS was also absent, selected BIOS bytes/hash and argv agreed |
| Independent read-only review | No blocker in this change's scope; all13 previous recorder helper ASTs unchanged, including resource/device/GDB/coverage guards |

The12 preflight executions are separate from, and overlap with, the262 full-suite executions. Native GDB is genuinely executed by the existing host lifecycle fixtures, with the configured private library path. The QEMU executable used by the new CLI tests is an explicitly labeled Python fixture: **no VM, Rust build, Cargo build or upstream22 guest matrix was executed for this packet**. Actual full TCP22 acceptance remains root A01's next step.

The new cases cover private BIOS/data paths with spaces, eight invalid input variants, explicit data selection combined with single/duplicate incoming `-L`, default behavior with an explicitly labeled fixture BIOS, coverage-profile gating, original UNIX GDB argv preservation, forbidden network/data-disk/readconfig inputs and non-loopback control rejection. Unset variables keep the integration FIRMWARE default and original data lookup. Existing FIRMWARE monkeypatch tests remain valid. No private path setting selects TCP or enables coverage.

The original parser is retained, including its existing unknown-option behavior. In particular, the shared helper rejects any incoming `-L` when `A01_QEMU_DATA_DIR` is explicitly present; this packet does not invent a different unset-variable policy or copy validation into a second implementation. Only the two shared selectors are reused: the integration recorder's existing `file_record` path-read semantics are unchanged and this patch does not claim normal-recorder artifact snapshot protection.

Only five integration-owned files change: `record-qemu.py`, `run.py`, `README.md`, `test_capture_lifecycle.py`, and new `test_private_tools.py`. The shared normal recorder and the old35-method `test_record_qemu.py` are byte-identical to the baseline. Kernel/core, OSTD, reproduction-profile source and earlier frozen evidence were not edited by this task.

`source-validation-ready.json` binds all five source hashes and exact host-suite log paths. `sources/` holds baseline/final input snapshots; `private-tools.patch` includes the new test file. `raw.tar.gz` preserves red/preflight/full-suite commands, selected environment, raw console output, disposable CLI observations, native GDB lease lifecycle evidence and independent review. Every retained regular member is size/SHA256 verified in `archive-manifest.json`; generated Python bytecode and symlink dereferencing are excluded.
