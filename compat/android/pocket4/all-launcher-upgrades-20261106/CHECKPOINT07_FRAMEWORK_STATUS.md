# Pocket4 all Launcher Apps — framework checkpoint 07

This is a continuation checkpoint. It does not qualify an Android deployment, an App business flow, or deletion of any old build.

## Actual framework progress

The independent builder470 Rust build and its 19 focused controls completed successfully in job `1a1b1d86cb7-fc05-7b1f`. The actual result is 76,136 bytes with SHA-256 `6599026ebe5071ecdd5f0e2d962eb96cc791041be0dee9fd59a402735a6387d8`. The 498-file source closure retains the prior source and adds the real SystemUI and WindowManager Shell providers. This Rust result is not a successful Soong, Java/JNI, or on-device qualification. Its one-GiB host build encountered 657 memory-limit events with no OOM; those observations are retained and do not qualify the separate ten-GiB framework profile.

Build06, job `1a1b1f6d728-fc05-7bc6`, failed before a Main snapshot or inner build. Its root snapshot supervisor still pinned the old snapshot source. Both owned outer children were retired. The exact failed source and terminal remain preserved. The new build07 packet corrects that nested source pin without changing the original snapshot, lifecycle algorithm, live runtime guard, or resource limits. A positive nested-pin check and a stale-pin negative check cover the repair; the earlier 59 pure controls and 19 Rust controls were not rerun as part of that packaging revision.

Build07, job `1a1b20bbc0a-fc05-7c2e`, is authoritatively **failed, exit 1**, with durable complete output, no overall timeout or cancellation, and no automatic retry. Its final stdout is 877 bytes, SHA-256 `9971c2ebeda5b9d28652f810a3cab9c24b8dd4e7b9708837f0784705c8d62b84`. The full fence terminal is 24,701 bytes, SHA-256 `22c315979504854e249d059762a2ef008fc278c93b26c4a2bd65e0ba0a68bc34`.

Build07 passed the four actual lifecycle controls and both current Main snapshots. The held process identities, five resource limits, and explicit 47-package scope passed the pre/post comparison; the recorded Main OOM deltas were zero. These are sampled invariants, not proof that every transient effect was absent. Every outer owned child and acquired descriptor in the six capture receipts was retired; the fault controls retain their intentional child termination evidence.

The inner controller was called, but it raised `FileNotFoundError(2, 'No such file or directory')` before returning. The terminal does not identify the missing pathname. A successful Soong invocation, fresh framework resource admission, new Android artifact, or source reconciliation is therefore **not established by this checkpoint**. The last actually completed normal builder invocation remains normal05, whose 225-project published source state is the predecessor that must be verified. Do not relabel build06 or build07 as successful builds or manufacture an inner terminal.

## Reproduction and evidence

`framework_provider_repair/normal06/source-r4/` contains the exact build07 request and source closure. Its exact request is 320,416 bytes, SHA-256 `bd60060c5a1bd329b3c05bfa5309f192c42168d48397f4bcdcfc674fc889054b`; its transport carries the original source packet with bounded compression. The corrected review document records the same build07 output directory used by the actual executable source. The obsolete review document is retained explicitly as a document correction, not as a runtime action.

`framework_provider_repair/normal06/actual-build06-fence-failure/` and `actual-build07/` preserve the actual terminal and readback evidence. Build07's first start response was lost from the transient orchestration store before it was copied to disk. The retained root start message is labeled as a message reference; it is not represented as the original start response. The actual durable job status, complete stdout/stderr, and version-bound fence terminal independently establish the observed job outcome.

The checkpoint also preserves unexecuted candidate revisions and their exact source differences. Their presence does not imply they were run. The baseline is commit `f491498a8a7bad7795c293f0e3f63e3ecdcaa383`; the explicit source/evidence delta lists 282 added files and zero removals before this checkpoint's new status and build07 readbacks.

## Continuing task boundaries

The user scope is all Launcher Apps, not the original eight. Actual App upgrades remain 11; production-ready Apps remain zero. A complete live installed-package and MAIN/LAUNCHER inventory is still being collected separately. Existing sidecar and container UI Automator paths remain required. No ADB dependency is added. Bilibili's historical isolated-cell Accept authorization is not transferred to Main, Meituan location is not proactively enabled, and no App integrity or valid ownership/permission constraint is bypassed.

Old Android/framework/App versions and associated outputs have not been deleted: **zero bytes reclaimed**. Deletion remains contingent on verified working replacements, complete applicable regression evidence, and retained final source, configuration, and reproduction records.
