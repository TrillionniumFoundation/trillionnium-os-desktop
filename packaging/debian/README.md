# debian-packaging

**Component registry ID:** `debian-packaging`
**Component path:** `packaging/debian`
**Owner class:** `image-and-service-custody`
**Plan revision:** `2026-08-29-d6`
**Registry:** `manifests/components.v1.json`

## Status and claim ceiling

Current status: `candidate_image_and_service_packaging`.

**Claim ceiling:** deterministic D1/D2I image assembly and profile-separated systemd installation source only; no fixed hardware, Secure Boot, production update, signing, or release.

This component is interpreted under the repository's evidence-tier and
invalidation rules. Source completeness and passing local tests establish only
the status above. They do not imply protected governance, integrated-main,
installed-product, physical-hardware, signing, or release authority unless the
applicable gate records independently bound evidence.

## Responsibilities

- Assemble the deterministic Debian D1 root filesystem, ext4 image, kernel/initrd input set, and D2I overlay.
- Install product, development, and qualification binaries into separate paths and feature graphs.
- Define systemd socket/service, preset, sysusers, and tmpfiles custody.
- Support QEMU evidence for PID 1, Wayland placeholder, no-network boot, AgentPort negative cases, recovery, and clean shutdown.

The component must keep these responsibilities explicit enough that reviewers
can identify the exact authority boundary, inputs, outputs, failure modes, and
evidence producer without inferring behavior from filenames alone.

## Non-responsibilities

- Packaging source does not prove a package was installed on the promoted image or physical device.
- The D1/D2I scripts do not grant external network, effect, update, hardware, or release authority.
- Development and qualification units must never be interpreted as production activation.

These exclusions are normative. A downstream caller, workflow, fixture, or
document may not widen the component by relabeling a lower-tier result.

## Dependency and call direction

Pinned Debian and host-tool manifests feed the image builder. Files enter a staged root through no-follow, canonical-path copy operations. Systemd units and ownership declarations are installed into the image. Dedicated workflows build twice for byte comparison, boot QEMU without a network device, run bounded guest probes, and export exact digests.

The allowed direction is from higher-level trusted policy into this bounded
mechanism and back through typed results. Reverse dependencies that let a lower
trust surface select policy, credentials, arbitrary paths, commands, devices,
network destinations, signing keys, or promotion state are forbidden unless a
new reviewed contract explicitly introduces that authority.

## Public interfaces and entrypoints

Registered entrypoints:

- `packaging/debian/image/build-d1-image.sh`
- `packaging/debian/hepta-agent-portd.install`
- `packaging/debian/systemd/hepta-browserd-agent.socket`

Architecture references:

- `docs/architecture/D1_DEBIAN_QEMU_SUBSTRATE.md`
- `docs/architecture/D2I_INTEGRATED_IMAGE.md`
- `docs/architecture/SYSTEMD_AGENT_PORT_CUSTODY.md`

Contract references:

- `contracts/d2i-integrated-image.v1.json`
- `contracts/agent-port-custody.v1.json`

Only registered entrypoints and versioned contracts are reviewable public
surfaces. An unregistered executable, workflow, package path, service unit, or
ad-hoc data format is a repository consistency failure.

## Configuration and features

Configuration is supplied through committed manifests, versioned contracts,
locked toolchain/input records, fixed workflow environment variables, or
explicit package/service profiles. Mutable upstream names, ambient host state,
unbounded workflow inputs, and undocumented feature flags are not valid
configuration. Defaults must remain least-authority and fail closed; development
or qualification profiles must be physically and semantically distinct from
production.

## State, concurrency, and failure semantics

Build state is an ephemeral staging tree plus explicit lock/input/output manifests. Guest state is bounded to the qualification boot. Service state is owned by systemd; sockets are created under root-controlled paths, peer identity is revalidated, and per-connection services terminate after one request. Partial outputs are never promoted.

Partial completion is never upgraded to success. Timeout, cancellation,
infrastructure failure, product failure, stale evidence, and indeterminate
external outcome remain distinct states. A retry must bind to the same exact
inputs or create a new evidence identity; it must not overwrite the historical
failure packet.

## Security invariants

- image inputs are resolved from pinned signed snapshots and copied without symlink traversal
- production AgentPort remains default-disabled and distinct from development/qualification binaries
- root-owned socket pathname custody is enforced independently of peer authentication

In addition, repository-relative paths must be canonical and read without
following symlinks where they influence authority or evidence. Structured data
must reject duplicate keys and malformed identities. Secrets and page content
must not enter logs or artifacts unless a reviewed redaction contract permits
specific bounded fields.

## Testing and evidence

Registered tests:

- `tests/d1/test_d1_tools.py`
- `tests/d1/test_d1_qualification_separation.py`
- `tests/d1/test_d1_path_custody.py`

Registered workflows:

- `.github/workflows/d1-final-qualification.yml`
- `.github/workflows/d2i-integrated-image.yml`
- `.github/workflows/agent-port-custody.yml`

Tests must include positive behavior and hostile boundary cases. Evidence must
record exact source/base/tree or image/input identities, workflow and artifact
IDs, bounded output digests, claim ceiling, and invalidation triggers. A verifier
self-test proves the verifier rejects bad fixtures; it does not prove a separate
producer generated authentic higher-tier evidence.

## Operations and troubleshooting

Resolve snapshot metadata before building, verify host tools, run path/symlink/duplicate-key tests, and inspect both build manifests on reproducibility failure. Never run image scripts with an unbounded destination or mutable package source. Keep production presets disabled until the corresponding gate is promoted.

Operational diagnosis starts from the first failed invariant and the exact
input object. Do not make a gate green by broadening permissions, accepting
missing fields, following symlinks, selecting a different process/device,
disabling negative cases, or rewriting expected evidence after the fact.

## Compatibility and change protocol

Package lists, source snapshots, host tools, filesystem layout, units, users/groups, presets, overlays, or copy logic invalidate D1/D2I and custody evidence. Update locks, contracts, tests, workflows, architecture, component registry, and claim ceilings in the same review object.

Every change must also update `manifests/components.v1.json` when paths,
entrypoints, ownership, references, status, security invariants, or claim
ceilings move. Run `python3 tools/validate_component_documentation.py`, the
project/repository validators, authoritative Python discovery, and the locked
Rust matrix before requesting independent review.
