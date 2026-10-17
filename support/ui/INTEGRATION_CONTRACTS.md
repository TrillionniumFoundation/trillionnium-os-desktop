# A10 integration requests for A00 / A05 / A07 / A08

Scope: this is an interface consumer checklist, NOT a new wire protocol,
driver interface, kernel device manager, capability format or trusted grant
implementation. Only the designated owners can define shared ABI changes.

## A05: trusted session and portal source

Require an authenticated process-instance identity (not PID alone),
workspace/trust-domain identity, grant provenance and revocation signal.
Shell must be a consumer, not a forgeable same-UID authorization origin.
The compositor/session must own focus, input and window permissions; ordinary
client windows cannot draw trusted system permission prompts. A05 should
expose the policy decision through the project-wide process/capability
object model after A00 coordination.

File picker: return explicit selected capability/object, no directory-wide
implicit delegation. Clipboard and drag/drop require source and target domain
and user-initiated access. Screenshot, screen share, microphone, camera and
notifications must be portal mediated with revocation, not default Hepta
recording. Trusted prompts must be rendered from a system-owned surface.
The host prototype offers none of these grants.

### Consumer-side permission state

`support/ui/src/permission.rs` provides the shell's consumer-only
`PermissionState`. It accepts an opaque owner-supplied scope key, capability
kind, revision and observed decision; it does not request a grant, mint a
token, identify a process, derive a workspace/trust domain or define a portal
wire format. An empty scope cache is `Unknown` and denies access. Only the
latest authoritative `Granted` observation for the exact scope allows an
action; a grant observed for one scope is never considered for another scope.
Older observations and same-revision conflicts are rejected, so a stale grant
cannot resurrect a revoked or expired capability. `request()` is an explicit
handoff marker for the future A05 portal and has no local side effect. These
are negative, scope-isolation and ordering checks for UI behavior, not
evidence that an A05 portal exists.

## A07: non-fabricated Hepta task stream

Consume the existing Hepta owner/ledger instead of maintaining an extra
effect database. The view should expose a stable logical K reference,
optional HOS2 D delivery namespace/sequence, executor identity, trust domain,
task operation type, time and source of last observation, optional HOS2
resource sample and revision, plus provenance for each status transition.
Mapping must preserve pending, running, partial, unknown, cancel_requested,
completed, failed and confirmed cancelled distinctly. No terminal success
without the owner-confirmed result; a provider/model message is text only.
A requested cancellation is not guaranteed effect cancellation. Error
details must distinguish transport failure and uncertain effect.

Task execution and history QueryDelivery/RetireThrough remain A07/A02/A05
interfaces; the UI must not emit HOS2 InstallBudget or synthesize D/K IDs.
Its A02-typed read-only transport consumer enforces opcode/payload matching,
and every typed result must correlate to the same request ID and opcode;
mismatches fail closed instead of being reported as an observation. This does
not authenticate an owner or substitute for A05/A07 broker credentials.
Do not permanently grant Hepta global clipboard, key input or screen capture.
Hepta outage must not stop independent host/client process use.

## A08: initial full-display Android surface

Define a negotiated full-display surface contract before individual activity
windows. Proposed consumer fields (names conceptual, not on-wire ABI):
- display instance and owner identity, display dimensions, pixel format,
  density, transform, orientation, color space, and redraw generation
- buffer import/export mechanism chosen by compositor (DMA-BUF where verified,
  CPU shared memory fallback where permitted), stride/planes and lifetime
- acquire and release fences with explicit synchronization ownership; buffer
  reuse only after release, no unverified zero-copy assumptions
- input coordinate transforms, key/text/IME composition and candidates,
  touch slots, soft keyboard, Back/Home, multiwindow focus
- SurfaceFlinger display root and lifecycle transitions, suspension/resume,
  generation change, destroyed surface and explicit failure/unknown states

The consumer-side Rust model for these fields is `support/ui/src/android.rs`
(`AndroidDisplaySurface`). It is deliberately a pure state model with no
Binder object, file descriptor, SurfaceFlinger call, dma-buf import or new
wire format. Its tests cover stale-generation buffer retirement, producer /
compositor ownership, acquire/release fence readiness and failure, coordinate
mapping, IME composition, Back/Home routing, suspend/resume and provider
failure. These tests are contract checks only; they do not count as Android,
GPU or target-kernel evidence.

The compositor, not the chat shell, must own buffer import and input routing.
Initial full-surface acceptance does not imply APK-level native windows or
independent per-activity integration. A08 negotiates Android semantics,
A09 may supply actual GPU import/reset evidence; neither is implemented here.

## Compositor and Xwayland failure domains

Intended ownership: shell client -> authenticated session/compositor boundary
-> existing Wayland compositor -> client surfaces. Shell restart shall not
destroy independent compositor/client sockets. Session restart currently
loses ownership records; old clients are not claimed reattached. Compositor
crash may disconnect Wayland clients and invalidate buffers, and GPU reset
may require buffer recreation. Reattach is a fresh compositor/renderer
protocol, not an assumption from a surviving PID.

One Xwayland instance per genuine trust domain where supported, not one
shared X server described as isolated. X SECURITY alone is not an isolation
proof. First host prototype remains one external host compositor with no
trust-domain Xwayland isolation.

## A00 acceptance hooks

Under A00 ownership: add .github/workflows host UI job scoped to ui/**,
tests/ui/** and support/ui/**. It should run Rust host build/test/fmt
with dependency cache, then install required Mesa/Wayland dependencies.
Use isolated XDG_RUNTIME_DIR and headless compositor if possible for
interactive smoke; record stdout/stderr, exit code, driver, compositor
version, input method and observed faults. Host green != kernel green.

Track UI, A05 identity/permissions, A07 task integration and A08 Android
display as independent gates; do not alter docs/STATUS.md from A10 branch.
