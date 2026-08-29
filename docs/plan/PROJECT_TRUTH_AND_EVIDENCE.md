# Project truth, evidence identity, and promotion protocol

**Revision:** `2026-08-29-d6`  
**Normative machine sources:** `manifests/project-state.v1.json` and
`manifests/gates.v1.json`

## 1. Problem statement

The repository previously allowed README, current-state, plan indexes, build
constants, documentation manifests, and repository manifests to carry
independent status text. That makes a tested branch, a squash-merged source
tree, and an integrated-main qualification easy to confuse.

d6 replaces that model with one machine truth and generated/validated human
summaries.

## 2. Truth fields

The project-state record owns:

- active plan and revision;
- integrated stage;
- integrated completed packages;
- source-candidate packages and their PR/branch status;
- explicit non-claims;
- evidence tiers and promotion rules;
- upstream sibling reference review;
- fixture/qualification/development/production profile boundaries.

No human document may independently promote a package.

## 3. Commit identities

A gate may record four distinct commits:

- `base_sha`: main used to create the package;
- `candidate_head_sha`: package branch head;
- `tested_merge_sha`: GitHub synthetic merge or an explicit local merge tested
  by CI;
- `integrated_main_sha`: main after reviewed merge and exact-main rerun.

These identifiers are never interchangeable. `github.sha` alone is insufficient
for PR evidence; workflows must also record the PR head and base SHAs.

## 4. Evidence tiers

```text
source-shape
  < host-unit/property
  < host-integration/fixture
  < headed-host
  < QEMU-image
  < integrated-QEMU-image
  < fixed-hardware
  < signed-release
```

A tier may prove only its stated environment and artifact. A pass at one tier
does not imply the next.

## 5. Promotion transaction

Promotion is atomic across:

1. implementation;
2. contracts and schemas;
3. tests;
4. exact-head workflow;
5. bounded machine evidence;
6. project-state and gate registry;
7. current-state and plan summaries;
8. claim ceiling.

After merge, an exact-main rerun either completes promotion or marks the
package `INTEGRATED_SOURCE_AWAITING_MAIN_EVIDENCE`.

## 6. Evidence invalidation

Each gate declares invalidation paths and input digests. Evidence is stale when
any of these change, including:

- implementation, tests, workflow, validator, contracts, schemas;
- workspace manifest or Cargo.lock;
- toolchain, Servo, Debian, kernel, firmware, package, or runner input;
- base image or product profile;
- authority, activation, signing, update, or claim-boundary files.

A path-filter optimization may not omit a transitive invalidation input.

## 7. Candidate status vocabulary

Allowed states are:

- `SOURCE_CANDIDATE`;
- `CI_RUNNING`;
- `CI_BLOCKED`;
- `INFRASTRUCTURE_FAILURE`;
- `PRODUCT_FAILURE`;
- `EVIDENCE_PROMOTION_REQUIRED`;
- `BASE_DRIFT`;
- `BLOCKED_UPSTREAM`;
- `SECURITY_REVIEW_REQUIRED`;
- `REPOSITORY_SETTING_REQUIRED`;
- `MODULE_CLOSED_CANDIDATE`;
- `INTEGRATED_SOURCE_AWAITING_MAIN_EVIDENCE`;
- `INTEGRATED_AND_EXACT_MAIN_VALIDATED`;
- `STALE_EVIDENCE`.

## 8. Non-self-referential source truth

A tracked source manifest cannot safely contain its own final commit SHA.
Instead:

- tracked truth records the baseline and package state;
- CI emits exact source/tree/workflow/input/output identities;
- promotion evidence binds the tracked truth blob digest to the tested SHA;
- release manifests bind exact final artifact digests.

## 9. Required review

Security, origin, sandbox, capability, AgentPort, receipt, update, signing, and
release promotions require independent designated review. Repository settings
are external evidence and must not be inferred from CODEOWNERS source text.
