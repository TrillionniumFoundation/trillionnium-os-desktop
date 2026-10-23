# Private Linux X11 / XIM Chinese input probe

This probe tests actual host input on the existing Rust/egui clients. It does
not replace the UI renderer, change locked dependencies or use a synthetic
`egui::ImeEvent`. XTEST sends ASCII key events into an authenticated, private
Xvfb server. The real Ubuntu IBus/libpinyin engine supplies XIM composition to
the locked winit X11 backend. The probe captures actual X11 framebuffer pixels
and reads the applications' own text outputs.

The sample is deliberately different in the two applications:

| Rust client | ASCII key input | Candidate confirmation | Required output |
| --- | --- | --- | --- |
| Shell Conversation | `nihao` | Space | `你好` in the private Clipboard and native local draft export |
| Independent Notes | `zhongwen` | Space | `中文` in the private Clipboard after focus leaves and returns |

No Unicode text is typed, pasted or preloaded into the clipboard. The distinct
Notes result excludes a stale Shell clipboard being accepted as Notes output.
The expected Unicode strings are assertions only. This is a virtual keyboard
test of a real OS input path; it does not establish physical keyboard input.

The [2026-10-17 real XIM evidence](../../tests/ui/evidence/2026-10-17-real-xim/README.md)
archives the completed UI-05 run, its nine unmodified screenshots and exact
output assertions, plus failed preflights and earlier attempts. UI-05 passed
the 23-action slice with the two different outputs above. Candidate placement
at the caret remains failed. The evidence records the harness and production
ELF sources separately; this runbook does not turn later documentation edits
into additional executed qualifications.

## Fixed prerequisites and provenance

The recorded environment is Ubuntu 24.04 on Linux x86_64, with Python 3.12,
Git, bubblewrap, DBus and the host Mesa/software OpenGL runtime. The separately
staged input packages provide Xvfb, xauth, x11-utils, x11-xkb-utils, xdotool,
IBus 1.5.29 and ibus-libpinyin 1.15.7, including their pinned dependencies.
This fixture uses the host runtime libraries read-only; it is not a complete
standalone distribution image or an installer for other distributions.

The evidence package preserves all 44 official package names, versions,
archive URLs, exact byte counts and SHA-256 values, the signed APT metadata
provenance, and the completed private extraction receipt. The compressed
archives total 33,809,094 bytes. To recreate the package prefix, download each
manifest URL to a new private directory, verify its exact byte count and
SHA-256, then run `dpkg-deb --extract <verified-archive> <private-root>/packages`.
Repeat for the complete manifest and retain a `package-stage.json` with the
verified 44 `items` and `passed: true` only after every real extraction succeeds.
Extraction runs no package maintainer scripts and changes no host packages.
The original staging commands and receipts are retained with the evidence.

Use a real 0700 package root owned by the current effective UID. The script
creates a symlink-only merged `/usr` view of the host and staged packages,
then mounts it read-only in a disposable bubblewrap namespace. Fixed upstream
paths such as `/usr/libexec/ibus-x11`, libpinyin's dictionary path and
`/usr/bin/xkbcomp` work only inside that namespace. The host `/usr`, installed
packages and ordinary desktop configuration are untouched.

Use the four real A10 ELF files from one recorded successful build:
`trill-session`, `trill-shell`, `trill-ctl` and `trill-app-window`. The build
receipt must contain `status: "passed"`, `exit_code: 0`, `source_commit`,
`source_tree`, and `binaries` keyed by those exact four names, each with
`sha256`, `bytes` and `path`. The probe hashes the actual ELF bytes before
launch. It also requires a clean committed probe checkout and confirms that
its `ui` subtree matches the build source. A later harness/documentation
commit is recorded separately from the source of the compiled Rust programs.
The harness resolves its commit once, then requires the environment, client
and process-guard files to occupy their expected tracked paths and match that
commit's exact bytes. Those snapshots, blob IDs and SHA-256 values are recorded.
The production source tree is also resolved from its recorded commit. A fixture
inside the tracked path must match its frozen blob; an explicitly supplied
external fixture is labeled only by its independent hash, not attributed to
the harness commit.

