# Original partial activation recovery and durable preparation gates

`run_native_owner_activation.py` is the separate runner for
`activation-after-proof-v1` and `activation-after-material-v1`. It consumes
the actual original producer contract in `NATIVE_ACTIVATION_REENTRY.md`,
including its initial complete `continuity_owner` observation, and the
current `ROOT_ACTIVATION_WITNESS.md` commitment. It does not add these plans
to the existing six-case runner or replace the same-disk two-boot campaign.

The source review must bind the actually compiled original entry and product
kernel. The original 8 MiB ELF file and 16 MiB LOAD limits, release profile,
default features, four initial role admissions, successor bootstrap/receipts,
and kernel authority remain unchanged. Each new case retains a maximum
120-second outer deadline. Root sessions are 120 seconds, writer leases 20
seconds, Manager grants 300 seconds, Recovery grace 30 seconds and the
independent watchdog 5 seconds. None is enlarged to make the test pass.

## Actual required failure and recovery

Both cases start with the complete actual initial Manager authority and
Supervisor state, a real 25 ms CPU budget effect, its durable source terminal,
independent Current/material, history ACK and progressing two-period usage
window. The original writer then releases successfully and its original
Supervisor records the actual exit-zero/reap transaction.

The next original Recovery activation is interrupted by the actual Root's
held pidfd. The oracle requires the selected failure point, the same captured
Recovery boot/PID/start identity, original spawn, exact POLLIN, and actual
`waitid(WNOWAIT)` SIGKILL observation. An arbitrary activation error cannot
pass. The original Starting generation must finish in its exact Failed
successor with no active/healthy Supervisor runtime. Only its original driver
reaps the child; no synthetic Process or adopted fork/exec child is accepted.

| Actual interruption | Retained original head | Fresh Manager local generation | Fresh Manager owner epoch |
| --- | --- | --- | --- |
| After original canonical proof, before material installation | Exact released Manager head and physical cut | Same unused generation in the failed canonical registration | Failed canonical epoch + 1 |
| After actual physical material install/verification, before sealed bootstrap | Exact head installed for the failed Recovery | Failed canonical local generation + 1 | Failed canonical epoch + 1 |

The failed registration itself is the exact next local generation/owner epoch
after the initial Manager. Supervisor spawn, local generation, kernel launch
generation and owner epoch are checked as distinct quantities. The final
Manager uses the actual original Failed-to-Starting transaction, one fresh
kernel pair and the same reviewed ELF. Source code containing these paths
does not prove that any of these transitions executed.

The complete current/future unretired authority selection for this Agent
must be retired by exact original revocations. Every selected lease, its
revision CAS, store revision, reason commitment and real observation time
are checked. The reason binds the original domain, failed peer, whole
retained checkpoint token and complete selected lease. The empty selection
must follow those revocations. The actual old local lease expiry is observed
without extending it or pretending it was released.

The failed head, retained material and both original FinalUse frontiers must
remain consistent. The fresh canonical proof advances the original issuer
highwater and changes the failed proof. After-material recovery checks the
intermediate installed head explicitly: `material_adopted.previous` still
names the initial released Manager, while the new adoption counter/publisher
advance from the actual failed installed head. The physical cut remains the
same throughout that bridge.

The new Manager must execute a real 35 ms CPU-budget operation in its fresh
namespace, retain the original Applied receipt and source terminal, reach the
independent Current, ACK history, and show actual CPU and heartbeat progress
over at least two original periods. A watchdog restoration is read from its
own immutable retirement receipt; its revision/time cannot replace either D.
Only actual QEMU exit 33, without a timeout, excessive serial or extra event,
can finish a case.

## Exact original activation witness

Every recovered writer uses the original checkpoint owner's preparation,
before registry publication and canonical signing. The signed finite lease
payload is SHA-256 of this original serialized tuple:

1. Domain `hepta.original-checkpoint.activation.v1`.
2. The complete candidate registration in the original Rust field order;
   only `authority_lease.binding.payload_sha256` is replaced by 32 zero bytes
   while computing this digest.
3. The whole original predecessor token.
4. SHA-256 of the original serialized `material.anchor()` exact cut, encoded
   as the original transparent hexadecimal `Sha256Digest`.
5. The actual preparing Root lifetime.
6. The actual candidate publisher lifetime.

The oracle reconstructs these bytes from actual observations. It does not
mint, sign, install or pass them to an authority. The former
`[cut, spawn, local_generation]` payload is rejected; no version fallback is
provided. `native_owner_continuity_types.py` retains the original complete
lease/proof/fence validation, while `native_owner_activation_witness.py`
checks this additional exact commitment.

The original observation ID is `checkpoint-activation-v1.` followed by
SHA-256 of the complete candidate's original JSON bytes. Its physical file is
`observation-v1-<SHA256(id UTF-8)>.json` in the original checkpoint Root
directory. The payload contains exactly `schema_version`, `previous_token`,
`material_cut_sha256`, `root`, `peer`, and `candidate`. The unchanged original
wrapper contains `schema_version`, `observation_id`, and UTF-8 `payload` bytes;
the complete encoded record remains bounded to 16 KiB.

The guest path is
`/state/hepta-native/protected/authority/checkpoint`; the raw disk contains
the same bind source at `protected-source/authority/checkpoint`. Read-only
extraction uses the original held-descriptor inspector. It checks protected
Root ancestors, the private 0700 directory, all exact witness/lock names,
Root UID, mode 0600, regular-file identity, one link, empty distinct locks,
complete wrapper/payload bytes and actual retained material SHA. A missing
record, changed byte, extra unsigned candidate or substituted material fails.
No private signing-key bytes are read or exported.

