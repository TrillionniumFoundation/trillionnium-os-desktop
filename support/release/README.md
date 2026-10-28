# Current Desktop / Hepta pair

For module-to-owner navigation, the thirteen directly tested packages and the
separate kernel/host/GUI/native source identities, see the
[2026-10-26 documentation supplement](../../docs/agents/MODULE_DOCUMENTATION_2026_10_26.md).
It preserves the original receipts and remaining manual gaps; it does not update
this checkout's release map or qualify a new source pair.
The current V5 candidate selects nineteen owning packages; the earlier
thirteen-package supplement and its original receipts remain historical.

This module binds one Desktop checkout to one complete original Hepta checkout,
builds the real host binaries and runs their owning-package tests. It does not
create an authority or enable effects.

## Development

Use Python 3.9+, Git, Rust 1.88.0 for Desktop UI, Rust 1.95.0 for Hepta,
`just` and `cargo-nextest`. Linux GUI development also needs the packages in
[the UI runbook](../ui/RUN.md). Keep Cargo targets and generated receipts outside
both source repositories. All build and test commands use committed lockfiles.

Run the tool regressions from the Desktop repository:

```sh
python3 -B -m unittest discover -s support/release -p 'test_*.py' -v
```

The active manifest is
[`profiles/current-organ-source.json`](profiles/current-organ-source.json).
Check out its exact Hepta commit, with enough original history to prove the
history-owner ancestor. Commit all intended changes first. Verify the source
pair without running host programs:

```sh
python3 -I -B support/release/check_organ_pair.py \
  --os-repo "$PWD" --hepta-repo /absolute/path/to/hepta-private-ci \
  --os-head FULL_REVIEWED_DESKTOP_SHA --os-tree FULL_REVIEWED_DESKTOP_TREE \
  --manifest support/release/profiles/current-organ-source.json \
  --required-schema 5 \
  --output-dir /absolute/path/to/new-pair-receipt
```

Add `--execute-host` to build the actual UI binaries and original Hepta programs,
then run UI, adapter and the schema-selected owning-package tests. Add `--offline` only
after the exact committed dependencies are cached. A missing dependency is a
failure; the runner never replaces a lockfile or reduces the Hepta workspace.
The output directory must be new and outside both repositories. Each command
has a separate full log and SHA256 in `pair-receipt.json`.
`--desktop-target-dir` and `--hepta-target-dir` may reuse existing external
Cargo caches; source verification and locked dependency resolution still run.
Use `--build-host` for a binary-only rebuild (for example after final formatting);
it records `host-builds` and does not claim to have run tests. It cannot be
combined with `--execute-host`. `--hepta-profile dev` can reuse an existing
debug test cache; the default `dev-small` keeps CI binary sizes smaller. The real
paired-process fixtures require repeated full-file sealing, so their small-artifact
profile and bounded test-watchdog evidence must accompany runtime claims; a
large-debug-ELF timeout is not a successful run.

## Technical contract

`organ_release_profile.py` owns source identity verification. It requires clean
checkouts, full commit/tree identities, original history ancestry, regular
tracked files and byte-identical protocol goldens. The manifest records one
Hepta pin and selected source blobs; the final external receipt binds the
Desktop commit/tree without a circular self-hash.

`check_organ_pair.py` consumes that manifest. Commands are defined in code,
never supplied by a manifest. The default result is `source-only`. With host
execution, every command must succeed and the original source check must pass
again afterward before `host-build-tests` is recorded. A binary-only run uses
the narrower `host-builds` qualification. A compiler, test, timeout,
or generated source/lock drift failure records `qualification: none`.

The runner does not claim graphical pixels, a production Notes transaction,
kernel boot, or physical device qualification. Those lanes have their own
original-owner and device receipts, bound to the same source pair. In
particular, a fixture issuer is never relabelled as a production issuer.

When the protocol or build inputs change, update the reviewed source map,
generate and review a new manifest with the original source-profile tool,
commit it, and verify again against the final Desktop identity. Keep historical
profiles and receipts intact. See [the detailed source contract](../../docs/agents/ORGAN_RELEASE_PROFILE.md).

## Fixed V5 current source profile

The fixed [`organ_source_map_v5.json`](organ_source_map_v5.json) requires 396
Desktop roles, 261 Hepta roles and the same five golden pairs. It preserves the
reviewed 354/260 draft paths, adds each missing OOM/strict182 dependency once,
the three V5 release inputs and the original Root failure-report owner. The
canonical map seal and literal role sets reject optional roles, path aliases or
operator-selected variants. V5 reuses the qualified typed owner-path and whole
current-source verifier; its source proof does not qualify a new runtime pair.

