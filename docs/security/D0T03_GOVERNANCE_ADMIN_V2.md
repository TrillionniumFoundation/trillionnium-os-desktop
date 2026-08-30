# D0T-03 governance administration — supported v2 entry point

The only supported settings manager in this candidate is:

```text
python3 tools/d0t03_governance_admin_v2.py plan ...
python3 tools/d0t03_governance_admin_v2.py apply \
  --confirm-repository TrillionniumFoundation/trillionnium-os-desktop ...
```

`tools/d0t03_governance_admin.py` and its original workflow are retained only
as historical review objects from the construction sequence. They are not an
approved administration entry point and must not be used for settings changes,
qualification, or closure evidence. The v2 workflow and check context supersede
them.

## Preflight

The authenticated API must expose three real organization teams:

- `security-reviewers` with at least two distinct non-author members;
- `governance-reviewers` with at least two distinct non-author members;
- `release-approvers` with at least two distinct non-author members.

Security reviewers and release approvers must be disjoint. The source author is
removed from all reviewer sets. Missing, private-to-token, empty, single-person,
or overlapping role sets fail before any write request.

## Generated settings transaction

The v2 plan emits only documented top-level GitHub REST fields for:

1. strict `main` branch protection;
2. read-only default workflow permissions and no Actions review approval;
3. protected `production` environment with self-review prevention and two
   independent team reviewers;
4. active default-branch ruleset with no bypass, two current approvals,
   CODEOWNER review, thread resolution, squash-only merge, strict unique status
   checks, deletion and non-fast-forward protection;
5. active `desktop-v*` tag ruleset with no bypass, creation/deletion and
   non-fast-forward protection.

The tool never stores a token. `plan` and `apply` require an authenticated token
through an explicitly selected environment variable. `apply` additionally
requires the exact repository string as a confirmation barrier.

## What the transaction cannot prove

Successful API requests do not close D0T-03. An operator must still prove:

- team CODEOWNERS are committed and effective;
- direct push, force push, branch deletion, author self-review, stale review,
  failed checks, unresolved conversations, environment self-review, and
  administrator bypass are rejected dynamically;
- two distinct authorized humans complete a compliant merge;
- release signing and source authorship are held by separate people;
- release keys have offline dual-control custody.

The v2 source self-test always records `settings_applied=false`,
`independent_review_completed=false`, and
`release_key_custody_proven=false`.
