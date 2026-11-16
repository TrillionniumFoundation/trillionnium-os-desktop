# Audio continuation controls

This portable Python module contains the reusable validation logic from the Audio continuation repair. It requires Python 3.9 or later and has no external dependencies. It does not contact a host, launch builds, install files, or create qualification records.

## Repairs

* `reviewed_reference` verifies the actual path, length and SHA-256 before preserving the reviewed mapping insertion order. The original binder compared equal dictionaries but embedded different `repr` text after sorted-key JSON transport, so the remotely assembled source differed from the reviewed bytes.
* `validate_raw_exit` consumes the on-disk durable exit schema. That record contains generation identity, exit code, timestamp and complete stream accounting; it does not contain the API wrapper fields `state` or `automatic_retry`. The guard binds request/start/exit generations and rejects incomplete, changed, cancelled, timed-out or truncated records.
* `ResourceProfile` keeps the build allocation and host reserve explicit. The current profile uses an 8 GiB build cap, a separate 5 GiB host reserve, two CPUs, no build swap and the unchanged 5 GiB Go heap limit. Both outer requests and actual completion evidence must agree with this profile. Historical records are never rewritten to make them fit.
* `validate_complete_apex` and `validate_stage_apex` require the actual whole APEX, signature/hashtree validation, signed-payload file contents and three compiled bridge translation units. The stage guard reads the pinned contents and compiled receipts; packet flags or an embedded declaration alone cannot grant completeness. Runtime and deployment remain separate qualifications.

## Integration

The production binder retains the exact reviewed reference after checking its values. The raw-exit adapter validates original runtime files without fabricating absent status fields. The deployment consumer embeds the same pure APEX/stage guards in its source-bound control bundle, avoiding an unpinned runtime import. Callers remain responsible for held reads, independently pinned controller sources, original job identities, locks, process retirement and source restoration.

`validate_stage_apex` expects a witness whose `read(reference, json=True)` verifies the path/byte-count/digest while reading and returns `(document, actual_reference)`. It returns the two evidence references for the deployment transaction's immutable proof set.

Run the focused regression suite:

```sh
python3 -B -m unittest discover -s tests -v
```

The 24 tests use synthetic records to reproduce the two production parser/binder defects and exercise the resource and stage rejection boundaries. Actual JSON integer and boolean types are checked explicitly, including process status, stream accounting and resource evidence. Passing these tests is code validation. It does not establish a real build, APEX qualification, deployment, or app acceptance. There are no private host paths, account identifiers, job records, device snapshots, signing secrets or raw logs in this package.
