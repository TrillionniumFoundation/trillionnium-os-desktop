# Native OSDK integration evidence

Published runner code: `efff58b94b167dc9a9f66b3a742a31189aa7805e`.
The unchanged pinned source is Asterinas v0.19.0,
`c4b7ed575b7b32773475b194d2ad41fb6d03765b`; the final adapter uses
`nightly-2026-07-21`, rustc commit
`87e5904f5eb6398af6b22eac2802c78934260c48`.

The 22-case latest-result view is **20 passed, 2 failed**, with **2 host-blocked
cases** and **1 VMX soft skip**. No case was removed from the denominator.
This is a per-case view across the original complete attempt and explicit
retries, **not** a single all-22 run from the final runner source.
`latest-results.json` links every original result, latest result, retry,
command, harness log and guest record with archive-root-relative paths.

| Run | Selection | Observed result |
| --- | --- | --- |
| `attempt-07` | All 22 real integration cases | 19 passed, 3 failed; 1 VMX soft skip |
| `attempt-08` | Coverage retry after fetching fixed dependencies | Real fixed-source build completed; UNIX monitor rejected with EPERM |
| `attempt-09` | kernel100 with explicit local align_ext dependency | Passed; real QEMU raw exit 33 |
| `attempt-10` | Coverage retry with a short owned TMPDIR | Real QEMU UNIX monitor still rejected with EPERM; raw exit 1 |

The UNIX GDB case retains its original transport and fails because QEMU cannot
create its UNIX socket. Coverage retains its original UNIX monitor transport
and fails for the same host restriction. The exact QEMU stderr is saved next to
each guest record. Neither permissions nor namespaces were changed. No raw
coverage profile was produced, so this archive claims no usable coverage.

The separate VS Code case used its real loopback TCP GDB listener, the original
Cargo symbol ELF, an actual GDB register read/detach, and a real guest that exited
33. It is not evidence that UNIX sockets work. The hypervisor example accepted
its upstream VMX-unavailable fallback; its complete serial log makes that soft
skip explicit, rather than claiming VMX execution.

These tests exercise actual OSDK tooling and small OSTD example kernels, not the
complete Asterinas kernel or HOS/Linux/Android/desktop workloads. The complete
Asterinas boot and kernel test evidence belongs to the surrounding phase report.

The isolation profile copies only the tests into scratch. Its final three
source adaptations are fixed `/tmp` prefixes to a newly created owned short
root, the local OSTD helper's manifest anchor, and kernel100's `align_ext`
dependency redirected to the fixed vendored path at the same version 0.1.0.
All assertions remain unchanged. The pinned toolchain file is copied unchanged
to support the test helper's relative include. Every run records its exact
harness patch and original/adapted test hashes; existing host example directories
are untouched.

Generated dependency locks are normalized offline from the fixed root lock and
external name/version/source/checksum identities must be a subset of that seed.
Actual builds use `--locked --offline`. The independently built harness is
similarly normalized from the original OSDK lock. The original root and OSDK
locks retain SHA256 `6b5de5d78a8e794567e1b07f1e7c621079023ff7f03c6c618abb7d5c09d8e316`
and `99a21f72f6a9f1582553b34f06e80f86e539f38e62eab7a0847afd0906e75be3`.

Earlier failed attempts remain available:

- 01 lacked a fixed Windows dependency in the local cache; a locked fetch is
  recorded. 02 and 03 exposed missing isolated-harness dependencies and the
  original relative toolchain include.
- 04 rejected new external versions after premature metadata had pruned the
  seed. The final adapter always restarts real resolution from the full seed;
  `--no-deps` metadata only identifies manifests before local OSTD is added.
- 05 exposed the upstream new-project template's unqualified `nightly` plus
  OSDK removing `RUSTUP_TOOLCHAIN`. It auto-selected a different nightly in the
  task's isolated toolchain directory and failed with incompatible compiler
  metadata. No successful guest is attributed to that attempt. The final
  adapter restores the fixed channel and absolute compiler paths, disables
  automatic installation, checks the compiler commit, and records executable
  paths, versions and hashes on real Cargo requests.
- 06 established the TCP VS Code pass and original UNIX GDB failure. 07's
  kernel100 registry identity was rejected and remains recorded; 09's explicit
  fixed local path is a documented profile adaptation.

`provenance/attempt-07-to-published-runner.patch` and the corresponding 08/09/10
patches describe the exact runtime runner differences from the published code.
The reconstructed earlier runner bytes were checked against each run's recorded
SHA256. In particular, 07/08 precede the third dependency adaptation and short
TMPDIR; 09 precedes the short TMPDIR and additional local-source hash fields.
The final source hashes match the published commit. Final and independent parent
pure-test logs both report **19 passed**; these are host regression tests, not
additional guest cases.

Each run's `invocation.json` and the supplemental dependency-fetch command
records are explicitly marked as recorded after execution from observed tool
calls. The raw exits are retained. Top-level terminal logs are archived as
`runner.log.gz`; the initial missing-rustc fetch failure and subsequent fixed
fetch success are both preserved. Logs use deterministic gzip. No generated
example implementation, target directory, or tool binary is included.

Reproduction from the project root:

```sh
python3 -I support/build/osdk-integration/run.py \
  --output "$PWD/support/build/out/osdk-integration-new"
```

Use the environment selection in each `invocation.json` for the recorded native
host. QEMU is the installed Ubuntu 8.2.2 binary, with explicit SeaBIOS, q35, TCG,
CPU max, one vCPU, 512 MiB, serial logging, no network and no data disk. Complete
requested and actual QEMU commands and artifact hashes are in each `qemu.json`.
An existing output is rejected, all cases are bounded, and only the run's owned
scratch paths can be cleaned up.
