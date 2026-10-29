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

The fixed [`organ_source_map_v5.json`](organ_source_map_v5.json) requires 402
Desktop roles, 271 Hepta roles and the same five golden pairs. It preserves the
reviewed 354/260 draft paths, adds each missing OOM/strict182 dependency once,
the three V5 release inputs and the original Root failure-report owner, plus ten required CLI producer dependencies. The
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


## Required CLI producer for the corrected V5 candidate

The undelivered V5 current contract now fixes 396 Desktop / 271 Hepta roles.
Its ten new explicit Hepta roles bind the normal CLI manifest/build script,
main/library/exec-server lifecycle sources, the RMCP package and original three
remote integration tests/support, and the original Cargo binary resolver.
The whole-current-source proof still binds all remaining transitive sources.

`codex-rs/rmcp-client/tests/streamable_http_test_support.rs:338` starts the real
`codex exec-server --listen ws://127.0.0.1:0` through the original
`codex-utils-cargo-bin` resolver. `codex-rs/cli/Cargo.toml` declares package
`codex-cli`, binary `codex`, normal `build.rs`, `src/main.rs` and `src/lib.rs`;
`src/exec_server_telemetry.rs` owns the dispatched service lifecycle. These are
unchanged original Hepta sources, not a replacement fixture executable.

V5's required `hepta-build` step selects exactly this package/bin union:

```sh
cargo +1.95.0 build --manifest-path codex-rs/Cargo.toml \
  -p codex-hepta-agentd --bin codex-hepta-agentd -p codex-cli --bin codex \
  --profile dev-small --locked --offline
```

Run it in the exact original Hepta checkout with the same external target and
profile as `just test`. The seven-step lane and nineteen test-owning packages
remain unchanged; CLI is a required producer, not a twentieth test owner.
Its failure stops Root/recovery builds and owning tests. Never inject an old
executable, change a binary-resolution environment variable, filter the original
remote tests, increase deadlines or turn retries on to qualify this dependency.

The original 7673 nineteen-owner run retained 3,088 actual tests: 3,085 passed
and three `streamable_http_remote` failures with the CLI producer absent.
Its three binary builds passed. Those failed receipts stay failed. A separate
later CLI build or three-case diagnostic cannot replace a complete successful
seven-step final-pair receipt. This source-only update performs no Rust build,
GUI transaction, native run or production activation.

The frozen earlier source-only V5 snapshot is Desktop
`f4cd75ea96ff452176758e9fb48d4842bf1be859` with Hepta
`7673ea62fc019f97ad17d205ee1f81f96e0f47a0`, its original 396/261 map, exact tool
and `60b7ecd2a57597ceb8825a616b7ee7f034a4ea3ec3acaa282e87547be5e9e244`
manifest SHA256. Verify that historical snapshot using its f4cd tool and pins.
The corrected current fixed 271-role tool refuses the old 261-role V5 shape;
it does not claim latest-tool compatibility with that old V5 declaration.
V1–4 maps, explicit routes and exact command lists remain unchanged. All seven
production inputs remain disabled in both source-only snapshots.


## XKB CI dependency successor and retained environment failures

The new CI-only code baseline is Desktop
`8b825fb742b4722259a7fd7b962565adf21d2fff`, tree
`a4df7550ee172cd91535ce980a299526fb67c09f` (8,088 tracked paths),
with Hepta `7673ea62fc019f97ad17d205ee1f81f96e0f47a0`, tree
`ff2372f10656d2e8f652b6ca1e6de03a075b9219` (9,214 paths).
Relative to frozen Desktop `6487830799a6417b554bf06bedfbab99498196c0`,
the code delta is only `libxkbcommon-x11-dev` in three Linux apt lists:
one in `.github/workflows/a10-host.yml` and two in
`.github/workflows/organ-current-pair.yml` (current V5 and historical V4).
All three retain `libxkbcommon-dev`. The X11 package supplies the runtime
and unversioned soname needed by the existing original X11 smoke. This source
change has not installed a package or run CI, Rust, a product, GUI or native guest.
The host dependency contract is in `support/ui/RUN.md`.

