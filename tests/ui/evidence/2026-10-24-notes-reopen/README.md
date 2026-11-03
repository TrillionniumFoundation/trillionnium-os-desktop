# Ordinary Notes reopen: executed evidence

The real Session and native Notes window passed this probe on 2026-10-24 in
an owned Xvfb display and private D-Bus session. `execution.json` records the
durable runner's successful terminal state, source inputs and probe digest.
`result.json` is the unchanged result produced by the actual probe.

## What ran

The probe typed text into the native Notes editor, waited for the original
store to persist it, closed the window, launched a fresh Notes target through
the same Session, selected **打开已保存笔记 → 打开副本**, independently read the
restored text through AT-SPI, and continued editing. The source checkpoint
remained byte-for-byte unchanged. The destination had a new target identity,
revision 1 after restore, and no imported effect or retirement receipt.

The persisted source revision was 5; the new local edit advanced the new
document to revision 2. No Hepta effect request was made. The three PNGs are
actual XGetImage captures, with hashes in `result.json`; they are not render
mockups. Assistant image inspection confirmed readable Chinese labels,
the saved-document picker and the restored text.

## Reproduce

The tested source is `95f71ba944374151bec537a61fd1a96012ad0888`, followed by
the exact Rust 1.96 formatter output in `tested-format.patch`. The small Git
bundle retains the original tested commit and its prerequisite declarations;
`git bundle verify tested-source.bundle` reports the required parent objects.
The current implementation contains the same Notes restore change, plus the
separately added queued-effect deadline regression.

Build the real Session and application binaries using the pinned Rust 1.96
UI workspace. Supply the original resource profile's real Noto Sans SC font
through `TRILL_UI_CJK_FONT`, then run:

```sh
python3 -B tests/ui/test-notes-reopen-x11.py \
  --repo /absolute/path/to/desktop \
  --bin-dir /absolute/path/to/built/binaries \
  --output /absolute/path/to/new-owned-evidence-directory
```

The output directory must not already exist. The probe creates its own display,
D-Bus session, Session process and temporary Notes store, and cleans up its
owned processes. It does not attach to the user's desktop or require an
original human/effect lease. The exact executed probe SHA-256 is recorded in
`execution.json`.

## Scope and retained failure

This closes the **ordinary local document reopen** check. It does not establish
production original-writer terminal publication, Root restart recovery,
physical-display behavior or real Chinese IME composition. Those remain
separate gates. The earlier probe reached a persisted restore but failed at a
Python GI method dispatch (`get_text_iface().get_text`); the successful probe
uses the original helpers' explicit `Atspi.Text.get_text` dispatch. The earlier
failed runner and receipt were preserved, not rewritten into a pass.

The real font test and the existing app-SIGKILL/lost-reply recovery probe also
passed in a separate run. That crash probe explicitly reported
`production_authority=false` and `original_writer_terminal=false`; ordinary
document recovery must not promote those results into a production effect
claim.
