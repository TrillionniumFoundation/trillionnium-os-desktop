# Retained original CPU owner: reviewed final CI

[PR #201](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/201) merged as `378aa44c6097a1fe62283d10da42055a037e1ba4`, tree `388bc4539217aca074a081ac107733a19cbe2bd4`, after all five checks and independent review. [A06 run 39212968844](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39212968844) executed exact candidate `c60f01bfe21f30436d5259bfdf33d411459b3404` with that identical tree.

`independent-review.json` records the complete source comparison (6,461 modes/blobs/sizes/SHA-256), reconstructed negative tree and independently applied frozen patch, exact 189 test names, actual 186-pass/3-fail old-behavior result, compiler/OSDK/lock/firmware identity and candidate restoration. OSTD reports 221 passed including three documented soft skips (218 exercised lower bound). The same ordinary kernel passed QueryAbi14, Linux/guest SCM27 and RLIMIT37, fixed CPU timing and original quota lanes.

The two original serial streams are losslessly gzipped with deterministic timestamps. `artifact-selection.json` binds every retained file to the original ZIP entry and both saved/raw hashes. QEMU paths in these historical receipts identify the actual CI invocation; moving these records does not execute those paths. The complete 44,670,031-byte artifact is `12169240176`, ZIP SHA-256 `a0da02f85b1a86adcbe3114019f513551d977b22b6b87b03c30c59a1025d62be`.

This closes the retained-incarnation owner defect. New clock, handoff, native-usage, trusted grant, full Linux/Hepta and device candidates require their own exact-source execution; these older successful records do not qualify new code.