The fixed V5 map remains 396 Desktop / 271 Hepta roles, five golden pairs and
nineteen owning packages. Stage 4 still builds normal `codex-cli` / `codex`
alongside `codex-hepta-agentd`; CLI remains a required producer. All original
commands, test cases, budgets and zero-retry rules remain unchanged. All seven
production inputs remain disabled. The current manifest retained from frozen
6487 is not a source qualification for this changed tuple: the typed source
manifest and external whole-source receipt must be rebound after documentation
is committed. `MODULE_DOCUMENTATION_CURRENT.json` uses the code-baseline /
documentation-successor convention; the final documentation HEAD/tree is bound
externally, without a self-referential pin. Historical snapshots and results
remain attached to their original sources.

The actual original seven-step attempt 01 on frozen 6487 / 7673 failed at
stage 1, `cargo build --manifest-path ui/Cargo.toml --workspace --bins --locked
--offline`, under Rust 1.88.0: Cargo exited 101 because the offline archive
`ab_glyph 0.2.32` was unavailable. The wrapper exited 1; stages 2 through 7,
new test cases, retained products, SDK, GUI and native guests did not execute.
The actual sources before and after were unchanged. The independent failure
audit is `work/goal-logs/release/final-v5-7673-seven-step-host-01/independent-terminal-audit.json`,
SHA256 `1a4a2ed45adaa503727e43d7a274209d8376f29b22f9c0889375e0eece0f009e`.

The separate cache repair attempt 01 also exited 1. It reported 43 completed
archive publication steps; step 44 downloaded and retained
`icu_properties_data 2.3.0` but failed to publish it because the default Cargo
cache directory was absent. The disappearance's cause is unknown. The retained
payload's checksum does not prove that publication or final offline resolution
succeeded. Its independent failure binding is
`work/goal-logs/release/ui-locked-cache-repair-01/independent-review-01/independent-failed-repair-binding.json`,
SHA256 `b2f23e8f3533d95f41115ce303c4f585b2d76a035ea2600a10ab310cff46d78c`.
Neither attempt qualifies a new product pair. A separate private cache must
first resolve the Linux UI tree including development dependencies, the normal
Hepta producer graph and exact nineteen-owner graph with the original flags;
no success for that preparation is claimed here. The original complete seven
steps and separate GUI/native gates still require their own exact-source runs.

The unchanged original Python tool cases passed on the 8b825 code baseline:
normal 54 / 7 / 24 and optimized 54 / 7 / 24, each with the original
600-second lane budget, zero skips and zero retries. Every lane
checked the complete 8,088 actual source paths before and after and
matched the prior original case identities. Completion SHA256:
`76c46b6498a0a4de14a92f897c08a99b8ad17d70b0f024b8d3e62ccde6b2e33b`. These are release-tool temporary-Git / bounded-child
fixtures, not a Rust/product or full 140-case-per-mode CI-union pass.


## Eight package manuals on the Hepta documentation successor

The current module navigation now links the eight new package READMEs on
Hepta `310c3c86a59472665c2bb4cf4fb1d515def9dd37`, tree
`6502ac49b5f3133bf2fc826ce3c07d90219a3a48` (9,222 tracked paths).
Its code baseline remains `7673ea62fc019f97ad17d205ee1f81f96e0f47a0`:
all original 9,214 actual source bodies/modes/blobs are preserved, with eight
new READMEs containing concrete technical and development sections. This is
documentation source qualification only. Added READMEs may change Cargo's
automatic readme/package metadata; no binary equivalence is asserted.

The module inventory retains its original 336 source records and adds eight
README records, each bound to its actual 310c blob/mode/SHA. Original code and
new documentation provenance remain separate. The 131 local link/line-anchor
and 27 historical case-identity checks are reference checks, not test execution.
The unwired cognitive `production.rs` is documented as an uncompiled surface,
not a proven defect. File-system has no library/doctest target on this baseline;
its real executor consumer tests remain a separate unexecuted development lane.

