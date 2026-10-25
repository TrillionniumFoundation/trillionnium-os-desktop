# Native accessibility and input acceptance

The Rust eframe/egui renderer enables the locked `accesskit` backend. On Linux,
AccessKit publishes its semantic tree to AT-SPI. Notes, the objective composer,
Calculator numeric fields and IME probe, and the restricted Terminal editor
link their visible labels to their edit controls. This remains an egui renderer;
it does not add a WebView, Makepad runtime, mobile port or Asterinas compositor.

All effect controls use the shared `ActivationGuard`. A focused fresh
Enter/Space, a primary pointer click or an explicit AccessKit action can
activate an enabled control. Active preedit, commit/cancel transitions,
held/repeated confirmation keys and disabled controls cannot dispatch an
effect. The policy is input routing, not admission: Session and the original
Hepta owners still decide whether an operation is allowed.

## Reproduce

Use Rust 1.96 and the committed UI lockfile:

```sh
cargo +1.96.0 test --manifest-path ui/Cargo.toml --workspace --locked
cargo +1.96.0 build --manifest-path ui/Cargo.toml --locked -p trill-app-window
bash tests/ui/accesskit-smoke.sh
```

The smoke gate needs `dbus-run-session`, `xvfb-run`, `xdotool`, `at-spi2-core`, Python GI
and the `Atspi-2.0` typelib. It creates its own X server and D-Bus session and
starts one test-owned Calculator process. Because Xvfb has no window manager,
it explicitly focuses only that process window; the production focus guard
is retained. It discovers the real native button
role/name and labelled edit fields through AT-SPI, activates `+` without
pointer coordinates, and requires the actual Calculator validation result for
empty inputs. This egui Calculator smoke neither performs nor validates
semantic EditableText SetText; its assertions cover the observed text/focus
interfaces, semantic button action and empty-input result. It cleans up only
its own processes.
`A10_APP_WINDOW_BINARY` can select an already built exact binary; otherwise
`${CARGO_TARGET_DIR:-ui/target}/debug/trill-app-window` is used.

The shared patched AccessKit source includes the five atomic EditableText
methods described in the [original Makepad contract](NATIVE_MAKEPAD.md#atomic-editabletext-and-the-remaining-native-paste-boundary).
An actual node exposes those methods only when its renderer publishes the
required actions; source presence does not show that this egui Calculator
implements or passes semantic text editing. Makepad's five-method test and its
separate candidate `PasteText` feature have their own binary, resource and real
D-Bus qualification requirements in that contract.

The egui tests separately exercise actual `AccessKitActionRequest` dispatch
and real TreeUpdate nodes, including IME and disabled-button refusal. The
policy tests cover delayed candidate key-up, repeat metadata absence,
focus changes, multiple layout passes and fresh navigation recovery.

## Acceptance boundaries

The AT-SPI test qualifies the native software adapter and its semantic action
path. It does not constitute a trial of a physical screen reader, hardware
keyboard, Wayland IME candidate placement, mobile input or physical display.
The archived XIM evidence predates this closure and must not be relabelled as
new input evidence. Caret candidate placement and physical assistive-technology
acceptance require their respective live environment gates.
