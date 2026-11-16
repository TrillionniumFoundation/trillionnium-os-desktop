# Audio r10 source-input diagnosis and independent regression evidence

This capsule records the actual Audio `full-desktop-r10-r2` failure and an
independent, bounded regression against exact recipe base
`a0e5114a1728e5ac5a96cdffbf68a84958218765`. It is supplementary evidence.
The subsequently published owner candidate
`0342210a3bd82bf46067a1dbaf740e16f291a38a` takes precedence for adoption.
Do not apply this independent patch over that candidate or remove its stronger
original-provider guards.

## Actual failure and input boundary

The retained `service-ondeviceintelligence` consumer requires current and removed
`api.combined.system-server.latest` modules. The fixed SDK's ordinary
`prebuilt_apis` generator creates these from selected versioned API input files.
The two original API36 system-server files were absent from Audio's sparse
selection. Their exact upstream content is a 25-byte signature header, with
Git blob `d802177e249b3f97128699222e65c35e57ba7540` and SHA256
`39824f8c9fee1582598de5aa8cfa9653e84fbd69bd8aeb92c4a78c861faad552`.
These are official original inputs, not replacement stubs.

The independent helper selects four original files: the current and removed
pair in both `36/system-server/api` and `36/public/api`. The public pair preserves
the original lower-scope inputs. It is **not** a separately proven undefined-module
blocker: the generator appends an inherited scope only when that scope exists in
its latest-input map. The owner's narrower two-file selection suffices to create
the two reported missing modules. `provider-review.json` binds this distinction
to the unchanged original generator, declaration, consumer and API blobs.

## Validation actually performed

The new input-contract test first failed on the unmodified exact lock, exit 101,
listing all four omitted inputs. The first four-path attempt then exposed four
existing current/historical hash tests. These failures are preserved. Historical
reconstruction now removes exactly the four later additions, each with an
occurrence-count assertion, before verifying the unchanged PASIT430 hash
`78cc10ee7459926ec151e6224e6341d1b33397801330499e5d7f1a13fadb997a` and
425 hash `1dd0671551fb3c07cac4bb9b587346421321a6e4809494299f7b6daa4c49371c`.
The current lock is separately bound to
`46084ee55d24ee0178d09fb886886e07e8897949ea6300a30860b99f0a89c84f`.
No historical hash assertion was removed or replaced with a newer generation.

Pinned Rust 1.93.0 then passed all 24 ordinary source tests, the new input
regression, and 45 Audio tests. The 174 other update tests were outside this
focused invocation; no tests were ignored. Both ordinary tools built, and normal
`verify-lock` reported 430 exact projects and eight root links, exit zero.
The eight final commands, including independent patch application checks,
all exited zero. Job `1a1bfe03d9e-5e21-792` is terminal succeeded with complete,
durable output. Original stdout/stderr and receipts are under `evidence/`.
The first wrapper's exit zero does not turn its recorded `HELPER_FAILED` result
into a test pass.

The helper used a private source archive, private copied cache and target,
one CPU (22), CPU quota 100%, 4 GiB memory limit and zero swap. It changed no
shared source, coordinator state or global cache and started no Android full
build. Its final peak memory was 794791936 bytes, with zero OOM/max events.

## Reconstructing the exact change for review

`evidence/preimages.json.gz` contains three complete UTF-8 preimages as JSON
`files[]` entries with `relative`, `bytes`, `sha256`, and `text` fields.
`audio-ondeviceintelligence-api36-r2.patch` changes those three files and adds one
regression source file plus two original-input fixtures. In a new empty review
directory, decode the archive, write only its three relative paths, and use
`git apply --check` followed by `git apply` on this patch. Verify all six resulting
files against `source-manifest.json`. Do not use an owner working tree for this
review. A full normal Rust test replay requires the complete pinned recipe base,
the existing Rust 1.93.0 toolchain, and its locked offline dependencies; the small
three-file archive is a patch review input, not a complete build checkout.

`source-manifest.json` binds the six postimages, three preimages, exact source
delta, baseline failure, successful normal commands and preserved historical
identities. `FILES.json` is the final capsule inventory and excludes itself.

## Required owner handoff

The failed r10-r2 process is fully retired: source projection restored, original
input requalified, owned unit dead, child reaped, and ordinary work locks observed
free. Raw terminal records and `r10-terminal-completion.json` preserve the failure.
The older live/retirement-pending observations remain immutable historical
snapshots. Neither old r10 request may be executed again.

Audio also has a separately confirmed static `bcc_compat` selection gap. The
latest qualified Native candidate selects **`tools/bcc_compat`**, not broad
`tools`. Its ancestor `tools/Android.bp` must be verified in actual normal
materialization; Native source qualification does not transfer an Audio source
or full-build pass. `handoff.json` records the unchanged libbcc revision and
Audio's observed direct-provider declarations. Its old seven-blob tools review
is retained only as original-source evidence, not as a recommendation to select
the broader cone.

The owner must retain its API checks, qualify the narrow Audio BCC delta, then
perform one normal source reconciliation and exact materialized verification
before admitting a fresh serialized full generation. Optional public-pair
integration must preserve the owner checks and receive a new exact-lock
qualification; it is not an additional diagnosed undefined-module blocker.

## Retirement and qualification limits

After terminal states and local evidence preservation were verified, this task
removed only its private compiler target, copied Cargo cache, temporary directory
and patch-check copy: 807595635 logical bytes, 824291328 allocated bytes.
`evidence/retirement-receipt.json` and its terminal job record bind this cleanup.
Reusable source and evidence remain; owner sources, global caches and shared
temporary paths were untouched.

These checks qualify original-input selection and ordinary recipe/tool behavior.
They do not model or qualify the entire Soong graph. Normal source reconciliation,
a complete Audio APEX, full Android image, boot and app runtime acceptance remain
unproven. All full/artifact/runtime/production-ready claims remain false.
