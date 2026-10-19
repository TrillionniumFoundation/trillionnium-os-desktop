# A05 ReadUsage gate: exact current blocker and fail-closed contract

Baseline: `dd1478e1f7c5528d81ed91a94e4db86c45971623` (`main`, 2026-10-19). This is a read-only contract slice. It does not add authority, change the supported-op mask, create a host-model grant, or claim A07 durability.

## Result

`ReadUsage` cannot be safely enabled on this head. The kernel has a real Process/image session identity and a real CPU owner observation seam, but it has no trusted CapSpace grant admission, no kernel target-slot/generation registry, and no production bridge from the ioctl to the actual CPU owner. Enabling opcode 2 would therefore turn a session identity into authority or would require using `os-control`'s host/portable model as kernel evidence. Both are prohibited.

The current safe behavior remains:

- `QueryAbi` is the only advertised operation (`supported_ops = 1 << QueryAbi`);
- every valid `ReadUsage`, `InstallBudget`, `QueryDelivery`, and `RetireThrough` frame is decoded and rejected with `EOPNOTSUPP`;
- no open, dup, fork, inherited fd, or successful QueryAbi operation creates a grant;
- malformed transport, user copy faults, stale/foreign Process images, and unknown operations remain fail-closed.

## Exact source inventory

| Source | Exact call point | What is real | What is absent |
| --- | --- | --- | --- |
| `kernel/asterinas/kernel/core/src/device/misc/hepta_control.rs:54-64` | `process_session_id` | Boot-local nonce plus `ProcessImageKey` from the authoritative Process | No capability or ResourceDomain grant |
| `.../hepta_control.rs:86-96` | `HeptaControlDevice::open` | Saves `Weak<Process>`, space id, and image key | `open` intentionally does not authorize effects |
| `.../hepta_control.rs:105-120` | `HeptaControlFile::check_session` | Exact `Arc<Process>` and current image key/phase check | No trusted-init admission or revoke/lease check |
| `.../hepta_control.rs:158-205` | `HeptaControlFile::ioctl` | Bounded transport/request snapshot, one codec, and disabled-op rejection | No target resolution, grant check, owner lock, usage response, or effect |
| `.../hepta_control.rs:207-221` | QueryAbi response | Only `QueryAbi` is advertised; features/revision are zero | `ReadUsage` is not supported |
| `kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/native.rs:167-197` | `Controller::read_native_cpu_usage_for_owner` | Reads the actual `SubController<CpuController>` owner under existing CPU lock after N0 settlement | Private `#[cfg(ktest)]`-only call surface; no syscall/grant adapter |
| `.../cpu/native.rs:199-228` | `bind_native_cpu_once_for_owner` | Binds `NativeResourceState`/`NativeTarget` to an exact owner Arc under membership lock | Production bootstrap does not call it; no kernel CapSpace/slot registry |
| `kernel/asterinas/kernel/core/src/process/process/image.rs:168-198` | `hepta_capspace_session`, `check_hepta_capspace_session` | Process/image epoch, nonce, Live/Closing/Closed fencing | These are identity checks, not authority grants |
| `libs/os-control/src/lib.rs:301-1018` | `ResourceDomain`/`Grant` | Host/portable control model and `try_usage` invariants | Its own documentation says it is not kernel ioctl, scheduler, credential, or persistence evidence |

A direct source search at this baseline finds no kernel `CapSpace` grant table, trusted-init grant activation, or target-slot/generation resolver. The existing `CapSpace` text is the Process image namespace identity only.

## Why the minimal implementation is blocked

