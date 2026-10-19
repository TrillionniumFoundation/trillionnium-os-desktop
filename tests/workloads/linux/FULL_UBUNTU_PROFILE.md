# Complete Ubuntu 24.04 x86_64 workload profile

`linux-ubuntu24.04-x86_64-20261019` is a new, explicit 32-case compatibility
profile. The original Debian 13 reference, four ELF hashes, rootfs manifest,
USTAR pin and failed recovery receipts remain unchanged. This profile does not
qualify the original Hepta Agentd W1, external provider credentials, hardware
devices or storage behavior across a power loss.

## Contract and implementation

The reviewed contract is
[`ubuntu24.04-x86_64-20261019.json`](../../../compat/linux/profiles/ubuntu24.04-x86_64-20261019.json).
It retains all 28 C ELF cases and the three Python workloads from the historical
32-case catalog. It also requires the actual locked Tokio program's four
standard threads, counter 4000, 16 async tasks, Unix socket roundtrip and async
filesystem results. Every case must return the complete concrete facts with
their original JSON types, actual process exit 0, and no stderr. No case can
be omitted, reordered, marked `not_run`, or replaced with a generic success bit.

| Component | Implementation | Required observation |
| --- | --- | --- |
| 28 static/dynamic C cases | Unchanged `probe.c` and `sqlite_probe.c` | File operations, process/exec/wait, locks, errno, futex, AF_UNIX, SCM_RIGHTS, resource limits, SQLite WAL/reopen |
| Three Python cases | `full_python_case.py` dispatches the unchanged functions in `run.py` | SQLite writers/crash/reopen, pathname AF_UNIX/epoll, localhost NSS and actual loopback TLS |
| Tokio case | Existing `rust/` source and reviewed lock, Tokio `=1.47.1` | Actual threads/tasks, Unix socket and async filesystem behavior |
| Runtime capture | `support/rootfs/ubuntu_full.py` | Every captured file's bytes/mode/source digest, and the loader/DT_NEEDED closure of each ELF, including extension/provider DSOs |
| Build/reference/guest entry | `run_full_ubuntu_profile.py` | One pre-execution input digest, one derived image, actual Linux and ordinary-kernel observations |

`/usr/bin/python3.12` is the interpreter in both the reference and guest. A
different Python installation earlier on PATH is not substituted. The image
contains its distribution standard library and extension modules, OpenSSL CLI,
configuration, available provider/engine modules, NSS files, public CA bundle,
UTC, and synthetic passwd/group/hosts/resolver configuration. Python bytecode
caches and development-only `config-*` trees are excluded. These are runtime
inputs, not a Python development SDK. Static dependency enumeration alone is
insufficient; all 32 actual Linux cases must subsequently pass from the image.

## Three stages and immutable inputs

`build` compiles each of the four C ELF files once and builds the locked Tokio
ELF once. Compiler logs and command vectors are retained. It captures runtime
bytes and derives `full-initramfs.cpio.gz` from the fixed original A01 image.
All original newc entries and metadata survive, except the intentional `/init`
insertion and its content length. The original boot checks remain active.

The build then writes `inputs.json` and `inputs.sha256`. The caller must retain
that digest **before** any reference workload runs. `reference` and `guest`
require it explicitly; neither is allowed to recompute a replacement digest
and silently accept changed inputs. They revalidate the contract, source
identity, helper files, manifest, all five ELF identities and image bytes.
The dynamic/static labels are checked against actual ELF program headers.

`reference` extracts that exact derived image into an owned temporary chroot.
Each command uses UID/GID 65534, an explicit environment, and an individual
private process group. It reuses the already maintained
`run_rlimit_nofile_guest.py::reference_process`, which uses
`run_original_agentd.py::ChildGroup/terminate_group`. Every terminal state is
observed through WNOWAIT, descendants are signalled before reaping, and the real
leader status is retained. There are no host mounts or host device attachments.
The rootfs copy and synthetic scratch files are removed after verification;
the immutable image and actual per-case invocation/stdout/stderr/exit records
remain. The verifier checks the complete environment/chroot/UID/workload argv
against the invocation frozen before execution. Those original paths remain
evidence when an artifact is moved; verification does not execute those paths.
Root is required only in the disposable CI process for chroot and UID
setup. Git trust is scoped per command to the explicit reviewed checkout; no
global Git configuration is changed.

`guest` independently revalidates all 32 original Linux raw observations. It
gets the ordinary kernel through the existing reviewed `product_input` chain:
the complete G1 product/QueryAbi receipt, exact reviewed source head/tree, and
unchanged before/after source snapshots. It executes the **same frozen image**;
the guest stage does not compile or repackage it. QEMU executable bytes are
bound to the build's pre-Linux tool digest. The fixed BIOS is also required.

Each guest workload is bounded by the original BusyBox timeout applet. The
script records its real exit status. It frames stdout and stderr as base64,
with their byte counts and SHA-256 digests, so kernel diagnostic lines cannot
be mistaken for or silently removed from application output. The host requires
all 32 frames in contract order, exact concrete facts, process completion and
the original boot marker, no kernel panic, no QEMU timeout, and raw QEMU exit
33. Exit 33 by itself never passes a case or a profile.

## CI dependencies and commands

Use a disposable **Ubuntu 24.04 x86_64** runner. In addition to the existing
A06 QEMU/SeaBIOS and fixed `nightly-2026-07-21` Rust setup, install:

```sh
sudo apt-get install -y gcc-13 libc6-dev binutils libsqlite3-dev \
  python3.12 python3.12-minimal libpython3.12-stdlib \
  openssl ca-certificates tzdata

cargo +nightly-2026-07-21 fetch --locked \
  --manifest-path tests/workloads/linux/rust/Cargo.toml
```

