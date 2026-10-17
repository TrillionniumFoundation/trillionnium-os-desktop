# Real Linux X11 / XIM Chinese input evidence — 2026-10-17

**UI-05 passed the recorded 23-action input slice at 14:09:30–14:09:55 UTC.**
XTEST sent ASCII `nihao` to Shell and `zhongwen` to the independently launched
Notes client. The real IBus/libpinyin XIM path supplied composition to the
existing locked winit/egui Rust programs. Shell's private Clipboard contained
`你好`, its native local export contained that draft in a regular 0600 file,
and Notes' Clipboard contained the distinct `中文` after focus left and returned.
The original [receipt](ui-05/receipt.json) has `passed: true`; the outer
[namespace receipt](ui-05/namespace.json) records return code 0.

This is a virtual-keyboard, software-framebuffer qualification of these short
samples on Linux x86_64. **Candidate placement at the text caret failed.**
The candidate panels remain at the lower left of the application windows.
There is no complete per-event winit IME trace. This archive does not qualify
Wayland text-input-v3, physical keyboard/monitor input, a GPU path, Asterinas,
mobile input, original Hepta Agentd execution, authenticated objectives or
device effects.

## Start with the final evidence

| File | Purpose |
| --- | --- |
| [UI-05 receipt](ui-05/receipt.json) | Original 23 actions, exact copied strings, export, final `cancelled` Notes state and child cleanup observations |
| [UI-05 namespace receipt](ui-05/namespace.json) | Actual namespace command, resource minimum, return code and provenance |
| [UI-05 source provenance](ui-05/probe-provenance.json) | Separate production and harness sources, frozen source blobs, fixture, four actual ELF hashes and font hash |
| [Original successful Rust build receipt](ui-05/rust-build-receipt.json) | The build that produced the four executables used in this run |
| [Original 23-action fixture](ui-05/replay-scenario.json) | ASCII key input, primary-pointer actions, focus changes and finish operation |
| [Original progress record](ui-05/ui-progress.json) and [ready record](ui-05/ui-ready.json) | Owned window/PID matching and input/output progression |
| [Native draft export](ui-05/state/trillionnium-ui/local-drafts-v1.json) | Exact original 33-byte output; original mode `0600`, SHA-256 `e1bbb8f9c70c67afcc2ddc2126083023ff6d284e0fa934a8b2458f3d3691feb4` |
| [Manifest](manifest.json) | Sources, run inventory, archive identity and hashes for the standalone files |
| [Raw member index](raw-members.json) | Every archived member's source path, exact byte count, SHA-256 and original file mode |
| [Lossless raw archive](raw-evidence.tar.gz) | 1,114 original/explicitly identified archival-validation members; 4,582,080 uncompressed content bytes |

The gzip archive is 2,515,692 bytes, SHA-256
`49ce8465d1d1529826666cfc9cc8d349470d47a1a46ff581710b2aeba5e31909`.
All archived source contents, including empty logs and newline bytes, were
compared byte-for-byte with their original files after archive creation.
Tar ownership and timestamp headers are normalized; original content and
source file modes remain recorded. The standalone receipts are identical
copies of their archive members. The nine final PNGs are standalone files;
earlier PNGs remain unmodified inside the raw archive.

## Nine unmodified UI-05 screenshots

All images are actual 1440 × 1000 X11 root-framebuffer captures through
`XGetImage`. Their original hashes and dimensions are in the receipt and
manifest. The pictures were visually reviewed; the Clipboard and native
export assertions provide the exact-text checks.

| Image | Recorded point in the input sequence |
| --- | --- |
| [Initial Shell](ui-05/ui-initial.png) | Existing Rust Shell before any typed input |
| [Shell preedit and candidates](ui-05/input-003-screenshot.png) | ASCII `nihao`, before candidate confirmation |
| [Shell committed text](ui-05/input-005-screenshot.png) | Space confirmed `你好` |
| [Shell saved draft](ui-05/input-008-screenshot.png) | Primary-pointer Save; native Export follows in action 9 |
| [Independent Notes](ui-05/input-011-screenshot.png) | Session-launched Notes child before typing |
| [Notes preedit and candidates](ui-05/input-014-screenshot.png) | Distinct ASCII `zhongwen`, before confirmation |
| [Notes committed text](ui-05/input-016-screenshot.png) | Space confirmed `中文` |
| [Notes after focus leaves](ui-05/input-018-screenshot.png) | Explicit focus changed to Shell |
| [Notes after focus returns and copy](ui-05/input-021-screenshot.png) | Notes regained focus; selection copied as the distinct `中文` |

