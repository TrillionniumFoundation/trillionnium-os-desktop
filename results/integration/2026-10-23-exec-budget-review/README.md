# #249 aggregate exec-copy independent review

The reviewed head `cfe28e3efb5e025d58a9d663d1dd6a681c224892` was merged at
`38227d33fd3ed668f0424bc153e0d3d811731597` on 2026-10-23 09:06:23 UTC.
Both commits have tree `26c89107d5b7da3e9b4dd8522dfe86546327bcf6`.

`premerge-review.json` binds the four successful checks, the original 19-check
native receipt, and the complete recursive-tree differences from the product
and probe source pins. `merge-readback.json` binds the returned merge commit,
parents and identical tree.

The two `.log` files preserve the entire decoded text returned by GitHub for
[exact-kernel-ktest](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39902615599/job/120247362925)
and [trusted-initial-control](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39902615715/job/120247362447).
The latter includes both the real positive guest and old-root negative control.
The manifest records the exact returned bytes, hashes and local review inputs;
these are not selected tail excerpts or a newly executed local guest.

The closed scope is aggregate argv/envp strings and pointer slots,
execveat/shebang replacement and bounded pre-copy admission. Total memory,
watchdog/public recovery, final exec roles, F1/G2 and production authorization
remain separate gates.
