# CJK font and actual Pixman capture evidence — 2026-10-17

The new Shell and native Notes window rendered readable Chinese labels and
TextEdit hints in **actual 1440 × 900 Pixman-composited PNGs**. The earlier
Shell rendered those labels as missing-glyph boxes. These are screenshots of
newly created private test compositors, not generated illustrations, synthetic
widget layouts or the user's current desktop.

The result qualifies the selected host font and software-captured window
pixels. It does **not** qualify real Chinese input: Weston 13's observed
registry advertises text-input v1, no v3 and no input seat; locked
`winit 0.30.13` binds v3. The readable TextEdit hints are not proof of typing,
preedit, candidate selection, commit, clipboard or keyboard focus on a real
input device.

## Exact source and binary identity

| Artifact | Qualified source | SHA-256 / tree |
| --- | --- | --- |
| New UI source | local `a601a1066f7b825ec62de57c64fbe94771429ba2` | tree `e244dbb04f482c15cfe6b6015197fbdce7238b83` |
| Identical published source object | remote [`397db55e34a3a65d50635dec6a6aae7bcd573803`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/397db55e34a3a65d50635dec6a6aae7bcd573803) | same complete tree `e244dbb04f482c15cfe6b6015197fbdce7238b83`; mapping verified by A00 |
| Source parent | local `6aa6cd40642b573c02a7253ca03302e9a42f552d`, published as `3e477d25` | owner `566267f6` and main `561f1e2` were normally merged before this change |
| New Shell ELF | built here from `a601a10`, Rust 1.88.0 | `c8ccdf38bf5190d473d17459adddc492a8ab2eb7b9cd5ad15df97ee7d4dd9f91` |
| New AppWindow ELF | built here from `a601a10`, Rust 1.88.0 | `07e5cd03a43dba3f302745f695a8df3bade41bb194fe1eb1ced10710529ca8c0` |
| Reused Session ELF | prior tested source `9b13dfb`, published with identical tree as `865ecf381dc8ddb70470ee173add9bd3b4a6a29a` | `3d52f8c3d61c81975a13f518810d4170e84c2c28a070684e91014567764d39c5` |
| Reused operator CLI ELF | same prior source `865ecf3` | `d8adf74b743389c70d606c36ab6faaf4f1f992013a9cc593385868577b633ffd` |
| Old Shell ELF, before font change | same prior source `865ecf3` | `21e838f81d35c0372731f1344cb886e96f5b025f6628fa9b73879c2c54d03c29` |
| Selected host font | existing Noto Sans SC instance, face 0, OS/2 weight 400, 10,595,948 bytes | `27251f8f257e831f4b876408a7d0ef88ae2c18fe0cbb6780bd18fe6bad8ddb10` |

The Session/CLI were deliberately reused and are not relabelled as newly
built binaries. Every command receipt includes source/tree, exact command,
raw log hash, binary hashes/modes before and after, timestamps and measured
free disk. The font was read from the existing report workspace, without
installing, copying or bundling it into the application or this repository.
Its old name-table label still says “Thin”; `font-asset.json` records that the
actual nonvariable instance is weight 400. Its cmap contains 30,890 codepoints
and all 61 distinct characters in the bounded UI sample. That count is not
a claim of full Unicode support.

## Captures and visual review

| Case | Actual capture | Font/visual conclusion |
| --- | --- | --- |
| Old `865ecf3` Shell | [`old-865-preflight/shell/wayland-screenshot-2026-10-17_14-12-23.png`](old-865-preflight/shell/wayland-screenshot-2026-10-17_14-12-23.png) | Capture succeeded; Chinese UI labels and hints were **tofu / visually failed**. The old raw receipt's `passed=true` describes its capture preflight, not CJK support. |
| New `a601a10` Shell | [`a601a10-cjk-pixels/shell/wayland-screenshot-2026-10-17_14-30-02.png`](a601a10-cjk-pixels/shell/wayland-screenshot-2026-10-17_14-30-02.png) | “本地任务”, “消息”, app names and “输入想法、任务草稿” are readable. |
| New `a601a10` Notes | [`a601a10-cjk-pixels/notes/wayland-screenshot-2026-10-17_14-30-03.png`](a601a10-cjk-pixels/notes/wayland-screenshot-2026-10-17_14-30-03.png) | “Notes / 笔记” and the native TextEdit hint “中文输入、候选词、焦点测试” are readable. |

