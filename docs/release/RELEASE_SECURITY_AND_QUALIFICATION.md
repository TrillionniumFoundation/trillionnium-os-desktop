# Release security and qualification

**Revision:** `2026-08-29-d6`

## Release principle

No branch, PR, QEMU image, or hardware build is a release until an independent
release promotion binds an exact reviewed commit, source tree, input locks,
artifacts, SBOM, provenance, signatures, update metadata, rollback policy, and
known limitations.

## Build provenance

A release record must bind:

- repository and exact commit/tree;
- active plan and project-state blob digest;
- Rust/Servo/Debian/kernel/firmware/package locks;
- workflow/build recipe digests;
- builder image and isolation;
- all output artifact digests;
- SBOM and license report;
- vulnerability scan timestamp and policy result;
- reproducibility comparison result.

## Key custody

- production signing keys are unavailable to ordinary CI;
- platform, application-publisher, update-metadata, and recovery keys are
  separated;
- offline or HSM-backed custody is documented;
- quorum/dual control is required for release signing;
- rotation, revocation, compromise response, and recovery are tested;
- development/test keys can never be renamed or promoted as production keys.

## Update and rollback

- signed immutable A/B or equivalent;
- metadata and payload signatures verified before activation;
- monotonic rollback state;
- failed boot/health does not promote;
- power-loss and disk-full corpus;
- offline recovery media;
- explicit support and rollback windows.

## Qualification tiers

| Tier | Minimum proof |
| --- | --- |
| host | deterministic source/contracts/unit/property |
| headed host | real Servo frame/input/recovery on fixed host environment |
| QEMU image | reproducible image, PID 1, Wayland, services |
| integrated QEMU | headed Servo plus AgentPort default-closed in the same image |
| hardware beta | exact BOM, drivers, suspend/resume, stability, recovery |
| signed release | exact artifacts, provenance, signatures, update/rollback and support |

## Performance and reliability gates

Numeric values become normative when a hardware BOM is selected, but D2/D3 must
start collecting provisional metrics for:

- boot to trusted frame;
- input-to-paint;
- observe/act latency;
- RSS, FD, PID, and disk ceilings;
- content and browser recovery;
- journal overhead;
- 24/72-hour growth and stability.

## Incident response

The release process must define vulnerability intake, severity, supported
versions, patch/update targets, signing-key compromise, dependency compromise,
emergency revocation, rollback, public advisory, and post-incident review.
