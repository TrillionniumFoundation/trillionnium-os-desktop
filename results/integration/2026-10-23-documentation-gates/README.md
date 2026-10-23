# Project navigation and module entry gates

The root README may contain project navigation. Regular-file, source identity,
immutable upstream pins, source snapshots, test denominators and artifact
checks remain enforced. This completes the contract migration begun in #247.

The [validation record](validation.json) binds changed source SHA-256 values
and actual commands. The nonempty-README regression fails against the old
acceptance runner and passes after the change; symlink and missing toolchain
pin rejection remain covered. Three targeted existing tests passed under both
normal and optimized Python. Nine workflow YAML files parsed, the host shell
script passed syntax checking, and regular/missing/symlink file controls behaved
as specified. This is targeted host evidence, not a complete A02 or UI run.

The remote workflows must run on the new final source. No CI status is bypassed,
and no native, production authority, recovery or hardware qualification advances.
