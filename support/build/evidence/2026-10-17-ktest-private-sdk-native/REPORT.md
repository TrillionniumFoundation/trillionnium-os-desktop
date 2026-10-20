# Real kernel-mode regression tests with a private source-bound SDK

Both default upstream kernel-test crates passed using the newly installed private SDK from exact producer `ff0d09a2c2e0cba1d528d11a06083f588989a9f3`. Root session 79302 exited 0; all six original controller commands passed, the source verifier checked 118 protected files with zero errors, and source HEAD/status were unchanged and clean before/after. This run reused the N2 target; it is not a cold-build claim.

| Target crate | Reported passed | Failed | Filtered | Soft skips | Exercised passed lower bound | Raw guest exit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| OSTD | 221 | 0 | 0 | 3 | 218 | 33 |
| aster-core | 141 | 0 | 0 | 0 | 141 | 33 |
| Total | 362 | 0 | 0 | 3 | 359 | Two exits of 33 |

The three OSTD soft skips report VMX unavailable twice and VMX/EPT invalidation unavailable once. Reported successes include those soft skips; 359 is the conservative exercised-passed lower bound. Expected-panic tests are valid test cases. The original checker and this offline verifier reject explicit uncaught/fatal test-runner panics and failures while preserving expected-panic output.

The actual test logs contain 54 OSTD and 83 aster-core compiling lines. These are observed recompilation counts while reusing an existing target; they do not establish a fresh target or a complete cold build. Both guests used x86_64, q35/TCG, CPU max, one vCPU, 512 MiB, explicit private guest SeaBIOS/data resources and complete retained serial logs. They executed real kernel-mode test ELFs through the fixed Asterinas-derived kernel, not host Linux model tests or an installer.

## Actual entrypoint and SDK

The completed controller was:

```sh
python3 -I round-next/run-native-followup-v2.py \
  ff0d09a2c2e0cba1d528d11a06083f588989a9f3 ktest
```

It ran the default two-crate command inside `/tmp/trillionnium-a01-private-sdk-N2`:

```sh
python3 -I support/build/ktest/run.py \
  --output /workspace/scratch/ae1a8cf05419/native-followup/ktest/run
```

The runner installed the source-bound SDK with the fixed nightly, `cargo install --locked --path osdk --root .../run/osdk`, then called the absolute private binary with `osdk test` for OSTD and aster-core. No deprecated `--skip-osdk-install`, crate selector or test-name filter was supplied. Full SDK bytes, installation metadata, environment, original installation/test argv and its embedded N2 compile-time source-root literal are preserved. The runner explicitly records that installation was not skipped.

The test-base locks generated during the actual run match the exact fixed source locks for both crates. The runner's input SHA map is checked against the retained Git-bound source files. `sdk-binding.json` and `report.json` give the actual SDK identity and complete results without substituting another run's binary or source root.

## Capture timing and evidence

The ktest recorder records each actual loaded ELF/BIOS path, stable artifact metadata and SHA; this protocol does **not** make ordinary-recorder-style private copies before QEMU. After root reported RUN DONE, the worktree/target was held while this packager opened only those explicitly recorded loaded files with NOFOLLOW, matched size/SHA against each QEMU record, and checked FD/path identity stability before/after reading. Every captured original was reread and compared. CAPTUREDONE then released the worktree/target for later work.

The later evidence copies are not represented as the paths QEMU executed. `loaded-inputs.json` retains both the actual loaded paths and packaged logical paths, along with the capture timing. This establishes matching retained bytes after the run; it does not establish immutable execution or resistance to a privileged concurrent writer. No entire target tree was copied or scanned for artifacts.

The phase preserves 48 original files, four unique binary payloads, all original command/cleanup receipts, both complete serial logs and loaded kernels/BIOS, the full private SDK, generated locks, source/head checks, environment and outer completed-tool observation. Ninety-one selected runtime/test/SDK controls have exact producer commit, raw Git tree and path/blob membership proofs. The complete kernel remains in its single Git import. Gzip payloads are deduplicated and every stored chunk is at most 2 MiB. `readable/` exposes the guest logs, QEMU records, controller index and runner environment/results.

## Offline verification and scope

```sh
python3 -I support/build/evidence/2026-10-17-ktest-private-sdk-native/verify.py
python3 -I -O support/build/evidence/2026-10-17-ktest-private-sdk-native/verify.py
```

The relative-path verifier checks complete retained bytes, source membership, original successful command/cleanup receipts, fixed generated locks, private SDK binding, actual QEMU inputs and serial-derived checker counts. It performs no dependency download, compiler/SDK invocation, original-target read, live check or VM launch.

This phase accepts these two real upstream kernel-test suites only. It does not turn host harness/draft-agent outcomes into kernel-test results, accept a later debugger run, demonstrate KVM/VMX support, accept cross-instance or immutable builds, or close the project-specific native HOS2/control/service blockers. The fixed upstream version/toolchain and zero-byte root README are checked from the tested producer.
