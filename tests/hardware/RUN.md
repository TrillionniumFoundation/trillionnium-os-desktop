# A09 hardware entry points: evidence is scoped to the execution kernel

The A09 second-phase tests are **read-only hardware discovery** and **CPU-only
contract fixtures** until an authorized, physically isolated GPU lab exists.
None of these scripts is a Rust kernel driver or VMM. Never run compute on H3,
training, production devices, shared system-disk guests or an active host GPU.
No Ollama, GPU driver rebind, firmware flash, power/thermal change, or reset.

## 1. Safe inventory — no device access

```sh
python3 support/hardware/probe.py --target-vendor nvidia --output -
python3 -m unittest discover -s tests/hardware -p 'test_*.py' -v
python3 -m py_compile support/hardware/probe.py support/hardware/vfio_preflight.py \
    tests/hardware/cuda_gemm.py tests/hardware/run_isolated_cuda.py \
    tests/hardware/test_*.py
```

## 2. Independent read-only group review — never an assignment permission

On an *isolated laboratory Linux host*, first read `probe.py` output for actual
PCI BDF and the **whole** IOMMU-group membership (including any audio or USB
functions). Then replace the examples with the observed IDs:

```sh
python3 support/hardware/vfio_preflight.py \
    --bdf '0000:01:00.0' \
    --expected-member '0000:01:00.0' \
    --expected-member '0000:01:00.1' \
    --vendor '0x10de' --device-id '0xNNNN' --output -
```

