# Organ cross-repository source profile

## Qualified source pair recorded on 2026-10-22

The first real [manifest](../../support/release/profiles/2026-10-22-organ-source.json)
has now been built and verified on clean OS `85d394f99c73ad3194d57c876712ac01b59d90ca`
and Hepta `6d6097da843f5831dfaf9cee3530da512d072a15`, with their exact trees in
the [retained receipts](../../results/integration/2026-10-22-organ-qualified/README.md).
The same source pair also has separately retained runtime evidence. This is
distinct from the tool's 19 temporary-Git regression tests. The dedicated
`organ-release-profile.yml` workflow checks those tool regressions and the map
schema only; it does not fetch private sources or qualify a deployed pair.

The manifest remains source-only and production-disabled. The executed OS head,
the #240 merge, and a later documentation/evidence head are distinct identities.
After committing or merging, verify the manifest again against the explicit
new OS head/tree; retain that new source-verification receipt separately instead
of relabeling the existing runtime receipts.

## Scope and current boundary

`support/release/organ_release_profile.py` generates and verifies a **source-only**
combination of one clean OS checkout and one clean Hepta checkout. It binds one
complete Hepta commit/tree, proves the original history owner's ancestry, checks
required original-owner source files, and compares both Notes protocol goldens
byte for byte. It uses Python 3.9+ and Git, with no third-party Python packages,
network calls, runtime RPCs, grant issuance, or device actions.

Passing this check establishes reproducible source identities. It does not
establish that the two projects build, that their integration tests pass, or that
an original-owner Notes/CPU transaction has completed. Those results must refer
to the same final pair of commits and have their own test receipts.

The supplied `organ_source_map.json` is a reviewable mapping of required source
roles and golden fixtures. An unconfirmed path is `null`; the tool rejects it as
`source map unresolved`. A path is not accepted just because it appears in this
document: it must be a tracked regular file at the pinned HEAD, and its working
bytes must match the Git blob. Confirm private-source locations against the
actual final Hepta checkout before completing the mapping. No release manifest
is claimed to have been generated for the real projects by the synthetic tests.

The original durable-writer role maps to
`codex-rs/hepta-memory/src/production_writer.rs`, which defines
`ProductionDurableWriter` and its existing external-verifier, lease and store
entry points. The history role maps to
`codex-rs/hepta-agentd/src/objective_history.rs`; the protocol's history schema
is not a substitute for this original owner implementation.

The source map separately includes `hepta-contracts/src/final_use.rs` and
`hepta-contracts/src/final_use_control.rs`. The first defines `FinalUseAuthority`
and the constructor that accepts issuer keys, a protected clock and an external
frontier store. The second implements independently pinned approval verification
against exact grant semantics and authenticated, fresh revocation-feed updates
handed to that original authority. These are distinct trust checks, so recording
both source identities is useful. Their presence does not configure any trust
keys, deploy a clock/frontier, authenticate an approval, or enable production.

## What a successful check means

| Check | Passing condition |
| --- | --- |
| OS identity | Caller supplies full lowercase 40-hex HEAD and tree; both exactly match the checkout |
| Hepta identity | Builder receives full HEAD/tree explicitly; verifier uses that single manifest pin |
| Clean checkouts | No tracked modifications or nonignored untracked files; no assume-unchanged or skip-worktree flags that can hide changes |
| Original history | `995b6fb9ef73ada7c3348b01deb28940a2c4a2d1` exists as a commit and `git merge-base --is-ancestor` returns success against Hepta HEAD |
| Shallow clone | Allowed only when that exact ancestry relation is actually provable; missing objects and cut/unknown ancestry fail |
| Required sources | Every fixed role in the reviewed map has a tracked regular blob; record its Git blob, SHA256 and byte length |
| Notes target golden | The OS and Hepta mapped files have exactly the same bytes, including whitespace; record SHA256 and byte length |
| Notes bootstrap golden | The same exact-byte check, independently of the target golden |
| Manifest integrity | Recompute the entire manifest and compare it; changed paths, hashes, fields or production status fail |

Git replacement objects are disabled for these reads. Legacy grafts are rejected.
The tool does not fetch history automatically. If the original history cannot be
proved, obtain sufficient original repository history and repeat the check; do
not substitute a new root commit, copy the owner source into a fresh repository,
or use object existence as an ancestry proof.

The existing `UPSTREAM_CONTRACT.json`, `OBJECTIVE_UPSTREAM_CONTRACT.json`,
`OBJECTIVE_HISTORY_CONTRACT.json` and `CPU_UPSTREAM_CONTRACT.json` remain intact.
Their bytes are included as OS source identities. This new profile identifies a
release combination; it does not rewrite the historical contracts or turn their
individual earlier commits into a claim that one current combination has passed
runtime validation.

## Why OS HEAD/tree are explicit inputs

A file committed inside the OS repository cannot contain the hash of its own
commit without creating a self-reference. The source manifest therefore does
not contain an OS commit/tree field. It records selected OS source identities
and the policy `explicit_caller_head_and_tree_in_verification_receipt`.

