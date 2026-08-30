# D0T-03 repository governance and release separation

This document defines the source bootstrap and live-setting evidence required to
close D0T-03. It does not itself prove that GitHub settings, human review
identities, release approvers, or signing-key custody exist.

## Source bootstrap

The repository contains:

- `contracts/repository-governance.v1.json` as the machine policy;
- an unconditional, read-only `governance-integrity / governance-integrity`
  check on every pull request to `main` and every `main` push;
- immutable full-SHA external Action references;
- no `pull_request_target` workflow;
- no workflow with repository write authority;
- no workflow that commits, pushes, tags, merges, rewrites source, or mutates
  promotion truth;
- unique required-check identities;
- no root-level probe or other generated authority file.

The validator also binds the legacy source manifest to the machine contract:
the required workflow registry and dynamic-acceptance corpus must match exactly.
It checks the tracked root-file inventory (the reviewed ten-file allow-list),
rejects unregistered root files and symlinks, and requires every protected
CODEOWNERS path to retain both interim identities.

`tools/validate_governance_integrity.py` parses the complete workflow graph with
a duplicate-rejecting YAML subset parser. It audits block and flow collections,
quoted keys, permissions, triggers, job/step `uses`, local and reusable
references, checkout credential persistence, and shell/Python/REST mutation
commands. YAML anchors, aliases, merge keys, tags, malformed collections, and
symlinked workflow inputs are rejected. The parser is intentionally dependency
free so the source gate does not acquire an unpinned package authority.

The source bootstrap is only `SOURCE_BOOTSTRAP_READY`. It cannot promote itself
to `INTEGRATED` or `CLOSED`.

## Live GitHub controls

D0T-03 closure requires captured GitHub API evidence showing:

1. `main` requires pull requests and strict required checks;
2. the required checks are exactly the committed unique contexts;
3. force pushes and branch deletion are disabled;
4. administrators are subject to the same rules;
5. at least two distinct approvals are required;
6. stale approvals are dismissed after a push;
7. at least one approval must be made after the latest push;
8. code-owner review and conversation resolution are required;
9. CODEOWNERS points to protected organization teams, not only the author;
10. GitHub Actions cannot approve pull requests;
11. workflow tokens default to read-only;
12. a protected `production` environment requires two non-author approvers.

## Dynamic acceptance

Static settings are insufficient. A reviewed evidence bundle must demonstrate:

- direct and force push attempts are rejected;
- deletion of the protected branch is rejected;
- author self-approval does not satisfy the rule;
- a new push dismisses earlier approval;
- a failed required check blocks merge;
- two distinct non-author approvals plus green checks permit merge;
- production deployment remains blocked until two independent release
  approvers authorize it.

Every probe must use disposable branches or pull requests and record actor IDs,
repository, refs, exact SHAs, timestamps, API outcomes, and cleanup results.

## Release and signing separation

Signing material must never be present in pull-request jobs. Source authors may
not be the only release approvers or signing-key custodians. Evidence must bind
protected-environment configuration, named organizational roles, key storage,
rotation and revocation procedures, and an independently approved release
transaction.

## Promotion sequence

After this bootstrap is independently reviewed and merged:

1. apply and capture the live GitHub controls;
2. pass the dynamic acceptance corpus;
3. replay D0A-02 and D1 on governed current `main`;
4. independently review and merge each candidate;
5. require exact-main qualification after each merge;
6. build and qualify D2I on one exact integrated image;
7. proceed to D3 and later gates only in dependency order.

No administrator bypass or historical artifact may manufacture a closure state.
