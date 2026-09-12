# TrillionniumOS Desktop product architecture

**Origin revision:** `2026-08-28-d5`
**Status:** inherited d5 design annex; subordinate to the active d6 plan
**Active plan:** [`2026-08-29-d6`](../DESKTOP_PLAN-2026-08-29-d6.md)
**Repository mode:** `FULL_PRODUCT_REPOSITORY`

This is the active architecture entry point. The complete original d5 text is
preserved in [the historical snapshot](PRODUCT_ARCHITECTURE.d5-historical.md).
The [inheritance map](D6_ANNEX_PRECEDENCE.md) makes explicit which decisions
control. Historical status and authority statements are not current truth.

## Product and authority topology

The target is an appliance with one logical PageOwner and one untrusted Servo
content surface. Native/compositor-owned trusted chrome owns navigation,
consent, trust indicators and recovery UI. It must not share a DOM, storage
partition or script realm with content. The historical alternative of two
WebViews is not an implicit option on the current native-shell design.

Browser process supervision, semantic request custody, resource capability
issuance, updates, image construction and release signing are distinct
boundaries. Completing one does not authorize another. Lower-level contract
and mechanism crates must not depend on application, signing or policy code.
The desktop default graph must not import Android/mobile, ADB or raw-shell
execution authority from a sibling product.

## Current implementation contract

The root workspace and `manifests/modules.v1.json` describe the actual source
module graph; [the generated index](../modules/README.md) describes its exact
per-module claim ceiling. Product status is read from
`manifests/project-state.v1.json`, not inferred from this target architecture.

S08 must bind the product daemon to the attested AgentPort, concrete
BrowserActor, exact-pin Servo command/completion boundary and durable receipt
journal. A type alias, deterministic runtime, independent Servo harness or
qualification mailbox is not the complete product path. Content crash must
withdraw stale pixels and references without terminating trusted chrome.

The required daemon/engine protocol is specified by
[the S08 supervision contract](../architecture/S08_PRODUCT_SERVO_SUPERVISION.md).
The broader [product subsystem coverage](../modules/PRODUCT_SUBSYSTEM_COVERAGE.md)
identifies boundaries that are not Cargo packages.

## Design detail retained from d5

The historical snapshot retains the original user promise, logical-session
versus process topology, synthetic trusted-app origin design, mobile/desktop
reuse boundary, daemon responsibility split and repository layout. Its trusted
origin design remains a requirement to implement and verify, not proof that
bundle verification, storage isolation or service-worker restrictions exist.

## Delivery constraint

Keep production AgentPort default-disabled and external-effect authority
closed. An installed image must execute the same reviewed product path, not a
fixture substituted by packaging. Independent review and exact-main reruns
remain necessary after protected promotion. This entry-point repair changes
no runtime behavior, installed image, capability or release authority.
