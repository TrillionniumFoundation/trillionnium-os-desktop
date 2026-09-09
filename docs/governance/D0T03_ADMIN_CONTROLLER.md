# D0T-03 live GitHub governance controller

This document defines the only supported automation path for configuring and verifying the repository-administration portion of D0T-03. Source files do not constitute live protection. Closure requires successful writes through a credential with repository **Administration** permission, live API readback, negative probes, independent review, and evidence bound to the then-current `main` SHA.

## Authority boundary

`tools/d0t03_admin_controller.py` is dry-run/readback oriented by default. `--apply` is an explicit administrative operation. The controller:

- never receives a token as a command-line argument;
- never prints credentials;
- never stores a credential in generated evidence;
- cannot approve a pull request or count its own execution as independent review;
- cannot convert source CODEOWNERS into proof that GitHub enforces CODEOWNER review;
- cannot describe a protected environment as closed until live environment readback succeeds.

Ordinary hosted CI must run only `--check-config`. The `--apply` path is performed interactively or in a separately protected administrative environment whose actor and approval evidence are recorded.

## Required credential

Authenticate the GitHub CLI through an organization-controlled identity with repository Administration permission. Production signing credentials must not be present. The administrator applying controls must not be counted as the independent source reviewer, signer, attestor, promoter, or publisher for the same release tuple.

## Static validation

```bash
python3 tools/d0t03_admin_controller.py --check-config
python3 -m unittest tests.test_d0t03_admin_controller -v
```

This validates payload construction only and makes no live claim.

## Apply and read back

```bash
mkdir -p artifacts/governance
python3 tools/d0t03_admin_controller.py \
  --apply \
  --output artifacts/governance/d0t03-live-readback.json
```

A successful command proves only that the configured controls were read back at the recorded repository and `main` identity. The evidence must be reviewed independently and invalidates on a `main` ref change, ruleset/protection change, protected-environment change, required-check change, reviewer/team change, or repository ownership change.

## Required controls

The controller requires:

- strict current-head required checks;
- separate prospective-merge checks;
- at least two approvals;
- current-push approval;
- stale-review dismissal;
- CODEOWNER review;
- conversation resolution;
- administrator enforcement;
- no force push or deletion;
- signed commits on `main`;
- merge commits only for the bounded stacked train;
- protected qualification, hardware-attestation, release-signing, and production-publication environments;
- self-review prevention and two independent environment reviewers.

## Negative probes

Administrative readback is necessary but not sufficient. Use separate non-administrator and administrator test identities to demonstrate that GitHub rejects:

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

The positive probe is an ordinary merge through the protected path followed by exact-`main` workflow success. The probe repository object, actor identities, timestamps, check-run IDs, review IDs, ruleset/protection IDs, environment IDs, commit/tree identities, and output digests belong in the immutable evidence packet.

Never probe by risking deletion or force-updating the production default branch. Use GitHub's authenticated policy-evaluation path or an equivalently configured disposable branch/repository, then separately confirm that the same immutable ruleset targets `main`.

## Failure semantics

Any API denial, incomplete readback, missing check, ambiguous reviewer identity, absent environment, or negative probe that unexpectedly succeeds leaves D0T-03 open. Do not weaken a control, dismiss an objection, reduce the approval count, replace an independent actor, or use an administrator merge merely to advance the successor train.
