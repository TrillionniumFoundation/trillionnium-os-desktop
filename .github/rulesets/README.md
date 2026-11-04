# Proposed main-branch protection

[proposed-main.json](proposed-main.json) is a concrete repository ruleset request.
Committing this file does not configure GitHub. No protection has been applied
by this change.

## Observed state and dependency

On 2026-11-04, the repository API reported default branch `main` at
`38227d33fd3ed668f0424bc153e0d3d811731597`, branch protection disabled,
and no repository or inherited rulesets. These are observations at that date,
not a permanent assertion about repository settings.

The prerequisite is [PR #296](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/296):
its G0 workflow runs on every pull request, without workflow path filters.
Merge that prerequisite, or the reviewed final integration containing it,
before enabling the required status check. A path-skipped required workflow
can otherwise remain pending.

The actual `host-contracts` check
[126754345602](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/41881356521)
passed on source `6533247104f3cdbf9c9ef68ac5369eb097467244`.
Its API publisher is GitHub Actions, integration ID `15368`; the request pins
that observed publisher rather than accepting a same-named status from any app.
The longer native and owner jobs remain separate qualification gates; their
path-filtered workflows are not proposed as universally required checks.

## Intended rule

The request targets only `refs/heads/main`, prevents deletion and force pushes,
requires a pull request with resolved review conversations, and requires the
up-to-date branch to pass the actual G0 check. The bypass list is empty.
All three currently enabled merge methods are preserved.

The approval count is explicitly zero. This minimal rule establishes PR and CI
gates; it does not assert independent human review. A named reviewer or team
must be established before adding that separate review requirement. It also
does not certify installed effects, recovery, native boots, signing, or hardware.

## Applying and verifying

After the prerequisite is on main, an authorized repository administrator can
import the JSON in Settings → Rules → Rulesets, review it, and create the rule.
The payload uses active enforcement, so creating it changes repository behavior
immediately. The current audit connection can read rules and write source/PRs
but exposes no ruleset write operation; the observed account's admin role alone
does not supply that missing operation.

Retain the actual returned ruleset ID. Re-read that ruleset and the effective
rules for `main`; require active enforcement, the exact ref and checks above,
and the empty bypass list before marking this blocker closed. If the create
reply is lost, reconcile existing rules by name and complete configuration
before considering another create attempt. A checked-in JSON file or successful
G0 run is not evidence that protection is active.

References: [GitHub rules API](https://docs.github.com/en/rest/repos/rules?apiVersion=2026-03-10),
[creating repository rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository),
and [required checks](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets).
