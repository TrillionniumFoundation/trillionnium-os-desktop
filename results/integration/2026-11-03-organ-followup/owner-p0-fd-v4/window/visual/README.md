# Original fd native window: AI image observation

All five screenshots listed by the original IBus receipt were retained and
actually inspected with `view_image` at original detail. The three window
captures are 1280 × 800; the two complete private-display captures are
1440 × 1000. Their sizes, dimensions and SHA-256 values match the original
receipt. Reads were version-bound; the first two window images also match the
complete original archive SHA-256. No image has been edited or recaptured.

The preedit image visibly shows underlined **你好** in the composer while the
heading and selected sidebar row remain **New conversation**. The final image
shows **你好** in the heading, sidebar title and preview, and composer. The
Chinese glyphs and Notes controls are legible in these captures.

The window-only preedit capture has a black rectangle near x=373–700,
y=733–799. The complete preedit display resolves that observation: a white
IBus candidate panel occupies the corresponding display rectangle near
x=523–850, y=793–859, after adding the App origin (150,60). Its top line reads
**ni hao**, candidate **1. 你好** is highlighted, and further candidates and
paging arrows are visible. The panel appears below the preedit text and stays
inside the private display in this frame.

The two captures support an overlapping-popup/window-capture limitation, not
a broken or black candidate panel. The original window image is retained
unchanged. Neither this frame nor the AI inspection grants candidate-position
or font-pixel qualification. Other sizes, scaling, monitors and IMEs are outside
this observation.

The separate committed-stage window and both final images show **你好** in
the heading, selected sidebar row and composer. The full final display no
longer shows the candidate panel. Its small blue-grey rectangle at
(1350,10), size 70 × 50, matches the original fd capture helper's owned focus
probe. The original test takes the final image before destroying that probe.

The final layout has separate sidebar, heading, tabs, status, Notes controls
and composer regions without an obvious overlap at this size. This is not a
responsive-layout, full font coverage, focus-order or accessibility review.

All five captures explicitly report that the host session, sending and Notes
readback are unavailable. The final hint says **Local draft · chat owner
unavailable**. These images therefore support a local window/draft observation;
they do not establish an original owner/model/application effect.

The machine-readable [AI review](ai-visual-review.json) records all five images,
the original receipt identities and these limits. It explicitly supersedes the
[initial two-window observation](ai-visual-review-initial-two-window.json),
which could not see the external popup. [Download verification](download-verification.json),
[archive chunk metadata](transport.json), and the individual PNG transport
records preserve the transfer identities. Source and runtime provenance remain
in the original qualifier receipts. No original qualification receipt has been
changed.

`human_visual`, `physical_hardware` and `orca` remain **false**. This report does
not claim an overall visual pass.

- [Original preedit capture](ime-preedit-window.png)
- [Original complete preedit display](ime-preedit-display.png)
- [Original committed-stage window](ime-committed-window.png)
- [Original final capture](ime-final-window.png)
- [Original complete final display](ime-final-display.png)

The separate [independent review](independent-review.json) rechecked all five
original PNG sizes/dimensions/hashes, viewed every image, and checked the
focus-probe source at the exact frozen Desktop commit. The [original IBus
receipt](../ibus-receipt.json) remains unchanged.
