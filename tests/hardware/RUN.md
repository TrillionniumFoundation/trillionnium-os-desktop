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