`check_current_contract_v5` checks the current declaration before emitting its
one Hepta pin. All seven deployment inputs remain disabled. The seven-step host
runner preserves V4's eighteen packages and adds `codex-rmcp-client`; commands,
profiles, locked inputs, deadlines and zero retries remain defined in code.

The two existing CI workflows select V5 automatically. `source-profile-host`
keeps its stable check name as a summary and passes only when all six bounded
oracle partitions succeed: legacy, typed V4 and V5, each normal and optimized.
Each partition retains the original ten-minute limit; actual discovery must
equal their disjoint union, with the original 54/62 case IDs preserved.

V1–4 maps, manifests and explicit CLI verification remain available. The previous
current V4 manifest is archived byte-for-byte as
[`2026-10-27-organ-source-pre-v5-v4.json`](profiles/2026-10-27-organ-source-pre-v5-v4.json).
Manual historical V4 jobs require a complete forty-hex `historical_os_ref` and
check out that historical Desktop, then read its matching manifest and Hepta
pin. A new checkout plus an old archive cannot qualify that historical pair.
The unchanged seven `CurrentWorkflowTests` execute those retained V4 caller
blocks; new `Schema5WorkflowTests` execute the current V5 pin reader, source
guard and full dispatcher over owned fixtures. These are release-tool tests,
not Rust package or production transactions.

## Expanded source profile

Schema 2 uses the code-owned map [`organ_source_map_v2.json`](organ_source_map_v2.json).
It adds the X11 effect/observation wire golden, signed Objective inbox and submission
store, Binder byte transport, seccomp dispatch, page-table accounting, requester DMA
domains, trusted boot roles and boot identity. On the original Hepta side it binds
the Desktop consumer, native HOS2 owner, original Root service/issuer/clock/frontier,
checkpoint coordinator, SQLite pool guard and commit gate.

The source-profile builder selects this map with `--source-map`; the pair runner
selects one of the fixed map filenames from the manifest's integer schema
version. Missing roles, byte drift, an unsupported version or a version downgrade
cannot remove those checks. Schema 1 and its map remain available for historical
manifests. A schema-2 tool does not make a historical schema-1 pin describe new code:
generate a new manifest only after both intended source commits are frozen.

All schema versions keep production effects disabled and all seven deployment
inputs unconfigured in a source receipt. An independently tested Root fixture or
a successful compilation does not promote those fields. Actual deployment,
original-owner GUI tests, persistent guest storage, trusted-role execution and
cross-kernel Unknown recovery require separate evidence for the same final pair.

## Native owner source profile

Schema 3 uses [`organ_source_map_v3.json`](organ_source_map_v3.json), with 274
Desktop/kernel roles and 146 original Hepta roles. It also binds the actual Binder object and file lifecycle and FAIR execution-interval
settlement modules, their development/technical contracts and guest probes.
The affinity owner, permission/race contract and SMP probe/runner are required
roles, as are the Session observer and reconnect regressions and their module
contract. This keeps the target-process lifetime fix and bounded private test
socket paths inside the reviewed source combination.
The scheduling-policy access owner, all three mutation syscall entries and the
actual cross-user probe/runner/contract are required roles as well. The original
Hepta recovered-writer integration oracle is bound separately: its close barrier,
wrong-cut refusal and authenticated lease advancement must survive the pair.
It preserves the five protocol
goldens and adds the real native entry/runner, bounded ELF loader, per-frame
kernel-stack accounting, actual proc credentials, SGID inode publication,
interruptible group stops, original Root composition, Current publisher and cold
read-only SQLite recovery. Each role names one distinct tracked regular source
file. Source identity covers a file's bytes, not a claim that every behavior in
that file has been audited or dynamically exercised.

The 25 IPC additions bind the actual page-budget exports and per-frame tests,
Pipe and Unix Stream/Seqpacket allocation and publication paths, shared physical
ring storage, development/technical contracts, the IPC guest probe and runner,
and its Unix source-profile oracle. The already required page-budget owner and
bounded Unix guest runner keep their existing roles. The original Unix oracle,
probe, protocol, host tests and immutable historical control files are also
bound under distinct roles. These source checks do not claim complete
`memory.max`, general kernel-heap charging or a protected recovery reserve.

