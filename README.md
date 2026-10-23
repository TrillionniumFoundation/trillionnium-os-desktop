# Trillionnium OS Desktop

Rust desktop and operating-system work for a Hepta-led execution platform. The
kernel is derived from Asterinas; Hepta keeps the existing authority, durable
writer, outbox and operation-history ownership.

## Start here

| Need | Entry point |
| --- | --- |
| System boundaries and component ownership | [Architecture](docs/ARCHITECTURE.md) |
| Hepta integration and original owners | [Hepta integration](docs/HEPTA_INTEGRATION.md) |
| Development and technical documentation by delivery area | [Module documentation audit](docs/agents/MODULE_DOCUMENTATION_AUDIT.md) |
| Current implementation sequence and remaining product work | [Implementation next steps](docs/agents/ORGAN_IMPLEMENTATION_NEXT.md) |
| Current status and historical execution records | [Status](docs/STATUS.md) |
| Kernel build, boot and source verification | [Build guide](support/build/README.md) |
| UI development and execution | [UI run guide](support/ui/RUN.md) |
| Session and Notes integration | [Notes organ](support/ui/NOTES_ORGAN.md) |
| Pinning and verifying one complete OS/Hepta source pair | [Release profile](docs/agents/ORGAN_RELEASE_PROFILE.md) |

## Evidence and supported scope

Read the scope and source identities attached to each execution record under
[`results/integration`](results/integration). A source-profile check verifies
source identities; it does not run the product, configure production authority,
or authorize effects. Host UI, native guest, and physical-device results have
separate scopes.

The next-step document records the remaining original-owner, native daemon,
isolation, recovery and hardware work. Shared module manuals are intentional;
the module audit identifies which crates still lack a nearby independent entry.

## Development

Use the pinned toolchains and commands in each component's run guide. Kernel
contributions also follow [Asterinas agent guidelines](kernel/asterinas/AGENTS.md).
To check the vendored kernel build inputs from a checkout that retains the
pinned upstream Git objects:

```sh
python3 support/build/verify-source.py
```

This checker protects the upstream inputs and the enumerated downstream build
changes. Project navigation and other root documentation can evolve separately.