The fixed sample font is the existing Noto Sans SC Regular file used by the
CJK pixel qualification: 10,595,948 bytes, SHA-256
`27251f8f257e831f4b876408a7d0ef88ae2c18fe0cbb6780bd18fe6bad8ddb10`.
Pass its absolute path; the probe only binds it read-only. It neither installs
nor downloads the font. IBus receives a new private Fontconfig configuration;
both Rust clients receive the explicit font override.

## Execute the fixed 23-action slice

Commit the harness and fixture before executing. Choose an absolute **new**
output directory whose parent already exists. Keep at least 100 MiB available
on the package-root filesystem throughout the run; the original threshold is
not relaxed for low-space environments. No Cargo build or package download
occurs in this command.

```sh
python3 -B tests/ui/probe-x11-ime.py \
  --base /absolute/private-package-root \
  --source-root "$PWD" \
  --output /absolute/new-private-ime-result \
  --ui \
  --bin-dir /absolute/built-ui/debug \
  --build-receipt /absolute/successful-ui-build-receipt.json \
  --font /absolute/NotoSansSC-Regular.ttf \
  --scenario "$PWD/tests/ui/x11-ime-actions.json"
```

The environment-only preflight omits `--ui` and the binary/font/scenario
arguments. An environment-only pass always leaves Rust IME verification false.
The full probe uses the fixed 1440 × 1000 display and default client geometry;
its pointer coordinates are part of this recorded fixture, not a generic
accessibility API or a model-controlled desktop actuator.

The process starts a new authenticated Xvfb server without TCP listening,
verifies that a client without its private cookie is rejected, creates a new
DBus and IBus instance, selects the actual `libpinyin` engine and checks
`XIM_SERVERS(ATOM) = @server=ibus`. A private schema override keeps the test's
US keymap. In IBus 1.5.29 the engine CLI otherwise returns failure for the
libpinyin `default` layout after selection because its `setxkbmap` argument
list is empty. No host GSettings or keyboard layout is changed.

The fixed actions then focus Shell's editor, send ASCII pinyin, capture the
candidate/preedit pixels, confirm with Space and copy the committed text.
Ordinary primary-pointer clicks invoke Shell's existing Save and Export
buttons. The required export is a newly created regular 0600 file containing
exactly `{"version":1,"drafts":["你好"]}`. No Hepta objective is submitted.

The existing CLI asks the owned Session to launch a real Notes child. The
probe waits for its observed first layout and mapped X11 window, then sends
the different ASCII pinyin sample. After Space, it changes X11 focus to Shell
and back to Notes, selects/copies Notes text and requires `中文`. Clipboard
selection is read solely from this disposable display as an output oracle;
the test never reads the user's desktop clipboard. XIDs are matched to the
owned processes and their Rust WM_CLASS before input is allowed.

Finally, the CLI sends a cancellation fenced by the observed Session instance
and requires the same Notes task to become `cancelled`. The existing waitable
child/process-group guard tears down only the probe's own Shell, Session,
trace, input method, bus and X server. The namespace uses `--clearenv` and
private state/config/cache/runtime directories. It isolates PID and network
namespaces. Where mounting a new `/proc` is denied, the existing `/proc` view
is bound read-only; it is not a private process-observation or host-metrics
qualification. No HOS2 or device authority is inferred from those metrics.

## Read the evidence without widening its meaning

`probe-provenance.json` and `namespace.json` separate the executed harness
commit/tree, both Python source hashes, fixture hash, actual four ELF hashes,
font hash and unchanged production UI subtree. `receipt.json` records the
actual input/output checks and cleanup. The output also keeps command stdout
and stderr, the original scenario and nine lossless framebuffer PNGs.

The PNGs require human inspection for actual preedit text, candidates,
committed text and focus presentation. Clipboard and export assertions
establish exact committed editor contents. Process layout markers alone do
not satisfy the pixel/input checks. An exception, timeout, cleanup error or
resource-floor violation remains a failed run, with its original receipt and
logs preserved in a different output directory.

