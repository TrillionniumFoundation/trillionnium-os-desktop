# Actual ordinary cold build with private SDK installations

The complete fixed Rust kernel built from an absent target and booted successfully using a separate OSDK installation prefix for each public action. The tested producer is `0a7037fdde1e4c21884ea4f490ff28134082d0a2`, complete tree `e9cb90e3504b5cb07fba5345af122315a487895f`, derived kernel tree `6b3cab110aa6d30d5b89f99c4389c9c3e01022da`. This is ordinary build/boot acceptance after the private-SDK fix; it invokes no path-projection profile.

## Actual results

| Check | Result |
| --- | --- |
| Controller | Root session 19957 exited 0; all eleven original subprocesses exited 0. |
| Cold source build | `kernel/asterinas/target` was absent; public `kernel.sh kernel` invoked the upstream `make kernel` developer target. There were 279 compiling lines. |
| Subsequent boot | Public `kernel.sh run_kernel` invoked upstream `make run_kernel`, reused the completed target with zero compiling lines, and the real guest exited raw QEMU 33. |
| Guest | x86_64, q35/TCG, CPU max, one vCPU, 512 MiB, explicit guest SeaBIOS and QEMU data files, small initramfs, retained complete serial log and all acceptance markers. |
| Live check | Original `check-boot.py --live-artifacts` exited 0. Source checks passed before/after with 118 checked files and zero errors; postrun Git status was empty. |
| First/boot kernel | Complete retained ELF bytes are equal: 8,255,688 bytes, SHA256 `5c2cee2a8806baf873149ce07f752cc3b1c633efd4199e0c8c0ba20ef5f325f7`. |
| Two private SDKs | Different installation paths/inodes, equal complete ELF bytes: 8,560,432 bytes each, SHA256 `94df3fd621055d9f99d3649c21a32d076448d68d8ea4b51d78c8b639a5d2adf0`. Both binaries contain the actual N2 compile-time OSDK source-root literal. |
| Existing global SDK | Before/after stable-FD path/stat and SHA256 observations are unchanged: `b5b92798bfcfb9416539fcaca3271cdc7017444affba26b34b7881d861171f2e`. No prelaunch global binary payload was retained, so no complete before/after global byte comparison is claimed. |

The actual run began at 2026-10-17 04:17:53 UTC and its last original subprocess completed at 04:23:37 UTC on `24f0ea2620fe`. The prior C4 run had already completed according to the root's completed-run observation before N2 began. The prelaunch record's original “may still be running” wording remains preserved; this phase does not claim overlapping C4/N2 execution.

## Actual entrypoints and SDK binding

The controller used the restored fixed `nightly-2026-07-21` and one Cargo job. Its exact source differs from the published N1 controller only in case, worktree/output paths and job count. `controller/origin.json`, the original N1 source and independent pre-run review are preserved in the raw archive. Known wrapper/projection/timestamp and inherited make controls were cleared. The inherited controller docstring retains historical “normalized” wording; actual source, argv and environment establish this ordinary run.

```sh
python3 -I round-next/run-private-sdk-native-n2.py \
  0a7037fdde1e4c21884ea4f490ff28134082d0a2 N2
```

Inside the new source worktree, it executed:

```sh
bash support/build/kernel.sh kernel
bash support/build/kernel.sh run_kernel
```

The two installations were under:

```text
/workspace/scratch/ae1a8cf05419/private-sdk-native-N2/kernel-build/osdk/bin/cargo-osdk
/workspace/scratch/ae1a8cf05419/private-sdk-native-N2/kernel-boot/osdk/bin/cargo-osdk
```

Both action environments put their private `bin` first, while retaining the explicit Cargo-home `bin` later in PATH. Their actual make vectors supplied `CARGO_OSDK` and `A01_OSDK_INSTALL_ROOT` explicitly. The pinned overlay installed with `OSDK_LOCAL_DEV=1 cargo install --locked --root ... --path osdk`; installation metadata and SHA receipts are retained. Full private SDK bytes, their embedded N2 source-root counts, and the pinned `option_env!("OSDK_LOCAL_DEV")` / `env!("CARGO_MANIFEST_DIR")` implementation are verified offline. This is recorded source binding, not compiler attestation or immutability.

## Preserved evidence

All 57 captured originals were opened with NOFOLLOW and stable FD/path stat checks, then reread and compared before packaging. They include all original controller/action logs, environment and command vectors, source receipts, manifest cleanup results, first-produced kernel, actual QEMU loaded inputs, full serial log, both private SDK binaries and installation metadata, global before/after observations, root postcheck source/results, and outer completed-tool observation.

Four unique binary payloads are gzip-compressed and deduplicated with an exact logical-path map. All archive chunks are at most 2 MiB. Eighty exact producer source controls are preserved with Git commit, raw tree object and path/blob membership proofs. This is a selected build/SDK control closure; the full kernel remains in its single Git import. The packager never read a source target tree or invoked a build, SDK, live guest check or VM. After CAPTUREDONE, the original worktree may advance for subsequent regressions; verification uses only this phase.

`readable/` provides the complete serial log, QEMU record, environments, actual make commands and eleven-command index. `raw.manifest.json`, `artifacts/manifest.json`, `capture.json` and `source/` describe the complete retained bytes.

## Offline verification and limits

```sh
python3 -I support/build/evidence/2026-10-17-private-sdk-native/verify.py
python3 -I -O support/build/evidence/2026-10-17-private-sdk-native/verify.py
```

The verifier is relative to the phase, needs only Python's standard library, checks all retained source/input/controller/guest bytes and original successful receipts, and performs no dependency fetch, compiler invocation, SDK execution, original-target read or VM launch.

This accepts one ordinary cold build and the subsequent warm boot, plus observed SDK isolation for those actions. It does not accept cross-instance ordinary ELF reproducibility, immutable execution, continuous global-SDK immutability, default AF_UNIX/KVM support, later debugger/ktest regressions, or closure of all project/native-feature blockers. The first and loaded kernel input remain actual complete Asterinas-derived kernel ELFs, not a host Linux or installer boot. No system disk, BIOS, GPU driver, production service, capability, namespace or sandbox setting was changed.
