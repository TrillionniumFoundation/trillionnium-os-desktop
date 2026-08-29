# Product-owned headed Servo runtime

This experiment is the executable `TOS-D0A-02` / initial `D2` qualification
source. The permanent workflow copies `src/main.rs` and the deterministic HTML
fixture into the exact pinned Servo checkout as an example target, compiles it
with Servo's own Rust channel and `Cargo.lock`, and runs it in an X11/Xvfb
session.

The embedder owns one native window and its trusted chrome pixels. Exactly one
untrusted Servo `WebView` renders into an offscreen context that is composited
below the chrome. Navigation is permitted only to the ephemeral
`127.0.0.1` fixture origin; popup/new-window and external navigation requests
are denied.

The runtime corpus records content and full-workspace screenshots, native X11
pointer/button/wheel/keyboard forwarding, Servo IME composition, process
topology, a test-only multiprocess content panic, trusted-window survival, and
one replacement content generation. It does not start WebDriver, BrowserActor,
AgentPort, external browsing, persistent credentials, or product authority.

Every asynchronous `WebViewDelegate` transition that can satisfy or advance a
qualification predicate explicitly posts `AppEvent::Drive`. This includes input
completion, crash notification, navigation denial, popup denial, and input-method
control delivery, so the event loop cannot sleep after the final prerequisite
without advancing into crash and replacement-generation recovery.

A failed runtime writes both the bounded public result and `runtime-state.json`.
The diagnostic state captures every gate predicate and counter—load/frame,
screenshots, focus, native and handled input, IME, page evidence, popup and
navigation denial, crash notification, replacement generation, chrome pixels,
and recovery—without recording page secrets. The permanent gate keeps the
failure artifact so a missing transition is repaired at its exact boundary
rather than by weakening the acceptance corpus.

The exact-pin adapter converts Surfman construction/current-context failures at
the application boundary, uses Servo's min/max `DeviceIntRect` convention, and
clones the current WebView handle before native IME dispatch so no temporary
`RefCell` borrow escapes its statement. These are compile-boundary adaptations;
they do not change the runtime trust topology or relax any navigation policy.