`0xNNNN` is a placeholder and will be rejected; substitute the **observed** PCI
ID. Group allowlist must match exact sysfs membership. Exit **2** means a hard
blocker (missing GPU, unsafe no-IOMMU, occupied group, invalid identity, etc.);
exit **3** means incomplete independent manual review, NOT authorization for
passthrough. There is intentionally **no pass/ready state**. ACS, interrupt
remapping, DMA quiescence, reliable reset, idleness, physical host ownership,
and actual guest isolation cannot be established by these Linux sysfs reads.
It never invokes VFIO, writes sysfs or unbinds drivers. Asterinas ownership
requires separate host-side evidence. See
[Linux VFIO IOMMU groups](https://docs.kernel.org/driver-api/vfio.html).

## 3. Bounded real CUDA compute — isolated idle lab ONLY

After **separately proving a disposable isolated NVIDIA GPU is idle**, and
confirming NVIDIA Linux driver + compatible GSP/firmware as applicable,
`libcuda.so.1` and `libnvrtc.so` are installed in the *actual Linux guest*:

```sh
python3 tests/hardware/run_isolated_cuda.py \
    --isolated-lab --require-name 'RTX 4060' \
    --require-bdf '0000:01:00.0' --timeout-seconds 30 --output -
```

The required exact BDF is the guest-visible target from that same guest. DO NOT
copy the example BDF or use `--isolated-lab` to misrepresent a production GPU.
The runner launches `cuda_gemm.py` as a bounded child and verifies the JSON
output (device BDF/model, CUDA launch, sync, copy, result SHA and resource
release). `cuda_gemm.py` itself requires isolated-lab opt-in and exact BDF,
including on direct Python calls. It uses CUDA Driver API + NVRTC to compile
and dispatch a **real GPU** 16x16x16 FP32 GEMM with deterministic integer-valued
inputs and an all-256-value **exact** CPU reference. Expected output SHA256:
`5bf61d6bb17edb58d70dd37589eeab5a02f5cc5d0c5aae5d142b06678416d847`.
No CPU compute fallback is allowed.

Runner exit codes: `0` child *reports* successful local CUDA in the execution
kernel, `2` blocked, `1` invalid result/numeric/CUDA failure, `4` child timeout.
Timeout/kill **does not prove device DMA stopped**; any uncertain effects require
fencing/quarantine by the future real Rust host (not implemented). A synthetic
fixture that returns exit 0 is **only** a unit test, not physical GPU evidence.
The runner always leaves `host_asterinas_execution_attested=false`,
`physical_gpu_passthrough_attested=false`, `DMA_quiescence_attested=false`.
Only independent Rust-host guest lifecycle/IOMMU/physical-card evidence can
advance those gates. The Linux host CUDA result, a QEMU VM on Linux, and a
Linux guest on Asterinas are **different execution claims**.

## 4. Actual 2026-10-16 execution-tool container results

- Linux 6.18.44, visible AMD EPYC 9V74 virtual CPU; no NVIDIA PCI GPU,
  `/dev/nvidia*`, `/dev/kfd`, `/dev/dri/renderD128` or `/dev/kvm`.
- `33/33` CPU-side/fixture unit tests pass (no GPU compute); Python syntax
  compilation passes. Rust compiler and QEMU were not available in this tool
  environment; no Asterinas host/VMM build/run test.
- [Original inventory](evidence/2026-10-16-container-probe.json),
  [read-only VFIO blocker](evidence/2026-10-16-vfio-preflight-blocked.json),
  [bounded CUDA blocker](evidence/2026-10-16-bounded-run-blocked.json).
- VFIO preflight: **exit 2**, target PCI BDF absent, no assignment.
- Bounded CUDA: **exit 2**, `libcuda.so.1` missing. No actual GPU context,
  DMA/queue submission, result or recovery validated.

## 5. Explicit seven-stage hardware acceptance

| Stage | Status now |
| --- | --- |
| Enumerate real GPU + matching PCI IDs + driver/firmware | BLOCKED; candidate only |
| Allocate real device memory | NOT RUN |
| Submit actual GPU command | NOT RUN |
| Copy back result | NOT RUN |
| Compare GPU with fixed CPU golden output | CPU golden tested only |
| Release actual device and queue resources | NOT RUN; cleanup code unit-tested only |
| Recover after device/VM failure | NOT RUN; timeout effect remains unknown |

**Next real gate:** A01 supplies fixed pinned Asterinas source/boot and host
memory/IOMMU/VMM surfaces; A05 owns CapSpace resource rights/lease and identity;
A06 owns ResourceDomain CPU/RAM/pinned-DMA budgets and protected recovery
reserve. Obtain an actually authorized, idle, isolated RTX 4060 and record PCI
IDs, entire IOMMU group, driver and loaded firmware, CPU VMX/SVM support,
actual PCI reset qualification, and separate Asterinas-host/Linux-guest logs.
Do not issue any production reset, driver detach or firmware change.


## Phase 3 (2026-10-16): cross-kernel provenance and Rust lifecycle contract

The independent cross-layer consistency gate is at `support/vmm/acceptance.py`,
described by `support/vmm/PROVENANCE.md`. It requires separate raw host/guest
logs, matched VM boot nonce/PCI identity, verified IOMMU and interrupt isolation,
successful bounded CUDA evidence and proof of DMA quiescence at teardown. This
is NOT an attestation authority: unsigned JSON/logs remain forgeable, so it
only returns `blocked` (2) or `independent_hardware_review_required` (3);
it never claims a hardware pass.

Host/guest evidence gate, missing real host and guest files:
```sh
python3 support/vmm/acceptance.py \
  --host host-vmm.json --host-log host-boot.serial \
  --guest guest-gpu.json --guest-log guest-boot.serial --output -
# blocked (exit 2) until independent real host + guest captures exist
```

The dependency-free Rust `#![no_std]` device transition model is under
`support/vmm/device_lifecycle/`. It encodes exclusive domain, buffer, queue
and completion generation/sequence checks, but does NOT perform DMA, hardware
quiescence, authorization or ResourceDomain charging. Rust tests are **not
executed** in the accessible tool container (no `rustc`/`cargo`), and need
an A00-scoped CI change before review/merge:
```sh
cargo test --manifest-path support/vmm/device_lifecycle/Cargo.toml --offline
```

Actually re-run in the execution-tool Linux 6.18.44 container:
- Python hardware tests: **50/50 pass**, 0 failures; Python syntax check pass.
- PCI read-only inventory: exit 0 (no NVIDIA GPU). No `/dev/kvm` or GPU nodes.
- VFIO preflight: **exit 2**, missing target, NOT safe for assignment.
- CUDA runner: **exit 2**, `libcuda.so.1` missing; NO physical GPU command.
- Cross-kernel acceptance: **exit 2**, host/guest evidence files absent.
- QEMU, Rust compile, physical GPU passthrough, failure recovery: **NOT RUN**.

Immutable scope summary: `tests/hardware/evidence/2026-10-16-phase3-summary.json`.
No production/H3/training devices were modified. No Ollama used.

## Post-A01 merge status

Latest verified main `e44c92ac885eb003665ff2e1e5c6fab1f104b2d6` includes
A01's pinned complete Asterinas kernel and QEMU boot baseline (merged PR #5).
This means source checkout/boot is available **in the repository**, not in
the limited A09 execution container, which still has no Rust compiler, QEMU,
GPU or KVM. No Rust VMM or GPU computing has been run by A09 on that kernel.


## A09 fail-closed CUDA submission cleanup (2026-10-16 follow-up)

The CUDA Driver API test previously attempted explicit `cuMemFree_v2`,
`cuModuleUnload`, and `cuCtxDestroy_v2` in `finally` even after a kernel launch
was attempted but no successful `cuCtxSynchronize` had been observed. This
risked treating an unknown-effect hardware command as quiescent. The corrected
test records `submission_attempted=True` immediately before `cuLaunchKernel`
and only grants explicit resource release after `cuCtxSynchronize` returns
success. If launch or synchronize reports an error, explicit frees are
suppressed and `UNKNOWN_DMA_EFFECT` is included in the error. Neither the
GPU driver nor the test claims that process exit stops DMA: independent host
quiescence / IOMMU fencing and quarantine remain required.

`tests/hardware/test_cuda_cleanup.py` exercises five CPU-only fake-driver
cases: uncertain launch (zero explicit frees), successful synchronization
(full cleanup), failure before submission (cleanup), cleanup errors reported,
and uninitialized context. The isolated test fixture ran 5/5 successfully
in the execution container; **a physical CUDA driver and new Rust kernel have
NOT been exercised**. This is not proof that GPU hardware has been recovered.

A test runner must **not** retry hardware work automatically after an
unknown-effect submission; the canonical A01/A05 device owner must mark the
device instance and outstanding queue generation unsafe until physical
quiescence is confirmed, and A06 must retain pinned-DMA charges. No automatic
GPU reset, host driver unbind, firmware or production service alteration.


## Linux subprocess output/timeout limits for disposable GPU lab

`tests/hardware/bounded_process.py` is now the default process runner used by
`run_isolated_cuda.py`. It does **not** run privileged device setup. Its
nonblocking `selectors` loop reads the Linux child's stdout/stderr with a
64 KiB **in-memory maximum per stream**, immediately stopping the isolated
child process group when output exceeds the cap. It does NOT use
`RLIMIT_FSIZE` or change the child file-size limit: CUDA/NVRTC must be
allowed to write normal compiler caches and other unrelated files.
There are no unbounded `subprocess.run(capture_output=True)` buffers.

Timeout kills only the fresh child process group and returns a
`TimeoutExpired`. Neither termination nor EOF is evidence that GPU DMA
stopped; children that detach into a different process session are an
independent host supervisor concern. The output-limit failure is mapped to
`failed_output_limit_device_effect_unknown`. Queue/device effects remain
`unknown`, not recovered, and no more GPU work should be admitted until
the A01/A05 hardware owner verifies quiescence. Safe <64 KiB JSON is
returned unchanged; nonzero child exits are not swallowed. The limiter
has no MMIO/IOMMU or firmware authority.

Eight subprocess-only Python tests (normal JSON, bounded stdout/stderr,
timeout/group kill, nonzero child code, invalid capture settings, cap size,
and a 1 MiB unrelated file write with no artificial RLIMIT interference)
ran **8/8 in the execution container** with no GPU or KVM access. Two
additional CPU-only integration assertions in `test_runner.py` cover
overflow classification and default bounded-runner selection, pending
the full CI run. Rust, Asterinas guest GPU computation and physical
reset/recovery remain unverified.


## First-lab Intel VMX/VT-d feasibility check

The `support/vmm/platform_gate.py` code reads the unmodified read-only
`probe.py` inventory. The candidate policy is Intel `GenuineIntel` plus a
visible `vmx` flag, DMAR table, IOMMU groups and NVIDIA GPU. AMD `svm` is
**not** Intel VMX, and cannot substitute for the pinned upstream VMX backend.
A passing synthetic inventory returns only `manual_review_required` (exit
3), never permission to bind VFIO, reset or attach a physical device. Seven
CPU-only negative/synthetic tests passed in the A09 container; an absent
inventory file was also checked to return `blocked` (exit 2). No real
suitable lab machine has yet been identified or exercised.
