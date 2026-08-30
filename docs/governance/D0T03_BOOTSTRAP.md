# D0T-03 repository-governance bootstrap

Status: `SOURCE_BOOTSTRAP_READY_REPOSITORY_SETTINGS_REQUIRED`

This document records the one-way bootstrap from an unprotected repository to the
D0T-03 governance model. Source changes are necessary but are not sufficient to
close D0T-03. Closure requires live GitHub settings and evidence produced by
independent authorized identities.

## Required repository controls

- `main` accepts changes only through pull requests.
- Required checks are strict, unique and always reported for every pull request.
- At least two approvals are required; the author cannot satisfy either approval.
- Stale approvals are dismissed and the latest push must be approved.
- Code-owner review and resolution of every review conversation are required.
- Force pushes, branch deletion and routine administrator bypass are disabled.
- Security-sensitive CODEOWNERS entries resolve to organization teams with at
  least two eligible non-author members.
- Actions use read-only default permissions, immutable action revisions and no
  persisted checkout credentials unless an explicitly reviewed release workflow
  requires otherwise.
- Release approval and signing-key custody are separated from source authorship.

## Bootstrap protocol

1. Merge only the static source controls: unique check names, workflow safety
   validation, immutable action pins, read-only permissions and this protocol.
2. Enable branch protection using checks observed on the merged bootstrap commit.
3. Create and populate organization security and release teams.
4. Replace interim individual CODEOWNERS with those teams.
5. Run negative probes for direct push, force push, branch deletion, self-approval,
   stale approval and failed-check merge.
6. Obtain independent after-action review of the bootstrap and the live settings.
7. Record D0T-03 as closed only after all machine and human evidence exists.

## Prohibited evidence shortcuts

A repository owner, bot, workflow, generated comment or duplicated account cannot
be counted as an independent reviewer. A settings template is not evidence that
settings are active. A candidate workflow run is not exact-main evidence. No
source commit may mark D0T-03 closed by itself.
