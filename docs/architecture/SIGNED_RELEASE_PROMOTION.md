# Signed release promotion

## Status and immutable boundary

This package is a D9 source candidate blocked by D8. It validates release
evidence without possessing any authority to protect a branch or tag, approve
a review or deployment, access a signing key, publish update metadata, upload
artifacts, or promote a production release.

A source self-test can prove only the verifier and attack corpus. Every fixture
identity and key is explicitly non-production.

## Exact release identity

A stable release binds:

- repository and exact `refs/heads/main` commit;
- exact Git tree and protected signed tag;
- source author identity;
- monotonically increasing version and rollback index;
- fixed D8 hardware profile and qualification identity;
- exact source archive, OS image, kernel, initrd, package lock, SBOM, licenses,
  provenance, update and recovery metadata, hardware evidence, governance,
  custody, release notes, machine non-claims, support policy, CVE process, and
  known limitations.

The evidence directory must contain exactly the declared regular files. Missing,
extra, symbolic-link, size-mismatched, digest-mismatched, or basename-remapped
artifacts fail closed.

## Required checks and protected source review

Every required workflow context is bound to the exact release commit and must
have completed successfully before the release evidence was created. The set is
closed and includes governance, Rust, headed Servo, D1, D2I, D3, D4, D5, D6,
D7, and D8 gates.

At least two distinct source approvers must approve the exact latest commit.
The source author, release promoter, and release signers cannot satisfy those
approvals. A governance auditor separately signs the exact branch-protection,
required-check, review, protected-environment, and protected-tag facts.

Administrator bypass, force push, branch deletion, stale approval, unresolved
conversation, an unprotected tag, or a non-main source object invalidates the
release.

## Protected production environment

At least two distinct deployment approvers approve the exact release ID for the
`production` environment. The promoter cannot approve the same release and the
source author cannot promote it. Promotion is valid only through the protected
environment path with `administrator_bypass=false`.

The verifier does not create these approvals; it only validates independently
attested evidence of them.

## Release signatures

The release manifest requires two distinct Ed25519 identities with separate
roles:

- `artifact_signer` binds the complete artifact and source identity;
- `release_attestor` independently attests the same canonical manifest.

A signer cannot also be the source author, promoter, source approver, or
production-environment approver. Production mode requires production-enrolled
keys. Revoked, expired, duplicate, unknown-role, or altered signatures fail.

The fixture signer is a deterministic test vector and is never production
custody evidence.

## Offline key custody

The custody document binds all release-manifest key IDs and requires:

- at least two distinct custodians;
- offline hardware security module storage;
- dual control;
- no pull-request workflow access;
- no repository-secret access;
- source-author and promoter exclusion;
- digest-bound rotation, revocation, and disaster-recovery procedures;
- an independent custody-auditor signature.

The governance auditor, custody auditor, custodians, signers, approvers,
promoter, and source author occupy separate trust roles. Source CI cannot mark a
fixture key production-enrolled or attest its own custody.

## D8 hardware binding

The release includes an exact D8 binding for the same image, kernel, initrd,
package lock, SBOM, provenance, and hardware profile. Production eligibility
requires the D8 physical-policy result, independent hardware-lab role, at least
72 hours of evidence, and zero critical failure, corruption, unexpected effect,
or network-policy bypass.

D8 deliberately records `hardware_beta_promoted=false` and `release_ready=false`;
D9, not D8, decides release policy after all remaining evidence is present.

## Update and recovery metadata

Update metadata is signed by a dedicated update identity and binds release ID,
version, rollback index, hardware profile, image digest and size, recovery
metadata digest, and support-policy digest.

Recovery metadata is signed by a distinct recovery identity and binds hardware
profile, minimum rollback index, recovery image, support policy, and
`automatic_destructive_recovery=false`.

Update and recovery signers are separate from release signers, approvers,
promoter, auditors, and custodians. Version and rollback index must strictly
advance from the previously accepted stable release.

## SBOM, licenses, provenance, CVE response, support, and limitations

The release verifies non-empty SBOM and license reports, exact source/artifact
provenance, an unexpired support policy, bounded CVE response targets, release
notes, and independently reviewed known limitations. Release notes bind the
known-limitations digest and include upgrade and rollback instructions.

A previous-release state is mandatory for production so anti-downgrade cannot
be bypassed by omitting history.

## Machine-readable non-claims

The signed release must explicitly keep the following false unless a future
reviewed plan revision changes the product boundary:

- unknown hardware support;
- ambient filesystem, device, or secret authority;
- public Agent listener or WebDriver;
- automatic external-effect replay;
- administrator bypass;
- source-author promotion;
- unreviewed known limitations.

The artifact copy must exactly equal the top-level signed set. Any true value or
cross-artifact mismatch fails closed.

## Promotion receipt

A successful verification emits a hash-bound policy result. Even a production-
shaped unit-test result states that the source gate did not protect GitHub,
obtain human approvals, access keys, publish artifacts, or promote a release.
Only externally performed and independently reviewed actions can establish
those facts.

## Final external sequence

After D8 is physically qualified:

1. merge the exact release commit through protected `main`;
2. complete all exact-main checks;
3. create and protect the exact signed tag;
4. freeze the artifact set and previous-release state;
5. collect two current source approvals and two production-environment
   approvals from allowed identities;
6. collect independent governance and custody attestations;
7. sign update and recovery metadata with their separate offline roles;
8. sign and attest the canonical release manifest under dual-control custody;
9. run the verifier with `--require-production` offline;
10. publish only through the protected environment;
11. record the final release receipt, hashes, support policy, and non-claims.

Until each external fact exists, production release remains No-Go.
