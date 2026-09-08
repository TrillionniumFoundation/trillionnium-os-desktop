# TrillionniumOS Desktop — current non-claims

**Updated:** 2026-09-08  
**Machine truth:** [`manifests/project-state.v1.json`](../manifests/project-state.v1.json)

Unless a later signed release statement explicitly closes an applicable gate, this repository does not currently claim the capabilities below.

## Machine-aligned non-claim identifiers

These identifiers are projected directly from `not_claimed` in the machine state:

- `headed_servo_integrated`
- `visible_product_first_frame`
- `debian_image_built`
- `qemu_pid1_wayland_boot`
- `integrated_qemu_headed_runtime`
- `product_agent_port_enabled`
- `taskflow_semantic_principal_bound`
- `browser_actor_dispatch`
- `external_navigation_or_effects`
- `signed_app_runtime`
- `controlled_egress`
- `signed_update_and_rollback`
- `fixed_hardware_beta`
- `production_release`

## Product integration

- a complete installable production desktop operating system;
- production BrowserActor/PageOwner activation in the exact installed image;
- production AgentPort enablement;
- a complete TaskFlow semantic-principal mapping;
- multi-window or unrestricted multi-surface browser authority;
- complete Wayland compositor, window-manager, input, IME, clipboard, or accessibility integration;
- compatibility with arbitrary Linux distributions or arbitrary hardware.

## Browser and external effects

- unrestricted external navigation;
- trusted DNS, TLS, redirect, connected-peer, publisher, or credential handling merely from URL shape validation;
- permission for file upload/download, clipboard, camera, microphone, payments, credentials, or arbitrary network effects;
- exactly-once external effects across crashes without a separately qualified reconciliation protocol;
- safe automatic replay of an operation that may already have produced an external effect.

## Persistence and recovery

- a general-purpose transactional database;
- recovery from every filesystem, storage-device, kernel, or power-loss failure mode;
- production-qualified journal migration across all future versions;
- signed A/B update, rollback resistance, recovery media, or emergency revocation closure;
- preservation of user state under every downgrade or repair path.

## Qualification

- that source compilation proves runtime integration;
- that a hosted runner proves an installed product image;
- that QEMU proves a fixed physical bill of materials;
- fixed-hardware 24-hour or 72-hour endurance qualification;
- raw power-loss, suspend/resume, GPU, display, input, audio, or network qualification on production hardware;
- independent security review of every current candidate head.

## Governance and release

- protected `main`, active no-bypass rulesets, or enforced independent approvals solely because CODEOWNERS exists in the repository;
- separation of author, reviewer, builder, signer, attestor, and promoter identities;
- offline or HSM-backed signing-key custody;
- reproducible production builds from two independent builders;
- signed provenance, signed SBOM, signed release metadata, anti-rollback state, or controlled publication;
- a production release.

## Interpretation rule

When a document, test name, manifest field, or implementation comment appears broader than this file, the narrower claim applies until exact evidence closes the applicable gate.