The optional passive IBus trace is diagnostic only. In each recorded UI-03,
UI-04 and UI-05 run it fell back from DBus Monitoring to legacy eavesdropping
and exposed only 29 empty `UpdatePreeditText` signals, with zero `CommitText`
signals.
That trace is not evidence of complete XIM traffic or a direct winit
`Event::Ime` callback trace. The qualified result uses the ASCII input record,
actual candidate/preedit pixels and application output checks together.

Archive only logs, receipts, copied harness sources, the action fixture,
private schema override source, package hash/provenance manifests, actual
test output text and unmodified PNGs. Keep Xauthority cookies, IBus/dconf
user databases, executable packages and ELF/cache bytes out of Git evidence.
Non-image raw files may be stored in a lossless archive with per-member hashes.
Failed preflights and earlier runs retain their original identities; a later
successful replay does not rewrite them.

## Candidate position remains unresolved

The observed IBus candidate panel appears at the lower left of the application
window, separated from the text caret. This does **not** pass caret-position
qualification. The locked egui-winit already reads `PlatformOutput.ime` and
calls `window.set_ime_cursor_area`:
[egui 0.31.1 source, fixed commit](https://github.com/emilk/egui/blob/1669e52a7ccfc3489c1b0999b9ed48894a0b3887/crates/egui-winit/src/lib.rs#L866-L890).

The locked winit 0.30.13 X11 IME code prefers preedit callbacks. Its `set_spot`
implementation still sends `XNSpotLocation`, but the source explicitly
documents that spot placement does not work with libX11 preedit callbacks
and can leave selection windows at the lower left:
[winit fixed source](https://github.com/rust-windowing/winit/blob/e9809ef54b18499bb4f2cac945719ecc2a61061b/src/platform_impl/linux/x11/ime/context.rs#L344-L378).
The actual PNGs agree with that limitation. No dependency version, input
style or application coordinate path is changed to conceal it.

This slice qualifies only the recorded Linux X11 software environment and
short Simplified Chinese samples. It does not qualify Wayland text-input-v3,
physical keyboard/monitor/GPU presentation, Android/mobile input, all Unicode,
IME cancellation, every candidate-selection key, all editing/shortcut cases,
an accessibility flow, original Agentd execution, authenticated objective
submission or a device effect. Those require separate real tests. Existing
pointer-only launch/cancel/run rules were part of the archived source. They
do not qualify the current keyboard activation policy described below.


## Current explicit-activation policy

Both native apps now share `ui/activation_policy.rs` and its egui adapter
`ui/activation.rs`. Effect controls use semantic `Response::clicked()` so a
focused, deliberate Enter or Space can request the same operation as a primary
pointer click. Repeating or modified keypresses do not repeat effects. No
keyboard shortcut submits the Chat composer, and original Session/Hepta
admission and receipt checks remain authoritative.

The adapter snapshots raw events before editors consume them. Nonempty preedit
blocks every effect source. Commit, preedit cancellation and active IME disable
block the transition frame; a trailing Enter/Space remains fenced until the
confirmation keys are released. A fresh Tab or primary-pointer press after
composition can restore navigation if the backend swallowed the key release.
A pointer does not bypass active preedit. Losing window focus ends local preedit
tracking but does not arm a delayed candidate key. Multiple egui layout passes
share the same frame policy.

The standalone policy tests can run without GUI dependencies:

```sh
rustc --edition=2021 --test ui/activation_policy.rs -o /tmp/trill-activation-policy-tests
/tmp/trill-activation-policy-tests
```

Real egui widget regression tests live in `ui/activation.rs` and the native app
test modules. Run them with the locked UI workspace:

```sh
cargo test --manifest-path ui/Cargo.toml --locked -p trill-shell -p trill-app-window
```

A policy-test pass does not establish successful egui compilation, a real IME
backend, pixels, or physical input. The archived XIM receipt above predates this
policy change and must be replayed against the new source before extending its
qualification. Caret candidate placement remains unresolved.

The adapter preserves egui semantic accessibility actions instead of requiring
a pointer, but the current locked build does not enable eframe's `accesskit`
feature. Screen-reader actions and accessibility-tree coverage are therefore
**not qualified or delivered by this change**. Enabling the backend requires a
separately resolved lockfile and live assistive-technology validation; do not
label synthetic input-policy tests as screen-reader evidence.
