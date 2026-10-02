# Product-owned headed Servo runtime

The separate [explicit native direct-INET qualification](../../docs/architecture/NATIVE_DIRECT_INET_QUALIFICATION.md)
profile uses a real systemd private network namespace, pre-engine descriptor and
protocol probes, and independent stopped-process pidfd observations. Its
immutable qualification fixture holds no INET listener. The default profile,
normal checkpoint gate, rapid native queue and held-gesture refusals keep their
existing behavior. The new profile requires its own exact-pin CI packet; local
kernel fixtures do not qualify Servo. AF_UNIX host forwarding/peer permissions,
installed browser activation and complete protocol confinement remain
unqualified; existing resource-report claim ceilings remain false.

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

The source resource gate also handles both HTTP resource callbacks at Servo pin
`670ae8a70801b162e186f81cbb5bdd2d59c39108`. A default `ResourceGate` admits no
resource. This qualification executable explicitly creates one capability from
its already bound IPv4 loopback fixture listener and retains a duplicate of
that real listener. Only `GET /?generation=1` or `GET /?generation=2` for the
current, live owned WebView can receive the bounded HTML bytes compiled into
the executable. The exact serialized URL, method, nonredirect main-document
request, generation, held-input latch, and actual callback WebView ID are
checked. No asset pathname or externally supplied response callback is used.

Allowed responses are intercepted with fixed MIME, no-store, nosniff and CSP
headers, one bounded byte chunk and explicit finish. All other WebView HTTP
loads are intercepted and cancelled, including unknown paths, methods, ports,
origins, query strings, credentials or fragments represented in the parsed
request URL. Stale, withdrawn or missing owned WebViews also explicitly cancel.
The global `ServoDelegate` is installed before the first WebView or event-loop
spin and always cancels requests without a WebView principal. Neither callback
drops a request to continue normal networking. The fixture listener returns
403 to any real network connection; successful evidence requires its actual
connection counter to remain zero.

The fixture's qualification CSP permits only two fixed script-refusal probe
locations (`'self'` and `https://resource-denied.invalid`) and a same-origin
POST probe to reach the actual embedder callback. Both content generations must
show the three actual cancellation submissions and matching DOM script-error
or fetch-rejection outcomes, with no successful forbidden-resource execution.
`resource-gate-result.json` records bounded typed facts; the independent checker
binds them to the existing runtime's generation-specific DOM evidence. It
reads bounded JSON and origin bytes through retained regular, single-link
descriptors with no symlink traversal, checks metadata before and after reading,
and prints their hashes from those same bytes. The checker is read-only and does
not create or overwrite an evidence file. The existing native
input, IME, SIGKILL, recovery and held-gesture thresholds are unchanged. A
service-worker registration probe is conditional; this pin's
`Preferences::default` keeps `dom_serviceworker_enabled` false and this
prototype does not enable it. The global
callback observation field is derived solely from actual delivered callbacks,
and zero observations do not qualify worker execution.

The standalone Rust corpus uses real loopback listeners to test the closed
default, retained ownership, exact admission, stale/global refusals and bounded
counters. Python mutation fixtures test the verifier through real files and
CLI invocation; these fixtures provide no native or installed runtime evidence.
The permanent CI still compiles this source against the actual pin and requires
the observed negative corpus in addition to all existing positive checks.

This is a source qualification HTTP-response prototype. It does not connect
the Python signed-app admission or AppStorage APIs to Servo, does not grant a
synthetic production principal, and does not qualify installed CSP, WebSocket,
non-HTTP protocols, complete worker behavior, or network namespaces. Those
integration boundaries remain open; production resource admission defaults
to empty.

