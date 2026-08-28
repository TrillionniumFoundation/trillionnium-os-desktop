# TrillionniumOS Desktop documentation

This directory is the normative documentation entry point for the desktop
product implemented by this repository. The repository itself—not a separate
local documentation tree—is the canonical source for plans, contracts,
implementation, tests, packaging, and release evidence.

## Canonical files

- [`DESKTOP_PLAN.md`](DESKTOP_PLAN.md) — stable plan index
- [`DESKTOP_PLAN-2026-08-28-d5.md`](DESKTOP_PLAN-2026-08-28-d5.md) — active plan
- [`CURRENT_STATE.md`](CURRENT_STATE.md) — implementation and claim status
- [`MANIFEST.json`](MANIFEST.json) — machine-readable documentation status
- [`adr/`](adr/) — architecture decisions
- [`architecture/`](architecture/) — state, process, and trust models
- [`security/`](security/) — threat and release-claim boundaries

The previous d4 plan remains recoverable history. It is superseded by d5 and
must not override current repository, origin, process, authority, revision, or
network decisions.

The Android/mobile company repository `TrillionniumFoundation/trillionnium-os`
is a sibling reference. It is not a source directory, workspace member,
submodule, or default build dependency of the desktop product.
