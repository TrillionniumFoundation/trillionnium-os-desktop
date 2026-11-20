# CI continuation

Append this packet after the existing original capsule and materialization
successor verification in the same job. Keep both existing verification stages.
Pass the materialization packet to `--parent-packet` and its reconstructed full
`producer` to `--parent-source`. Require the new external inventory hash, complete
successor tree, and `run_ci.py` report state `COMPLETE` with 42 fresh passes.

This successor tests only `droidloom-applications` on the complete source tree.
The previous materialization crate's 100-test evidence stays attached to its
unchanged parent packet; it is not represented as a newly rerun test. Existing
release profiles and original 19-target identities remain historical claims.

Production stays unqualified. Unit tests and the complete-source replay cannot
replace the current Main, APK custody, UI, business, transport or cleanup gates.
