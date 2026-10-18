# A04 original rootfs input recovery

The exact Debian13 rootfs and all four manifest-pinned ELF files already exist in A01 history. Rebuilding them with a similar compiler is unnecessary. The tracked compressed artifact is `support/build/evidence/2026-10-16-review/linux-guest/rootfs.tar.gz` at A01 commit `cdf308e751e561328c556ca2ece86056d15809a0`, Git blob `fb8c5d5417c1c19cf107c18d8bb94512ba52388b`. This directory contains only the verification entry point and source metadata; it does not duplicate the 4.2 MB payload.

From this repository checkout, choose a new output directory whose parent already exists:

```bash
python3 -I support/build/handoffs/a04-exact-rootfs/verify.py --output /tmp/a04-original-inputs
cd /tmp/a04-original-inputs
sha256sum -c SHA256SUMS
```

`verify.py` reads the fixed artifact with `git show --no-ext-diff --no-textconv`, disables optional Git writes and lazy fetching, bounds the output, and verifies its exact size, Git blob and SHA256. If the old commit/blob is absent, fetch `agents/A01-asterinas-boot` from this project first; the verifier never fetches or resolves a moving branch. `--repo /absolute/checkout` selects an explicit repository when needed.

The verifier authenticates the copied A04 manifest by its original Git blob and SHA256, decompresses the original USTAR bytes, and checks every one of its 17 files against the original size, mode and SHA256. It reads archive members without extracting paths, rejects unlisted, duplicate or nonregular files, and verifies the four ELF hashes independently. It writes `rootfs.tar`, the four ELF files, `verification.json` and `SHA256SUMS`; ELF output copies have mode 0400 and are never executed. The original tar retains its original internal metadata.

Existing output paths are refused. Output ancestors must exist and cannot be symlinks. Writes remain relative to opened directory descriptors; each written payload is read back through the same FD and compared with its intended bytes between matching stat observations. Final directory/file identities are rechecked before the incomplete marker is removed. An interrupted/failed output can remain marked `.input-recovery-incomplete`; a successful result requires that marker to be absent and the checksum table to pass. These are point-in-time checks, not immutable storage: consumers must check the checksum table before use. The verifier does not remove or overwrite a partial directory: use a fresh name for a retry.

| Original input | SHA256 |
| --- | --- |
| Compressed rootfs | `9c81d284039c811e07d633840594d763b85f46f707dc19057db1af5e0729aa5c` |
| Original USTAR, 8,837,120 bytes | `df8df2e3cdcd308ef62a59268a4519e2923c9ff78145e46f26a4092725e80797` |
| A04 manifest, 8,135 bytes | `55aa8369d4f912267139ef7626c752814d7dc833e49accc337529f2545fb94cb` |
| probe_dynamic | `36a021aa7877170aedda535fff2a6ab2fc51cdb4b48d04c8c90ff873a40f4324` |
| probe_static | `edd3063a60c3f5c23679de3ab13e71955f7155be619f191468800931d101b078` |
| sqlite_dynamic | `d9c953e2dba4473ac1fad46446bc4768a448063547f32180813a868b3bdb7fc6` |
| sqlite_static | `2b8ca0007725bbf94856fc559572b1c86c163cca380cdbf6cce38faa69abefa2` |

A04 can supply the recovered original `rootfs.tar` and its unchanged manifest to its own guarded replay runner. This closes the missing-input handoff only. No new QEMU, Linux compatibility, HOS2, W1 or persistence success is claimed. Historical A01 guest failures remain in [the original report](../../evidence/2026-10-16-review/linux-guest/report.json); the rootfs supplied here is the same fixed input, not evidence those failures are repaired. A05/A06 retain ownership of their kernel changes.

For an independent optimized-Python check, run the same command with `python3 -I -O` and another unused output directory. The seven host custody fixtures include an actual same-UID writer changing equal-length bytes during fsync; the verifier must refuse that output and retain its incomplete marker:

```bash
python3 -I -m unittest discover -s support/build/handoffs/a04-exact-rootfs -p test_verify.py -v
python3 -I -O -m unittest discover -s support/build/handoffs/a04-exact-rootfs -p test_verify.py -v
```

Actual handoff validation and its exact source hashes are recorded in `validation.json` and `validation-*.log` when published. The failed pre-readback candidate and its independent red→green reproduction remain historical evidence, not accepted input verification.
