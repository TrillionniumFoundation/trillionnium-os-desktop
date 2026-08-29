# Servo embedder compatibility boundary

**Work package:** `TOS-D0A-01`  
**Servo pin:** `670ae8a70801b162e186f81cbb5bdd2d59c39108`  
**Claim class:** compile compatibility only

## Purpose

D0A-01 prevents the product plan from depending on an imagined or moving Servo
API. The exact upstream commit is compiled with its own toolchain and lockfile.
The gate proves that the public APIs needed to begin D0A-02 remain nameable and
type-correct from a separate example crate.

## Compile targets

The permanent `servo-exact-pin` workflow checks:

1. an exact, clean Servo checkout with zero local patches;
2. Servo's declared `rust-toolchain.toml` and `Cargo.lock`;
3. `cargo check --locked -p servo --example winit_minimal`;
4. the Trillionnium public API example under the same Servo workspace lock;
5. the official headed `servoshell` binary with a reduced explicit feature set;
6. source-level presence of the callbacks and methods listed in
   `manifests/servo-api-requirements.v2.json`.

The Trillionnium probe covers:

- `ServoBuilder`, `EventLoopWaker` and `Servo::spin_event_loop`;
- `WebViewBuilder` and exactly one logical content `WebView`;
- focus, resize, navigation, native input, paint and screenshot entry points;
- navigation denial and auxiliary-WebView interception;
- frame-ready, URL, load-status and crash callbacks;
- composition/input-method, clipboard and resource-interception types;
- accessibility activation and tree-update surfaces.

## Patch policy

`manifests/servo-patch-ledger.v1.json` is normative. D0A-01 requires
`patch_count = 0`. A later patch must be explicit, minimal, tested, owned and
tracked upstream; an unrecorded dirty checkout is a hard failure.

## What passing D0A-01 does not prove

A successful compile does not start Servo and does not prove:

- a window or first frame;
- Wayland/X11 presentation;
- pointer, keyboard, wheel, clipboard or IME delivery at runtime;
- popup denial in a live page;
- content-process crash recovery;
- stable semantic element identifiers for BrowserActor;
- a direct arbitrary hit-test query;
- external navigation, credentials or effects;
- Debian/QEMU integration.

Those facts require the D0A-02 local-fixture runtime and later D1–D4 evidence.
No WebDriver listener is introduced by this gate.
