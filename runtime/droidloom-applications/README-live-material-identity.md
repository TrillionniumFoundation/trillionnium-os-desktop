# Live application material identity

The existing runtime-plan dispatcher now has a source-admitted material identity
factory. It does not accept an offline "passed" report as evidence of an installed
application. The factory obtains two actual InspectApplication observations from
the selected normal early production daemon, compares the complete base/split
byte sets, and associates identical installed bytes with the normal SDK signature
evidence for that exact material batch.

The source table in src/runtime_identity_admissions.json is the trust anchor for
normal material provenance. A caller cannot extend it by supplying another hash,
signer list, selection document or normal-looking result. The first entry is the
actual r5 snapshot. Neither APK count nor version numbers are built into the
algorithm; subsequent normally verified batches use the same schema and factory.

## Run the readonly factory

Use the existing complete schema-3 runtime plan and its actual independently
recorded hash:

    droidloom-applications --verify-material-identity /absolute/RUNTIME-PLAN.json \
      --expect-identity-plan-sha256 ACTUAL_PLAN_SHA256 --expect-app-count 39

This command invokes no launcher, browser or leaf, even when those routes occur in
the pinned plan. It retains every selected application. It requires the fixed
normal /run/droidloom/control.sock, the root-published early launcher, the actual
normal executable inode, the kernel's original peer PIDFD, fixed root credentials
and the normal production argv. The original root-owned selector, executable,
socket and process are revalidated. An ordinary user socket or unsupported layout
cannot substitute for this path.

Input selection and signature documents are held by descriptors across the
operation. Their complete F9 identity, named inode and whole SHA-256 must survive
the final readback. Equal bytes at a replacement inode are rejected.

Successful rows contain eight verified identity facets: package, Android user,
stable UID, version code, version name from the identical verified base APK,
complete base/split bytes, the corresponding SDK-verified signer sets, and the
unchanged live Main epoch. Split filenames are observed from PM; downloaded
filenames are not inferred to be PM split identities.

The report explicitly retains incomplete identity facets: engine mapping and the
semantics of the independent Main qualification. It does not prove a systemd
InvocationID, the latest available version, original-account/data compatibility,
UI behavior, lifecycle, stability, all application gates or production readiness.
The command exits with incomplete application acceptance even if these identity
facets match. The source-admitted factory also runs around ordinary selected
runtime routes; a changed final Main or installed identity blocks that row and
does not credit its retained leaf result.

## Admit the next normal material batch

First complete the ordinary public-material producer, SDK signature/full-split
checks and normal Rust input verifier. Preserve their actual outputs and failure
records. Construct a candidate-input JSON with:

- schema: droidloom.application-material-admission-candidate-input.v1
- id: a new normal batch identifier
- selection, signature_receipt, normal_import, normal_input_verification: four
  actual FilePin objects, each containing path, bytes and sha256

Then run:

    droidloom-applications --prepare-material-admission /absolute/ADMISSION-INPUT.json \
      --expect-material-admission-sha256 ACTUAL_INPUT_SHA256

The output is a source-review candidate, not an admission. This command checks
full document bytes, exact cross-document references, normal schemas, complete
package/split membership, manifest identities and signer relationships. It does
not execute SDK signing checks or independently certify an arbitrary signature
receipt. The retained normal producer/signature evidence must be reviewed, and
the resulting row added to the source table through a normal source release.
There is no runtime table override or automatic admission path.

This permits a real later batch, including changed versions and split counts,
without replacing historical r5 evidence or treating its freshness flags as true.
A normal tool publication containing the reviewed new row is required before the
new batch can receive live identity facets.

## Authority boundary

VerifiedMaterialBatch is process-local and cannot be deserialized. Its constructor
consumes only source-approved normal document commitments. IdentityObservation
and NativeInspectionPeer are output-only records; they cannot construct a
runtime owner, a material batch or final activation permission. The permanent
activation gate still requires actual complete Main, application and private-data
acceptance. The declaration-only release checker is not used as that authority.
