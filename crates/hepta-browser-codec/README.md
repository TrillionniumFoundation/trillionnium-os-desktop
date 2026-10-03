# `hepta-browser-codec` technical development contract

The codec is the sole boundary allowed to turn untrusted Browser API bytes into typed requests and responses. It owns a strict JSON implementation, closed operation shapes, canonical re-encoding, semantic-reference and URL validation, stable error/retry taxonomy and canonical SHA-256 inputs for later receipts.

This document is normative for source maintenance at the recorded claim ceiling. It does not replace `manifests/project-state.v1.json`, the gate registry, live GitHub state, exact-head evidence, installed-image qualification, or an authorized release record.

## Status and claim ceiling

Status: `candidate_canonical_browser_wire_boundary`  
Claim ceiling: `bounded canonical Browser API parsing, validation, encoding, hashing and risk classification only; no listener, peer authorization, BrowserActor dispatch, Servo execution, external effect, installed image, hardware, signing, publication, or release authority`

A narrower machine-state, gate or non-claim always wins. Source presence and documentation completeness do not promote runtime or release authority.

## Responsibilities

- Reject invalid UTF-8, BOMs, duplicate members, floats, non-canonical key order, unknown fields and trailing bytes.
- Apply equal byte, depth, item, key and string limits to decoded input and programmatically constructed output.
- Validate request/session generations, semantic references, action fields, timeouts and URL authorities.
- Classify operations as observation, local interaction or potential external effect without authorizing them.
- Produce byte-for-byte canonical JSON and its digest.

## Non-responsibilities

- Do not create sockets, select a peer/principal, start Servo, dispatch BrowserActor or grant a capability.
- Do not treat HTTPS syntax as proof of resolver, redirect, connected-peer or TLS trust.
- Do not provide raw JavaScript evaluation or permissive unknown-field compatibility.

## Dependency and call direction

Transport hands opaque bytes to this crate only after mechanism admission. AgentPort consumes the resulting typed request and copies validated identity into the response. BrowserActor may consume only decoded types. The codec depends only on exact `sha2`; it must not depend on applications, network stacks or Servo.

Relevant architecture:

- `docs/architecture/CANONICAL_BROWSER_CODEC.md`
- `docs/architecture/RUST_BROWSER_CODEC.md`

The dependency direction is one-way. Lower-level mechanism and contract crates must not import application, profile, image, hardware, signing, or publication authority.

## Public API and binaries

- `decode_request`, `decode_response`, `encode_request`, `encode_response` and `self_check` are the primary entry points.
- `BrowserRequest`, `BrowserOperation`, `BrowserResponse`, `BrowserWireError`, `ElementReference`, `NavigationTarget`, `PageAction` and `WaitCondition` are wire-domain types.
- `JsonValue` and `JsonObject` are bounded canonical values, not general JSON containers.
- Resource constants are mirrored by `browser-codec-resource-limits.v1.json`.

This library registers no binary target. Cargo binary auto-discovery and package build scripts are disabled.

## Configuration and features

The crate has no features or runtime configuration. All limits are compile-time reviewed constants. External URLs are credential-free HTTPS syntax; fixture URLs are loopback HTTP only. Network access remains disabled elsewhere until controlled egress is implemented.

Registered Cargo features: none.

## State, concurrency, and failure semantics

Codec operations are pure with respect to product state. Parsing uses bounded recursive accounting; encoding revalidates constructed values so internal callers cannot bypass parser limits. Failures return typed `CodecError` and produce no partially validated request.

Failures must preserve the last truthful state. A timeout, crash, peer loss, storage ambiguity or unsupported operation cannot be converted into successful completion by a caller, retry loop, fixture, log message or evidence generator.

## Security invariants

- Received bytes must equal canonical re-encoding; attacker-selected formatting is never hashed as authority.
- Recursive duplicate-key rejection and signed-64-bit numeric rules must remain aligned with the independent Python reference.
- URL validation rejects userinfo, backslashes, control characters, invalid ports, ambiguous IPv6 and non-loopback fixtures.
- Semantic actions require non-zero published revisions; the engine must still re-resolve atomically.
- Every navigation/click/type/press/select remains a potential external effect.

Every invariant above is a review condition, not merely commentary. Weakening one requires a new threat analysis, hostile regression and explicit claim-ceiling decision.

## Testing and evidence

Primary source or test references:

- `crates/hepta-browser-codec/src/tests.rs`
- `tests/test_validate_rust_browser_codec.py`

Applicable workflows:

- `.github/workflows/browser-codec-reference.yml`
- `.github/workflows/ci.yml`

Contract references:

- `contracts/browser-codec.v1.json`
- `contracts/browser-codec-resource-limits.v1.json`
- `contracts/browser-api.v1.schema.json`
- `contracts/browser-wire.v1.schema.json`

A passing unit or hosted-CI test proves only the evidence tier named by its gate. Any source, workflow, dependency, base, head or claim change invalidates earlier evidence according to `manifests/gates.v1.json`.

## Operations and troubleshooting

- Run the codec workflow, Rust tests, Python differential/reference tests and source audit.
- Execute the validator with `PYTHONPATH=.` or as `python3 -m tools.validate_rust_browser_codec`; direct-script behavior is also regression-tested.
- A golden mismatch requires regenerating only through the deterministic reference tool and reviewing the semantic change.
- Do not edit checked evidence to make an old host result appear current.

