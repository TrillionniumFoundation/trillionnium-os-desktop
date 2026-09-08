# Non-Cargo component development documentation

This index covers every non-Cargo component discovered by
`tools/validate_component_documentation.py`. The machine registry is
`manifests/components.v1.json`. Cargo workspace members remain governed by
`manifests/modules.v1.json` and `docs/modules/README.md`.

| Component | Path | Kind | Status | Documentation |
| --- | --- | --- | --- | --- |
| `repository-automation` | `.github` | `automation` | `source_policy_active_live_governance_external` | [`.github/README.md`](../../.github/README.md) |
| `contract-catalog` | `contracts` | `contract-catalog` | `normative_source_contracts` | [`contracts/README.md`](../../contracts/README.md) |
| `documentation-system` | `docs` | `documentation` | `normative_human_projection_with_machine_index` | [`docs/README.md`](../../docs/README.md) |
| `d3-semantic-resolver-experiment` | `experiments/d3-semantic-resolver-rust` | `experiment` | `deterministic_reference_not_servo_adapter` | [`experiments/d3-semantic-resolver-rust/README.md`](../../experiments/d3-semantic-resolver-rust/README.md) |
| `servo-embedder-probe` | `experiments/servo-embedder-probe` | `experiment` | `exact_pin_compile_probe` | [`experiments/servo-embedder-probe/README.md`](../../experiments/servo-embedder-probe/README.md) |
| `servo-headed-runtime` | `experiments/servo-headed-runtime` | `experiment` | `headed_host_and_d2i_candidate_runtime` | [`experiments/servo-headed-runtime/README.md`](../../experiments/servo-headed-runtime/README.md) |
| `manifest-catalog` | `manifests` | `manifest-catalog` | `canonical_machine_truth_and_input_locks` | [`manifests/README.md`](../../manifests/README.md) |
| `debian-packaging` | `packaging/debian` | `packaging` | `candidate_image_and_service_packaging` | [`packaging/debian/README.md`](../../packaging/debian/README.md) |
| `platform-boundary` | `platform` | `platform-boundary` | `reserved_boundary_no_product_adapter` | [`platform/README.md`](../../platform/README.md) |
| `runtime-boundary` | `runtime` | `runtime-boundary` | `canonical_runtime_pointer_no_duplicate_implementation` | [`runtime/README.md`](../../runtime/README.md) |
| `service-boundary` | `services` | `service-boundary` | `reserved_authority_split_no_service_implementation` | [`services/README.md`](../../services/README.md) |
| `test-system` | `tests` | `test-system` | `authoritative_discovered_python_and_shell_corpus` | [`tests/README.md`](../../tests/README.md) |
| `validation-toolchain` | `tools` | `toolchain` | `reviewed_validation_and_evidence_toolchain` | [`tools/README.md`](../../tools/README.md) |
| `wasi-worker-boundary` | `workers` | `worker-boundary` | `reserved_wasi_component_boundary` | [`workers/README.md`](../../workers/README.md) |

The registry and documents are a source-quality gate. They do not prove live
repository settings, installed runtime behavior, physical hardware, HSM
custody, signatures, or release publication.

Run:

```bash
python3 tools/validate_component_documentation.py
```

The validator rejects missing discovery coverage, duplicate IDs or paths,
short/missing documents, missing required sections, unsafe or symlinked
paths, missing references, and missing CI/contributor integration.

## Exact status and claim projections

Both documentation gates now call `tools/documentation_claims.py`. The README
must contain one exact registry status and one exact claim-ceiling projection
inside its canonical section. Missing, conflicting, repeated, disguised, or
stale values fail closed; matching prose does not promote a gate. The format,
negative corpus, and limitations are specified in
[`DOCUMENTATION_CLAIM_PROJECTIONS.md`](../architecture/DOCUMENTATION_CLAIM_PROJECTIONS.md).