No Unicode string was typed, pasted or preloaded into the Clipboard. The
expected Unicode strings are assertions. XIDs were matched to the owned
Rust processes and WM_CLASS before input. The test reads only this private
display's Clipboard. Save and Export are the applications' existing native
buttons; the fixture does not write their expected output file.

## Production bytes and harness bytes have different identities

| Role | Local commit recorded during execution | Published commit with the same full tree |
| --- | --- | --- |
| Four compiled Rust executables | `35f379101c0863027e971ccb91faf8da71cf929c` | [1974d9a94037440da358253e1f449b395daa4b64](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/1974d9a94037440da358253e1f449b395daa4b64) |
| Final UI-05 harness | `02cf552485f899cfbb9cba7eeae663c7f0e8bb9c` | [698d1bf47fadbdd0fc18fad191b3bd5f9744101f](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/698d1bf47fadbdd0fc18fad191b3bd5f9744101f) |
| Earlier UI-04 harness | `fb4666d989dcee87e8027eea22be7fedba74f168` | [0d43c7f4f2fba5a86781c4b4af93e0c25725d28e](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/0d43c7f4f2fba5a86781c4b4af93e0c25725d28e) |

The production full tree is `48433c4f1e55de53e8c298193765949996eb18a0`.
UI-05's full tree is `3a46eb76dd667a0fe54fa7b9936df93a7080d430`; UI-04's is
`863bf82a6ab9e907374c76c0ed1b00bc28d0e543`. The production `ui` subtree remains
`037f318be7140ef046eac1e9cabe230c07eb7059` in both harness commits. This
evidence/archive commit itself is not the source of a new Rust build or test.

| Actual executable | Bytes | SHA-256 |
| --- | ---: | --- |
| `trill-shell` | 24,153,992 | `81e9bcbf79c4060c3047ad0c80df711bfd855f2f47c3900522927d37404d776f` |
| `trill-session` | 3,527,808 | `5c29cfd7f11455000d7c3d9c0cc2c58fb7fe8761ab326da34c794d0f3481924f` |
| `trill-ctl` | 1,494,736 | `920093314640ad1dd721425ec78457f4ca74c83f9c1a0a878d4ddfee4924a882` |
| `trill-app-window` | 22,627,904 | `08c3bbe84b5d6e773f367f9751a1432eaee327bf45a5b172150f34f165342510` |

UI-05 snapshots all three executed Python sources and the action fixture.
Their archived bytes match the tracked blobs in the recorded harness commit.
The [environment harness](../../probe-x11-ime.py),
[client harness](../../x11-ime-client.py) and
[action fixture](../../x11-ime-actions.json) remain separately navigable in
the repository. The process guard is the unchanged original Agentd gate's
waitable-child helper; using that helper does not mean Agentd was launched.

The existing Noto Sans SC Regular font is 10,595,948 bytes, SHA-256
`27251f8f257e831f4b876408a7d0ef88ae2c18fe0cbb6780bd18fe6bad8ddb10`.
No font, ELF or package archive is included in this evidence directory.

## Earlier outcomes remain earlier outcomes

Each prefix below names members within `raw-evidence.tar.gz`. The raw member
index maps it back to the original private directory. A receipt is never
invented for an attempt that failed before the inner probe could create one.

