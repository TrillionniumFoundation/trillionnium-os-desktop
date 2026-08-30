# D0T-03 governance bootstrap

This change closes only the source-controlled portion of the repository
governance gate. It installs an interim two-identity CODEOWNERS surface, a
machine-readable policy contract, a fail-closed validator, and a read-only
source evidence workflow.

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
