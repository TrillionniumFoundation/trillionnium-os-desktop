# D0T-03 live GitHub governance controller

This document defines the supported automation path for configuring and verifying the repository-administration portion of D0T-03. Source presence is not live protection. Closure requires successful Administration writes, exact readback, independently attested negative and positive probes, and an unchanged current `main` SHA across the complete transaction.

## Authority boundary

`tools/d0t03_admin_controller.py` is readback-only by default. `--apply` is an explicit administrative operation. The controller never accepts a token on the command line, never logs credentials, never self-approves, and never treats a workflow, CODEOWNERS file, local JSON packet, or repository author as independent evidence.

The connected repository application may write source, pull requests, and workflows, but it does not expose GitHub repository Administration mutation. Running `--check-config` therefore proves only source shape. An organization-controlled administrator must execute `--apply` through a separately authenticated and reviewed session.

## Closed live policy

The controller applies and reads back all of the following as one fail-closed policy:

- an active default-branch ruleset with no bypass actors;
- deletion and non-fast-forward rejection;
- required commit signatures;
- merge commits only, strict current-base checks, and no squash or rebase merge;
- exactly two current approvals, stale-review dismissal, current-push approval, CODEOWNER approval, and conversation resolution;
- administrator enforcement and explicit prohibition of force pushes and deletion;
- the exact four required checks, each bound to GitHub Actions App ID `15368`;
- protected `qualification`, `hardware-attestation`, `release-signing`, and `production-publication` environments;
- exactly the two reviewed user identities in every environment, with no teams, extras, duplicates, ID drift, or self-review.

Missing, null, malformed, legacy-only, duplicated, foreign, or unexpected readback fields are failures. Absence is never interpreted as a safe default.

## Transactional `main` binding

The controller reads the exact default-branch SHA before policy readback and again after all repository, ruleset, protection, reviewer, and environment reads. Any movement fails the readback.

After detached-signature and probe validation, it reads `main` a third time. The initial, post-readback, and post-probe SHA values must be identical. This prevents a successful result from being issued for a commit that ceased to be current during the evidence transaction.

## Signed probe packet v3

Version 3 deliberately uses one evidence authority: an independent governance attestor whose public-key digest, numeric identity, and login are supplied from an external protected trust store. The controller verifies an OpenSSL SHA-256 detached signature over the exact packet bytes and requires the packet attestor to match those external bindings.

The packet does **not** contain or claim to verify GitHub workflow URLs or arbitrary digest-shaped fields. A detached signature does not turn a nonexistent or unrelated GitHub run into server evidence. The attestor is responsible for observing the operations through an independently controlled collection process and signing the closed projection below.

Each packet contains exactly:

- schema version `3` and authority `external_independent_governance_attestor`;
- repository and exact `main` SHA;
- strict UTC issuance time within 24 hours;
- the externally bound independent attestor identity;
- a globally separated identity map for author, reviewer, builder, signer, attestor, promoter, and publisher;
- exactly one record for every required probe;
- a unique observation ID, expected result, expected operation, actor ID/login/role, strict UTC observation time, and exact subject SHA for each probe.

Unknown fields, missing fields, duplicate probes, duplicate observation IDs, stale or future times, role sharing, attestor overlap, wrong actor, wrong operation, wrong result, or wrong subject fail closed.

## Required probes

The independently signed packet must cover rejection of direct push, force push, branch deletion, missing required checks, stale approvals, missing CODEOWNER approval, insufficient approvals, unresolved conversations, administrator bypass, unauthorized environment deployment, and environment self-approval. It must also cover one ordinary authorized protected merge and one protected publication.

Destructive tests must use a safe policy-evaluation path or equivalently configured disposable target. The attestor must separately establish that the same immutable ruleset targets `main`.

## Static validation

```bash
python3 -m py_compile tools/d0t03_admin_controller.py tests/test_d0t03_admin_controller.py
python3 tools/d0t03_admin_controller.py --check-config
python3 -m unittest tests.test_d0t03_admin_controller -v
```

The hostile tests cover foreign or duplicate check integrations, malformed critical protection controls, extra/team environment reviewers, unsigned packets, trust-root substitution, attestor mismatch, role overlap, stale timestamps, duplicate observations, moving `main` during readback, and moving `main` after probe verification.

## Apply and verify

```bash
mkdir -p artifacts/governance
python3 tools/d0t03_admin_controller.py \
  --apply \
  --probe-evidence /secure/probes/d0t03-probes.v3.json \
  --probe-signature /secure/probes/d0t03-probes.v3.sig \
  --probe-public-key /secure/trust/governance-attestor.pem \
  --expected-probe-public-key-sha256 "$D0T03_PROBE_TRUST_ROOT_SHA256" \
  --expected-probe-attestor-id "$D0T03_PROBE_ATTESTOR_ID" \
  --expected-probe-attestor-login "$D0T03_PROBE_ATTESTOR_LOGIN" \
  --output artifacts/governance/d0t03-live-readback.json
```

All three external bindings must come from an organization-controlled trust store or protected administrative environment, not from the repository or packet.

## Failure and invalidation semantics

Any API denial, incomplete write, incomplete readback, moving `main`, missing or foreign check source, ambiguous reviewer, extra environment reviewer, invalid signature, mismatched external attestor binding, stale packet, role overlap, missing probe, or unexpected probe result leaves D0T-03 open. A source workflow, controller run, or configuration write alone is not closure.

Evidence invalidates on any `main` movement, ruleset/protection/environment change, required-check integration change, reviewer identity change, trust-root rotation, repository ownership change, packet expiry, or relevant GitHub policy change. Do not weaken controls, dismiss independent objections, reduce approvals, synthesize probe facts, or use administrator bypass to advance the successor train.
