# Original CP3A platform policy source reader

This Rust tool reads the pinned public CP3A system image and extracts the platform policy, context, mapping-directory and init inputs required by Pocket4's Linux Android work.

The GSI init file is at `/system/system_ext/etc/init/init.gsi.rc` in this image. The earlier `/system/etc/init/init.gsi.rc` lookup returned an empty member. The fixed table uses the actual system_ext location.

## Inputs and execution

The input directory must contain the original, single-link `system.img` and executable `debugfs`. The tool opens path components without following symlinks, retains the descriptors, verifies their identities and SHA-256 digests, and rechecks the inputs after extraction. Run it as the ordinary Pocket4 user (UID 1000) inside an owned unit with a deadline and resource limits.

| Input | Bytes | SHA-256 |
| --- | ---: | --- |
| system.img | 2294853632 | dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4 |
| debugfs | 231368 | 864e1d7b445e7b5bfc831da78330dbcafc590fa82b89ea9de60b7527f989954f |

From this directory, with the locked dependencies available:

```sh
cargo build --release --locked --offline -j 2
cargo test --release --locked --offline -j 2 --lib -- --test-threads=1
systemd-run --user --wait --collect --pipe \
  --property=MemoryMax=4G --property=MemorySwapMax=0 \
  --property=CPUQuota=200% --property=TasksMax=128 \
  --property=RuntimeMaxSec=180 --property=NoNewPrivileges=yes \
  --property=KillMode=control-group \
  "$PWD/target/release/droidloom-first-init-policy-sources" \
  --inspect-original-platform-policy \
  /absolute/path/to/public-source-copies /absolute/path/to/new-output
```

The output directory must not already exist. The tool records every fixed member and reader exit, including explicit missing or empty members.

## Verification

The ordinary Linux release build and the two existing CIL format tests passed on Pocket4 on 2026-11-13. Actual extraction from the pinned image produced all 19 nonempty members. The corrected GSI init script was 132 bytes with SHA-256 `fb08d2d291cdb989ca023fea1edd342afbc0cb6ffbeb4c40aa49ffc5344478c3`, matching an independent read from the image. The other 18 member hashes matched the previous extraction.

The verification used two CPUs, a 4 GiB memory ceiling and zero swap. Its unit exited successfully and its cgroup was removed. [verification.json](verification.json) preserves the measured commands and result.

These are source extraction results. The tool does not compile or load SELinux policy, execute Android init, issue ExecutionAdmission, or grant runtime or production qualification. A real normal vendor policy, VINTF/product receipts, policy compilation and enforcing runtime validation remain required.
