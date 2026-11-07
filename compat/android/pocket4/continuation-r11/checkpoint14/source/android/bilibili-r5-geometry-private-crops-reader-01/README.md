# Two retained private crop copies only

The original geometry attempt failed with `VIEWPORT_SCOPE_CHANGED_DURING_CAPTURE`. This reader preserves that failure. It accepts only the four exact safe summary JSON files and the two exact previously published crop PNGs listed in the source. It never reads the third failed raw capture, a full screenshot, a UI tree, any other flow or the current App.

The two PNGs are 493547 and 494153 bytes, both 1200 by 675. Their recorded prior before/after proof chains match exactly. The third proof differs in absolute horizontal coordinates, window hash and render-structure hash, so no third crop is accepted. Package, UID, activity, window token and Main identity stayed equal. These observations locate a change between snapshots; they do not establish the instant or cause of the change, atomic screenshot attribution, video decoding, playback or audio output.

Default execution is PLAN_ONLY. The admitted `--collect-once` operation reads six fixed paths with component-by-component `O_NOFOLLOW`, exact original byte counts and SHA-256 pins, root/single-link/regular-file checks, stable held-FD metadata, a 2 MiB total bound and a 10-second read deadline.

It then makes byte-identical copies of only those two PNGs into the new create-only directory `/home/alex/work/pocket4-bilibili-r5-player-geometry-private-crops-01`. New files are operator UID/GID 1000, mode 0400; the new directory is mode 0700. Existing files, modes and owners are never modified. The directory is handed to the operator only after all copies and metadata are synced; its named inode is rechecked. A partial or existing export is never overwritten or retried automatically.

The stdout contains only metadata and paths, not pixels/base64. The operator must check the exact PNG size/SHA before private visual inspection. PNGs and their decoded pixels must not enter Git, general evidence publication or a public summary. This new private-copy operation performs no Android, process, UI or audio action and makes no runtime acceptance claim.

Seven local controls exercise the actual admission predicate on the retained safe JSON plus explicit negative mutations. They do not run the copy operation, chown, filesystem reader, device or UI. Root reviews and executes the single exact request separately.
