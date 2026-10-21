# Integration input snapshots: host validation

Status: `host_validated_pending_publish_and_real_full22`. The actual full suite exited 0 in tool session 32695: 150 tests passed in each of `-I` and `-I -O`, with identical source hashes before and after. This package does not claim a real kernel or VM pass.

The new nine host CLI tests per mode exercise exclusive read-only snapshots, source overwrite after capture, optional initrd, persistent earlier-guest bytes, pre/post snapshot tampering, invalid inputs and strict EM62 symbol-copy binding through a fake capture process. The exact d895dd old recorder fails the retained source-overwrite regression because the fake QEMU reads the overwritten kernel. Existing GDB lifecycle tests use a real host GDB TCP lease, not a project kernel.

The recorder's 14 existing helper functions are byte-identical to the exact old source; only its existing `main` changes, with five added snapshot helpers. The ordinary recorder and coverage acceptance checker are unchanged. Sources and hashes are in `source/` and `source-validation-ready.json`. The candidate depends on published case-target isolation commit fb508445fe63efdfdd596dc58e42c621b1fd3752.

`raw-evidence.tar.gz` retains every regular raw payload from the full-suite and separate red/green fixture directories. Its ordered members, sizes and hashes were read back and verified. Nonregular entries such as intentional FIFO negatives and cache symlinks are described in `raw-members.json`; no link is followed and no special file is embedded as an extractable tar member. No archive extraction is required for verification.

The earlier 20/22 real matrix and its original 7 guest records are unchanged. Its case14 full boot bytes were replaced by a later same-name example, so only six old kernel paths still matched their recorded inputs. This candidate preserves future actual inputs; it does not recover those missing historical bytes. The abandoned observer draft was never executed. A separate post-publication full22 phase must establish the real acceptance result.
