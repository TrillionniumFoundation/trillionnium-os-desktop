# Security policy

TrillionniumOS Desktop is pre-release software. No repository state, self-check,
development image, QEMU run, or candidate PR should be treated as production
safe or as a signed public release.

## Reporting

Report vulnerabilities privately through the repository's GitHub Security
Advisory interface. Include:

- affected repository, commit/tree, artifact digest, and product profile;
- threat scenario and trust boundary;
- reproducible steps or a minimal proof;
- expected and observed behavior;
- whether credentials, secrets, personal data, external effects, signing
  material, or update state may have been exposed;
- suggested containment when known.

Do not place live credentials, private keys, user data, undisclosed exploit
details, or sensitive evidence in public issues or pull requests.

## Security-sensitive areas

- trusted shell/origin and compositor indicators;
- AgentPort mechanism and semantic-principal identity;
- PageOwner/BrowserActor arbitration and stale references;
- capability permits and portals;
- browser/content sandboxing and controlled egress;
- signed applications and storage isolation;
- durable receipts, privacy, and effect reconciliation;
- reproducible images, updates, rollback, recovery, provenance, and release
  claims;
- CI actions, dependency locks, runners, and signing-key custody.

## Response model

The maintainers should acknowledge private reports, classify severity and
affected evidence tier, identify supported artifacts, prepare a reviewed fix,
rerun invalidated gates, and publish an advisory when disclosure is safe.
Signing-key, update, dependency, or CI compromise additionally requires
revocation/rotation and provenance review.

The repository currently has no supported production release. A future release
must publish supported versions, response targets, update channels, key
rotation/revocation procedures, and end-of-support policy.
