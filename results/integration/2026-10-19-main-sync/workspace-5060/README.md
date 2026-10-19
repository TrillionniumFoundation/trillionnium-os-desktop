# Current R9 native Workspace / Chat and embedded Console

This package contains two new, unedited native PNGs from the current R9 Rust
Shell, one empty owned Session and a private Xvfb display. The first image is
the default Personal / Chat workspace; one actual XTEST primary-pointer click
selects Console within the right workspace pane for the second image. A10 and
the root reviewer each opened and inspected both PNGs.

## Outcome and exact scope

`capture-02/receipt.json` completed with exit 0. Source, harness and all four
ELF hashes remained unchanged. Actual namespace identities were Session PID
7 / instance `4673be60fa79a390b65a827836b94d16`, Shell PID 10 / XID 4194307,
and Xvfb PID 3. The outer namespace leader was PID 511394. All three long-lived
owned groups and the outer leader were reaped; their guards were disarmed.
Short command groups use the same anchored wait/reap path in the retained
harness. The actual Snapshot observations all retain the same Session, empty
host tasks and unconfigured Hepta.

| Original PNG | Bytes | SHA-256 |
| --- | ---: | --- |
| `capture-02/inside/initial.png` | 87,112 | `418ba2bdfd86234e80bb1376c82a6d48553bea538c0e565f4a3572105b1fbbad` |
| `capture-02/inside/action-002-screenshot.png` | 101,494 | `2d64764cc883803bb2c908c4f1c1a3989e7a681e77e8e60e733e7ed5d100687f` |

Both files preserve the complete 1440x1000 root framebuffer, including the
1360x840 Rust window and the remaining black area. There was no cropping,
repainting or reconstruction. The Console frame shows the local draft area
alongside the selected Console tab, its read-only host observation labels,
the real Session instance, and empty process/notice lists. No red ScrollArea
ID conflict text is visible in that frame. Selected Chinese labels and the
placeholder are readable under this explicitly loaded Noto configuration.

This qualifies current two-page rendering in this private X11 setup. It does
not restore R7's lost original pictures or transfer qualification to other
source commits. There was no draft save, task lifecycle, Session replacement,
independent scroll or Runtime-age pixel exercise. It does not upgrade the two
ignored font tests, old IME failures, an unexecuted CI X11 branch, physical
input, GPU, mobile, original Agentd, issuer, model or device behavior.

## Source and unchanged build reuse

The executed current source was clean local commit
`2bc512a445f30a53ac4c579fece1ff91c03c8741`, tree
`ae588699126910065c16b77d83f3ef20b53509f2`. Its compiled UI/observer files exactly
match the earlier R9 build closure
`d720db71872f8c263b73ab3b5ad9702a856898a32b7cfde312cfe805156d0fe0`.
No executable was rebuilt. All four production ELF bodies were copied from
the executable RAM view after matching their original SHA and byte lengths,
then rechecked before and after capture. The normal sandbox's earlier RAM
FileNotFound observation was a mount-view difference, not missing binaries.

`original-r9-build/` preserves the actual original build receipt, launch,
source inventories and four-bin identities. Its recorded HEAD remains 09cf
plus the executed source patch; it is not relabeled as the capture commit.
`capture-02/inside/input-binding.json` records the current full source view,
the original compiled closure, exact ELF identities, source correspondence,
font and environment hashes. `post-cleanup-source-inventory.json` is a later
actual source/ELF read which matches the capture's before inventory; the
outer receipt independently checked equality at namespace completion.

## Preserved environment failure and minimal recovery

Attempt `capture-01` started Xvfb but could not load `xdpyinfo`: the first
private runtime set lacked `libXtst.so.6` and `libXxf86dga.so.1`. It reached
its bounded readiness limit, exited 1, produced no PNG and started no Session
or Shell. Xvfb and the outer namespace were reaped; source/harness/ELF inputs
were unchanged. These raw receipts and all command outputs are retained.

The restoration scripts downloaded fixed Ubuntu package URLs, checked SHA
and lengths, and used `dpkg-deb --extract` only into this task's private
sysroot. No system package installation occurred. Environment 01 contains
11 packages. Environment 02 adds only the two loader gaps actually observed
and constructs a new `view03/usr`; the first receipt/view/harness remain
separate. Link diagnostics then found no unresolved libraries for Xvfb,
xdpyinfo, xdotool and xprop. The actual second launch is the display proof.

The font is `NotoSansCJK-Regular.ttc`, 19,484,784 bytes, SHA-256
`b76b0433203017ca80401b2ee0dd69350349871c4b19d504c34dbdd80541690a`.
The real Shell stderr records the explicit font load and selected face.
Xvfb's retained XKEYBOARD warnings report unsupported key names and state
that they are nonfatal; they are not hidden or upgraded into IME coverage.

## Harness and storage

The tracked `tests/ui/probe-chat-workspace.py` requires the broader R7
31-action/task/export/replacement scenario. The task-private derivative
keeps the actual Session, window/PID checks, XGetImage capture, parent-death
wrapper and anchored process-group cleanup. It restricts input to click,
screenshot and finish; finish requires exactly two images, one unchanged
Session with no tasks and no Hepta configuration, and the same actual window.
The original source, both derivative versions, derivation scripts and exact
diffs are retained. Production source and the tracked harness were not edited.

All raw JSON/PNG and harness text are stored unchanged. Raw logs and patches
are losslessly gzip-compressed with mtime 0 and deduplicated by content hash;
`archive-manifest.json` maps every original filename to its raw SHA/length and
stored SHA/length. This retains each of the 100 identical failed readiness
command outputs without duplicating their bytes. Packaging verified every
decompression against the original file. `SHA256SUMS` covers every stored
file except itself. ELF bodies, Debian packages, sysroot/view symlinks,
sockets and caches are excluded; their needed provenance is retained.
