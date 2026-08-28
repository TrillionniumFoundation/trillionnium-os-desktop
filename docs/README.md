# TrillionniumOS Desktop Edition — canonical documentation

This directory is the **only canonical planning/documentation entry point**
for the desktop edition of TrillionniumOS on the migrated desktop. The
canonical product spelling is **TrillionniumOS** (three `i`s); “Trollionnium
OS” is an informal conversation spelling, not a second product.

The desktop edition is a sibling lane of the active Android/mobile edition.
It does not replace, modify or silently share the mobile image or release
authority.

## Start here

- [`DESKTOP_PLAN.md`](DESKTOP_PLAN.md) — stable plan index
- [`DESKTOP_PLAN-2026-08-28.md`](DESKTOP_PLAN-2026-08-28.md) — normative dated
  development plan (revision d4)
- [`CURRENT_STATE.md`](CURRENT_STATE.md) — verified starting state and scope

The mobile documentation sibling is:

`../trillionnium-os/README.md`

## Locked product direction

The desktop product starts from a pinned Debian stable userland/image and a
stock or near-upstream distribution Linux kernel. Its only user-visible
browser runtime is one headed Servo WebView owned by `hepta-browserd`.

The Agent API and the human keyboard/mouse/IME operate on that same WebView,
page, DOM, JavaScript state, cookies, storage and history. User-visible
applications are signed `hepta://` bundles; privileged work is provided by
separate typed capability services or sandboxed WASI workers.

This plan deliberately does **not**:

- fork Linux as the first step;
- use the Android Root Linux Bookworm image as a desktop base;
- combine Obscura and Servo browser cores;
- add a second browser or an implicit Chromium fallback to the desktop
  baseline;
- put PID 1, hardware, secrets or update authority inside Servo.

## Location and source-of-truth lock

Canonical desktop docs:

`/data/toshiba-dev/TrillionniumOS/rootfs/home/qian-qi/.openclaw/workspace/docs/trillionnium-os-desktop/`

Canonical mobile docs:

`/data/toshiba-dev/TrillionniumOS/rootfs/home/qian-qi/.openclaw/workspace/docs/trillionnium-os/`

The Android/Lineage checkout and the Rust Agent-native checkout are separate
mobile inputs; their exact paths and the desktop boundary are recorded in the
dated plan. The older top-level `/data/toshiba-dev/TrillionniumOS-desktop/`
directory was staging only. Its former duplicate plan is archived and its
README now points here; it must not be used as a second source of truth.
