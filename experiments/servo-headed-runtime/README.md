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
topology, a real multiprocess content-child termination, trusted-window
survival, and one replacement content generation. It does not start WebDriver,
BrowserActor, AgentPort, external browsing, persistent credentials, or product
authority.

The crash injector does not call a privileged DOM helper or treat a caught
script-thread panic as a process crash. The trusted parent enumerates `/proc`
and requires exactly one direct child whose canonical executable is identical
to the parent binary and whose NUL-delimited command line contains
`--content-process`. Only that PID is recorded and sent `SIGKILL`; zero or
multiple candidates fail closed. Exact selected-process termination must then be observed; the pipeline
`notify_crashed` callback is recorded when delivered but is not required. The
parent-owned window and trusted chrome must remain alive, and generation 2 must
be created through the normal `WebViewBuilder` path.

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

`runtime-state.json` is emitted through a Rust format string. Its literal JSON
object delimiters therefore remain escaped as `{{` and `}}`; predicate value
placeholders remain single-braced. This is a compile-time contract, not a reason
to skip or soften any runtime predicate.

The exact-pin adapter converts Surfman construction/current-context failures at
the application boundary, uses Servo's min/max `DeviceIntRect` convention, and
clones the current WebView handle before native IME dispatch so no temporary
`RefCell` borrow escapes its statement. These are compile-boundary adaptations;
they do not change the runtime trust topology or relax any navigation policy.

## Native input ownership candidate (2026-10-02)

`src/input_ownership.rs` is compiled into the real Winit example. Native pointer
coordinates use physical pixels and the fixed chrome offset. Leaving content,
leaving the window, losing window focus, or crashing withdraws the saved pointer
coordinate. A chrome press cannot deliver a click or wheel event at an earlier
content point, and content keyboard/IME requires a physical content press in the
currently focused window. Reconstruction inherits no pointer, keyboard or IME
ownership. Generation-bound delegates and asynchronous screenshot/focus/evidence
callbacks ignore withdrawn and replaced content. Line wheel deltas stay in line
units. The ownership module has 21 executable regressions, including repeated
IME compositions, normal matched mouse down/up, generation and button mismatch,
held content/window/focus withdrawal, held crash, bounded simultaneous buttons
and persistent input retirement, pending release callbacks and dispatch failure.
Five Python source wiring checks verify that
the native dispatcher calls these boundaries; they do not prove engine behavior.

The permanent X11 corpus first establishes a content pointer coordinate, then
clicks, wheels and types `x` in trusted chrome before its positive content
sequence. The DOM must see exactly the three intended content presses and no
`x` key. This candidate must compile and run at the immutable Servo pin before
its native qualification is accepted. The standalone runner's full v2 evidence
corpus additionally requires source/process-topology work not provided by this
v1 example; only its exact Git identity step is shared by this workflow.

This still does not connect native input to the product BrowserActor/PageOwner,
provide variable scaling or keyboard-layout/clipboard integration, prove Chinese
OS IME composition, or install a product embedder. Those G3 requirements remain
open. Native IME event counters record observation, including refused events;
synthetic composition is reported separately.

The native IME enabled context is separate from a composition. A commit ends
only that composition; later preedit/commit events remain accepted under the
same enabled context once current physical content ownership exists. Pointer
withdrawal without an unsettled mouse gesture notifies Servo `MouseLeftViewport`;
chrome presses and window focus loss blur the WebView. Requested-fault success
requires the selected PID/start
identity, successful SIGKILL command and exact termination observation; a
spontaneous crash is a qualification failure. Native CI binds the GitHub builtin
event/SHA/repository/ref and current remote main for authoritative main runs.
Seven real Git-object identity regressions cover those constraints.

## Held mouse gesture retirement source candidate

Each forwarded native Down now binds its exact button and current content
generation. Up is forwarded only when that button has an admitted Down in the
same current generation and a current content coordinate. Duplicate Down,
orphan Up, mismatched button and stale generation refuse. A release cannot reuse
the original press coordinate after leaving content. At most 16 distinct native
buttons may be held or awaiting release completion; overflow refuses the extra
Down and retires the generation.

Sending the physical Up does not immediately clear its binding. The dispatcher
retains the actual returned Servo `InputEventId`, and only the matching callback
in the current generation without `DispatchFailed` settles that release. Unknown,
duplicate or stale callbacks cannot clear it. A failed release dispatch retires
the generation, and another Down for that button is refused while completion is
pending. This callback binding confirms the pinned dispatch outcome, not a
general mouse-cancel or page-state recovery guarantee.

Leaving content/chrome, leaving the native window, losing native focus, or
crashing while an admitted button remains held or awaits release completion
latches a typed
`RecoveryRequired { generation, reason, held_buttons }`. Pointer, new buttons,
wheel, keyboard, IME and callbacks are already withdrawn before the embedder
handles that outcome. Consuming its one-shot notification does not clear the
latch. `reconstruct` refuses for that owner; focus changes or another pointer
entry cannot restore input. The existing fixture crash/replacement flow remains
available only when no admitted gesture was held or awaiting release completion
at the crash.

The native dispatcher checks the withdrawal's generation, takes its owned
WebView handle, blurs and hides it, and drops that handle. It changes the trusted
window title and emits `gesture-recovery-required.json`, recording the actual
reason, generation, number of unsettled buttons and whether the owned handle was
removed. The runtime reports failure requiring a fresh Servo owner. It sends no
synthetic MouseUp, performs no automatic reconstruction, replays no gesture and
does not turn this failure into qualification success. Other temporary callback
handles can defer the last-handle drop; stale callbacks remain refused.

This conservative withdrawal addresses an actual missing upstream boundary.
At [the fixed input API](https://github.com/servo/servo/blob/670ae8a70801b162e186f81cbb5bdd2d59c39108/components/shared/embedder/input_events.rs),
mouse actions are Down/Up with a required hit-test point. There is no mouse or
pointer cancel variant, and Touch Cancel has only Pen/Touch pointer types.
Substituting touch input is unsupported. Releasing at an earlier content point
could deliver mouseup/click and cannot be treated as harmless cancellation. The
[pinned document handler](https://github.com/servo/servo/blob/670ae8a70801b162e186f81cbb5bdd2d59c39108/components/script/dom/document/document_event_handler.rs)
clears hover on viewport exit and retains the prior mouse-down location used by
MouseUp's click handling.

The [pinned constellation](https://github.com/servo/servo/blob/670ae8a70801b162e186f81cbb5bdd2d59c39108/components/constellation/constellation.rs)
stores a global pressed-mouse-button mask, initialized with the Servo instance
and updated by mouse Down/Up. Blur, viewport exit and WebView retirement provide
no matching reset of that mask. The
[WebView API](https://github.com/servo/servo/blob/670ae8a70801b162e186f81cbb5bdd2d59c39108/components/servo/webview.rs)
closes its resources on last handle drop, but this does not prove reset of the
global Servo mask or successful cancellation of already queued events. The
recovery diagnostic therefore explicitly records
`servo_mouse_state_reset_proven=false`. Resuming input under the same Servo
instance is unsupported after a held-gesture withdrawal.

A tracked, independently reviewed upstream cancellation API or a real fresh
Servo owner with authenticated recovery is required for safe continuation.
Lossless dragging beyond content and restoration of the original page state
remain open. This is source input retirement, not a complete product recovery
UX, installed PageOwner integration or an OS IME qualification. Local standalone
ownership tests do not qualify the Servo dispatcher: this candidate still needs
the exact pinned compile and native runtime corpus. Existing native evidence does
not prove the newly added held-withdrawal paths ran on X11/Wayland.
