# D0T-03 live GitHub governance controller

This document defines the only supported automation path for configuring and verifying the repository-administration portion of D0T-03. Source files do not constitute live protection. Closure requires successful writes through a credential with repository **Administration** permission, exact live API readback, authenticated negative and positive probes, independent review, and evidence bound to the then-current `main` SHA.

## Authority boundary

`tools/d0t03_admin_controller.py` is readback oriented by default. `--apply` is an explicit administrative operation. The controller:

- never receives a GitHub token as a command-line argument;
- never prints or stores credentials;
- cannot approve a pull request or count its own execution as independent review;
- cannot convert source CODEOWNERS into proof that GitHub enforces CODEOWNER review;
- cannot describe a protected environment as closed until live environment readback succeeds;
- cannot accept a locally asserted probe JSON file as closure evidence.

Ordinary hosted CI runs only `--check-config`. The `--apply` path is performed interactively or in a separately protected administrative environment whose actor and approval evidence are recorded.

## Required credential and identities

Authenticate through an organization-controlled identity with repository Administration permission. Production signing credentials must not be present. The administrator applying controls must not be counted as the independent source reviewer, builder, signer, attestor, promoter, or publisher for the same release tuple.

The connected ChatGPT GitHub App has repository contents, workflow, issue, and pull-request write access, but no repository Administration mutation surface. Broad repository write permission therefore does not make `--apply` executable through that App. An organization administrator must run the reviewed controller from an independently authenticated session.

The two protected-environment reviewer identities are resolved live by login and numeric user ID. Any missing identity, ID change, non-user type, duplicate, team, or additional reviewer fails closed.

## Static validation

```bash
python3 tools/d0t03_admin_controller.py --check-config
python3 -m unittest tests.test_d0t03_admin_controller -v
```

Static validation proves only the source configuration. It verifies that every required check is bound to GitHub Actions App ID `15368`, rather than accepting an unbound context string or legacy context-only representation.

## Apply, read back, and verify signed probes

The probe packet must be produced and signed by an independent governance attestor. Its public-key trust root is supplied outside the repository. The controller hashes the supplied public key, compares it to the externally provided digest, and verifies a detached OpenSSL SHA-256 signature over the exact packet bytes before inspecting any probe claim.

```bash
mkdir -p artifacts/governance
python3 tools/d0t03_admin_controller.py \
  --apply \
  --probe-evidence /secure/probes/d0t03-probes.v2.json \
  --probe-signature /secure/probes/d0t03-probes.v2.sig \
  --probe-public-key /secure/trust/governance-attestor.pem \
  --expected-probe-public-key-sha256 "$D0T03_PROBE_TRUST_ROOT_SHA256" \
  --output artifacts/governance/d0t03-live-readback.json
```

The external digest must come from an organization-controlled trust store or protected administrative environment, not from a repository file or the probe packet itself.

## Closed policy readback

The controller requires and reads back:

- four exact required check contexts, each bound to GitHub Actions App ID `15368` in the ruleset and classic branch protection;
- no context-only fallback, duplicate context, foreign integration, or unexpected required check;
- strict live-base behavior;
- exactly two current approvals, stale-review dismissal, CODEOWNER review, last-push approval, and conversation resolution;
- administrator enforcement;
- explicit `enabled: false` readback for force push and deletion;
- explicit `enabled: true` readback for required commit signatures;
- a no-bypass active default-branch ruleset;
- merge commits only for the bounded stacked train;
- protected qualification, hardware-attestation, release-signing, and production-publication environments;
- exactly the two reviewed user identities in each environment, with no extras, teams, duplicates, or self-review.

Missing, null, malformed, legacy, or ambiguously sourced fields are failures; absence is never interpreted as a safe default.

## Signed probe packet v2

The packet is a closed JSON object bound to one exact `main` SHA and issued within 24 hours. Every probe records:

- the exact expected probe ID, result, operation, and actor role;
- actor ID and login matching the packet's globally separated role map;
- the exact current `main` subject SHA;
- a strict UTC timestamp;
- an immutable GitHub Actions workflow-run attempt API URL;
- a SHA-256 digest of the server-produced evidence object.

The attestor identity must be distinct from every operational role. Mutable HTML pages, issue URLs, unrelated runs, stale timestamps, role/actor mismatches, missing or extra probes, and unsigned packets are rejected.

## Required probes

Use restricted test identities and safe policy-evaluation paths to demonstrate rejection of:

1. direct and force pushes to `main`;
2. deletion of `main`;
3. a PR missing a required check;
4. a PR whose approval became stale after a new push;
5. a PR without CODEOWNER review;
6. a PR without two current approvals;
7. a PR with an unresolved review conversation;
8. an administrator bypass attempt;
9. an unauthorized protected-environment deployment;
10. self-approval of a protected-environment deployment.

Positive probes are an ordinary authorized protected merge and a protected publication. Never risk deletion or force-updating the production default branch; use GitHub's authenticated policy-evaluation path or an equivalently configured disposable target, then separately prove the same immutable ruleset targets `main`.

## Failure and invalidation semantics

Any API denial, incomplete readback, missing or foreign check source, ambiguous reviewer, extra environment reviewer, absent environment, invalid signature, stale attestation, mutable evidence reference, or unexpected probe result leaves D0T-03 open. A successful source workflow, controller execution, or configuration write alone is not closure.

Evidence invalidates on a `main` ref change, ruleset or branch-protection change, required-check or integration change, environment policy change, reviewer identity change, trust-root rotation, repository ownership change, or expiration of the signed probe window. Do not weaken a control, dismiss an objection, reduce the approval count, replace an independent actor, or use administrator merge bypass merely to advance the successor train.
