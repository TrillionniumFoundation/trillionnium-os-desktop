# Selected CP3A public CI source-binding audit

## Result and scope

**No authenticated full source-revision binding was obtained for CP3A.260905.010 / 16176746.** This is an access/evidence limitation, not a finding that its manifest, repo.prop, target_files, or source revisions do not exist.

The audit used unauthenticated, bounded HTTPS GETs against official Android CI, official Google Build API services, and Android Gitiles between 18:03 and 18:09 UTC on 2026-11-09. It did not use or seek credentials, open a login flow, change a gate, replace a release with a floating branch, or perform a build. Following the v4 caller-identity denial, the rejected interfaces were not replayed.

The selected image identity remains the previously qualified official GSI: raw system.img 2,294,853,632 bytes, SHA256 dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4. This audit does not add source provenance to that image. The separate qpr1-coherence capsule and its existing stock ART/ELF observations remain unchanged.

## Actual observations

| Probe | Observed result | What it proves |
|---|---|---|
| ci.android.com/builds/submitted/16176746 | HTTP 404 HTML | This root-shaped URL was not served; it does not identify or exclude build targets. |
| Exact build with candidate aosp_x86_64-user target page | HTTP 200, only the artifact-page HTML/JS shell; authed=false and blank branchName | The UI route exists. It is not an artifact inventory or evidence that the candidate target is correct. |
| Official v3 discovery | HTTP 200; revision 20261029; exact buildId and pinnedManifest fields documented | The precise legacy query format was read from the service, not inferred from a floating build. |
| v3 build.list with buildId=16176746, buildType=submitted, pinnedManifest; candidate target get | HTTP 403 with legacy-API migration/rateLimitExceeded response | The legacy calls did not return build metadata. This is not a source-artifact absence result. |
| Legacy v3 candidate artifact list and manifest URL | HTTP 404 | These deprecated endpoints did not serve the requests. No artifact existence conclusion follows. |
| Official fetch_artifact fixed commit 0b93639b08957306f07abaeded736986b073286c | Physical Gitiles source read and Git blob SHA1 computed | The current client uses androidbuild-pa.googleapis.com/v4. It also supports an unauthenticated client; no credential path was executed here. |
| Current v4 candidate target metadata, artifact list, manifest_16176746.xml, repo.prop | All HTTP 403 PERMISSION_DENIED requiring API consumer identity | An anonymous caller could not obtain this metadata. The response occurs at caller admission, so it cannot establish whether this build/target/artifact exists. |
| Public manifest heads and tags | Complete bounded HTTP bodies read: 3,597 heads and 3,061 tags; matching names extracted | The named Android 17 / CP3A filter did not yield an exact CP3A source binding. This is not a search of private or unadvertised revisions. |

The **aosp_x86_64-user CI target is explicitly a candidate**, based on the GSI architecture/name. No successful CI metadata authenticated that target. The artifact-list denial prevented enumerating a correct target_files filename, so no guessed target_files archive was downloaded or treated as an origin.

An initial all-refs response exceeded the 4 MiB read limit. Its hash covers only the bytes read and it is explicitly marked truncated. No negative conclusion uses that response. Separate heads/tags responses were complete; their SHA256/byte counts and derived filter results are in the raw process stdout. Their full HTTP bodies were not retained locally. The filter was literal android17, android-17., or CP3A; it is not a claim to enumerate every security-tag naming convention.

The public matching refs included android17-release at 29ace668ae756c7b8917c57abb440f6518844b0c, android17-security-release at 6b08b798c827300cd65a1623c6f8dc776886f887, and android-17.0.0_r1 peeled to 5bc9a7ce1cd78dd53613bbfd0ebf506e1e4adb0f. No one of these was promoted to the selected CP3A cohort.

## Source and process evidence

The fixed official reference client is stored under reference/ with its Apache header intact; it is evidence, not a new tool or an executed entry point.

- Source bytes: 8,615
- SHA256: c208576dc465521e71ff39f458a8f7b4768e95c167de4b5021b9ed5acb1a4c47
- Git blob SHA1: 789bb1fa13243784ee1567b853f0f123850fffb3

Six read-only H jobs were independently reconciled to succeeded / exit 0 / output_complete / output_durable. Process success means the observation was captured; the HTTP permission failures and qualification gates remain failures/pending.

| Job | Evidence |
|---|---|
| 1a1c17a5b8b-e62c-ac | CI HTML and legacy discovery |
| 1a1c17b474d-e62c-ae | Legacy GET schema extraction |
| 1a1c17d5e22-e62c-b0 | Exact legacy build query and rejected/truncated probes |
| 1a1c17e50b0-e62c-b2 | Complete public heads/tags and obsolete-host v4 discovery |
| 1a1c17f084b-e62c-b5 | Current-service discovery failure and fixed official client source |
| 1a1c1800aac-e62c-b8 | Current v4 candidate artifact caller-admission failures |

JSONL files preserve the complete process stdout, including HTTP response bodies when small, exact request URLs, bounds, body hashes, and declared derived/truncated observations. Terminal JSON files preserve the original H result text. No signed download URL or credential was obtained.

## Binding still required

A future source-cohort claim needs an officially authenticated exact-build/target/attempt artifact inventory plus a pinned manifest/repo.prop or equivalent complete revision record. Its relation to the selected system image and separately delivered ART/APEX payload must be verified from actual bytes or an authoritative artifact chain. A matching build-number string alone is insufficient. The current CP2A Native601 repair/full can supply its own exact source proof; it cannot establish this missing CP3A relation.

All source_binding_authenticated, selected_qpr1_abi_qualified, runtime_qualified, and production_ready fields remain false. No change was made to the native generation pair or the required post-specialization grant.

## Original import operation remains unresolved

old-import-pty-read-original.json is the exact 703-byte original read result, SHA256 cd7fff040ea22e90209775d32cd7564ef25a99a2d4b21535b0ec5026c7c23077. It identifies dpty-cdbd8afd5072d1e150e2d0f387a5b4867190a34e6a8d0de99bbefa835f068521 on ai395 with state launch_unknown, available_end=0, and output_complete=false. There is no start acknowledgement. The operation was not replayed. Later Native materialization/full receipts are separate identities and do not resolve this uncertainty.
