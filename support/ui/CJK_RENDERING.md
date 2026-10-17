# Host Chinese text rendering and input qualification

The Linux Rust clients share `ui/host_fonts.rs`. It is compiled into Shell and
AppWindow, outside the Session/protocol crate. No font bytes, file paths or
font configuration arrive through a model response or Hepta projection.

## Configure a host font

Set these variables in the environment of **both Session and Shell**, before
starting them. Session's native app children inherit the font configuration.
Use an existing, licensed font file; the clients do not install, copy, download
or bundle fonts.

```sh
export TRILL_UI_CJK_FONT=/absolute/path/to/NotoSansSC-Regular.ttf
export TRILL_UI_CJK_FONT_INDEX=0
cargo build --manifest-path ui/Cargo.toml --locked -p trill-shell -p trill-app-window
```

`TRILL_UI_CJK_FONT_INDEX` selects a face in a TTC collection. Without it the
index is zero. A collection's first face is not necessarily its Simplified
Chinese face; select the appropriate index for the actual font. An index
without an explicit font path, a relative path or a malformed index is rejected.

An explicit font selection is authoritative. If it is unreadable, is not a
regular file, exceeds 32 MiB, fails parsing or lacks the documented UI sample,
the application retains its built-in fonts and reports the failure. It does
not quietly qualify some other file as the selected font. Without an explicit
selection, both clients try the same Noto/WenQuanYi/Arphic host paths and accept
only a valid sample-covering face. No font in those paths means CJK remains
unavailable, even though the process can launch and draw English.

The bytes are size-limited during reading, then parsed by the same locked
`ab_glyph 0.2.32` parser used by egui before they reach egui's panic-on-error
font wrapper. The existing dependency identity is reused; no new UI engine or
font parser implementation is introduced. The override is trusted host
configuration, not a file-access API for remote input.

The selected font supplies proportional text and a fallback for monospace
text. This includes AppWindow's default `TextEdit`, previously missing the
CJK fallback. A CJK fallback does not make its Latin glyphs monospaced, and
the existing ASCII monospace face retains priority. `TRILL_UI_FONT_V1` on
stderr records selection source, face, byte count, UI-sample glyph count and
a stable error code. Shell Settings and AppWindow display font availability.

## Separate the evidence layers

The fixed string `CJK_SAMPLE` in the shared loader is a limited set of current
UI labels and input examples. Parsing and nonzero glyph IDs establish sample
coverage, not every Chinese character or every Unicode script. The ignored,
explicit-font test additionally checks both egui font families and rasterizes
four Chinese outlines into nonzero ink:

```sh
TRILL_UI_TEST_CJK_FONT=/absolute/path/to/NotoSansSC-Regular.ttf \
  cargo test --manifest-path ui/Cargo.toml --locked -p trill-shell \
  host_fonts::tests::selected_real_font_covers_egui_proportional_and_monospace -- --ignored
```

The same test is compiled into AppWindow. This explicit-font test is excluded
from ordinary tests because CI or a developer must select an actual font;
skipping it is not a successful CJK qualification. Ordinary tests reject
corrupt font bytes, an invalid face, a valid Latin-only font, nonregular files,
oversized files and invalid override configuration.

For actual software-composited pixels, first build the current binaries and
record the exact source commit, toolchain and binary hashes. Then run:

```sh
python3 -B tests/ui/probe-cjk-pixels.py \
  --binaries "${CARGO_TARGET_DIR:-$PWD/ui/target}/debug" \
  --font /absolute/path/to/NotoSansSC-Regular.ttf --font-index 0 \
  --output /absolute/path/to/new-cjk-pixel-evidence
```

The probe requires Linux, Weston with Pixman and `weston-screenshooter`,
`wayland-info`, Python 3 and Pillow, plus the four A10 executables. It creates
a private compositor with `--renderer=pixman --no-config --debug`, its own
0700 runtime and isolated state/config/cache directories. Debug capture is
enabled only on that private test compositor. It never connects to the user's
desktop. Session owns a real Notes child, and the probe requires observed
Notes cancellation before reaping its own processes.

Receipts preserve raw compositor/registry/client logs, PNG files, source and
binary/font hashes. The probe checks decoded image dimensions, actual color
detail, and changes away from the compositor clock. Those checks establish
captured window pixels; they do not recognize Chinese words. A reviewer must
inspect the Shell/Notes PNGs for readable Chinese labels and TextEdit hints.
The checkout hash alone cannot establish where a stale ELF was built: pair
the recorded binary hashes with the matching build receipt. No-op renderer
layout markers cannot satisfy this Pixman capture check.

## Chinese input is a different gate

Current `winit 0.30.13` Wayland code binds `zwp_text_input_manager_v3`.
The inspected Weston 13 headless environment advertises v1, lacks v3 and
has no `wl_seat`. It cannot exercise this application's host IME protocol
path. Fonts or synthetic `egui::ImeEvent::Commit` events do not fix that
environment mismatch. The capture receipt records the observed registry;
the result always keeps `real_ime_verified=false`.

To qualify input, use a host compositor that actually advertises v3 and an
input seat, with a configured Chinese input method. Verify preedit/candidate
placement, candidate commit, cancellation, focus changes across Shell and
Notes, editing after commit, and keyboard shortcuts. Preserve actual host
events and screenshots separately from synthetic egui tests. Existing
pointer-only process actions and the rule that candidate Enter must never
launch or terminate a process remain in force.

Software capture does not establish physical monitor presentation, a GPU
driver path, target Rust-kernel graphics, Android/mobile input, the original
Hepta daemon, authenticated objective submission or a device effect.
