# R36 storage owner source compatibility

The frozen r8 storage capsule recognizes an R34 owner-acquisition v1 record.
The independently acquired R36 owner uses v2, with `window_started_at_utc`,
`window_seconds`, native-envelope budgets, and the complete archived v1
record. The original admission and dispatch paths therefore reject that
record before a new storage operation can be admitted.

This packet provides a separate source generation that validates the exact
observed v2 record. It retains the fixed owner, acquisition ID, UTC endpoint,
archived history, original resource thresholds, and 140,700-second schedule.
Old-v1 or mixed acquisitions, extended deadlines, altered budgets, lossy F9
integers, reused r8 nonces and old/retirement ROOT substitutions are rejected.
The sealer applies the owner check before its first target write.

## Source layout

`baseline-r8` contains the original 29 source members and their original
manifest, whose SHA256 is
`91772330fc4f500a6ed0961bf3b0ab5efcab3381a35de647c4470f0919f8fa11`.
`postimages` holds the three changed original members (`contract.json`,
`prepare.py`, `rotation_support.py`) and the candidate manifest. The sole
`owner_acquisition_v2.py` at the packet root supplies the new source member
and the test/generator imports. The 26 unchanged members are stored once.

The complete candidate manifest SHA256 is
`cb129e2de653765fb4e67cc1a1e856336de506d030b80540ba943ea16937ee7f`.
The candidate contract is 60,011 bytes and retains the strict 65,536-byte
source-member and 262,143-byte archive limits. Generation names and nonces
are identity bindings, used together with exact source and admission hashes;
they are not credentials or independent execution permission.

## One actual input remains unresolved

The acquisition CURRENT reference was obtained by a complete original
no-follow read with SHA256 verification and matching file-descriptor/path F9
bookends. Its exact nine native integers are preserved in the candidate.
This is a captured acquisition reference, separate from any later live
CURRENT containing a new adopted source binding.

`owner_acquisition.root_acceptance` remains null. An actual R36 owner/CAS ROOT
acceptance has not been supplied. Old R34/R35 owner evidence and the distinct
declared retirement metadata do not fill that slot. `prepare.py`,
`rotation_schedule()` and `storage_binding()` continue to reject the actual
candidate. `CANDIDATE-STATUS.json` therefore records no new storage admission,
Full-B admission, Android start or production result.

Adoption requires the actual R36 owner/CAS ROOT reference, a newly reviewed
source manifest and exact binding, then the original owner/lock/current,
image, retirement, resource and phase-budget checks. The fixed owner expiry
remains `2026-11-20T01:53:12.988458+00:00`. Full-B still requires its own new
source binding, complete second-pass verification and independent admission.

## Ordinary CI

`run_ci.py` verifies an externally pinned `FILES.json`, reconstructs the
complete candidate in a new temporary directory, and executes all 23 frozen
source regressions. It explicitly loads the verified local modules under
Python isolated mode. The temporary candidate is removed on completion.
It does not execute a storage entry point or access a device, owner, ROOT,
CURRENT, host lock or image.

```sh
python3 -I -B run_ci.py \
  --inventory-sha256 "$REVIEWED_PACKET_SHA256" \
  --out "$SOURCE_TEST_REPORT"
```

The CI result reports ordinary source replay and tests only. Device evidence
is not revalidated, the owner/CAS ROOT remains unverified, and all storage,
Full-B and production admission fields remain false. `prepare_candidate.py`
is a local create-only source builder for separate review; CI never invokes
its command-line builder or any operational entry point.
