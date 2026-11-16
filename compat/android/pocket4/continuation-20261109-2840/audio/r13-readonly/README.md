# Audio13 independent read-only failure and input audit

This package freezes a bounded audit of the owner's unique Audio13 full build. It starts no build, stops no job, and changes no remote source, locks, deployment or CURRENT.

## Result

The original normal `audio-apex-build` child returned 1. Its Soong bootstrap reports three dependency errors: `enforce_permission_counter` requires `soong_lint_fix`, while `fontchain_linter` and `update_font_metadata` require `fontTools`. The original command receipt records complete retirement of that normal command's owned children. The outer H job, actual unit and shared-lock retirement were not re-observed to terminal in this audit. No complete-full, artifact, QPR1, runtime or production qualification is granted.

The one actual-unit read at 19:04:27Z still showed active/running with memory events oom=0 and oom_kill=0. At the later bounded log read, the normal command had already failed. These observations concern different scopes and timestamps; neither overrides the other. The desktop's embedded `14:04:42` in Soong output is its local log time, not UTC. Exact nanosecond values are preserved in the raw command file and as strings in OBSERVATION.

## Actual source binding

The owner used recipe `656a52175b4e91073aaee0865e05ce2b3fc74b1f`, tree `faaee46cdde2fb3490edaaaae9f3c8fef3015844`, lock SHA256 `9a68f55567b88f89face6dce6121a60ee27fae028285c3cc0cda4cbae1d43364`. This is not our b555 commit. All 430 project path/name/commit tuples are unchanged from b555. The owner selects the entire `33/module-lib` directory and both zygote crate directories. The full bytes, SHA256 and Gitblob identities of our two independently fetched SDK33 module-lib JARs and eight zygote Rust originals all match the actual materialized files. The materialized manifest SHA256 is `6298380690d6bb5253c40999c6d2331350b2a5137944b3110b75764eba894ffc`.

The initial reader checked literal file-selector membership, which is false under the owner's equivalent broader directory selector. The final static selector read and source-delta original resolve that difference explicitly; it is not a remaining missing-input defect. The controller lists 151 SDK originals and 10 zygote files. This audit fully hashes ten targeted originals, not all 161 entries. Normal tool binary hashes in the controller were not independently rehashed in this audit.

## Evidence and limits

The two saved 8 KiB log tails are separately hash-checked. Both complete remote logs were streamed for stable size and SHA256; their complete content was not copied here. The command JSON and source-delta JSON are exact original contents and hashes. The read-only observer stdout files retain their original text and integer precision. Only OBSERVATION and channel provenance are synthesized summaries. Original H status is included solely to bind the unique build job. Observer exits do not constitute build success or full-job retirement.

The actual command retains `ALLOW_MISSING_DEPENDENCIES=false`, jobs=6 and `TARGET_RELEASE=cp2a`. Its failure cannot be relabeled as QPR1 validation. Next work is a separate fixed-revision provider-closure audit after checking whether the owner has already prepared it. No such repair or control execution is included here.
