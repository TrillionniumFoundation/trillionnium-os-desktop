# Three-policy CPU comparison preparation

This directory freezes available real source inputs, checks the common trial
contract and imports bounded original-owner observations. **It does not yet run
or qualify a three-policy native experiment. It produces no benefit numbers or
ranking.** The actual fixed and ordinary feedback algorithms are implemented in
the companion Hepta `codex-rs/hepta-agentd/src/cpu_policy.rs`; their detailed
parameters, typed request adapter and tests are documented beside that source
in `CPU_POLICY_EXPERIMENT.md`.

## Actual paths and remaining runtime work

| Arm / prerequisite | Implemented entry | What still prevents a measured three-arm run |
| --- | --- | --- |
| Fixed target | `CpuPolicyKind::Fixed`, explicit target and bounded approach | Original-owner runtime embedding and final-consumer freshness after grant waits |
| Ordinary feedback | `CpuPolicyKind::Feedback`, two real same-direction samples | Actual wait-cause collector; ReadUsage does not expose I/O, lock or ancestor throttling causes |
| Hepta | Original Agentd operation/writer/grant-provider and `ProductionHos2Target` interfaces exist | Actual CPU policy/model/provider configuration and source-bound executable are not supplied |
| Original native owner | `../hepta_cpu_control/run_native_owner.py` and its strict raw-event oracle | Finite effect/recovery cycle only; no three controllers or whole-arm measurements |
| Existing SMP2 probe | `../../organ_backend/smp2/run_parallel_candidate.py` | Separate two-vCPU quota diagnostic; it is not the N0 policy experiment |

The synthetic Cart example is not a native CPU workload or the Hepta arm. A
feedback controller renamed Hepta, or three labels attached to one action trace,
cannot fill the missing runtime. No file here creates an ioctl path, delivery
sequence, signer, grant provider, writer, outbox or effect ledger.

## Freeze the available sources

After committing the selected Desktop tree and the actual Hepta companion
commit (including formatting), run:

```sh
python3 -B tests/workloads/policy_comparison/freeze_inputs.py \
  --desktop-source /absolute/frozen/desktop \
  --hepta-source /absolute/frozen/hepta \
  --output /absolute/new-evidence/source-inventory.json
```

The entry checks HEAD/tree, tracked cleanliness and skip/assume-unchanged flags,
hashes the actual policy/original adapter/writer/consumer and Desktop harness
files, and repeats the check. Cargo's ordinary untracked markers are permitted;
this is a tracked-source check, not remote attestation. The output records the
exact available policy source hash, concrete interface names and explicit
missing workload, collector, model, executable and measurement inputs. It never
fills missing fields with a model-generated success result. Re-run it after
integrating the single final companion commit; a branch name is insufficient.

## Common plan and per-trial records

`comparison.py` defines the exact machine-checked fields. Freeze the plan before
running any arm. Its schema is `hepta.cpu-three-policy-plan.v1`:

| Section | Required actual inputs |
| --- | --- |
| `common.sources` | Desktop and Hepta `head` / `tree` |
| `common.workload` | Code/data SHA-256 and complete unique `task_ids` |
| `common.native` | Kernel/rootfs SHA-256, `native-control`, `N0-single-cpu` |
| `common.budget` | Original 100 ms period, maximum and initial cap, whole-arm local CPU/memory ceilings, explicit external/no-external resource ceiling hash |
| `common.faults` | Exact profile and injection schedule SHA-256, including an explicit no-fault schedule |
| `common.environment` | Hardware and background profile hashes, predeclared temperature limits |
| `common.collector` | Actual source hash, continuous independent observer clock and whole-arm local/external accounting scope |
| `policies` | Exactly fixed, feedback and Hepta; actual source/executable/configuration hashes, original effect path, common bounded rules, inference location; explicit fixed target and real Hepta model configuration |
| `rounds` | Predeclared repeat count, seed, and separate cold/warm states |

