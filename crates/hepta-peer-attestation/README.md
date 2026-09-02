# hepta-peer-attestation

**Module registry ID:** `hepta-peer-attestation`  
**Workspace path:** `crates/hepta-peer-attestation`  
**Owner class:** `local-identity-security`

Pidfd/procfs/cgroup/systemd and executable/path attestation for an accepted Unix peer.

## Status and claim ceiling

**Current status:** `host_validated_identity_mechanism`

**Claim ceiling:** local Linux process/service identity attestation; no semantic principal, browser authorization, or production activation.

The status above describes the strongest repository-local statement this module may
make. It does not promote lower-tier source, host, headed-host, or QEMU evidence
into integrated-main, physical-hardware, signing-key-custody, or release facts.

## Responsibilities

- Bind SO_PEERCRED PID/UID/GID to bounded procfs snapshots, process start time, unified cgroup-v2 path, systemd unit, and pidfd liveness.
- Detect identity changes between pre- and post-policy snapshots and support dispatch-time refresh.
- Provide explicitly separate static executable binding features for D1 qualification and the D3 development profile.

## Non-responsibilities

- Attestation proves a mechanism identity, not an Agent semantic principal, capability, user consent, browser target, or external-effect authorization.
- Static executable binding is never enabled by default and is not production authority.

## Dependency and call direction

The crate consumes transport peer identity and Linux APIs. AgentPort apps and BrowserActor consume attested peers. It must remain independent of codec semantics, product policy, and browser runtime.

The authoritative workspace membership and review links are recorded in
`manifests/modules.v1.json`. New reverse dependencies, cycles, or authority-bearing
dependencies require an explicit architecture/security review.

## Public API and binaries

Key APIs read snapshots, construct exact service policies, attest a peer, retain an `AttestedPeer`, check liveness, and refresh identity before dispatch. Account resolution and trusted executable path/digest helpers are bounded and fail closed.

Public types and executable names are compatibility surfaces. Rust source remains
the API truth, while this document explains the intended boundary and correct use.
Callers must not infer authority from a type being constructible or a binary being
present in a non-production feature graph.

## Configuration and features

Expected users/groups, unit, cgroup, and trusted executable path/digest are explicit profile inputs. Features `qualification-static-attestation` and `development-static-attestation` select non-default code paths; they must never enter the default product graph.

All configuration inputs must be bounded, typed, documented, and included in the
applicable gate's invalidation set. Missing configuration must fail closed rather
than select a broader profile.

## State, concurrency, and failure semantics

An attestation is valid only while the held pidfd remains alive and refreshed identity equals the admitted snapshot/policy. PID reuse, start-time drift, UID/GID drift, cgroup/unit movement, executable/path replacement, symlink, ownership, or writability mismatch invalidates it.

Rejected transitions and failed validation must not leave partial authority,
advanced revisions, committed responses, or invented receipt outcomes. Where a
result may be indeterminate, the caller must preserve that state and follow the
documented reconciliation policy instead of retrying blindly.

## Security invariants

Read procfs files with strict byte limits; compare all real/effective/saved/filesystem IDs; reject ambiguous cgroup entries; hold pidfd across checks; use no-follow/root-owned non-writable trusted paths for static modes; re-open and re-hash at dispatch.

The relevant contracts and architecture documents are listed in the module
registry. A source-only self-check or fixture never proves enforcement by a booted
product image.

## Testing and evidence

Run synthetic procfs parsing, PID/start-time/cgroup/unit mismatch, path traversal/symlink/ownership/writability, digest replacement, and dispatch refresh tests. Systemd custody and D3 profile workflows must exercise the selected mode.

Minimum local verification:

```bash
python3 tools/validate_module_documentation.py
python3 tools/validate_repository.py
python3 tools/validate_project_truth.py
cargo fmt --all --check
cargo check --workspace --all-targets --all-features --locked
cargo clippy --workspace --all-targets --all-features --locked -- -D warnings
cargo test --workspace --all-targets --all-features --locked
```

Interpret every result under the claim ceiling and evidence tier recorded by the
gate registry. A skipped, cancelled, historical, or differently bound run is not
current evidence.

## Operations and troubleshooting

On denial capture only bounded identity metadata and the exact mismatch class. Verify kernel peer data first, then pidfd, procfs IDs/start time, cgroup/unit, executable/path digest, and post-check refresh. Do not grant ptrace capabilities as a shortcut.

Troubleshooting must preserve the original files, journals, identities, and exact
Git/build context needed for diagnosis. Do not make a gate pass by deleting a
hostile test, bypassing an admission check, broadening permissions, substituting a
fixture, or editing generated evidence by hand.

## Compatibility and change protocol

Linux file formats and unit-path assumptions are explicit compatibility surfaces. Kernel/systemd changes require fixture updates and image evidence. New static modes require a distinct Cargo feature, profile, threat review, and final-image audit.

Every behavior-changing pull request must update, as applicable: implementation,
contracts/schemas, golden vectors, tests, module registry, this README, architecture
and threat documentation, gate invalidation paths, evidence, and explicit
non-claims. Exact-head review and exact-main reruns remain separate promotion
transactions.
