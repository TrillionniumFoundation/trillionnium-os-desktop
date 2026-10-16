# A01 full raw boot-evidence binding

The old checker accepted a real boot log after harmless bytes were appended. The new recorder binds the entire actual serial logfile by SHA256, and the new checker rejects replacement, truncation or append mutations. New real QEMU records confirmed both acceptance of the matching successful run (raw 33) and rejection of the original known boot failure replay (raw 65). No old archive was backfilled with a new hash.

## Preserved before/after observations

Before edits, a temporary copy of the old checker accepted the existing daemon-phase raw serial both unchanged and with harmless tail bytes. `old-mutation-result.json` records exact source paths, commands, exits and byte hashes.

The parent then performed two new real QEMU runs using the new recorder. This subdirectory contains unchanged copies of those new qemu.json/serial.log records and one explicitly modified copy of the successful serial log. Original run directories were not changed.

| Case | Old checker | New checker |
| --- | --- | --- |
| Matching new successful QEMU record | accepted in all 4 modes | accepted in all 4 modes |
| Same record, harmless serial tail appended | incorrectly accepted in all 4 modes | rejected in all 4 modes |
| Matching real known-failure replay, raw 65 | not rerun | rejected in all 4 modes |
| Successful fresh record, live kernel/initrd/BIOS validation | unsupported | accepted in all 4 modes |

The four modes are ordinary Python, `-O`, `-I`, and `-I -O`. The 24 exact calls, exits and individual output logs are recorded in `real-new-mutation-result.json`. The actual parent source-run paths and original raw serial SHA256 values are in `fresh-record-provenance.json`. The mutation driver did not start a VM or create a new guest result.

## Interface

`record-qemu.py` selects the logfile belonging to the actual `-serial chardev:...` ID. For the fixed profile this is cwd-relative qemu.log. After QEMU exits or times out, it hashes the complete raw file bytes and records top-level serial_sha256, serial_size and serial_path. If that selected file is missing, it records serial_error without substituting a stale default logfile or supplying a hash. Input artifact hashes and sizes are calculated from the bytes read before invocation.

`python3 -I support/build/check-boot.py DIR` is archive mode: it reads only DIR/qemu.json and DIR/serial.log, requires matching full raw serial SHA256, valid metadata for kernel/initrd/BIOS, raw exit 33, explicit no-timeout, all original five completion markers, and no explicit fatal panic. It does not require old absolute artifact paths to remain present. The checker hashes bytes before decoding or stripping ANSI. There are no assert statements.

`python3 -I support/build/check-boot.py DIR --live-artifacts` additionally checks the actual recorded kernel/initrd/BIOS files against both size and SHA256. Relative paths are resolved against recorded QEMU cwd. This is intended for fresh runs before their inputs change. It is deliberately not the default for relocated archives. The existing five boot markers were retained; SYS_REBOOT was not made an additional logger-dependent requirement.

Older archives lacking serial_sha256 are rejected by the strict new checker. Their historical evidence is preserved and is not retrospectively relabelled as bound.

## Tests and coverage

The new 15-test host suite passed under both `python3 -I` and `python3 -I -O`. Every checker acceptance/rejection fixture is itself executed in all four modes. Coverage includes actual archived raw bytes, append/replacement/truncation, wrong/missing digest and fields, missing artifact records/hashes, changed live bytes for all three inputs, absent original paths in archive mode, non-33/timeout, all missing completion markers, seven fatal-panic forms, actual selected chardev recording, absent selected logfile despite a stale qemu.log, and timeout with complete serial data. Recorder child-process tests use disposable fake QEMU tools; they are host tests, not guest boot evidence.

The current 10 shell-runner compatibility tests also passed without modifying their source. Independent read-only review found no functional issue for the fixed profile. Syntax, diff whitespace and absence of assert statements were checked. No generic authenticity claim, full upstream matrix, HOS2 implementation or new hardware support is inferred from this evidence.

## Source and reproduction

The old checker is reconstructed from commit a3636414209c5b712fe4376af29fab2471a25374. `code-commits.json` records its exact digest and the measured new recorder/checker/test digests. The new code is published as `2c658089bb90aa5b254ddf336ef3dc1333e755c9`, tree `477484d2ba446d54024fcd0ea739dfb89035a12d`; Git object bytes for all three new source files were checked against the measured SHA256 values. No duplicate old/new production Python source is archived here.

```sh
python3 reproduce_mutation.py --repository /path/to/repository --output /path/to/new-scratch
```

The script obtains checker code with git show, verifies measured SHA256 values, and reproduces the 20 portable archive comparisons. Add --run-tests to reconstruct the other two measured source files and original raw fixture from Git, then rerun both 15-test commands. The four original live-path checks are retained observations and are not replayed by default because archived runs must not depend on this host's scratch paths.

From this directory, `sha256sum --check evidence.sha256` verifies all retained files.

## Published Git-object replay

The reproduction script was actually executed after publication. It rebuilt the old and new checkers using git show and verified their measured SHA256 values, then reproduced all 20 portable archive comparisons with exit 0. `git-source-replay-command.json` records the exact call, `git-source-replay-results.json` retains every output/exit, and `git-source-replay.log` retains the completion message. No live artifact paths or new VM were needed. The recorded source tree was independently checked, and all three new recorder/checker/test Git blobs match the earlier measured source hashes.

Both `SHA256SUMS` and `evidence.sha256` contain the same internal file manifest; neither includes itself or the other manifest. They cover only this boot-binding subdirectory.