The 43 recovery additions bind the original Supervisor's durable intent,
release transaction, independent recovery verifier, actual daemon mutation gate
and typed Unix process driver; the legacy recovery CLI, real CLI/daemon and
paired-process regression fixtures, restart cases, package feature manifest,
technical contract and recovery runbook; and the original Fleet immutable-bundle
owner and copy regression. They also bind the changed Git/recall fixture sources,
Automation's actual store and historical migration regressions, every one of its
19 real SQL migration inputs, and the code-owned Nextest execution policy. An
unsigned exact-digest file still cannot settle an ambiguous production outcome.
A new commit label cannot reuse old role bytes, omit a migration or alias a
recovery role to another required source.

The fixed schema-3 host lane directly tests all thirteen original owning packages:
`codex-hepta-agentd`, `codex-hepta-memory`, `codex-hepta-cognitive-store`,
`codex-hepta-contracts`, `codex-state`, `codex-hepta-agent-protocol`,
`codex-hepta-learning-ledger`, `codex-git-utils`, `codex-hepta-memory-extension`,
`codex-hepta-automation`, `codex-hepta-fleet`, `codex-hepta-supervisor` and
`codex-arg0`.
It separately builds the original `codex-hepta-agentd`, `hepta-authority-host`
and `hepta-supervisor-intent-recovery` binaries. The recovery CLI has its own
`hepta-recovery-build` log and must compile before the owning tests can qualify.
The original arg0 helper/runtime dispatcher has its own required source role and
direct owning-package tests; an empty native path bundle cannot stand in for
that executable setup. A failed binary build stops the lane. `--build-host` selects the UI and all three
Hepta build steps and continues to record only `host-builds`, never a test pass.
The host lane retains locked dependencies, explicit toolchains,
separate external caches, no test retries, and source checks before and after
execution. Schemas 1 and 2 retain their earlier three-package host lane and
exact required role sets. Removing a schema-3 role, aliasing two roles to one
source or changing only a version number to downgrade a map fails before host
execution. Schemas 1 and 2 remain verifiable with their unchanged role sets. Earlier
schema-3 maps/manifests must be checked with their matching original frozen
version of this tool and source map; the expanded schema-3 role set deliberately
rejects an earlier incomplete role set. A current release that requires the expanded checks must explicitly
pass `--required-schema 3`; the runner then rejects an otherwise valid historical
profile before executing host commands. The current-profile CI and manifest must
adopt that requirement together.

The receiving expansion binds the actual FAIR/RT administration, cold capacity,
physical switch and affinity transaction, cgroup CPU owners, user-policy limits
and inheritance, and their real guest/host regressions. It binds the three
physical entropy entries, the module-documentation audit/evidence and UI contract,
and A02/A06 workflows and their actual runners, oracles and three new runtime
negative controls. Existing paths retain one role each; no alias is introduced.
The added Hepta roles bind the original owner-status diagnostic and its oracle,
deployment issuer and Root implementations/tests, production-authority regressions,
and the actual protected-clock observation boundary tests and Root service contract.
The production clock and writer keep their existing roles rather than aliases.
They are original source paths, not replacement fixture implementations. A08's
actual Java/JNI/build-tool preflight workflow and Android source-audit oracle are
also required; their source identity does not assert Android transactions or native
qualification. The minimum-horizon contract retains the fixed 500ms v2 freshness
and one-second durable ceiling; only separate exact-source tests can qualify its
runtime behavior.

This is a finite source-identity contract. It does not claim complete module
coverage, full `memory.max`, live non-root hierarchical `cpu.weight`, phone/GPU
support, real deployment grants or successful execution of each newly bound
file. Thirteen owning packages, five goldens, nineteen original migrations and
all seven disabled-production inputs retain their existing rules. Full test and
runtime qualification still require the exact final source/ELF combination.

The earlier current manifest is preserved byte-for-byte as
[`2026-10-26-organ-source-8542-fef6-v3.json`](profiles/2026-10-26-organ-source-8542-fef6-v3.json).
Its SHA256 is `d76299cd6fa63f7e1fa3de21e850f696986d6348094706ac727aa3f92e10eed4`.
Use the original `85425721` tools/map and its named source pair to verify that
archived schema-3 artifact. Updating these mandatory roles does not regenerate
`current-organ-source.json`; that file remains the prior reviewed pin until a
separate explicit final-pair generation and review.

The checked-in `current-organ-source.json` names its reviewed source pair.
Changes to required roles or source bytes require deliberate regeneration and
review against both frozen commits; changing the checker alone does not update
the pin or qualify a new pair.
The new manifest still records `source-only` and disabled production authority.
Only a later successful host run earns `host-build-tests`; native application,
same-disk restart/history, GUI device effects and real deployment evidence must
be recorded independently. A prior native failure and a successful compiler
run cannot be relabelled as a passing original-owner guest.