Continuity and both partial-activation cases supply complete original
candidate DTOs. The partial cases require both failed and successful witness
records. The prior-boot campaign supplies the actual second-boot candidate
through its original authority observation. The two earlier crash cases
expose only a proof SHA and Current: their one candidate is selected from the
actual stopped disk's exact final canonical proof, validated against its
original issuer ID, complete signed claims/fence, actual observed spawn and
Current, and the whole protected registry frontier. No directory scan or
latest-file heuristic selects an authority. Historical multi-owner chains
cannot use this single-final-candidate path.

## Separate actual execution

Run from a clean integrated OS checkout. All seven input/output paths must be
absolute and the output must be a new directory outside sources/build inputs.
The harness identity is recorded separately from compiled source identities.

```sh
python3 -B tests/workloads/hepta_cpu_control/run_native_owner_activation.py \
  --execute \
  --desktop-source "$G2_FROZEN_OS" \
  --hepta-source "$G2_FROZEN_HEPTA" \
  --source-review "$G2_SOURCE_REVIEW" \
  --expected-source-review-sha256 "$G2_SOURCE_REVIEW_SHA256" \
  --owner-elf "$G2_ORIGINAL_OWNER_ELF" \
  --owner-build-receipt "$G2_ORIGINAL_OWNER_BUILD_RESULT" \
  --expected-owner-build-receipt-sha256 "$G2_ORIGINAL_OWNER_BUILD_SHA256" \
  --kernel-pipeline "$G2_PRODUCT_KERNEL_DIRECTORY" \
  --expected-kernel-pipeline-sha256 "$G2_PRODUCT_PIPELINE_SHA256" \
  --qemu "$G2_QEMU_BINARY" \
  --expected-qemu-sha256 "$G2_QEMU_SHA256" \
  --mkfs /usr/sbin/mkfs.ext2 \
  --debugfs /usr/sbin/debugfs \
  --bios /usr/share/seabios/bios-256k.bin \
  --timeout 120 \
  --output "$G2_NEW_ACTIVATION_OUTPUT"
```

Both new cases are selected by default; `--scenario` can select a named case
without claiming the other passed. `--kernel-pipeline` is the complete actual
product-build directory; its digest is the original `pipeline.json` SHA.
No execute flag means disabled, `passed=false`, and no guest attempt. There
is no CLI to inject a failed Process, witness, authority, clock or result.

Both original immutable-loader negative controls execute first. Every real
case then uses a separate fresh 256 MiB raw ext2 disk, the same admitted owner
and product kernel, and a fresh nonce. Original QEMU flags and CPU/memory/
network/device settings are retained. Every raw serial log, exact argv,
exit, tool identity, source snapshot, retained ELF/BIOS/initramfs and both
physical extraction stages are recorded. All source/harness/input/tool hashes
are checked again before the campaign can pass.

| Retained path | Evidence |
| --- | --- |
| `source-*.json`, `harness-source-*.json`, `owner-build/`, `kernel-build-evidence/` | Original source/build admissions and separately unchanged running harness |
| `manifest-byte-mismatch/`, `truncated-snapshot/` | Actual original loader negative controls before any role resumes |
| `<scenario>/qemu.json`, `serial.log`, `run-plan.json` | Actual bounded VM, raw exit, complete original events and fresh nonce |
| `<scenario>/state.raw`, `state-before.raw`, `format-state.*` | Actual fresh execution disk, retained preimage and real formatter receipt |
| `<scenario>/root-launch-observations/` | Original durable kernel launch/retirement records and actual Root inodes |
| `<scenario>/checkpoint-activation-witnesses/` | Original full activation preparations, exact canonical selection when needed, raw read-only commands and physical material hashes |
| `<scenario>/result.json`, `result.json` | Finite per-case/campaign conclusions with complete failure evidence |

A transcript alone keeps `passed=false` for the new cases. Only transcript,
actual launch files and actual activation witnesses together can set
`partial_activation_recovery_verified`. Overall
`both_partial_activations_verified` additionally requires both named actual
cases and both loader controls. These results do not qualify issuer
reservation cuts, fresh genesis recovery, unbounded control, host power loss,
cross-boot Unknown preservation, the other six cases, complete G2 or production
readiness. Those independent obligations remain explicit.

## Host validation

Run from `tests/workloads/hepta_cpu_control`:

```sh
python3 -B -m unittest -v test_native_owner_evidence test_native_owner_copyout \
  test_native_owner_runner test_native_owner_continuity test_native_owner_state_observations
python3 -B -m unittest -v test_native_owner_prior_boot_io test_native_owner_prior_boot_store \
  test_native_owner_prior_boot_disk test_native_owner_prior_boot_evidence
python3 -B -m unittest -v test_native_owner_activation test_native_owner_activation_witness
```

The groups contain the existing 52 and 20 tests plus the new partial-activation
and witness tests. They use inert parser records, private temporary ext2 files,
actual read-only extraction and a disabled-runner check. Their logs, real exits,
elapsed times and hashes accompany the delivery manifest. They never create a
native build receipt, original owner execution or guest qualification. Rust
Root tests and all actual native campaigns must still run independently under
the final frozen source pair.