The build uses `/usr/bin/gcc-13 -O2 -std=c11 -Wall -Wextra -Werror -pthread`.
The static variants add `-static`; SQLite links `-lsqlite3`, with
`-lpthread -lm -ldl` on the static variant. The Tokio build uses:

```sh
cargo +nightly-2026-07-21 build --offline --locked --release \
  --target x86_64-unknown-linux-gnu \
  --manifest-path tests/workloads/linux/rust/Cargo.toml \
  --target-dir <new-bundle>/build/cargo-target
```

All output directories below must be new and outside the source checkout.
`HEAD`, `TREE` and `INPUT_SHA` denote independently frozen values, not mutable
references recomputed after a workload runs.

```sh
/usr/bin/python3.12 -I -B tests/workloads/linux/run_full_ubuntu_profile.py build \
  --a01-initramfs support/build/evidence/2026-10-16/artifacts/initramfs.cpio.gz \
  --expected-source-head HEAD --expected-source-tree TREE \
  --output <new-bundle>

# Freeze INPUT_SHA from <new-bundle>/inputs.sha256 before the next command.
sudo /usr/bin/python3.12 -I -B tests/workloads/linux/run_full_ubuntu_profile.py reference \
  --bundle <new-bundle> --expected-input-sha256 INPUT_SHA \
  --output <new-linux-reference>

/usr/bin/python3.12 -I -B tests/workloads/linux/run_full_ubuntu_profile.py guest \
  --bundle <new-bundle> --expected-input-sha256 INPUT_SHA \
  --linux-reference <new-linux-reference> \
  --product-evidence <ordinary-a06-product-evidence> \
  --expected-source-head HEAD --expected-source-tree TREE \
  --bios /usr/share/seabios/bios-256k.bin --qemu qemu-system-x86_64 \
  --output <new-guest-evidence>
```

`build` has no workload qualification claim. `reference` and `guest` return
nonzero unless their complete 32-case stage passes. There are no
`--proven-only`, `--rust auto` or skip switches. Keep all existing OSTD/core,
CLOEXEC 27, RLIMIT 37, ordinary product/QueryAbi and CPU qualification gates.
This additional profile does not replace any of them.

The Linux process-group guard has a three-second cleanup grace per case. The
guest case timeout is 45 seconds; the whole QEMU invocation defaults to 1500
seconds and is capped at 1800. A CI job timeout around 40–45 minutes permits
bounded failure diagnostics alongside the existing kernel build/test gates.
Actual successful runtime and disk use must be recorded by CI; the local
implementation host did not perform a new full build due to its disk budget.

## Retained artifact contract

Keep the complete `build` output for the first reviewed run, including:

- `inputs.json`, its original `inputs.sha256`, `build-input.json` and `result.json`;
- `runtime-manifest.json`, `contract.json`, `full_guest.sh`;
- `original-initramfs.cpio.gz` and `full-initramfs.cpio.gz`;
- all compiler/Tokio logs and all five actual files under `workload-elf/`.

Later archival may discard regenerable cargo target intermediates only after
retaining the five actual ELF bytes, the complete image, hashes and logs. Do
not discard failed build/reference/guest attempts when a retry succeeds.

Keep the Linux reference's `input.json`, `result.json`, and every
`cases/<name>/{input.json,stdout.log,stderr.log,exit-code.txt,result.json}`.
Keep the guest's actual kernel, BIOS, image, pre-execution input, raw serial and
receipt, plus the separate complete ordinary product/source evidence.

## Verification status

The maintained negative controls run as:

```sh
/usr/bin/python3.12 -I -B tests/workloads/linux/test_full_ubuntu_profile.py
/usr/bin/python3.12 -I -B -O tests/workloads/linux/test_full_ubuntu_profile.py
```

The implementation passed 27 tests in each mode. They cover strict
facts and types, every missing case, reordered/duplicate/malformed frames,
stderr and actual exit failures, raw-QEMU-33 masking, panic, original newc
metadata preservation, runtime replacement/extra-file/path/ELF drift, frozen
reference observations, full chroot/UID argv, bounded byte framing, DSO
dependency capture without a program interpreter, and the cargo proxy command
path. The actual BusyBox bytes from the original pinned initramfs also accepted
the generated script with `sh -n`; all required applets are present. These are host gate
tests with explicit synthetic fixtures, **not** Linux32 or guest32 evidence.
Real full-profile qualification remains pending the CI build, original Linux
32-case execution, and the same-image ordinary-kernel run.

## First complete-image CI failure and bounded repair

Run [39213225541](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39213225541), head `a027fd01253f3c816f6e67233089ceaa8fb82914`, compiled all five ELF inputs and captured 673 runtime files (43,204,445 bytes), then failed before Linux or guest execution with `archive exceeds limit`. The full image's fixed 256 MiB bound was not passed to the inherited 16 MiB small-probe newc parser. Artifact `12168244389` is SHA-256 `5d6824523b02bfeb41199d103ce61c013639eacb96514821b095085b24054a62`.

The parser now accepts a keyword-only positive integer bound while retaining its original 16 MiB default. Only the complete profile explicitly passes its already specified 256 MiB bound. The same captured bytes reproduce the original failure and then pass the corrected pack/validate roundtrip: 45,482,140 raw newc bytes, 16,653,770 gzip bytes, image SHA-256 `04aab3a89cc6a018e9111be0d5b7fa3a6586b8e80c8ac289e9501c3e95dfcca5`. The default small parser still rejects this image. The existing 27 runner tests remain, with two additional real large-image and invalid-bound regressions (29 total); SCM 8 and RLIMIT 18 related host regressions also pass. This forensic packaging replay does not execute or qualify the 32 Linux/guest workloads. The repaired exact-source CI must do that next.
