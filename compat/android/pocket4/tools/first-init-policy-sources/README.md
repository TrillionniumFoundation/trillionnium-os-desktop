# Original CP3A platform policy source reader

This Rust tool reads the pinned public CP3A system image and extracts the platform policy, contexts, compatibility mappings and init inputs required by Pocket4's Linux Android work.

The GSI init file is at `/system/system_ext/etc/init/init.gsi.rc` in this image. The earlier `/system/etc/init/init.gsi.rc` lookup returned an empty member. The fixed table uses the actual system_ext location.

The reader also collects the three original compatibility mappings for vendor policy version `202604`. The platform mapping contains CIL forms. The system_ext and product mappings in this exact image each contain one newline; the reader preserves those original bytes. Only those two fixed mapping roles allow that representation. Empty, missing or whitespace-only policy inputs still cannot qualify as CIL policy.

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

The output directory must not already exist. The tool records every fixed member and reader exit, including explicit missing or empty members. The v2 source receipt identifies the mapping version; the final vendor producer must independently prove that its actual policy version matches.

## Verification

The ordinary Linux release build, two existing CIL format tests and a regression test for original blank mappings passed on Pocket4 on 2026-11-13. Actual extraction from the pinned image produced all 22 nonempty members. The hashes of the previous 19 members were unchanged, including the corrected 132-byte GSI init script.

The original platform mapping is 234191 bytes with SHA-256 `34f9db1571f43aab25ee785130fb2a080c99a49bd87a8a8a4f5c574969b5365e`. It has 4347 structurally balanced top-level CIL forms. The system_ext and product mappings each preserve their original one-byte newline, with SHA-256 `01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b`. All three sizes match the independently retained original image directory entries.

The verification used two CPUs, a 4 GiB memory ceiling and zero swap. Its unit exited successfully and its cgroup was removed. [verification.json](verification.json) preserves the measured commands and result; [verification-retirement.json](verification-retirement.json) records retirement.

These are source extraction results. The tool does not compile or load SELinux policy, execute Android init, issue ExecutionAdmission, or grant runtime or production qualification. A real normal vendor policy, matching policy version, VINTF/product receipts, policy compilation and enforcing runtime validation remain required.
