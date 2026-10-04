# Proposed GitHub required-check context correspondence

Every repository job has an explicit unique display name derived from its
workflow filename and original job ID. The four existing `matrix.object`
jobs append that original lane. The 27 workflows retain all 47 job IDs,
conditions, original matrices, checkouts, steps, commands, flags, deadlines,
profiles and budgets. Their expanded inventory contains 51 distinct proposed
contexts: 48 repository-source contexts and three availability diagnostics.
The latter provide no source qualification. Workflow names are unchanged.
The S07 real-Servo job retains its original `exact-head-real-servo-behavior`
semantic label as a final segment after the unique workflow/job prefix.
Original adjacency of the G2 prospective job ID and event condition is also
retained; its display name follows that condition and precedes all steps.

[`ci-required-contexts.v1.json`](../../contracts/ci-required-contexts.v1.json)
records each path, ID, explicit name, expanded context, original matrix lanes,
trigger events, path-filter status and conditional job IDs. Its expected source
is the GitHub Actions application (`app_id: 15368`), observed on the repository
at head `653464efa4ada8197e16c91d63448d8d116fa11d` on 2026-10-03.
That observation is historical; new contexts require authenticated hosted
readback on the eventual exact candidate and current GitHub application ID.
The proposed binding uses `required_status_checks.checks[].context` together
with `app_id`; it never proposes `-1` or an unconstrained application source.

GitHub recommends unique job names across workflows because duplicate names
can cause ambiguous results and block merges. Its branch-protection API binds
checks by context and application, rather than workflow filename or job ID.
Multiple workflows using the same context from the same application cannot
be distinguished by that configuration pair. These facts establish binding
ambiguity; no merge bypass has been exercised or claimed. See the official
[protected branch documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
and [branch protection API](https://docs.github.com/en/rest/branches/branch-protection).
The [workflow syntax documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idname)
defines the display name separately from the unchanged job ID.

## Source validation and review

`python3 tools/verify_ci_required_contexts.py` performs only finite source
correspondence. The repository validator also invokes it. Its closed profile
rejects unknown fields, missing workflows/jobs, unqualified or duplicate names,
matrix lane drift, application/claim aliases and changes to recorded workflow
bodies. SHA-256 retains every workflow byte except job-level name lines, so
changing steps, source guards, conditions, triggers, budgets or flags requires
an explicit source review and a new recorded digest. This is a reviewed source
inventory, not a general YAML interpreter or authority against simultaneous
unreviewed edits to source, catalog and validator.

Reads retain managed regular-file owners through final source inventory
validation; symlinks, multiple hard links, duplicate JSON keys, changed source
identity and files above 128 KiB are rejected. The fixed inventory is bounded
to 28 files and 64 jobs. Initial and final workflow-directory inventories must
also retain the same directory identity, metadata and visible-entry names;
enumeration stops and rejects at the 29th visible entry, including non-YAML
entries. These checks reject an unlisted workflow added during validation,
a removed entry or a replaced directory before return. This local snapshot
does not promise that files remain unchanged after return or that all
asynchronous mutation windows are closed.
`tests/test_ci_required_contexts.py` exercises actual source files, hostile
catalog variants, matrix/name/run/condition mutations and real filesystem
replacement. Original test assertions are retained.

## Administrative review still required

This inventory is a directory for selecting precise proposed checks, not a
command or complete branch-protection configuration. Applying every entry as
a global requirement would ignore path-filtered workflows, manual workflows
and original conditional jobs: checks can be absent or skipped on a PR. GitHub
also accepts skipped and neutral required checks, so even a distinct successful
context does not prove that a native or installed qualification actually ran.
The administrator must review required coverage for each event/path, current
exact-head and prospective-merge provenance, actual check conclusions, strict
up-to-date policy, approval and CODEOWNER rules, administrator bypass controls,
protected environments and authenticated settings readback. Existing workflow
conditions are preserved; this source patch adds no acceptance shortcut.

No online protection, ruleset, environment or reviewer identity is provisioned
by this tool or catalog. Source success does not close G0 or establish current
hosted execution, independent human approval, installed images, boot-health,
hardware qualification, signing, promotion or production readiness.