1. **No admission authority.** `ProcessImageKey` proves the caller is the same live image; it does not prove `resource.observe` for a specific target. Root/0600 devtmpfs metadata is not a grant.
2. **No target binding.** The wire request carries nonzero `(target_slot, target_generation)` for `ReadUsage`, but the kernel has no canonical mapping from that pair to the exact current `SubController<CpuController>`/`ResourceDomain` incarnation.
3. **No production owner entry.** The only usage method is private and checks single-CPU N0, local settlement, current-owner Arc identity, and the existing `CpuMax` lock. Calling it from ioctl requires a narrow public adapter with a specified lock order and closed/replaced-owner behavior.
4. **No response path.** `ReadUsageResponse` and status mapping are available in the codec, but no kernel code currently constructs or copies a successful response after authorization and owner sampling.
5. **No durable delivery claim.** A05 must not construct `K`, `D`, a delivery ledger, or an `os-control` host `NativeGrant` in the kernel. Those belong to the authenticated Hepta owner/A07 path and are a separate blocker.

## Required implementation seam before enabling opcode 2

The next implementation must add all of the following together, otherwise leave the operation disabled:

1. Trusted init/process-start admission that installs a scoped, revocable `resource.observe` grant bound to the exact Process/image key, boot, CapSpace, target domain, stable object, target slot, and generation. `open`/`dup`/`fork`/fd passing must not mint or widen it; successful exec must revoke the old image and require fresh admission.
2. A bounded kernel target registry that resolves `(slot, generation)` to the current native CPU owner and fences replacement/deletion. It must retain the exact `Arc<SubController<CpuController>>` identity and stable object, not a second accounting owner.
3. A public A05 adapter in the CPU controller that invokes the existing private observation seam after actual local settlement, under the documented membership → owner lock order, and returns `Closed`, `Indeterminate`, `UnsupportedProfile`, or accounting faults without manufacturing a sample.
4. `ReadUsage` request admission and `ReadUsageResponse` encoding/copyout with capacity preflight before any owner mutation or observation; map revoked/stale/closed/indeterminate outcomes to the HOS2 status contract and preserve fail-closed copyout semantics.
5. Exact negative coverage for foreign Process, inherited old fd, post-exec old key, revoked grant, owner replacement/deletion, wrong slot/generation, unsupported SMP/profile, clock rollback, accounting inconsistency, and response copyout faults.

Only after a positive one-vCPU QEMU guest proves a real static ELF reading the actual owner should `QueryAbi` add the `ReadUsage` bit. That result must be bound to the exact source head/tree, kernel/guest ELF, initramfs, QEMU argv, raw serial, exit code 33, and all negative markers.

## Exact regression and workflow contract

The contract guard is `tests/kernel/control/test_readusage_contract.py`. It is host-only and checks that this baseline still has the disabled mask, the Process/image checks, the real CPU-owner seam, and no kernel-side host-model grant shortcut. It is not presented as kernel evidence.

The exact kernel/QEMU regression remains the existing candidate runner:

```sh
python3 -I tests/kernel/control/run_queryabi_candidate_guest.py \
  --expected-source-head "$(git rev-parse HEAD)" \
  --expected-source-tree "$(git rev-parse HEAD^{tree})" \
  --target-dir "$RUNNER_TEMP/a06-target" \
  --output "$RUNNER_TEMP/a06-queryabi-candidate"
```

It builds and boots the ordinary product in a fresh x86_64 q35/TCG one-vCPU guest, checks the real QueryAbi response, and requires exactly one valid disabled marker for each of the four known operations, including `HEPTA_DISABLED_READ_USAGE_OK`. It is wired to the `A06 exact kernel scheduler and QEMU tests` workflow; the workflow also runs the A05 contract guard before this guest step. The `G0 scoped host contracts` workflow runs the same guard and host protocol regressions. A passing host guard or QEMU QueryAbi-only guest does **not** close ReadUsage; it proves only that the fail-closed boundary remains intact.

## Acceptance boundary

This contract is closed when a later exact-head PR provides the five implementation seams and the positive/negative QEMU receipt described above. Until then, leave `supported_ops` QueryAbi-only and keep `EOPNOTSUPP` for all four resource/history operations. Do not convert this audit into an A05/A07 completion claim.
