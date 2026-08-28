# ADR 0003: Desktop and mobile authority models remain separate

- Status: Accepted
- Date: 2026-08-28

## Decision

The Android/mobile company repository is a sibling reference and not a build
dependency. Desktop capability permits, browser effects, and trusted-shell
policy are desktop contracts. Mobile direct shell/ADB, Root Linux, Android
integration, and owner-open execution packages are forbidden in the desktop
default graph.

Only deliberately extracted platform-neutral contract primitives may be
shared, under explicit version and dependency review.
