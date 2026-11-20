# Pocket4 CP3A bootstrap and source selector integration

The published CP3A postimages were not consumed by the existing source bootstrap preparations. The canonical source selector still selected the old system identities and IHG 5.110.0. This packet records the source preparation repair and the exact source-pointer integration performed on Pocket4 on 2026-11-20.

## Result and scope

- Materialized the complete 224-file source closure from the pinned original files, overlaying exactly the 24 postimages already published in `system-cp3a-provider-rebind-20261120` at commit `1af163b21f5c7dcaaf94084d7cc1ef19aed05ae1`.
- Passed six unchanged `inspect-source` CLIs and the unchanged IHG `bootstrap` function. IHG has no `inspect-source` CLI; its runtime `main` was not called.
- Rebound the Camera display wrapper through only `PHOTO_PREPARED`, `PREPARATION_REF`, and `SOURCES`. All other AST is unchanged, and all 20 actual Supervisor methods are byte-identical. The historical metadata's count of 16 was inaccurate.
- Selected all eight new preparations through the existing 13-entry selector. Indices 0 through 7 changed; Gallery indices 8 through 12 and all other applications remained unchanged. The full 42-package route map now points its ten affected leaf occurrences to those eight preparations.
- Committed exactly five canonical source metadata keys under the original two lock inodes, a fresh whole-CURRENT SHA/F9 comparison, a live-writer check, and an unchanged owner window. The complete compact JSON was read back, then independently verified in another process.

**These are source results.** Android actions and APK installs were zero. Runtime accepted remains zero, `runtime_qualified=false`, and `production_ready=false`. No runtime authorization, owner deadline, userdata, VM, AOSP build input, or runtime binary was changed.

## Files

| File | Purpose |
| --- | --- |
| `reconstruct_inputs.mjs` | Recreates the exact reviewed input packet from existing Git blobs, without copying the 224-source closure into this packet. |
| `prepare_bootstrap.py` | Checks all original input pins, creates seven source preparations, and runs the existing bootstrap inspection paths and six refusal controls. |
| `prepare_camera_display.py` | Rebinds the three display-wrapper constants, proves all other AST/method bytes unchanged, and performs one inspection plus three refusal controls. |
| `prepare_source_selection.py` | Checks the full 13-entry selector, current 39+3 package scope, nine source profile occurrences, six complete current APK identities, and builds the source-only selector/route-map transition. |
| `commit_source_selection.py` | Finalizes the exact recorded plan and implements the original-lock, whole-CURRENT CAS for this fixed generation. It preserves every unrelated JSON value and all runtime flags. |
| `evidence/verification-summary.json` | Small source-only verification summary and references to full host evidence. |
| `evidence/canonical-source-commit.json` | Original exact commit result; includes no CURRENT document body. |
| `evidence/independent-readback.json` | Original independent process readback result. |
| `evidence/input-reconstruction.json` | Exact reconstruction and four malformed-input refusal results. |

## Reproduction boundary

These scripts retain the exact inputs, paths, and preimage of one audited generation. They are create-only, and the canonical commit intentionally refuses a different CURRENT or a repeated commit. They are not a command to activate Android or a general installer.

With the pinned commit available in a repository checkout, reconstruct the input bytes using:

```sh
node reconstruct_inputs.mjs /path/to/trillionnium-os-desktop /absolute/new/reviewed-inputs.json
```

The output must be exactly 454,653 bytes with SHA256 `c38a0ef25c51497f2056169ca130d3ff6e13fa710d3159444604341af33c4b25`. JavaScript JSON serialization is retained to reproduce the recorded representation of historical numeric metadata. Every original source file is independently checked by exact bytes/SHA and stable file metadata; historical rounded JSON inode timestamps are not used as a substitute for fresh metadata.

The fixed Pocket4 task root is `/home/alex/work/p4-cp3a-bootstrap-20261120-runtimeaudit-r1`. The source preparation commands for that original generation were:

```sh
sudo -n /usr/bin/python3 -I -B prepare_bootstrap.py prepare
sudo -n /usr/bin/python3 -I -B prepare_bootstrap.py verify --expect-manifest-sha256 0f6d48ca590a9e0f7951f383361bcaeafced5dbd4e7f2ac9e74b5efbbc061baf
sudo -n /usr/bin/python3 -I -B prepare_camera_display.py
```

The ordinary selector preparation then produced a complete reviewed draft. Its final payload bookend initially used the source reader's default 16 MiB limit for the 47,680,737-byte IHG APK and refused before any canonical write. The corrected source preparer uses the same 128 MiB APK bound as initial hashing. The separate finalizer re-read every exact SHA/F9 using that bounded APK reader, completed the pinned plan, and the commit succeeded. No runtime reader or admission condition was changed to accommodate this correction.

## Validation

Eight original source inspection paths passed. Nine bootstrap/display refusal controls rejected invalid pins, duplicate common source, wrong schema, an attempted publication runtime flag, repeated candidate creation, invalid Camera preparation metadata, and a live input passed to inspection. Two current identity controls rejected a wrong version and an incomplete APK set. Three CAS controls rejected a stale CURRENT SHA, an unrelated change, and attempted runtime enablement.

The source selector validation checked all 13 preparation and primary-entry pins. Nine actual profile occurrences matched the source custody records and six freshly rehashed complete current APKs. The package set remains exactly 39 required plus TextNow, TextFree, and Uber Rider as the existing three exceptions. All original business gate definitions remain unchanged.

Canonical CURRENT changed from `b29be8cb340b4744c73df67046be421faf33ad00ea04bff84c4516e6def1d3bc` to `69e836deed4aeebd1377a67b3e24413aaa281e076f02ad89448fab40af5f6c3a`. Its 1,582,648-byte compact representation remains within the original 2 MiB reader bound. The commit result and independent readback are included verbatim; the 1.58 MiB CURRENT body, original source closure, APKs, GSI, and userdata are not included.

## Remaining runtime requirements

Original apexd still needs a genuine preconfiguration block-device OFD and its provider association. Real BLKRASET/sysfs, dm-verity/EIO, AVB, original APEX activation, coherent full-GSI/current-Main custody, and original application business cases remain required. Calendar historical receipts were not relabeled. Six old modified-Gallery entry guards remain retired in the reviewed source closure; this packet does not introduce a current official Gallery consumer or remove its runtime hold.

## Required-39 resume scope correction

A later, separate metadata correction removed one obsolete instruction to obtain the three explicitly exempt unavailable APKs. `correct_required_scope.py` changes only `/resume_order/3`, from the existing source-selector CURRENT preimage to the authorized 39 required contracts plus TextNow, TextFree, and Uber Rider as the three exceptions. It preserves the inventory count of 42, all source pointers, the owner and expiry, original lock inodes, and every runtime flag.

The exact original-lock whole-document CAS and independent readback produced CURRENT SHA256 `091f53bb8ad9623c9825c5e94a91e7226157ba90205fa1bddf06eb362aa0875b` (1,582,705 bytes). `scope_independent_readback.py` restores just the old sentence in memory and requires the resulting complete JSON to equal the preimage. The two small verbatim result records are `evidence/required39-scope-commit.json` and `evidence/required39-scope-independent-readback.json`. This change grants no Android or application runtime credit.
