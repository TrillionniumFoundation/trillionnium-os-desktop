# F1 source-pair follow-up: live-readonly rejection

Source commit: `4af65c14516ac65c60f68738c6bec1b6147daff1`.
Source tree: `720738d394c17a2c6d84a36fdf86066b8fdcdafc`.
Parent: `0f0d9402fa7da409dfddfa7ce4041c08a04af5ac` from Desktop PR #259.

The fresh-build workflow previously checked out Desktop `7d8906ef9fbb5f3af4e6bb0843b79ac666394833`,
which precedes the live RDONLY transition rejection in `ce8378b71c426e6f5e0227b65624895cb81212cd`.
This three-file update moves the workflow pin, reviewed head/tree and current-profile documentation
together to `ce8378b71c426e6f5e0227b65624895cb81212cd` / tree
`8fe94570ea0ad5d63c44c6c02e5872fa532abcca`. Hepta remains
`b3d3f2d4b01f123d7ac17575c27fb54d00094f7f` / tree `b035a577969cb503d7c09620694a6b6c54178c97`.
All 84 earlier selected source identities remain exact; five added selections bind mount.rs and
the readonly/remount probes and runners. The separate retained archive profile is unchanged.

## Actual qualification

- The unchanged original 42 host tests pass, with zero failures and zero skips.
- Four synthetic host negative controls reject the previous source pair, the previous Desktop
  tree, the previous source-file list and an altered mount Git blob. The current synthetic input
  passes the same original parser. These are not executed kernel or Agentd inputs.
- The first 42-test attempt had one missing historical initramfs fixture error. Its complete
  output is retained as round 01. After supplying the original fixture, round 02 passes.
  The fixture's Git blob is `d96438b6a33186ab1d2c906f6cbc04710f962a74`, SHA-256
  `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3`, size 1,107,990 bytes.
  Its identity record is included; the already-published binary is not duplicated here.
- All workflow Bash steps and 12 Python source files pass syntax validation; three-file patch
  application and independent source review pass. Full remote readback covers all 8,160 leaves,
  including unchanged paths, modes and blobs.
- No new kernel build, guest execution, 57-case readonly run, 37-case remount run, F1 completion,
  production authority, native G2, reboot recovery or physical-device result is claimed.

`raw-evidence.tar.gz` preserves the fetched source/preimages, full fetched tree and comparison,
exact patch/publication entries, original host outputs including round 01, synthetic controls,
syntax scripts, source before/after hashes, independent review and remote source readback.
`manifest.json` enumerates every included byte sequence and its SHA-256/Git blob. No compiler
cache, compiled executable, dependency cache or relabelled old kernel is bundled.
