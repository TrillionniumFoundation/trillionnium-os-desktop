# Debian image packaging

This directory contains product unit/install metadata and D1/D2I qualification
image recipes. Source recipes are present; a current reproducible build, guest
boot or release is not inferred from their existence.

## Source and input ownership

- `hepta-agent-portd.install` is the production install map.
- `systemd/`, `systemd-preset/`, `sysusers.d/` and `tmpfiles.d/` define the
  default-disabled AgentPort socket, service identity and pre-provisioned paths.
- `image/build-d1-image.sh` builds the locked minimal Debian substrate.
- `image/rootfs-overlay/` contains D1 qualification-only acceptance services
  and its explicitly separate inherited-stream fixture.
- `image/d2i-overlay/` adds the headed Servo qualification runtime and guest
  acceptance services; it does not activate production AgentPort.

The substrate selects `manifests/debian-d1.selection.json`, the signed package
closure in `manifests/debian-d1.lock.v1.json`, the exact e2fsprogs tool lock and
the Rust/dependency locks. D2I additionally binds the Servo source/patched-runtime
inputs. Changing an overlay, install map, unit, input or tool invalidates the
associated evidence under the gate registry.

## Build and qualification entry points

Read [`D1_DEBIAN_QEMU_SUBSTRATE.md`](../../docs/architecture/D1_DEBIAN_QEMU_SUBSTRATE.md),
[`D2I_INTEGRATED_IMAGE.md`](../../docs/architecture/D2I_INTEGRATED_IMAGE.md) and
[`tests/d1/README.md`](../../tests/d1/README.md) before running image jobs.
`tools/run_d1_final_qualification.sh` and `tools/run_d2i_integrated_image.sh`
implement the controlled workflow steps; `tests/qemu/` contains guest runners.
The permanent `d1-final-qualification` and `d2i-integrated-image` workflows
declare the dependencies and execution environment for every main push and
prospective PR merge. The S10 workflow is a manual, non-authoritative diagnostic
entry point. Image builds require Linux, elevated image-building facilities,
the signed package inputs, mmdebstrap, QEMU, filesystem tooling and the exact
Rust/Servo build dependencies. A host-only source check does not provide these.

Current Cargo metadata keeps `hepta-agent-d1-fixture` as an explicit example
requiring the non-default `fixture` feature. It is separate from the default
`hepta-agent-portd` binary and absent from the production install map. Runners
must use that actual target/feature and copy its example artifact into the
qualification image; no stale `d1-qualification` feature or product fallback
is valid.

## Acceptance and failure handling

D1 requires two byte-identical normalized builds plus a no-network QEMU PID 1
run. D2I requires the current image lineage, headed content frame, trusted chrome,
explicit crash reconstruction, and absence of production AgentPort activation.
Guest results, kernel/initrd/image digests, package locks, source/tree/workflow
identity and evidence role must agree in the final verifier packet.

Use the existing verifier against immutable artifacts. Do not overwrite a
failed receipt, claim a manual run as protected promotion, install a fixture
into the product map, or carry predecessor evidence across changed inputs.
Neither recipe establishes physical hardware, signed A/B updates, production
key custody, protected publication or release readiness.
