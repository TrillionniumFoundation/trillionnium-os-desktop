# Actual same-plan AOSP source restoration

The normal source tool restored 26,047 missing members (13,818,632,037 logical bytes) on ai395 on 2026-11-19. The actual R2 worker reconciled and verified the original 651-project lock once each. Its 9,131 original child commands exited successfully and were reaped; an independent observer checked the terminal, exact service/cgroup retirement, original three locks, and all restored live file identities.

R1 remains a real failed attempt: three nominally full projects still had older sparse exclusions. It performed no reconcile and receives no restoration credit. R2 preserved that failure and used the existing normal source tool to disable those exclusions, in addition to restoring the four missing clang/Rust prefixes. No source-tool mutation or reduced admission gate was needed.

The original manifest content stayed identical. Normal reconciliation replaced its inode; the old and new full identities remain in the actual records. The original 2,336-file canonical producer snapshot stayed identical.

## Evidence replay

Run `python3 -I -B compat/android/pocket4/vendor-same-plan-source-restoration-20261119/source_replay.py` from the repository root. This checks the whole original compressed R1/R2 receipts, recorded child lifecycle, both real normal command streams, exact worker source, resource boundaries, and independent retirement. The operational worker files are preserved as evidence and are never imported or executed by this command.

The 26,047 restored source bodies and their complete per-body inventory remain in the original operational workspace. This packet verifies their recorded producer and independent observer bindings; CI does not rehash those live bodies, rerun reconciliation, or claim all 651 source trees had identical complete bodies before and after. The actual repair changed the missing source payloads.

Vendor compilation, device activation, Android runtime tests and app business acceptance remain separate gates. All runtime and production flags remain false. The R14 vendor admission failure and its successor have separate records and receive no success from this source repair.
