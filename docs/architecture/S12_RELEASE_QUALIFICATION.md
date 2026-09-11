# S12 independent release qualification

## Scope and claim ceiling

S12 defines a strict offline verifier for a release-evidence packet rooted in an external detached signature. It checks that one current-main source object, one exact image, installed S10/S11 receipts, two independent rebuilds, fixed-hardware qualification, endurance, raw power-loss recovery, production-key custody and separated promotion roles agree on the same immutable subject.

The verifier is source code only. It does not create external facts, run a second builder, operate physical hardware, advance 24 or 72 hours, remove power, access a production key, sign an image, promote a release or publish it.

## Externally rooted evidence

The evidence packet is one bounded strict UTF-8 JSON object. Duplicate keys, a BOM, non-JSON numbers, unknown top-level fields and malformed identifiers fail closed. The exact packet bytes must have a detached signature verified with a public key whose SHA-256 digest is supplied from outside the packet and repository checkout. The expected attestor ID and login are also supplied externally and must match the separated `release_attestor` role.

The packet is fresh for at most 24 hours and must bind the current `main` commit, its tree, the active `2026-08-29-d6` plan, locked-input digest, complete image digest and length, normalized image digest, SBOM, license report, vulnerability report, S10 installed-product receipt and S11 installed update/recovery receipt.

A digest-shaped string is not authority. The protected promotion controller must obtain current-main and environment readback independently, verify the detached signature, then re-read main before acting.

## Independent rebuild

Exactly two independent builders are required. Builder A and Builder B must have different actor IDs, builder IDs, runner IDs and administrative domains. Both records must bind the same current-main source commit, source tree, locked-input digest, complete image digest, normalized image digest and image length.

The verifier rejects a single builder duplicated under two names, a shared runner, a shared administrative domain, different inputs, different trees, different byte lengths or different normalized output. Source CI is not either independent builder and cannot self-issue these records.

## Fixed hardware and endurance

The hardware record binds the exact image to one canonical fixed BOM digest. The BOM includes model and revision, firmware digest, CPU, memory size, storage, GPU, display EDID digest, input inventory digest, audio device and network device. Secure Boot and a TPM or equivalent hardware root must be observed. Firmware, CPU, memory, storage, GPU, display, input, audio, network, suspend/resume and recovery must all report `pass`.

The same image and BOM require one real 24-hour record and one real 72-hour record. Both are signed by the separated endurance attestor, contain exact start/end timestamps, begin and end checkpoints, strictly monotonic checkpoints no more than 15 minutes apart, a terminal pass and a receipt digest. A short run labelled 24-hour or 72-hour is rejected.

## Raw power-loss qualification

Three distinct records must use `non_graceful_power_removal`: during update staging, during first boot before the health commit, and during rollback or recovery. Process termination, VM shutdown and exception injection are not substitutes for non-graceful power removal on the fixed hardware.

After each cutpoint, the exact image and BOM must reboot with filesystem, durable receipt journal and update-state reconciliation all passing. Every record is bound to the separated power attestor and an immutable receipt digest.

## Key custody and role separation

The production signing key must be held offline or HSM-backed. Exactly two distinct key controllers are required, along with a separated signer. Rotation, revocation and compromised-builder drills must each have a fresh terminal-pass receipt.

The following actor IDs are all distinct: author, reviewer, builder A, builder B, hardware attestor, endurance attestor, power attestor, key controller A, key controller B, signer, promoter, publisher and release attestor. Renaming one actor or using multiple accounts under one identity does not satisfy the independence requirement.

## Protected promotion and publication

A valid packet is only eligible for independent promotion review. It must show live readback that `production-publication` is a protected GitHub environment, bind that boundary to the same current-main commit and bind different promoter and publisher identities. The qualification packet precedes publication and therefore requires `release_published=false`.

The fixed output fields are:

```text
eligible_for_independent_promotion_review=<derived from every check>
release_published_by_this_verifier=false
external_facts_created_by_this_verifier=false
```

Actual signing and publication must occur later through the protected environment, under the independent signer, promoter and publisher. The verifier has no credential or API path that can perform those actions.

## Evidence invalidation

Any source push, main movement, base movement, changed source tree, lockfile, package/firmware input, image digest or length, normalized digest, S10/S11 receipt, BOM, builder identity, administrative domain, endurance record, power-loss record, key generation, role assignment, environment protection or attestor trust root invalidates the packet.

The exact-head and live prospective-merge source jobs must be terminal-success on the final immutable verifier object. They prove parser and policy behavior only; they do not validate a production packet unless the separately protected promotion lane supplies the external packet, signature, trust root and current-main readback.

## Non-claims

S12 source CI does not execute the second builder, fixed hardware, 24-hour or 72-hour endurance, non-graceful power removal, HSM/offline key ceremony, production signing or publication. No administrator may replace those facts with a comment, label, workflow URL, self-review, manually edited JSON or historical artifact.