The fixed and feedback policy rules are one accepted sample/proposal per second,
two-second maximum native/demand observation age, at most one tenth of the
authorized maximum per change, and two same-direction samples for feedback.
Initial budget and warm-up must be common; the fixed arm does not bypass the
slew bound to obtain a different startup advantage. `schedule(plan)` derives a
stable SHA-256 randomized order within each state/repetition. Keep cold/warm
results separate; do not reshuffle or drop failures after observing results.

Each `hepta.cpu-policy-trial.v1` record binds the entire plan, common inputs,
policy and budget, and retains every predeclared task. Task statuses are success,
failure or timeout, with actual observer start/end or censoring times and a hash
of the completion/failure evidence. Missing, duplicate, skipped and unsupported
tasks cannot pass as complete trials. The gate preserves failures and timeouts
in the denominator; a failed task does not disappear from its arm.

Costs must include all owned local processes, split into non-overlapping
workload/policy/observation/install/recovery/local-inference CPU categories;
aggregate owned-subtree peak RAM; end-to-end energy; and recovery elapsed time
and lost work. External inference requires **separate real provider CPU, peak
memory and attributable energy measurements**, not zero or the caller's client
CPU time. Local and remote peak memory are separate peaks, not a fabricated
simultaneous sum. GPU/provider resource details must remain in their frozen
profiles and measurement evidence; a local process's RSS is not GPU or remote
memory.

Energy must cover an exclusive whole-trial system/domain with the actual meter
and exclusivity evidence identified. Shared host/package RAPL is not per-task
energy. A provider without attributable energy leaves the net-energy comparison
unavailable. Do not divide unrelated shared-package joules by task count and
call the result a measurement. All retries, failures, inference, observation,
installation and recovery remain inside the measured interval.

Run the contract checker using new output paths:

```sh
python3 -B tests/workloads/policy_comparison/comparison.py \
  --plan /absolute/frozen/plan.json \
  --trials /absolute/retained/trials.json \
  --output /absolute/new-evidence/contract-result.json
```

It writes specific contract errors and retained reported denominators. It exits
**2 even when the JSON contract is complete**, because the source-bound actual
three-arm runtime/collector is not implemented. `contract_complete` is distinct
from `native_measurements_verified`, `comparison_complete` and `ranking_allowed`;
the latter remain false. A self-reported `passed` flag or digest is not native
execution or authentication. Future runtime qualification needs the actual
collector's raw-record parser and original-owner dispatch/freshness integration,
not simply changing these booleans. This prevents complete-looking JSON from
being promoted to experimental evidence while those implementation gaps remain.

## Read the existing original-owner evidence without changing its scope

```sh
python3 -B tests/workloads/policy_comparison/native_observation.py \
  --native-result-directory /absolute/retained/native-owner-run \
  --expected-receipt-sha256 ACTUAL_ROOT_RESULT_SHA256 \
  --source-inventory /absolute/frozen/source-inventory.json \
  --output /absolute/new-evidence/native-prerequisite.json
```

The importer checks selected Desktop/Hepta/harness identities and retained raw
serial/QEMU hashes, then re-runs the existing original native-owner oracle. It
exports bounded workload CPU/heartbeat windows only after that parser accepts
the original K/D/terminal/retirement sequence. It performs no guest run and does
not revalidate a remote build host or elevate the source receipt's qualification.
The output has no policy-arm identity, whole-arm costs, task latency/success or
energy, and cannot be accepted as a trial by the comparison checker.

## Reproducible checks

```sh
python3 -B -m unittest discover -s tests/workloads/policy_comparison -p 'test_*.py' -v
```

The fixtures are explicitly inert contract records. Negative checks remove the
Hepta arm, alter the budget/source/order, drop a timeout, omit external inference
cost, substitute shared-package energy or one-process RSS, and mutate original
raw native events while preserving a rehashed `passed` receipt. A complete inert
contract still cannot qualify native measurements or a benefit claim. These
checks do not manufacture benchmark data or prove that either policy improves
latency, throughput, energy, stability or recovery.
