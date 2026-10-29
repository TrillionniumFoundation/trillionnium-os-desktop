# Trillionnium OS Desktop

Asterinas-based Rust OS research and a Linux desktop Organ for the original
Hepta runtime. Hepta owns objectives, authorization and durable operations;
the desktop supplies bounded application targets and observations; the kernel
enforces process identity and resource policy.

## Current development

The integration branch starts from Desktop `38227d33` and Hepta `6d6097da`.
The current reviewed source manifest and final execution receipts, rather than
these starting points, identify a buildable pair. Do not combine successful
receipts from different branches into a release claim.

- [Build and verify the current host pair](support/release/README.md)
- [Module index](docs/INDEX.md), [architecture](docs/ARCHITECTURE.md) and
  [current integration work](docs/agents/ORGAN_CONVERGENCE.md)
- [Linux UI development](support/ui/RUN.md) and
  [Notes protocol and authority](support/ui/NOTES_ORGAN.md)
- [Kernel build/QEMU](support/build/README.md),
  [native ABI](docs/NATIVE_ABI.md) and
  [security and recovery](docs/SECURITY_AND_RECOVERY.md)
- [Original Hepta adapter](services/hepta-os/README.md)

## Development boundaries

Linux host builds, original-owner integration, Asterinas guest execution and
physical devices have separate acceptance results. Ordinary Asterinas exposes
QueryAbi; experimental control profiles do not enable production Agentd roles.
An application receipt must follow durable document storage; an operation's
terminal record remains owned by the original Hepta writer.

Production authority is supplied by the independently deployed original owner.
Source manifests and tests never install signing keys, approve an operation,
or enable effects. Android, GPU/DMA isolation and native graphical integration
remain separate development tracks.

## Source and licensing

The kernel is derived from Asterinas 0.19.0, with its original source identity in
[the upstream lock](support/upstream-lock.json). Preserve the upstream license
headers and file-level notices when changing or distributing it.
