# hepta-workspace-composition

Engine-neutral D0A-02 model for one visible TrillionniumOS Desktop workspace:

- compositor/native-owned trusted chrome;
- exactly one untrusted browser content surface;
- no shared DOM or external-navigation replacement of trusted chrome;
- explicit pointer, keyboard and IME ownership;
- popup/new-window denial;
- content crash placeholder while trusted chrome remains available.

This crate does not start Servo, create a native window or render a frame. It
provides the deterministic state and invariant layer that the headed runtime
adapter must satisfy.
