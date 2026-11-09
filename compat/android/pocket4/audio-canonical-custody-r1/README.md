# Audio evidence imported from a build host

This module closes a path and identity boundary in the Audio staging reader.
The original complete APEX result refers to files on its build host. Copying
those JSON bytes to the device does not make their original paths available,
and does not turn the original inode, process or cgroup observations into
device observations.

`canonical_audio_import.qualify` accepts an immutable, source-bound import
receipt and a destination file witness. It reads 13 explicitly mapped local
files. Each mapping contains an original path/length/SHA256 pin and a separately
observed destination pin. Original receipts remain byte-for-byte unchanged.
The function checks actual destination ownership, single-link regular files,
the caller's canonical directory, complete file contents, and the exact
reviewed qualifier sources. It does not open any original-host path.

The reader binds the original qualification to its complete durable H request,
start, exit and stdout. The executed qualifier command, source manifest,
specification, result pin, process interval and complete stream sizes must all
agree. Millisecond terminal timestamps are treated as millisecond intervals;
they are not mistaken for nanosecond timestamps.

It then reuses the existing strict complete-APEX validator from
`../audio-continuation-r1/audio_continuation_control.py`. The actual copied
contents and compiled-bridge JSON must match the references and embedded
evidence in the original whole-APEX result. A failed, incomplete, mismatched or
runtime-promoted source result is rejected. Stage receives actual destination
JSON pins for its subsequent checks.

## Integration contract

The caller must pin the import receipt through its reviewed source binding
before calling this module. It supplies the allowed destination directory,
distinct build/device host labels, destination owner UID, and independently
reviewed SHA256 hashes of `qualify_audio_whole_apex.py` and
`apex_evidence_join.py`. Those values are not taken from the receipt itself.
The strict raw-exit and complete-APEX guard is also supplied by the caller's
reviewed stage source manifest.

The exact roles are `whole_apex`, `qualification`, `contents`, `compiled`,
`source_manifest`, `source_qualifier`, `source_join`, `specification`, and the
five `H_request`, `H_started`, `H_exit`, `H_stdout`, `H_stderr` records. The
last stream may be empty. All eight JSON records, including the source
manifest and specification, retain their original bytes and paths inside
their bodies. They are read from independently pinned destination files.

The receipt schema is
`pocket4-audio-canonical-whole-apex-qualification-v1` with state
`CANONICAL_BYTES_BOUND_RUNTIME_PENDING`. It explicitly retains
`origin_host_authority_inherited=false`, `runtime_qualified=false`, and
`production_deployment_performed=false`. Import validation grants no runtime,
linker namespace, VINTF, physical-audio or application acceptance.

## Focused controls

Run from a checkout containing the adjacent existing guard capsule:

```sh
python3 -m unittest discover -s compat/android/pocket4/audio-canonical-custody-r1 -p 'test_*.py' -v
```

The 19 controls use real temporary destination files and synthetic records.
They reproduce the previous reader's failure on absent original-host paths,
then verify local copy composition and rejection of corrupt bytes, symlinks,
hardlinks, unexpected ownership, path escapes, missing roles, wrong reviewed
sources, process-generation mismatches, malformed terminal types, changed
qualifier commands, mismatched stdout result pins, failed qualification and
out-of-window timestamps. Synthetic fixture artifacts are not real APEXes;
these tests do not claim cryptographic or runtime acceptance.