## Historical schema 4 candidate

Schema 4 uses the distinct code-owned
[`organ_source_map_v4.json`](organ_source_map_v4.json). Its current contract
contains 312 OS roles, 201 Hepta roles, the same five exact-byte goldens and the
same nineteen automation SQL migration roles. It adds the reviewed group/GDT
and Unix profile owners, original observation/checkpoint/thread-store owners,
compression/rollout sources and their oracles, fixtures and contracts. The
release tool, map, tool regressions and both release documents are also explicit
sources. The two CI callers and the exact previous V3 current manifest also have
distinct mandatory roles. The previous current bytes are retained at
[`2026-10-26-organ-source-1138-f397-v3.json`](profiles/2026-10-26-organ-source-1138-f397-v3.json),
SHA256 `805fdc48788d467d3eef27f4f573ee441d3250258e019f3e67a2c60336e77e3f`.
The retirement extension binds the finalized retirement sources, its distinct
90-owner Unix profile, and the real CAB84 archive/exporter: nine additional OS
roles, reusing seven existing roles for changed files. This records source
ownership, not a passing retirement/kernel matrix. Future OAuth paths require
their actual finalized source and an explicit reviewed addition; a planned path
is not accepted as an existing file. The prior 300/201 tooling receipts retain
their original source head and counts.

The V4 role sets are closed, and `SOURCE_MAP_V4_SHA256` fixes the complete
canonical role/path/golden map in code. Creation also reads the tracked V4 map
from the supplied OS checkout and requires the same reviewed contents. A CLI
source-map argument cannot replace required paths or provide accepted hashes.
The map contains paths rather than source hashes, so binding the tool and map
as source files creates no self-hash cycle. The external verification receipt
continues to bind the caller's exact OS commit and tree.

The historical V4 CI pin reader calls `check_current_contract` before selecting a
Hepta checkout. It requires the fixed V4 map, exact source/golden declarations,
complete Hepta identities, the external OS caller binding and all seven disabled
production inputs. Missing inputs, old/current schema confusion, duplicate JSON
keys, map substitution and production tampering stop before pin output.
This declaration gate does not prove repository bytes or ancestry; the real
pair runner still verifies both frozen repositories and requires schema 4.
CI path triggers cover every mandatory OS source, including both workflow
callers, documentation, evidence inventories and backend oracles.

V1/V2/V3 maps, role sets, command lists and archived bytes remain unchanged.
Historical verification uses an explicit archived manifest and its actual
original source/tool version. An old manifest can be valid for its historical
pair while being refused by the current-only CI entry point.

Freeze the code/map/doc commit, generate the V4 manifest outside both source
repositories, review that candidate, then commit only the new current manifest.
The manifest contains no OS head/tree; a fresh external receipt binds the final
caller commit after the pin commit. Committing the pin does not earn host or GUI
qualification. The final head must run the complete tool suite, fixed host lane
and isolated GUI checks again with before/after source and product bindings.

The V4 host lane is the fixed union of V3's thirteen Rust owning packages and
`codex-app-server-protocol`, `codex-thread-store`, `codex-core-plugins`,
`codex-rollout` and `codex-file-system`: eighteen distinct owners. It retains the
same three Hepta binaries, locked Cargo/Just commands, selected build profile
and pinned toolchains. Earlier schemas keep their exact original command lists.
Node consumer/SDK tests and provenance are separate evidence, not additional
Rust owners. Tool regression fixtures run real temporary Git histories and
bounded child commands; they do not claim that those Rust packages, a native
kernel or a production authority executed successfully.

The preceding Desktop `ac96fe6b818f72322268961ed5f66b53707a7723` / Hepta
`97c22293ba80af33dfc60a8b955fb63cf82be538` candidate completed seven host steps,
2,821 Hepta tests (55 original skips), and three isolated real GUI cases
(352 unselected tests). Those receipts keep that exact source identity. The GUI
issuer was an explicit qualification fixture; a current-pin commit cannot
relabel it as a production deployment. The separate b446 kernel receipt keeps
its own identity. Ordinary kernel access remains query-only; this release switch
adds no native durable control. Native authority and the seven real production
assembly inputs remain unqualified and disabled.

### Selected original-owner ancestry proof

