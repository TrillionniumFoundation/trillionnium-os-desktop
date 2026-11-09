# Audio430: restore original system-server API provider inputs

The actual Audio `full-desktop-r10-r2` stopped on two undefined generated
`service-ondeviceintelligence*.api.combined.system-server.latest` providers.
The original API36 input files were missing from the sparse SDK selection.
The fixed SDK's normal `prebuilt_apis` declaration and Soong generator require
both the current and removed system-server API files to create those providers.

This patch selects the two exact original paths at the unchanged SDK commit
`0f07e8d60ab0aba46129e427101f96ba459a95c1`. Both files are upstream 25-byte
signature headers with Git blob `d802177e249b3f97128699222e65c35e57ba7540`.
They are not invented replacement API stubs. The SDK declaration, generator,
consumer and API bytes are verified before build projection. Strict dependency
handling, all 430 project revisions and eight root links remain unchanged.

Apply `fix.patch` only to source base
`a0e5114a1728e5ac5a96cdffbf68a84958218765`. The qualified candidate is
`0342210a3bd82bf46067a1dbaf740e16f291a38a`; `preimage.json` binds every
changed source file before and after the patch.

## Validation actually performed

- All 11 source and 52 update Audio tests passed with the repository-pinned Rust
  toolchain and one compilation job. Historical 425/430 lock identities remain
  exact; missing API inputs, source drift, altered revisions and symlinks fail.
- Both normal source/update development tools built successfully.
- The new normal source binary's `verify-lock` reported 430 exact AOSP projects
  and eight root links at superproject
  `28f0bbddc24d56c8ec5a8df5342ac7a292184039`, exit zero.

The patch changes three existing recipe/lock files (230 additions and seven
deletions). Six new fixture/provenance files preserve complete original inputs;
there was no formatting sweep. `qualification.json` contains the bound actual
results, including the separate verify-lock follow-up. Its state fields describe
the source qualification when recorded, before this publication.

The old full build remains a preserved failure. Its source projection was
restored and its owned process/unit retired. The active coordinator must admit
this candidate through normal source reconciliation and materialized-source
verification, then use a fresh full-build generation with the original lock
inodes and resource limits. The old r10-r2 job must not be restarted.

No shared source or coordinator state was mutated by the independent candidate.
No full Audio APEX build, Android boot or application runtime pass is claimed.
Production readiness remains false. CI verifies this publication's exact file
inventory; it does not convert source qualification into runtime acceptance.