The fixed 396/271 role map, five goldens, nineteen test packages, required normal
CLI producer and both lockfiles remain unchanged. The retained current profile
still declares old 6487/7673. A later source-only generation/manifest-only commit
and exact new-HEAD verification must bind this Desktop documentation successor
with 310c. No source proof, host/GUI/native/product run or production activation
was performed for this navigation update. Old full19/target3/native outcomes and
the 8b825 Python QA keep their original source identities.

See [current package manuals and source boundaries](../../docs/agents/MODULE_DOCUMENTATION_CURRENT.md).


The current V5 CI caller retains a separate `organ-pair-invocation` directory
with the exact command exit code and stdout/stderr even when source verification
refuses the pair before creating its protocol output directory. That invocation
receipt never infers host qualification; the original nonzero status still
fails the build step. Uploading the refusal evidence does not turn refusal into
a passing source or product check. Historical V4 dispatch remains unchanged.

A change to a mapped QA source also changes the source-only contract. After the
code commit, regenerate the fixed V5 manifest against the actual Desktop code
head and the single pinned Hepta source, commit only the manifest, then verify
from that final head/tree. The manifest has no own source role and binds Desktop
identity through the explicit caller head/tree in the verification receipt;
this is why the final verification must include the newly committed manifest.
Keep all original maps, seven stages, eight products, 19 selected test owners,
budgets and disabled production inputs. Earlier host results retain their
original source tuple and do not qualify a successor by association.

## M6 delivery source contract

The current fixed V5 requires 402 Desktop roles, 271 Hepta roles, five unchanged
wire-golden pairs and nineteen unchanged owning packages. Six explicit roles
bind the real Unix datagram message owner, its eight native tests, the original
ordinary probe and runner, and the technical/development manuals. Existing IPC
and page-memory contract roles bind their updated documentation. Required
normal CLI production, all seven host commands and their budgets are unchanged.

The prior 396-role V5 is retained by Git at Desktop
`9088f2e5ef5666859ffe76ffb4db3c58e0733497` with its then-matching source tool,
map and `profiles/current-organ-source.json` (relative to `support/release`).
Use that exact historical checkout for its verification. Removing the six M6
roles from the current map is an unsupported current shape. V1–V4 routes and
all old refusal assertions remain unchanged.

The original M6 commits are 5d82e62e2141a280931866251aa8a39a6e6d064e and
8a1ea448fc58a47f9a36800a52bfc9c63ef7c763. The delivery integration preserves
their production/native/probe inputs; their historical passing kernel and
ordinary receipts remain tied to 8a1. Source-only QA and manifest generation do
not transfer those results to a new head. The actual combined candidate must
repeat the full unfiltered Core/OSTD and both ordinary SMP2/SMP4 seven-group
profiles under their original budgets. Linux `memory.max`, production-authority
assembly, real Agentd control and phone/GPU isolation remain separate work.

## V5 host ELF identity: technical contract

The host receipt is version 2 only when this runner actually selects a V5
`--execute-host` or `--build-host` lane. Source-only receipts and historical
V1–V4 host receipts retain version 1. The source manifest remains fixed V5:
402 Desktop roles, 271 Hepta roles, five wire-golden pairs and nineteen owners.
No historical receipt is rewritten, and its successful commands do not acquire
product hashes retroactively. A new real CI run is required for this contract.

After the original seven successful host stages (or four build-only producers),
the runner opens exactly these eight products from the actual `CARGO_TARGET_DIR`
used by their commands. Desktop uses `debug`; Hepta `dev-small` uses `dev-small`,
and Hepta `dev` uses `debug`:

| Product | Target side | Original producer | Toolchain |
| --- | --- | --- | --- |
| `trill-ctl` | Desktop | `ui-build` | 1.88.0 |
| `trill-session` | Desktop | `ui-build` | 1.88.0 |
| `trill-shell` | Desktop | `ui-build` | 1.88.0 |
| `trill-app-window` | Desktop | `ui-build` | 1.88.0 |
| `codex-hepta-agentd` | Hepta | `hepta-build` | 1.95.0 |
| `codex` | Hepta | `hepta-build` | 1.95.0 |
| `hepta-authority-host` | Hepta | `hepta-root-build` | 1.95.0 |
| `hepta-supervisor-intent-recovery` | Hepta | `hepta-recovery-build` | 1.95.0 |

Successful version-2 receipts add `host_products`, an ordered list with each
product's name, producer stage, side, Cargo profile, toolchain, absolute target
directory, profile directory, absolute path, complete SHA256, byte count,
permission mode, ELF magic, and observed device/inode/uid/gid/mtime/ctime/link
count. `host_products_verified_after_source_recheck: true` means the retained
descriptors and current paths matched after the original source/lock recheck.
Any missing, non-ELF, non-owner-executable or changed product refuses host
qualification, even when all command exits were zero. A refusal has
`passed: false` and `qualification: none`; it cannot substitute old product
hashes or infer success from an earlier receipt.

The Linux observer walks every absolute parent through retained nofollow
directory descriptors, rejects symlinks and non-regular leaves, hashes all
observed bytes plus EOF and checks ELF magic. Leaf device, inode, mode, owner,
size, mtime, ctime and link count must remain equal before/after both full reads.
The final source recheck runs between those reads. Fresh nofollow path walks
before and after the final read must match the retained parent device/inode/mode
and leaf identity. Parent mtime/ctime are deliberately excluded because writing
this invocation's receipt/logs can change them. Cargo's stable hardlinked
outputs are accepted and their link counts recorded; link-count changes refuse.

This is an observation of the actual selected build outputs, including when an
explicit external Cargo cache is used. It is not isolation against a malicious
same-UID process, binary reproducibility, a trusted publisher signature, native
Windows or kernel qualification, production authorization, or a Notes runtime
claim. No fallback chooses an ELF from another target or an old receipt.

The seven original commands, package selection, toolchains and timeouts are
unchanged. ELF reads and the final source check consume the remaining budget of
the last executed original stage; no new time allowance or retry is added.
Reads stop at the sampled size plus EOF and check the deadline between reads;
this does not promise cancellation of a synchronous kernel read that blocks.

## V5 host ELF identity: development and verification

`host_product_specs` owns the eight paths; manifest content cannot add an
executable, select a different product, or replace the command list. Changes to
this observer, its tests, this manual and the already-mapped workflow require a
new strictly generated current V5 manifest, followed by verification at the final
clean Desktop head/tree against the one pinned Hepta head/tree. Fixed source-map
roles, old manifests, golden bytes and their historical owners remain intact.

Reporter tests use real copies of the local Python ELF in owned temporary
directories. They exercise the same descriptor/stat/hash path as production,
including stable Cargo-style hardlinks and real file truncation, growth,
symlinks, FIFOs, leaf replacement and parent movement during hashing. Copies
are only reporter fixtures, never evidence that eight Rust products were built.
V5 pair fixture tests still execute bounded real child commands, then create
these owned reporter fixtures; the production runner has no fixture override.
The unchanged original test functions and assertions continue to run.

The workflow retains the exact original 54 legacy case IDs and SHA256
`20011921d9f6abdb12fe852abaa62c3cccd7ea03e7a906707b9b7fad3f417d38`,
then requires all twenty explicitly enumerated new reporter cases. The original
62-case V4 identity hash is also unchanged. All 74 legacy, 62 V4 and 25 V5 cases
form an exact disjoint 161-case discovery union per normal/optimized mode;
no prefix-based exclusion can hide a missing or unexpected test. Each original
lane keeps its 600-second budget, zero skips and zero retries. Passing these
Python fixtures qualifies the release tool source only. The eight real ELF
identities must still come from the next complete real host execution.
