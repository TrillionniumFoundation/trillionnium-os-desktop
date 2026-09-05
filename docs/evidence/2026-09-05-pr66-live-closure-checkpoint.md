# PR #66 live closure checkpoint — pre-truth-refresh snapshot

**Observed:** `2026-09-04T17:45:12Z`
**Plan:** `2026-08-29-d6`
**Evidence lifecycle:** committed snapshot; live GitHub state must be re-read
**Machine record:** `docs/evidence/generated/pr66-live-closure-checkpoint.json`

## Frozen object

```text
base main:              addaf73a48bae65f19f6bfe91c6264fd2ddb85a1
source head:            ecb8c2ac0ec0e58277b64a5056a10a8262e8e63e
source tree:            f5e5cc16dcd6c088dcef6ed6c3793bd7808b4aa8
prospective merge:      8d9c1de8b3af62eb32f5cd2bca1a0230afc30115
prospective merge tree: f5e5cc16dcd6c088dcef6ed6c3793bd7808b4aa8
```

At this exact object, all 22 permanent pull-request workflows were terminal
`success`. The run identities are preserved in the machine record. All 22
review threads were resolved and one independent non-author approval from
`Tomasrgbsf` was present. The governance contract requires two current-head
independent approvals, so the review gate was not complete.

## Live D0T-03 readback

GitHub reported `main` at `addaf73a48bae65f19f6bfe91c6264fd2ddb85a1` with branch protection disabled, no
required status contexts, and no repository rulesets. A fail-closed governance
transaction was executed from control commit
`f6304383a45bfa8b17019972f19c9330da1ae7c7` (run `33901170417`). It terminated
before any administration API operation because
`TRILLIONNIUM_GITHUB_ADMIN_TOKEN` was unavailable. Its artifact `9947679279`
has digest
`sha256:b97280c17a569b1cf45ba84aa251e3378c72d94163443680a6f2146f14a9d183`.
No partial repository-setting change is claimed.

## Source custody

The exact tracked source at `ecb8c2ac0ec0e58277b64a5056a10a8262e8e63e` was exported by run `33901522952`.
Artifact `9947810361` has digest
`sha256:cbf0c1ca5671ffd71bbb35f58dfdfdd4726f982b388f655e6912798bd8d481c4`.
The local audit found zero tracked-file checksum mismatches.

## Invalidation and claim ceiling

This truth-refresh commit changes the PR head and therefore invalidates the
workflow matrix and approval snapshot above. It is historical input for the new
exact-head run, not promotion evidence. It does not prove protected-main
governance, a governed merge, exact-main evidence, a Servo-owned D3 retained-node
runtime, installed D4-D7 authority, physical D8 qualification, or D9 HSM
signing/publication.