Both new PNGs were opened and visually reviewed by the UI implementer, A00
and the independent documentation reviewer. The raw capture receipt remains
unchanged with `visual_review_required=true`; automated color/difference
checks alone are not represented as OCR. Raw background PNGs are retained
alongside each run. The new Shell image has 2,461 distinct RGB colors and the
Notes image has 2,570; these are image sanity checks, not text recognition.

The new probe started the real Notes client through the private Session's
generation-fenced CLI. The Session recorded task #1, PID 536800, a completed
first egui layout and subsequently **CANCELLED / observed SIGKILL**. All
probe-owned Shell, Session and Weston processes were reaped. This is a real
owned host-process lifecycle; it is not a Hepta objective or device effect.

## Executed checks on `a601a10`

All of the following completed with exit 0. The source stayed unchanged
throughout, including the final formatter check.

| Raw case under `a601a10-host-checks/` | Executed qualification |
| --- | --- |
| `build-shell-01` / `build-app-window-01` | Real Rust 1.88.0 `--locked --offline` native builds; no framework rewrite or dependency download. |
| `shell-font-tests-01` | Four tests: explicit configuration, malformed/Latin-only font and face rejection, oversized/nonregular input rejection, and an actual selected-font test. |
| `app-font-tests-01` | The same four checks compiled and executed in AppWindow. Both real-font tests ran with `--include-ignored`, so **0 ignored** in these runs. |
| `shell-owner-rules-01` | Four existing Shell lifecycle tests, including refusal for equal epoch 3 and older epoch 2, acceptance only of newer epoch 4 with a previously rendered Running process, and refusal of keyboard-generated process-button activation. |
| `shell-synthetic-ime-01` | One synthetic egui focus/Chinese-commit regression; **not** host IME evidence. |
| `app-synthetic-ime-01` / `app-pointer-rule-01` | Two tests preserving candidate-Enter and primary-pointer-only command rules. |
| `cjk-pixels-01` | Actual new Shell and Session-owned Notes captures with the selected font, independent of first-layout markers. |
| `ui-clippy-01` | Shell and AppWindow `--all-targets --locked --offline -- -D warnings`; passed. |
| `final-source-checks-01` | Actual Rust/cargo versions, `cargo fmt --all -- --check` including shared `ui/host_fonts.rs`, locked source, two shell-script syntax checks, Python AST without bytecode, empty README, unchanged dependency package identities/checksums. |

This is **15 actual targeted test executions**, plus builds, real captures,
Clippy and final source checks. It is not a rerun of the historical 137-test
host suite or the entire current cloud workflow. The full headless lifecycle
scripts were changed to select Pixman explicitly, but were not rerun end to
end in this slice; their exact renderer arguments were exercised by the new
capture probe. Historical 137/Weston receipts retain their original source
and no-op/layout qualification.

## Resource, source and evidence controls

The two new direct manifest edges reuse the already locked and compiled
`ab_glyph 0.2.32` identity. Cargo generated exactly those two lockfile changes;
all registry package versions/checksums remained unchanged. New artifact
hashes used more disk than the initial 30 MiB estimate, so work paused after
the Shell build. A00 then authorized up to approximately 45 MiB more with a
24 MiB free-space stop threshold. Subsequent work stayed above that threshold;
the lowest command-recorded free space was about 42.77 MiB during final
checks. No previous Cargo cache, ELF permissions, source or old evidence was
deleted or rewritten.

The initial scratch preflight import created one new untracked Python
bytecode file. A00 explicitly authorized removal of **that exact new file**;
the path, size, hash, timestamp and authorization are preserved in
`environment/new-bytecode-cleanup.json`. The committed probe disables
bytecode generation before importing the tested process-identity guard.

`raw-artifacts.json` maps 76 retained raw files to their original paths, sizes
and SHA-256 values; `RAW_SHA256SUMS` is independently checkable. Every retained
raw file is byte-for-byte identical, including trailing empty log lines.
Development-only precommit metadata/check output is explicitly separated
from commit-bound acceptance. The raw command/probe helpers are preserved
for reproducibility. The evidence commit follows the tested code commit; it
does not rewrite the source identity inside any original receipt.

Remaining gates: a compatible host seat/compositor plus actual Chinese IME
preedit/commit/focus, full current CI/lifecycle rerun, accessibility and visual
design review beyond this text sample, physical GPU/monitor paths, mobile and
target-kernel UI, original Agentd and authenticated Hepta objective execution.
