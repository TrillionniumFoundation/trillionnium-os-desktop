# R36 storage owner source compatibility

The frozen r8 storage capsule recognizes an R34 owner-acquisition v1 record.
The independently acquired R36 owner uses v2, with a fixed UTC window,
native-envelope budgets and the complete archived v1 record. This packet
validates that exact v2 declaration and adds a read-only consumer for the
three original root-owned R36 CAS publication records.

The publication chain is now understood. Complete owner-acquisition
acceptance still lacks original-lock custody and source/plan review evidence.
`owner_acquisition.root_acceptance` remains null, and both the sealer and the
storage admission path reject the candidate before any storage action. No
JSON flag or shape-valid ROOT object can override that missing evidence.

## Source layout

`baseline-r8` contains the original 29 source members and their original
manifest, whose SHA256 is
`91772330fc4f500a6ed0961bf3b0ab5efcab3381a35de647c4470f0919f8fa11`.
`postimages` contains four changed original members (`admit.py`,
`contract.json`, `prepare.py`, `rotation_support.py`) and the candidate
manifest. The sole `owner_acquisition_v2.py` at the packet root supplies the
new source member and the test/generator imports. The 25 unchanged members
are stored once.

The complete candidate manifest SHA256 is
`f3ad987024396fe19d33a51be57af57d1b2c6e3b7d97c4e249a49d422f5592fc`.
The candidate generation is `e6ac-storage-r8-r36-v2-r2`; its contract is
61,693 bytes. The strict 65,536-byte source-member and 262,143-byte archive
limits remain unchanged. Generation names and nonces are public identity
bindings used with exact source and admission hashes. They are not credentials
or independent execution permission. The old r8 and earlier R36 candidate
nonces remain frozen and cannot identify this generation.

## Publication proof and remaining acceptance

The acquisition CURRENT reference came from a complete original no-follow
read, SHA256 verification and matching file-descriptor/path F9 bookends.
Its exact nine native integers are retained. This captured acquisition
reference is distinct from a later live CURRENT that might adopt a newly
reviewed source binding.

The following original event references were independently read from
`/home/alex/work/p4-current-r36-owner-commit-e6ac-r6`. Their root-owned,
mode-0400, single-link identities and raw bytes establish the predecessor,
protected temporary inode, held-directory rename boundary and published
CURRENT linkage.

| Original record | Bytes | SHA256 |
| --- | ---: | --- |
| `INTENT.json` | 1,585 | `1adffc8dcd6e97fe70c68e7bcef427a91a9e0ecda0baa4b7dd60a7cc0c53773c` |
| `REPLACE-BOUNDARY.json` | 925 | `016fc43be5b2fc6c1e1e72a8601151877d2beae523b816c01ecfecdb3beae7c1` |
| `RESULT.json` | 464 | `442c93097e69c4510a2788f5958bcee80330ee17be9ed61e9d50bae20dfa6090` |

The packet contains their metadata pins and the prior verification result,
not the operation-record bodies. The source and plan hashes mentioned in
the intent are references only; their contents and the original lock held
by the CAS operation have not been verified. Draft, diff, source, plan and
retirement references inside the records are never followed by the reader.

`admit.py` uses the existing no-follow pin function to read only these three
fixed originals. It requires complete raw-byte hashes, full F9 identities,
two matching read passes and unchanged original-directory bookends. It then
applies the original-lock/source-review gate before image, allocation-lock,
resource, rotation or admission operations. `prepare.py` applies the same
gate before its first target or proof write. Publication alone cannot
satisfy `rotation_schedule()` or `storage_binding()`.

The fixed owner window remains
`2026-11-18T01:53:12.988458+00:00` through
`2026-11-20T01:53:12.988458+00:00`. Filesystem event timestamps are publication
metadata, not a new commit clock or a lease extension. The original
140,700-second schedule, 145,200-second native budget and all resource,
retirement, live-CURRENT and phase-admission requirements remain unchanged.
No owner handoff, retirement proof, new storage admission, Full-B admission,
Android start or production result is granted by this packet. Full-B still
requires its own new source binding, complete second-pass verification and
independent admission.

## Ordinary CI

`run_ci.py` verifies an externally pinned `FILES.json`, reconstructs all 30
candidate source members in a new temporary directory, and executes all
35 ordinary source regressions. These retain the original 23 cases and add
12 publication/consumer cases: raw-byte and native-integer checks, exact
event/inode links, metadata chronology, directory and file bookends, false
ROOT substitutions, and the actual admission gate before storage effects.
Publication parser fixtures in CI are explicitly synthetic. CI does not
replay the private operation records or revalidate their live originals.

```sh
python3 -I -B run_ci.py \
  --inventory-sha256 "$REVIEWED_PACKET_SHA256" \
  --out "$SOURCE_TEST_REPORT"
```

The wrapper explicitly loads only the verified local modules under Python
isolated mode and removes the temporary candidate on completion. It never
executes a storage entry point or accesses a device, CURRENT, original CAS
directory, host lock or image. Its result reports source checks only;
original-lock, source-review, owner-acquisition and runtime admission fields
remain false. `prepare_candidate.py` is a local create-only builder that
validates separately supplied original-byte observations for review. CI
never invokes that builder or any operational entry point.
