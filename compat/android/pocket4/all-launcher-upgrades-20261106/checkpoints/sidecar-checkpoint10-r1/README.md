# Sidecar public increment for checkpoint10

This is an exact file manifest for the parent coordinator to merge and commit. It performs no Git operation and does not change any frozen source or original receipt.

The comparison baseline is the cumulative actual checkpoint06, checkpoint08 and checkpoint09 file indices, with later entries taking precedence. Earlier matching files are verified and listed separately; they are not duplicated as a new increment. Any mismatch aborts manifest creation.

The new public increment contains the independent full b05 corrective source and actual completed originals, its independent review, the preserved unexecuted linked r1 draft, the frozen linked r2 closure, public Calendar raw manifest/tool diagnostics and parser review, public Beike permission receipt metadata and minimal literal derived observations, and the new 45-target permission design.

The parent has begun executing the linked audit. This snapshot intentionally selects linked r2 only through its original 52-file frozen `SOURCE_REVIEW.json` plus that manifest. Root's new execution helpers, claims and b06-b13 actual ledger evidence are not swept into a moving snapshot; root will add them separately.

No private UI directory is scanned. Complete PM/AppOps bodies and the two-log private reader's full stdout/read originals remain outside the repository. Only the reader's source/pins and public start/terminal metadata are included. Files matching the known two private log hashes or their full combined private stdout hash are rejected. Every included file must be regular, non-symlink UTF-8 text without NUL bytes. APK/JAR/ELF binaries, images and key material are outside the allowed selection. Derived bytecode is skipped and retained on disk.

`prepare_delta.py` writes a new manifest with exclusive creation, then reads it back and reports its exact byte count and SHA. The manifest records which earlier files were unchanged and labels each new file's purpose. Its own pin is reported separately to avoid a self-reference.
