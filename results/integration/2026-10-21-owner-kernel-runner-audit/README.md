# Kernel owner and dedicated desktop evidence

This directory retains the complete #224/#225 source comparison and the
original dedicated desktop job response observed on 2026-10-21. It records
existing qualification results; it does not confer a new release qualification.

## Fixed sources

| Source | Exact commit or job |
| --- | --- |
| OS #224 | `49e5582db15493eed60d62fb16b4c85fc7408307` |
| OS #225 | `47141400acd8f6c26d4069dba1d08206980493e7` |
| Main after the independently performed #225 merge | `168d053e2d5493fbc4bc45914099c62b6691ad45` |
| #224 native job | `118984639491`, run `39527232732` |
| #225 native job | `119118562629`, run `39569111993` |
| Hepta dedicated desktop source | `f8c9419df6ddeb36ff8b522a50219981fb8d9345` |
| Dedicated desktop job | `118981704826`, run `39526325715` |

Both complete recursive Git trees contain 9,226 entries and 7,531 blobs,
with `truncated=false`. The comparison covers every entry. Twelve file paths
differ. The only changed kernel file removes two explanatory comments;
production kernel behavior, including the leading bootstrap newline, is
unchanged between these owners. The ExFAT guest probe in #225 formats each
credential line into one bounded buffer and performs one checked write, fixing
the interleaving observed by #224's unchanged strict credential oracle.

The #224 native job failed: its five guest business cases passed, but four
credential markers were malformed or reordered. Its complete failed job log
is retained alongside #225's successful log. The latter retains the complete
core minimum of 262 tests, the compiled SMP denominator of 265, the 24 required
core tests, the positive guest evidence and the actual production mutation
negative control. The artifact metadata referenced by those jobs does not mean
the approximately 190/206 MB artifact ZIPs were downloaded here.

`kernel/assessment.json` lists the host-test differences that must not be
silently erased by the merge. The missing unterminated-firmware-line regression
has a separate follow-up, OS #227, at
`9aa5dddaa89b8493524d5e9b289b1ecc7532d9b0`; its source change and original gates
are independent of this evidence commit. This audit did not perform #225's
merge, which GitHub attributes to Qian QI at 09:05:50 UTC.

## Dedicated desktop status

The captured Hepta workflow is restricted to trusted `main`, the
`trillionnium-android-gpu` runner group and runner name `desktop`. It would run
only the existing read-only system, ADB and GPU probes. At the timestamp in
`desktop/receipt.json`, the original job was queued with `runner_id=0`, an empty
runner name and no steps. There is no runner assignment, ADB result, GPU result,
or physical-device qualification in this snapshot. A temporary build container
does not replace that dedicated runner.

## Artifact integrity and bounds

Each retained file is smaller than 400 KiB. The full tree and compare JSON
responses, complete diff, and job logs use deterministic gzip containers; `manifest.json` records both
stored-file hashes and uncompressed hashes. Tree JSON bodies have one trailing
newline added during saving. All JSON values and entries are preserved.
Decoded job logs decompress to the complete original UTF-8 text, including
trailing whitespace. They are not downloaded artifact ZIPs. Raw
API collection bodies, semantic assessment and source differences are retained
separately so the conclusions can be checked against their exact inputs.

Run `python3 verify.py` from this directory to verify all hashes, gzip contents,
full-tree coverage, changed-file identities, the failed/successful native-log
identities and the still-unassigned desktop snapshot. It does not query GitHub
or rerun a native kernel gate.
