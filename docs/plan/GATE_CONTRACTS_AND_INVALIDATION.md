# Gate contracts and evidence invalidation

**Revision:** `2026-08-29-d6`  
**Machine registry:** `manifests/gates.v1.json`

## Contract shape

Every gate defines:

- prerequisites;
- immutable source/input locks;
- implementation outputs;
- test classes;
- exact commands;
- evidence tier;
- required artifacts and digests;
- claim ceiling;
- invalidation paths;
- review class;
- allowed failure outcomes.

## Gate outcome rules

`PASS` means every required command ran and every required artifact was
validated. A skipped command cannot satisfy a gate. Runner provisioning,
tool-install, cache, or formatting failure is `INFRASTRUCTURE_FAILURE` or
`CI_BLOCKED`, not product incompatibility and not a pass.

`MODULE_CLOSED_CANDIDATE` means the package branch is complete but not
integrated. `INTEGRATED_AND_EXACT_MAIN_VALIDATED` requires a main-branch rerun.

## Canonical command baseline

For the integrated Rust workspace:

```bash
python3 tools/validate_repository.py
python3 tools/validate_project_truth.py
cargo fmt --all --check
cargo check --workspace --all-targets --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --all-targets --locked
cargo run --locked -p hepta-browserd -- --self-check
```

Specialized gates add their own independent reference, QEMU, fault-injection,
headed runtime, image, hardware, or release commands.

## Required evidence envelope

Each evidence JSON must contain at least:

```text
schema
gate_id
package_id
status
evidence_tier
repository
base_sha
candidate_head_sha
tested_merge_sha
integrated_main_sha
tree_sha
workflow_path
workflow_sha256
input_digests
runner
commands
artifacts
claim_ceiling
recorded_at
```

Fields that do not yet exist are explicit `null`; they are not omitted or
inferred.

## Invalidation closure

The machine registry is the minimum closure. A gate implementation may add more
inputs but may not remove listed inputs without a plan revision and review.
The truth validator checks that all active workflows and machine manifests are
included in their own invalidation sets.

## Promotion review classes

- `standard`: ordinary deterministic implementation;
- `security`: trust, identity, origin, sandbox, capability, receipt, or egress;
- `release`: update, signing, rollback, provenance, release;
- `repository-setting`: branch rules, team ownership, secret/signing custody.

Authors may prepare evidence but may not self-certify repository-setting or
release gates.