Each build or verification requires an explicit OS HEAD **and** tree. The
receipt binds that exact OS checkout to the single pinned Hepta checkout and
the SHA256 of the manifest file. A manifest alone is not a complete release
identity; use the final verification receipt with it. Committing a reviewed
manifest or documentation changes the OS commit/tree. Verify again against the
new explicitly reviewed OS identities. If any mapped source changes, the old
manifest must fail and a new one must be generated and reviewed.

## Generate a candidate

Finish the intended source changes in both repositories, commit them, and
confirm the source map against the actual files. Supply the reviewed full Git
identities; abbreviated hashes and branch names are rejected.

```sh
python3 support/release/organ_release_profile.py build \
  --os-repo /absolute/path/to/trillionnium-os-desktop \
  --os-head FULL_REVIEWED_OS_COMMIT \
  --os-tree FULL_REVIEWED_OS_TREE \
  --hepta-repo /absolute/path/to/hepta-private-ci \
  --hepta-head FULL_REVIEWED_HEPTA_COMMIT \
  --hepta-tree FULL_REVIEWED_HEPTA_TREE \
  --source-map support/release/organ_source_map.json \
  --output /tmp/organ-source-profile.json \
  --receipt /tmp/organ-source-profile-build-receipt.json
```

Output paths must be new files outside both source repositories. Existing files
are not overwritten. All source checks run before the candidate manifest is
written. This prevents generation from making a checked checkout dirty or
silently replacing an earlier candidate. Read the manifest and receipt, then
commit the reviewed manifest in the OS repository at the chosen release path.

## Verify the final source combination

After committing the manifest, use the **final** OS commit and tree. Keep the
Hepta checkout at the exact commit pinned by the manifest. This check does not
select a newer Hepta branch tip or silently combine several upstream commits.

```sh
python3 support/release/organ_release_profile.py verify \
  --os-repo /absolute/path/to/trillionnium-os-desktop \
  --os-head FULL_FINAL_OS_COMMIT \
  --os-tree FULL_FINAL_OS_TREE \
  --hepta-repo /absolute/path/to/hepta-private-ci \
  --source-map support/release/organ_source_map.json \
  --manifest /absolute/path/to/trillionnium-os-desktop/support/release/profiles/organ-source.json \
  --receipt /tmp/organ-source-final-verification.json
```

Exit status `0` means the source checks passed. Exit status `1` means a source or
input check failed; the error names the failed boundary. Invalid command-line
usage uses argparse's exit status `2`. Omitting `--receipt` prints the receipt to
standard output. Runtime evidence must not be inferred from the exit status:
every receipt explicitly says `runtime_tests: not_run_by_this_tool`.

## Production remains disabled

Every manifest and receipt contains `production.activation: disabled` and
`production.effects_authorized: false`. The verifier recomputes these literal
values. Editing the manifest, adding a string such as `provider: production`, or
removing unresolved items makes verification fail. There is no enable flag.

The following deployment inputs are not configured or qualified by this source
profile. Their absence remains visible even when every source check passes.

| Unconfigured input | What the later integration must establish |
| --- | --- |
| Production grant provider | The existing approved issuer/provider supplies original final-use grants; this tool does not create one |
| Protected AuthorityClock | The original authority uses its protected clock and expiry semantics |
| External AuthorityFrontierStore | The original authority has the intended durable external frontier state |
| Trusted issuer keyring | The actual trusted keyring is bound to the intended issuer and deployment |
| Revocation head | The original authority uses the correct current revocation frontier |
| Recovered writer configuration | The intended original durable writer is recovered with its existing store and outbox; no parallel owner/store is introduced |
| Current-cut authorization state | The actual current authorization cut is supplied and validated by the original authority |

Configuring and exercising those components requires a separate integration
that uses the original authority and owner, with evidence from the same source
combination. A string in this manifest cannot establish a protected clock,
durable frontier, recovered writer or current cut. This tool has no credentials,
opens no device/session channel, and does not approve or perform effects.

## Tool regression tests

```sh
python3 -B -m unittest discover -s support/release -p 'test_*.py' -v
```

The tests create real temporary Git repositories and commit DAGs. They exercise
clean success; wrong OS HEAD/tree and Hepta HEAD; tracked, untracked and hidden
worktree changes; committed golden differences and missing files; missing owner
source; missing, unrelated and shallow-unknown history; proven shallow history;
source change after pinning; manifest commit without OS self-reference; refusal
to enable production; unresolved source mapping; and output path isolation.

Synthetic tests replace the history constant only inside the imported test
module to construct controllable Git histories. The production CLI has no
history-owner override and always requires the original full commit above.
These tests qualify the release-profile tool; they do not stand in for either
project's source qualification or an original-owner end-to-end transaction.

## Schema 4: closed expanded source and owning-package contract