| Attempt | Actual result | Meaning preserved in this archive |
| --- | --- | --- |
| `preflight-01` | Namespace exit 1; no inner receipt | Kernel denied mounting a new `/proc`; raw stderr retained |
| `preflight-02` | Namespace exit 1; no inner receipt | Guard imported at a path too shallow for its repository-relative lookup; original traceback retained |
| `preflight-03` | Failed, exit 1 | Strict schema compilation found an undefined magnifier enum |
| `preflight-04` | Failed, exit 1 | `ibus engine libpinyin` command failed; subsequent private keymap/schema handling is documented in the runbook |
| `preflight-05` | Failed, exit 1 | Probe queried `_XIM_SERVERS` and found no atom; later attempt queried the correct `XIM_SERVERS` |
| `preflight-06` | Passed, exit 0 | Environment/XIM selection only; Rust UI input remains unverified by this attempt |
| `ui-01` | Failed, exit 1 | Shell XID lookup failed before any recorded actions; environment success was not UI success |
| `ui-02` | Failed, exit 1 | `xdotool mousemove --sync` timed out; 19 started action records and one Shell Clipboard sample do not satisfy the complete slice |
| `ui-03` | Raw receipt passed, exit 0 | Both editors used `nihao` → `你好`; a stale Shell Clipboard could satisfy the same-value Notes oracle. Preserve this weaker result without promoting it to the final independent-editor proof |
| `ui-04` | Passed, exit 0 | 23 actions; different Shell/Notes outputs; older committed harness and provenance format. Shell's Clipboard value was recorded without UI-05's strict exact-string assertion. Actual interval 14:05:06–14:05:32 UTC |
| `ui-05` | Passed, exit 0 | 23 actions; different outputs; frozen tracked environment/client/guard sources and fixture. Actual interval 14:09:30–14:09:55 UTC |

UI-05's finish action cancels the observed Notes task through Session using
the observed Session instance fence. The final snapshot reports that same
task as `cancelled`, with an observed SIGKILL termination. The receipt then
records termination/reaping observations for the owned Shell, Session,
passive trace, IBus, DBus and Xvfb child groups. This is process cleanup,
not a claim that every private socket pathname or state file was deleted.
Private state stays outside the published evidence.

## Official environment provenance and archive verification

The `packages/` archive prefix preserves the original package plan, staging
receipt, download-cleanup receipt, source list, original APT update/simulation
commands and logs, package metadata, extraction logs and three signed
InRelease files. All 44 package names, exact versions, original archive URLs,
sizes and SHA-256 values are recorded. The original verified downloads total
33,809,094 bytes; the plan records 208,898,048 bytes of installed size.
Staging privately extracted packages without executing maintainer scripts
or installing/upgrading host packages. The later cleanup receipt records
removal of only this round's already verified `.deb` downloads.

The separate `archive-validation/` prefix is **new offline integrity work
performed while archiving**, not a replay or a runtime input trace. It contains
the exact public Ubuntu archive keyring copy, three `gpgv` stdout/stderr pairs,
and `metadata-verification.json`. Each original InRelease signature verified;
all six original package indexes' decompressed byte counts and SHA-256 values
matched their signed InRelease entries. All 44 selected package name/version,
architecture, filename, size and SHA-256 fields matched those verified indexes.
The selected original paragraph bytes are retained. The complete large index
caches are excluded, so the archived paragraph extracts alone are not a
standalone cryptographic inclusion proof; the signed metadata and the actual
offline verification receipt document that check.

The archive excludes Xauthority cookies, IBus/dconf user databases, private
bus configuration, runtime sockets/locks, font caches, executable packages,
ELFs and full APT index caches. No original log was edited to remove a line
or turn a failure into a pass. Only the explicitly selected noncredential
files are archived. No UI test was rerun during this archival step.

## Limits that remain open

The final screenshots show preedit and candidate choices, but the candidate
panel does not track the text caret. The locked winit 0.30.13 X11 implementation
documents the libX11 `PreeditCallbacks` spot-placement limitation; the locked
egui-winit already supplies the cursor area. The fixed source references and
reproduction details are in the [X11 / XIM runbook](../../../../support/ui/X11_IME.md#candidate-position-remains-unresolved).
No dependency or input-style change hides the failed positioning gate.

The passive DBus traces in UI-03, UI-04 and UI-05 each contain 29
`UpdatePreeditText` signals with empty strings and zero `CommitText` signals.
Monitoring fell back to legacy eavesdropping. These traces do not expose the
full XIM path or individual winit `Event::Ime` callbacks. The qualified input
result combines recorded ASCII actions, real preedit/candidate/commit pixels,
distinct native-editor output assertions and Session lifecycle observations.

Candidate cancellation, every selection key, broader editing and shortcut
cases, accessibility, all Chinese/Unicode input, Wayland v3 with a real seat,
physical input, GPU presentation, Asterinas and mobile remain separate gates.
The final snapshot explicitly reports Hepta `not_configured`. No original
Agentd, authenticated objective, HOS2/device authority or device effect is
claimed here. See the [XIM runbook](../../../../support/ui/X11_IME.md) for the
fixed procedure and [CJK rendering guide](../../../../support/ui/CJK_RENDERING.md)
for the separate font and Wayland pixel qualifications.