The fixed-pin API evidence is upstream's
[WebView resource callback and interception ownership](https://github.com/servo/servo/blob/670ae8a70801b162e186f81cbb5bdd2d59c39108/components/servo/webview_delegate.rs#L217-L310),
[global resource callback](https://github.com/servo/servo/blob/670ae8a70801b162e186f81cbb5bdd2d59c39108/components/servo/servo_delegate.rs#L27-L34),
and [explicit cancellation to a network error](https://github.com/servo/servo/blob/670ae8a70801b162e186f81cbb5bdd2d59c39108/components/net/request_interceptor.rs#L75-L79).

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
units. The ownership module has 51 executable regressions, including repeated
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
withdrawal immediately invalidates local ingress and unsent events before an
event-loop spin. Chrome presses and window focus loss blur the WebView. This
local invalidation does not prove cancellation of Servo input state; any possible
unsettled dispatch closes the lane as described below. Requested-fault success
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
the generation, and another Down for that button remains unsent in the ordered lane while
completion is pending. The dispatch ledger itself still refuses a direct new
Down while release completion is pending. This callback binding confirms the pinned dispatch outcome, not a
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

## Exact positive input checkpoints

The actual native CI run `37010289801` tested merge
`9c5479b178e10e45da53ea01cd683cfacbbb7ee4` of candidate `c61bb83b496fbd479e7d931d1a594d286374568a`.
It compiled and finished the local fixture/crash/replacement run, then failed the
unchanged DOM requirement of three content pointer-downs: its raw result recorded
two, with four forwarded native button events. Native IME was observed twice.
Earlier run `37005158637` recorded three DOM downs and six forwarded button
events with identical native source and workflow. The raw artifact does not
identify which pair was refused or establish its exact callback timing.

A source replay of exactly the original three pairs reproduces four forwarded
events and two downs when the first release callback arrives after the next pair.
The input owner correctly refuses another same-button Down while the actual Up
callback is pending. The qualification script previously issued the next pair
without satisfying that prerequisite. This is a concrete source interleaving
consistent with the actual failure, not a reconstructed per-event native trace.

Both the workflow's v1 positive entry and the standalone runner's separate v2
positive entry now use `tools/native_input_checkpoints.py`. A fresh 32-hex run
nonce enables the explicit host profile. The native parent first confirms the
initial content pointer's actual Servo callback, then observes the physical
chrome position in the focused current generation. This preserves the original
chrome click/wheel/`x` exclusion stimulus. For each of the original three content
pairs, the driver waits for that point's actual MouseMove callback, submits one
Down, waits for its matching accepted `InputEventId`, submits one Up, and waits
for its matching accepted release callback before proceeding. Missing, stale,
duplicate or mismatched callbacks do not advance the sequence. `DispatchFailed`
fails the runtime; pending release ownership is never cleared by a counter or
file. IME submission and page evidence wait for all three matching releases.

The parent publishes each one-shot checkpoint as private JSON through a retained
temporary file and rename. The host checks bounded strict JSON, no symbolic-link
path traversal, private regular one-link files, root/file identities, its exact
PID/start time and nonce, generation, sequence, point, dispatch outcome and actual
event identifiers. A new driver refuses any already published checkpoint or
receipt even for the same live owner and generation. Earlier records are checked again before further stimuli and
at final verification. The driver has one absolute 30-second budget. It never
retries an input, adds clicks to reach a counter, or sends a cleanup Up. Its
`HOST_STIMULUS_COMPLETE` receipt records host commands and checkpoint digests;
the existing DOM `pointerDowns == 3`, native IME and crash/recovery requirements
remain independently mandatory. The v2 runner still cannot accept this v1
example or replace its missing v2 topology evidence.

The new Rust and private-file host regressions test source sequencing and driver
validation. They do not prove the new source compiled or ran at Servo's pin; a
fresh actual native CI result is required. Checkpoints are a qualification
protocol, not a production renderer authentication channel, installed PageOwner
integration, hardware/Wayland qualification, or a queue for fast user input.
Rapid same-button double-clicks remain refused while a release is awaiting its
callback; lossless input queuing and multi-click UX require separate owner work.
The held-gesture negative profile explicitly excludes this nonce and continues
to inject no Up or automatic recovery.

## Permanent native held-gesture refusal corpus v1

After its complete positive input and requested-SIGKILL recovery corpus, the
permanent workflow invokes the independent runner mode `run-held-gestures-v1`
against the native example it compiled at the exact Servo pin. The old full
runner's `run-runtime` and `enforce-evidence` modes still require their separate
v2 contract; neither is called or relaxed to accept this example's v1 results.

The new mode starts three separate native fixture processes on three fresh Xvfb
displays. Each admits one native X11/XTest Button1 Down in content and then either
moves into chrome, moves outside the native window, or transfers actual focus to
a mapped auxiliary `xmessage` window. XQueryPointer must observe Button1 still
held before and after withdrawal. These are real native OS event tests, not a
physical hardware input qualification. No case injects MouseUp, including during
cleanup. An implicit pointer grab can report an out-of-bounds move before window
leave; the outside case accepts either corresponding typed withdrawal reason.

Each process must exit 1 within the bound and emit its actual held-gesture FAIL,
`gesture-recovery-required.json` and `runtime-state.json`. The verifier requires
one admitted native button event, one unsettled button, generation 1, removed
owned WebView handle and explicit false reset/reconstruction/product claims.
Initial frame/content/chrome/focus readiness must have been reached. Synthetic
IME, crash injection, replacement generation and recovery evidence must remain
absent. A timeout, signal exit, another failure reason, malformed diagnostic or
missing fact fails the gate. This negative corpus cannot satisfy the positive
crash/recovery predicates.

The harness binds the actual native executable PID/start time/session/process
group, native window PID and the parent's concrete loopback fixture-listener
inode. Python's Linux child-subreaper custody allows orphaned content children to
be reaped. Exit observation uses `waitid` with `WNOWAIT`, preserving the actual
leader's PID until its group is closed. Before every group signal, the captured
leader start time, session and group must still match. Cleanup reaps adopted
nonleader children first and releases the exited leader only when no other group
member remains. An already reaped or changed leader refuses group signalling;
repeated completed cleanup never touches that numeric PID again. Cleanup targets
only groups started and identity-checked by this harness, uses bounded
TERM/KILL/wait, verifies those groups and the fixture
listener disappeared, and closes that case's fresh display. It does not claim
graceful Servo teardown or engine mouse cancellation. A 16 MiB inherited regular
file bound limits each log and fits the fixed viewport's screenshots; any file
exhaustion fails the supported corpus. Logs, stimuli, identities and raw failure
diagnostics remain in each case directory even when verification fails.

Only all three verified native cases produce
`artifacts/servo-headed-runtime/held-gestures-v1/negative-corpus.json`, with exact
source-object identities and raw-fact hashes. Its status is
`PASS_HELD_GESTURE_REFUSAL_LOCAL_X11_ONLY`; mouse cancellation, same-Servo
recovery, DOM action success, installed BrowserActor, OS IME and product readiness
remain explicitly false. Adding this executable gate is a source change; its
actual fixed-pin native result must be observed in CI before claiming it passed.


## Bounded ordered default native lane source candidate

The fixed-viewport prototype now admits all native pointer moves, buttons,
wheel, keys and IME controls through one `OrderedNativeInput` FIFO. It is the
normal nonce-disabled Winit path as well as the existing qualification path.
`PhysicalIngress` projects OS focus, the pointer and physical button/IME state;
admission does not focus Servo or change its dispatch-side held ledger. Each
event freezes the original WebView ID, generation, physical ownership epoch,
payload and arrival point. A physical Up keeps its own arrival point, including
when further pointer moves have already arrived. Native preedit/commit expands
to at most two adjacent queued engine events (Start plus Update/End); native
Enabled/Disabled controls are ordered local events. A real OS Disabled event
may enqueue Dismissed for its active composition. Focus/content/window/crash
barriers do not synthesize a mouse/key release or IME dismissal.

Each busy episode has one five-second absolute `Instant`, starting with its
first admitted event. Further arrivals, local control, submission and ACK do
not renew it. The queue includes the in-flight event in its 64-event count;
queued plus in-flight payloads total at most 16 KiB, and each payload is at
most 4 KiB. Event sequence, owner, payload, capacity, expiry, dispatch failure,
unknown submission and withdrawal are typed refusal paths. `WaitUntil` uses
that same deadline so a missing callback cannot leave the lane waiting forever.
IME expansion is admitted as one group; capacity refusal cannot admit its
Start while silently dropping its End. Evidence is capped at 256 native records
and 128 actual DOM button-event records; overflow fails qualification.

One Drive submits at most one event. It reserves `Submitting`, releases all
`RefCell` borrows, then enters Servo. It validates the current owner and absolute
deadline again when binding the actual returned `InputEventId`. A reentrant
callback before binding is unknown submission and closes the lane. Only the
matching callback for that actual ID, WebView, generation and epoch without
`DispatchFailed` settles the event. The callback posts a later Drive; it does
not recursively drain. Unknown or duplicate callbacks never advance the queue,
renew its deadline or satisfy a qualification checkpoint.

Every observed OS withdrawal is applied before spinning the Servo loop. Unsent
events are discarded with `withdrawn_unsent` facts, without engine IDs, counters,
synthetic releases or fabricated held-button counts. A possible submitted mouse
Down or pending Up retains the original held-gesture recovery reason. An
unresolved nonbutton dispatch, a dispatched key Down awaiting its actual Up
ACK, or a possible composition awaiting its actual End/Dismissed ACK also
requires a fresh Servo owner. Key auto-repeat retains one bounded physical-key
hold. Local IME disable cannot clear a possible dispatched composition. Neither
focus reentry nor same-Servo WebView reconstruction clears these latches. Clean
fixture crash/replacement requires the lane to be idle with no possible key or
composition hold; unsent old-generation events are never replayed into it.

The qualification-only synthetic Start/Update/End triplet uses this same ordered
lane only after all admitted native events and held key/composition state settle.
It is labelled `qualification_synthetic`, independently of the actual Winit IME
observation counter. It does not qualify OS IME composition. The existing private
nonce/checkpoint profile still submits exactly its three original pairs, and
the existing three held-button negative cases still send no Up.

The permanent workflow additionally calls `run-native-burst-v1` in a fresh
process, Xvfb server and private output directory without a qualification nonce.
A single XTest batch sends exactly three rapid Down/Up pairs at native window
points (200,132), (400,164), (200,132), with no per-pair ACK waits, retries or
extra clicks. Key `k` and wheel input follow that burst. The actual DOM must
observe exactly three pointer downs, three document click events and the nine
ordered down/up/click events at content points (200,68), (400,100), (200,68).
The existing fixture-button `clicks > 0`, keyboard, wheel, native IME, requested
SIGKILL, exact termination, recovery, chrome pixels and HTTP-resource refusal
checks all remain required. Servo ACK is dispatch completion, not DOM execution
proof; both are independently required.

The fresh burst captures `process-topology-pre-burst.json` before its stimulus.
The unreaped native leader anchors its process group; an actual retained pidfd
brackets bounded observation of exactly one direct, same-executable content
process. Closed integer PID/start/parent/group/session facts bind the later
selected SIGKILL incarnation. Only the fixed content-entry flag is recorded;
opaque IPC tokens and other command arguments are excluded. Missing topology
or a copied earlier text file cannot satisfy the burst gate. The first b339
burst demonstrated all three clicks and six ACKs but failed this missing
producer check; that failed packet is not retroactively supplemented or passed.

The checkpoint driver's absolute deadline is sampled again after actual owner
and file-snapshot validation. A nonpositive remainder raises the explicit deadline
refusal before polling sleep or another command; expiry during these checks
cannot return a negative sleep budget or renew the original deadline.

`native-input-queue.json` contains closed `native-input-queue.v1` source facts:
actual owner PID/start time, default versus nonce profile, bounded ordered
admitted/submitted/accepted/local/withdrawn records with frozen owner and point,
actual returned IDs, resource limits and explicit false product/DOM-proof claims.
The burst verifier reads bounded strict JSON through retained regular,
single-link, non-symlink descriptors, compares metadata and named identity,
and rereads all consumed raw facts before recording their hashes. It writes
`native-burst-stimulus.json` and `native-burst-verification.json`; stale output
is refused. The receipt binds source SHA/tree identities, source file hashes,
compiled binary hash, original stimulus, raw facts, matching actual ACK IDs and
actual DOM event order. The harness observes and cleans only its captured
PID/start-time/session/group and requires its fixture listener to disappear.

The host Rust corpus includes rapid queued pairs, mixed event order and points,
IME expansion, key/composition completion, capacity/byte ceilings, a missing
ACK, absolute deadline, wrong/duplicate/stale callbacks, reentrant submission,
and unsent versus possible-effect withdrawal. Python private-file mutation
fixtures and source-wiring checks test the verifier and adapter boundaries;
fixture PASS is not native qualification. Acceptance still requires compilation
and the new runtime corpus at the immutable Servo pin. This prototype does not
qualify a product PageOwner/BrowserActor, installed input, Wayland, variable
scaling, complete key layouts, clipboard, physical hardware, or mouse-state
cancellation. Those integration and qualification requirements remain open.
