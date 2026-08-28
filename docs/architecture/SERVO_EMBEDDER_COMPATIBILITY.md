# Servo embedder compatibility boundary

**Checkpoint:** `TOS-D0A-01`

## Purpose

The desktop product pins one exact Servo commit. The pin is not sufficient by
itself: every upgrade must prove that the public embedder boundary used by the
product still compiles and that Servo's own headed reference shell still passes
`cargo check --locked` on the qualification toolchain.

`tools/verify_servo_compatibility.py` performs that proof without starting a
browser runtime. It resolves and compiles the public paths for `Servo`,
`WebView`, `WebViewBuilder`, `RenderingContext`, `EventLoopWaker`,
`ServoDelegate` and `WebViewDelegate`; verifies the builder constructor and an
event-loop entry; generates one final compile sentinel; and checks the pinned
source's headed `servoshell` package.

## Product boundary

The compile sentinel is deliberately external to the main Rust workspace. It
depends on `.servo-source/components/servo` and therefore cannot silently pull
Servo into the fast D0 control-plane build. The dedicated compatibility workflow
clones the exact pin, verifies a clean tracked tree and records the upstream
Cargo.lock and component-manifest digests.

This checkpoint permits the next wrapper implementation to use the proven
public types. It does not grant a stable ABI across Servo revisions. A changed
public path, constructor, event-loop entry, source lock or headed reference build
moves the checkpoint to `HOLD` until the patch ledger and product wrapper are
requalified.

## WebDriver and process model

The probe neither imports nor starts WebDriver. Product control remains direct
and typed; WebDriver may exist only as a later development/conformance adapter.
Servo-created content, renderer, networking or GPU subprocesses are compatible
with the one-logical-session rule. The forbidden condition is a second hidden
Agent-controlled page/session, not a second operating-system process.

## Evidence hierarchy

A passing D0A-01 report establishes compile compatibility only. It is below:

1. a headed process start;
2. a visible first frame;
3. native pointer/keyboard/IME delivery;
4. local navigation and lifecycle recovery;
5. Debian QEMU and fixed-hardware qualification.

No lower result may be promoted to one of those higher claims.
