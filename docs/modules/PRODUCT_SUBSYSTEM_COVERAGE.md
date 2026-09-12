# Product subsystem documentation coverage

Cargo package coverage is not whole-product coverage. This map is a design
navigation and acceptance checklist, not a second status registry. Actual
maturity remains in project-state, current non-claims and exact-object evidence.

| Boundary | Current documentation entry point | Required delivery beyond a README |
| --- | --- | --- |
| Governance and evidence | `docs/governance/BRANCH_PROTECTION_REQUIRED.md`; `docs/plan/PROJECT_TRUTH_AND_EVIDENCE.md` | Live enforced settings, independent review/probes, artifact identity and invalidation |
| Rust packages | Generated `docs/modules/README.md`; `manifests/modules.v1.json` | Exact Cargo inventory, API/configuration behavior, module tests and reviewed contracts |
| Servo/product supervision | `docs/architecture/S08_PRODUCT_SERVO_SUPERVISION.md`; `docs/architecture/S08_SERVO_BROWSER_ACTOR_VERTICAL_SLICE.md` | Real product entrypoint, event-loop ownership, command completion, journal continuity and crash reconstruction |
| Linux and desktop input | `platform/linux/README.md`; `docs/architecture/TRUSTED_WORKSPACE_COMPOSITION.md` | Actual window/frame/focus/keyboard/pointer/IME and human preemption; endpoint custody alone is insufficient |
| Debian image/QEMU | `docs/architecture/D1_DEBIAN_QEMU_SUBSTRATE.md`; `docs/architecture/D2I_INTEGRATED_IMAGE.md` | Exact installed product path, package inventory, reproducibility, crash/reboot and no fixture substitution |
| Receipt operations | `docs/architecture/MANAGED_RECEIPT_STORE.md`; `docs/architecture/RECEIPT_PERSISTENCE_FAULT_MODEL.md` | Capacity/archival policy, reconcile-only recovery, explicit repair authority, privacy and anti-rollback threat boundary |
| Trusted applications | d6 D5 and inherited product-origin design | Signed bundle format, trust-root/revocation/rotation, CSP/storage/worker isolation and data migration |
| Capabilities and network egress | d6 D6 and `platform/linux/README.md` | Concrete services and permit-bound I/O; DNS/TLS/connected-peer/redirect enforcement and bypass corpus |
| TaskFlow/Agent collaboration | Actor module contract and d6 D3/D4/D7 | Task lifecycle, typed model-output admission, consent, cancellation, budget and human handoff; webpage text cannot mint authority |
| Update and recovery | `docs/architecture/S11_UPDATE_RECOVERY.md` | Production-rooted signature verification, installed slot/boot-health integration and interruption/recovery evidence |
| Hardware and release | `docs/architecture/S12_RELEASE_QUALIFICATION.md` | Independent builders, physical BOM, actual 24/72-hour endurance, raw power cuts, key custody and protected publication |

For every boundary, the development handoff must identify responsibility and
exclusions, concrete APIs/configuration, dependency/call direction, resource
budgets, state transitions, failure/recovery semantics, security invariants,
executable positive/hostile tests, deployment/rollback and compatibility.
A proposal, schema, helper function or evidence parser alone is not delivery.

Track specification, source implementation, installed integration and external
qualification independently in the relevant gate evidence. Do not replace
those dimensions with an unqualified `complete` flag.
