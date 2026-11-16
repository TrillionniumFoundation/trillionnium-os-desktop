# Native601 original dexdeps and pyee provider correction

## Result and scope

This source-only candidate restores two pinned upstream providers omitted from the strict Native600 source plan. The fixed plan contains **601 AOSP projects and 8 root links**. Its 31 focused ordinary Rust tests pass, both normal tools build, and the normal `droidloom-source verify-lock` command succeeds.

Source materialization, a new complete Android build, Android startup, and app runtime acceptance remain separate gates. This package does not grant production readiness.

## Fixed source identity

- Baseline commit: `68a334c93b4b42846cd2fe2ef23e46c7021149c0`.
- Baseline tree: `4903434ccc65abcf26b569e155e643e538338b51`.
- Candidate commit: `579f8374655159869898c0c71203ba7e8a3146de`.
- Candidate tree: `2aaa2d2dbd44063cd4aa1366ddf847b24a6bca77`.
- Candidate workspace: `ai395:/home/qq/work/pocket4-native601-dexdeps-pyee-buildclosure-20261109-r1/source`.
- Working tree was clean after the ordinary source commit.

The patch modifies exactly two tracked files:

| File | Before SHA-256 | After SHA-256 |
| --- | --- | --- |
| `android/native-generation-pair/source-lock.json` | `86a215da1fed2945feccebe7878b95fe507114de6e3b8ee0fa673e830d9a7aba` | `55316606071a02ff5cb4d2f3985edb048d1861e5c15aa7d901d542e69f8e9dd9` |
| `tools/droidloom-update/src/native_generation_pair_build.rs` | `30a67139ba814589bf2c671ecaf00d6314dac80b3d7ce9abf5969df41a0e4ace` | `a5f88ee8ae9d5ae0eacf3f76a3fdb707c4a31377dab09f01395aa1c3adfb18fa` |

The new lock is 354,815 bytes. The format patch is 16,502 bytes, SHA-256 `582e81f0dca666a4c4410f3e10dc05ab8ef4a3762cee243c201ae42ed8fc7b27`.

## Why these inputs are required

The actual owner `full-ai395-r10` failed during Soong graph generation. Two retained example APEX modules lacked `dexdeps`; the retained `bumble` module lacked `pyee`. The original APEX dependency is introduced by Soong's Java API usage rule, so the consumer APEX Blueprint need not contain the literal string `dexdeps`.

The correction adds the complete `dalvik/tools/dexdeps` cone at the unchanged dalvik commit `5013071e756f89aa2cea97b437af12aacb8d4485`. It contains the original Blueprint, wrapper, manifest, README and eight Java source files. Existing dx selectors and root license metadata remain selected.

The new `platform/external/python/pyee` project is fixed to the superproject gitlink `d67e4b09ff002069a025bfb232836eecab6dab52`, selecting `Android.bp`, `LICENSE` and the complete `pyee` package. Its sole named Blueprint library dependency, `typing_extensions`, already remains selected as the entire original project at `8430d542d65e5607ece1e810e247b982384b32f9`.

All 600 existing project revisions, the other 599 project entries, root links, superproject, policy fields, two build targets and strict dependency mode remain unchanged. The exact lock length/hash, embedded expected additions and 601-project guard are synchronized. Original provider blobs and immutable revisions are recorded in `provider-provenance.json`; no provider implementation or Blueprint is synthesized.

## Actual ordinary validation

| Gate | Actual result | Durable H job |
| --- | --- | --- |
| Focused Rust tests, locked/offline, 2 Cargo jobs | 31 passed, 0 failed, 0 ignored; 222 filtered; 6.28 s | `1a1c028da7b-5e21-936` |
| Normal tool build | Successful dev build, 0.23 s | `1a1c02a6cb1-5e21-93b` |
| Normal verify-lock | 601 exact AOSP projects, 8 root links, superproject `28f0bbddc24d56c8ec5a8df5342ac7a292184039` | `1a1c02a6cb1-5e21-93b` |
| Source commit | Exit 0; clean working tree | `1a1c02d42be-5e21-945` |

These jobs have successful authoritative terminal states and complete durable output. `qualification.json` records exact command arguments, environment, binary hashes, log hashes and receipt references. Tools and tests ran as ordinary UID 1000 with a candidate-owned target and TMPDIR, incremental compilation disabled, and the candidate restricted to CPUs 0 and 1 after a resource check.

The new regressions reconstruct the exact failed r10 lock and independently reject each missing, altered or unreviewed provider selection. Earlier r3/r5/r6/r7/r8 byte reconstructions remain exact. BCC, signature-common and RKPD partial-provider controls retain every other current provider, preventing unrelated omissions from masking their checks.

The independent review reports no blocking finding within this source scope. Its reviewed 15,703-byte plain diff and this 16,502-byte format patch have identical source preimages and postimages; the latter adds commit and Git patch metadata.

## Owner coordination and remaining gates

At 11:57:25 UTC, the recorded ai395 owner root still contained the 600-project `recipe-bcc-r1` at `47a625a3435fccf466982c8b043c1f8ea72d4891`, with latest matching full generation r10. The observed shared source manifest matched the earlier independent audit. The desktop `native-pyee-original-provider-review-r1` receipt records upstream verification only, with zero source changes and zero builds started. These observations cover their explicitly recorded paths.

The current owner must review and integrate this candidate into its recipe, run the normal source materializer for the exact new lock, and launch a fresh strict full generation under its existing ownership and resource controls. The failed r10 receipt remains failed. This candidate has not changed the shared source, CURRENT, original lock inodes, or namespace/private-control state.

One earlier unrelated read-only request lacked a recovered durable identity; it was not replayed or credited as successful. The fixed-source snapshot and every validation reported here have separate recorded identities.

## Package contents

`FILES.json` locks the exact five peer files: this README, the format patch, qualification, original provider provenance, and independent source review. No APK, Android image, executable, Cargo output, cache, or large build log is included.
