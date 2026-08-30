# D0T-03 governance bootstrap

This change closes only the source-controlled portion of the repository
governance gate. It installs an interim two-identity CODEOWNERS surface, a
machine-readable policy contract, a fail-closed validator, and a read-only
source evidence workflow.

The validator treats CODEOWNERS ordering as a security boundary. It requires:

- every active rule to contain the exact approved identity set, using exact
  owner tokens rather than substring matching;
- the active rule order and pattern set to equal the canonical ordered registry
  in `manifests/repository-governance.v1.json`;
- no duplicate or unsupported patterns;
- the sole catch-all rule to appear first;
- last-match-wins evaluation of canonical sensitive paths to resolve to the
  approved identities;
- every currently required workflow, including the D0T-03 workflow itself, to
  exist exactly once in the required-workflow registry.

D1 and D2I workflows remain explicitly listed as pending integration rather
than being represented as present required workflows before their reviewed
merges.

The source workflow emits evidence schema
`trillionnium.desktop.d0t03-source-evidence.v2`. Pull-request evidence is bound
to the PR number, exact event head and base SHAs, checked-out two-parent
synthetic merge, tree SHA, full ref, workflow ref and SHA, run ID, and run
attempt. Push evidence is accepted only from exact `refs/heads/main`; manual
runs remain non-authoritative. No source-only evidence can promote D0T-03.

It deliberately does **not** claim that GitHub repository or organization
settings exist. D0T-03 remains `REPOSITORY_SETTING_REQUIRED` until all of the
following are observed and independently reviewed on GitHub:

- protected `main` with pull requests required;
- strict required workflows and no direct/force push or branch deletion;
- at least two approvals, including a CODEOWNER approval;
- stale approvals dismissed and approval after the latest push required;
- all conversations resolved before merge;
- no routine administrator bypass;
- real organization security and governance teams replacing direct-user
  CODEOWNERS entries;
- a protected `production` environment with independent approvers;
- signing-key custody separated from source authorship and ordinary PR CI;
- dynamic negative tests showing direct push, self-approval, failing checks,
  stale approval, unresolved conversations, and unauthorized release attempts
  are rejected.

The direct-user CODEOWNERS pair is an interim bootstrap because the repository
API available to this implementation session cannot create organization teams
or rulesets. It improves review routing but is not equivalent to the required
team-based separation.

After these settings are configured, attach immutable evidence containing the
ruleset/protection identifiers, target branches, required workflow identities,
review policy, bypass actors, team membership, protected-environment reviewers,
and results of the negative/positive acceptance exercises. Only then may the
machine truth change D0T-03 to an integrated status.