Operational diagnosis must retain bounded/redacted evidence and must not weaken admission, limits, ownership, sync, isolation or default-disabled controls simply to make a test pass.

## Compatibility and change protocol

Wire changes require a versioned schema/contract and explicit compatibility window. Unknown fields remain rejected. Any divergence between Rust, Python reference, JSON schemas, golden vectors or resource manifest is a release blocker.

Required change sequence: update implementation and Cargo metadata; update machine contracts and hostile tests; update this README and `manifests/modules.v1.json`; run module, repository, project-truth and Rust checks; obtain independent review on the immutable final head; then perform the required exact-main or higher-tier rerun after protected promotion.

The versioned CI required-context source inventory in
`contracts/ci-required-contexts.v1.json` and
`docs/architecture/CI_REQUIRED_CONTEXTS.md` gives every original workflow job
a distinct proposed GitHub display context and expected application source.
`tools/verify_ci_required_contexts.py` checks that closed correspondence;
`tests/test_ci_required_contexts.py` exercises hostile names, matrices, source
bodies, catalog aliases and real filesystem replacement. This source index
provides no configured protection, independent approval or G0 closure.


### CI-only namespace configuration source candidate

`contracts/ci-namespace-python.v1.json`, `tools/verify_ci_namespace_python.py`, `tools/ci_namespace_python.py`, `.github/apparmor/hepta-ci-namespace-python.v1.profile` and `tests/test_ci_namespace_python.py` register the job-private interpreter configuration. The two existing `ci.yml` source jobs run the fixed checker before setup and always run fixed-system-Python cleanup after the unchanged full corpus. The real root-owned interpreter byte copy retains the normal runner UID/GID and standard-library prefixes; the named temporary debugging profile attaches only that unique path. Global AppArmor/sysctls, original workers and tests remain unchanged. Run `python3 tools/verify_ci_namespace_python.py` or the existing `make check` discovery to check source/ordinary-FS correspondence. Do not invoke privileged setup outside its fixed CI context. The unchanged `make validate` target does not separately register this CI-only gate. The helper/profile have not been activated in author validation, and no hosted, crypto-consumption, native, installed or production result follows from these tests. Architecture details and the preserved hosted failure are in `docs/architecture/MOZJS_AUTHENTICATED_INPUT.md`.


### Four affected source jobs: expanded CI-only candidate

The configuration now covers four literal workflow/job pairs: `ci / repository-contracts`, `ci / repository-contracts-prospective-merge`, `g2-approved-native-startup / source-prospective`, and `g2-native-product-owner / source-prospective`. The two G2 source jobs execute the original complete Make corpus, so they require the same named private-interpreter preparation and always cleanup. Their original exact-pin owner bodies, native cases, flags and deadlines remain byte-preserved. The bounded fixed repository/file/ref check selects the literal workflow stem; profile and directory names include workflow, job, actual run ID and attempt, so the two same-named G2 jobs have distinct attachments. Ref text never becomes a pathname. GitHub documents `GITHUB_WORKFLOW_REF` as repository/workflow-file plus ref; supported PR merge syntax is `refs/pull/<positive-number>/merge`. The actual hosted values and profile permission still require new-run readback.

The earlier two-job source object is historical, rather than four-job qualification. The existing additional source failures are preserved under `work/round14-source650-hosted-failure-logs-1791022023626787005`; their raw SHA256 observations are retained externally without rewriting escaped traceback output. All five source failures were reported for the original readonly namespace case, before actual snapshot/capability-drop completion. This four-job candidate has performed only source and ordinary-file/model tests. It has not loaded a profile, invoked privileged setup or cleanup, created a new namespace, rerun Actions, or executed Cargo/native cases. Default Make discovery runs the tracked source-gate/negative tests; the unchanged Make validate recipe does not separately claim this CI gate. Neither the historical local Root success nor the new source checks establish hosted permission or production readiness.


### CI-only serialized retirement ledger

The current four-job candidate adds a minimal non-secret root-owned retirement ledger, rather than claiming all root state is deleted. Its unique derived directory is mode0700, with a mode0600 create-new lock and finite `STARTED`/`READY`/`RETIRED` JSON. Setup and cleanup acquire a nonblocking flock on the same inode; state pins that inode. The actual setup worker PID/start ticks/PGID/SID and executable identity are written before any parser/profile action. Cleanup refuses a held lock, unknown or interrupted state, any remaining recorded setup session/group member, matching setup command, named-profile descendant, private executable inode or mapped private ELF. It checks absence before unload and again after unload/retirement. Timeout proves only the direct child was waited, rather than descendant termination; there is no broad process kill or cleanup retry that hides errors.

After validated removal of the private interpreter directory and active named profile, only the tiny readonly-by-policy `RETIRED` deny ledger remains. Early cleanup also creates this tombstone: a delayed setup cannot recreate the namespace because setup requires create-new allocation, and phase revival is refused. No interpreter bytes, active profile, secret or production trust is retained in the ledger. Ordinary-file/model tests exercise real lock contention and phase/identity refusals, while root ownership, process inventory and parser activation are substituted explicitly. This source candidate still has no actual privileged setup, profile activation, new namespace, hosted permission, native or production qualification.
