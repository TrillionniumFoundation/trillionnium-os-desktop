# Real kernel-mode regression, 2026-10-16

Two real x86_64 QEMU guests completed the fixed Asterinas-derived OSTD and aster-core kernel tests. This archive retains every file of `support/build/out/next3-ktest` byte-for-byte, plus the original one-line parent console. It does not turn host tests or a userspace smoke boot into kernel-test passes.

| Target crate | Reported passing | Explicit soft skips | Exercised lower bound | Failed / filtered | Raw QEMU | Timeout | OSDK |
| --- | ---: | ---: | ---: | --- | ---: | --- | ---: |
| OSTD | 221 | 3 | 218 | 0 / 0 | 33 | false | 0 |
| aster-core | 141 | 0 | 141 | 0 / 0 | 33 | false | 0 |

OSTD soft skips are VMX unavailable twice and VMX/EPT invalidation unavailable once. Across these targets the reported total is 362, with at least 359 exercised after subtracting the known soft skips. The runner's global 240/504 headers include explicitly skipped crates; no full workspace, architecture, hardware, Docker/Nix or OSDK integration matrix pass is claimed here. Expected-panic tests are valid; no uncaught/fatal test-runner panic was found. The two aster-core IoError messages belong to its successful persistent-backend error-injection test.

## Source and tool provenance

The fixed upstream remains v0.19.0 commit `c4b7ed575b7b32773475b194d2ad41fb6d03765b` and `nightly-2026-07-21`. The unchanged run environment records local HEAD `7a27db93120dc2156b723512ef91628277455fb7`; its full tree `801e3e9143c165d6961a46bcda61215fdf1b1f8d` equals published `69335fcf2ccf4741346aa31bea2d1e3dca397ac6`. Their complete kernel and OSDK trees match source commit `4ae1a80e6b87fd55913bd01e6aadd28a20e6c322`. All 11 recorded build-input file hashes were checked against all three Git objects. The recorded dirty state is retained verbatim, without claiming a clean checkout.

The run used `--skip-osdk-install`, reusing source-built cargo-osdk SHA256 `1689a417b07b8fd8ec45a8dd2d2d103759bab25f63faec1ab486e606e1c24011` from the previous fresh make. The prior installation log records compilation and replacement. That installation occurred before publication with four OSDK files dirty; their recorded content hashes establish the equivalent published 4ae source. `provenance.json` pins the already retained installation log, original environment, command, source report and four-file hash report. This run does not claim a second OSDK installation or a clean rebuild of every cached dependency. Both generated test-base Cargo locks are retained unchanged and match the committed fixed lock inputs.

## Commands and evidence

`commands.json` is the original execution-time list of the two cargo-osdk test invocations. `top-level-invocation.posthoc.json` explicitly labels the parent's later transcription of the top-level command and environment. A complete inherited environment and a top-level numeric status file were not saved in the original run directory. The parent later polled the original completed tool session 59172 with write_stdin and obtained exit_code=0 with no stdout because output had been redirected. That completion receipt is explicitly recorded as a posthoc transcription, alongside both OSDK status0 files, raw QEMU33 records, complete guest results and the original PASS console.

Actual guest configuration was q35, TCG, CPU max, one vCPU, 512 MiB, SeaBIOS, serial and isa-debug-exit. The QEMU JSON preserves both the original requested upstream device arguments and the actual smaller argv; only the latter was run. No network, data disks, VMX/EPT exercise, ISO, Nix or userspace initramfs was needed for these kernel-mode tests.

Each target includes its complete cargo/OSDK log, raw serial bytes, QEMU command/input hashes, result, OSDK status and generated Cargo.lock. `artifact-references.json` points to the already retained ELF gzip files: decompression was verified against each executed kernel SHA and size, so no ELF binary is duplicated. BIOS is the standard host SeaBIOS package dependency; its recorded input hash is retained, rather than claiming a firmware binary in this archive. Current live input bytes were also checked after the run in `observations.json`; portable archive rechecking does not require those original absolute paths.

From this directory, `sha256sum --check SHA256SUMS` verifies the local content list. `python3 -I verify_archive.py` recreates the exact checker via Git, checks source/input/retained artifact hashes and runs both guest archives in normal, -O, -I and -I/-O modes without starting a VM. Its saved result is `archive-recheck.json`; it is a recheck of existing guest evidence, not eight new kernel boots. Reproduce a new real run from the project root with the recorded toolchain and dependency environment, `python3 -I support/build/ktest/run.py --output NEW_DIRECTORY`; omit `--skip-osdk-install` when a source-built OSDK is not already installed.
