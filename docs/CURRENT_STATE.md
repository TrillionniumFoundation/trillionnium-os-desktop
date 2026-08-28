# TrillionniumOS Desktop — current state

**Updated:** 2026-08-28  
**Status:** `DESIGN_BASELINE` / `PLANNING_ONLY`  
**Implementation:** not started  
**Canonical plan:** [`DESKTOP_PLAN-2026-08-28.md`](DESKTOP_PLAN-2026-08-28.md) (revision d4)

## Verified starting point

The desktop is being added as a sibling documentation/product lane. The
migrated project currently contains an Android/Lineage checkout and a
separate Rust Agent-native/release checkout; neither is a Servo desktop.
The control-workspace mobile documentation is at `../trillionnium-os/`.

The exact inputs are:

```text
Android/Lineage source:
/data/toshiba-dev/TrillionniumOS/rootfs/home/qian-qi/android/lineage-fogos

Rust Agent-native/release source:
/data/toshiba-dev/TrillionniumOS/rootfs/home/qian-qi/trillionnium-release-sources/p0-agent-native-integration-20260731/trillionnium-os

Mobile documentation:
/data/toshiba-dev/TrillionniumOS/rootfs/home/qian-qi/.openclaw/workspace/docs/trillionnium-os

Desktop documentation (this directory):
/data/toshiba-dev/TrillionniumOS/rootfs/home/qian-qi/.openclaw/workspace/docs/trillionnium-os-desktop
```

The old top-level `/data/toshiba-dev/TrillionniumOS-desktop/` location is
staging/provenance only and is not an implementation checkout.

## Active decisions

1. Start from a pinned Debian stable userland and bootable image, using a
   stock/near-upstream LTS kernel, initramfs, firmware and drivers.
2. Use one headed Servo WebView as the only desktop browser runtime.
3. Give each session one `BrowserActor`/`PageOwner` and one event loop. Agent
   API calls and human native input are two serialized inputs to that same
   live page; there is no engine switching or page migration. v1 has one local
   seat, one visible window and one top-level browsing context; same-page
   iframes are allowed, while popup/new-window/tab requests are denied or
   navigated in the existing WebView.
4. Keep `hepta-browserd` in user space. `systemd`, Wayland and typed capability
   services retain lifecycle, display and machine-authority responsibilities.
5. Reuse Obscura only as a semantic-contract/fixture reference if useful; do
   not link Obscura engine crates into the Servo runtime.
6. Keep external search, credentials and web side effects behind later gates;
   the current plan has no production listener, persistent secret or
   CAPTCHA/anti-bot bypass authority.

Agent and human mutations use a short lease and one queue. `PageOwner`, not
the observer, increments `page_revision` on every mutation, navigation and
committed DOM change; stale references fail closed.

## First acceptance slice

```text
Debian boots
  -> full-screen Servo shell starts
  -> Agent navigates through the local authenticated API
  -> human sees and edits the same page
  -> Agent observes/extracts the resulting state
  -> a capability request is explicitly allowed or refused
```

No item in this file is evidence that the slice has already been implemented;
it is the baseline and gate definition for the next development stage.