The schema-4 current candidate has its own literal role sets and
`support/release/organ_source_map_v4.json`. Its current 312 OS / 201 Hepta roles
preserve all V3 paths and add the reviewed CPU/GDT/Unix owners, observation and
checkpoint diagnostic paths, thread-store fixtures, compression and rollout
components, and release tool/map/oracle/document ownership. It is a source
contract with an explicit current-only CI entry point. A source manifest still
records `source-only`; separate real receipts establish each runtime lane.
The nine-role retirement extension names the finalized page-table activation,
managed-root retirement, real charged-root oracle, technical contract, new Unix
profile/oracle/contract and CAB84 archive/exporter. Other changed task/thread and
marker files reuse their existing roles. The original 300/201 tool receipts stay
frozen under their own source identities. This source extension does not claim
a completed retirement or native matrix. Future OAuth additions wait for actual
finalized files; the checker never tolerates a missing file to reserve a future
role.

The final three OS roles bind `organ-current-pair.yml`,
`organ-release-profile.yml` and the exact previous current V3 manifest archived
as `2026-10-26-organ-source-1138-f397-v3.json`. The archive preserves SHA256
`805fdc48788d467d3eef27f4f573ee441d3250258e019f3e67a2c60336e77e3f`;
none of the older archives is overwritten or used as a new runtime receipt.

A code-owned canonical-map SHA fixes the whole V4 role-to-path and golden
mapping. The ordinary structural checks still reject unknown/omitted roles,
invalid or duplicate paths and duplicate JSON keys first. `create_manifest`
then verifies the tracked OS V4 map has those same reviewed contents. Records
are read from regular committed blobs, with exact worktree bytes, clean status,
full identities and the existing original-history-owner ancestry proof.
Neither an operator-selected path/hash nor an ancestry waiver is introduced.
A shallow checkout is usable only when the original existing ancestry proof
actually succeeds; unknown ancestry is rejected even if its owner object was
copied into the object store.

The map contains repository paths, not a manifest hash. The manifest retains
`os_identity_binding: explicit_caller_head_and_tree_in_verification_receipt`;
committing a manifest changes the OS identity subsequently bound by the external
receipt without making the manifest contain its own hash. This also permits the
release checker, fixed V4 map and regressions to be explicit mandatory OS source
roles. Creation writes new outputs outside both source repositories and never
updates the current pin automatically.

`check_current_contract` validates the current V4 declaration before CI emits a
Hepta pin. It checks exact manifest fields, strict integer schema, complete
commit/tree identities, the original history-owner declaration, fixed canonical
map seal, exact role/path and golden sets, source digest/size shapes and the
seven disabled production inputs. This is a structural preflight. Only
`verify_manifest` with both repositories proves actual bytes, clean caller
identities and original ancestry. A declaration cannot choose commands, owning
packages, hash exceptions or an OS identity embedded in its own manifest.

The pair workflow then requires schema 4 and dispatches its code-owned V4 map.
The source-profile workflow still checks maps 1, 2 and 3, and additionally checks
map 4 and the current contract. Both CI callers are mandatory source roles.
Every mapped OS path can trigger the current pair job. Regression fixtures
execute the actual CI Python blocks and bash command expansion over real
temporary Git DAGs; bounded child programs exercise the real source verifier
and host dispatcher without pretending to execute Rust packages in tool tests.

The switch uses two commits: freeze all code/map/docs and the old-current
archive, generate/review a candidate outside both repositories, then commit only
the current manifest. The external verification receipt must be recreated for
that final OS commit. The self-binding field above remains unchanged and the
manifest never carries its own OS head/tree. Final tool/host/GUI qualification
must refer to that exact final caller identity.

V4's code-owned host test list is exactly the original thirteen V3 packages plus
five directly tested owners: `codex-app-server-protocol`, `codex-thread-store`,
`codex-core-plugins`, `codex-rollout`, and `codex-file-system`. The original three
Hepta binary builds, profile/toolchain/lock rules and post-command source
recheck remain. Node/SDK provenance and native/device/authority receipts are
separate qualifications. No additional future OAuth owning package is inferred.

The earlier ac96 Desktop / 97c Hepta pair actually passed seven host steps,
2,821 Hepta cases with 55 skips, and three isolated GUI cases with 352 unselected
cases. Those original receipts remain immutable; a newer pin requires fresh
bindings. The GUI used an explicit qualification issuer and owned display and
temporary storage. Its lost-reply and SIGKILL recovery observations do not
qualify physical power loss, the native durable authority chain or production
deployment inputs. The ordinary kernel surface remains query-only and all
seven real production inputs remain disabled. The independently qualified b446
kernel component is referenced under its actual source identity.

V1, V2 and V3 remain separate historical contracts, including their maps,
23/20/4, 41/43/5 and 274/146/5 source/golden counts respectively, their exact host
command lists, and all archived manifest bytes. V4 keeps the same five goldens,
nineteen automation migration roles and seven disabled production inputs.
Historical artifacts continue to identify their own source/tool version; a new
schema or source head cannot turn them into receipts for a later composition.
Once a V4 release contract is frozen, later role/path expansions require a new
reviewed schema rather than loosening that published acceptance set.