Current V4 creation and verification require Git 2.43 or newer and local-only
object reads (`GIT_NO_LAZY_FETCH=1`); verification never repairs missing objects
by fetching them. Both checkouts must report nonshallow. That flag is not proof
that every historical object exists. V4 uses breadth-first search, in actual
parent-header order with strict LF separators, to find one real chain from the pinned HEAD to exact owner
`995b6fb9ef73ada7c3348b01deb28940a2c4a2d1`. Each searched commit is streamed and
SHA-1 verified; only the continuous parent block after its tree is an edge.
Missing candidate side commits may remain unknown; wrong types, bad hashes,
framing errors and late parent/tree headers fail. An unavailable unique owner
path fails. The search has a 16,384-header limit; exhausting it fails unproven,
without declaring a partial chain successful. Commit headers over 1 MiB fail.

A legitimate join may put the owner on its second parent and retain a different
older mainline as its first parent. Requiring every path to pass through the
owner would reject that real join. The earlier all-parent proposal, its passing
tool tests and its real missing-side-history rejection remain historical
evidence; they do not qualify this corrected scope. V4 no longer depends on
`merge-base` reading unselected history. It explicitly rejects existing graft
files and replacement refs, in addition to disabling replacements for reads;
the extra existence policy is new to V4, not a historical-reader claim.

After selecting the first chain, the verifier walks every chain tree/blob and
the owner, plus the complete current OS tree. A zero Git exit with `?OID` or any
stderr still fails: Git can report a wrong-kind object while returning zero.
Every listed tree/blob is streamed, type/framing checked and Git SHA-1 rehashed.
Tree bodies are decoded as mode/name-NUL/20-byte-ID entries across read boundaries;
headers over 1 MiB, unknown modes and malformed names/IDs fail. Each root must be
a tree. Every non-gitlink edge must name a listed object of its exact expected
tree/blob kind; conflicting kinds or omitted children fail. The parser retains
edge metadata, not full tree/blob bodies. Enumeration and a generic tree-or-blob
type allowance alone are insufficient. A missing selected-chain tree/blob fails
immediately without searching another path. Genuine local alternates are
permitted. Current-source snapshots compare the whole HEAD tree
and stage-zero index, all H flags, actual regular-file Git modes (owner execute
bit) and bytes and raw
symlink bodies before and after role/golden reads. Parent symlinks are not
followed. The receipt binds the complete inventory digest, including unmapped
files. Original roles, goldens and disabled-authority checks remain mandatory.

The V4 receipt's `git_object_closure.hepta` uses `proof_version: 2` and
`scope: selected_owner_ancestry_path`, with ordered owner-to-HEAD commits and
actual child/parent/index edges. Every unselected merge parent OID is explicitly
`not_verified`; its older trees/blobs and the owner's earlier history are
unknown. `missing_objects: 0` covers only the selected closure. The receipt also
records `all_parent_graph_verified: false`, current-source inventory evidence,
`whole_repository_history_complete: null` and `earlier_history: not_verified`.
Canonical `160000` gitlinks are opaque external commit edges; the tree/blob proof
does not open their target object stores or require subrepository history.
`gitlink_edge_count` and `gitlink_edges_sha256` bind their exact parent-tree,
entry-index and target-ID metadata. `gitlink_target_objects_verified: false` and
`gitlink_subrepository_history: not_verified` preserve that separate unknown.
It does not claim all reachable repository history exists or a build/test ran.
V1–V3 readers, manifests, receipt fields and historical shallow-history rules
remain unchanged. Do not regenerate an old manifest to make a new gate pass.

Missing required objects need genuine source data before qualification; the
verifier does not fetch it or demand unselected side history. Never invent a
parent, alter shallow/graft/replacement metadata, change the fixed owner, or
reuse an old successful receipt. Owned temporary Git regressions distinguish
real joins and unknown sides from missing selected commits/trees/blobs, malformed
parent headers, corrupt historical bodies and hidden current-source drift.

Run both interpreter modes for the complete tool suite:

```sh
python3 -I -B -m unittest discover -s support/release -p 'test_*.py' -v
python3 -O -I -B -m unittest discover -s support/release -p 'test_*.py' -v
```

The new regressions require every added role, reject missing or aliased files,
new-commit byte drift, unknown/schema-downgraded maps, duplicate JSON keys,
production tampering and unproved original ancestry. They also preserve exact
legacy map/archive/dispatch contracts, verify the tracked V4 map itself, and
reject source changes after host commands. The original seven production inputs
remain unconfigured and effects remain disabled in every schema.
