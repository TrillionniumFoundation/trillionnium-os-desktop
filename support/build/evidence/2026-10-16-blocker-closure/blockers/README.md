# A01 remaining-blocker ledger

This archive binds diagnosis to committed source `350d98d70a3d7b7c720cabd7720063849afb5a29`, tree `073bcd257facb6213bddbd20093bf5a699a1b074`. It is **read-only diagnostic evidence**, not a new build, QEMU result or claim that all blockers are closed. [Machine ledger](ledger.json) records each owner, observed failure or missing acceptance, exact next commands/change ranges and closure criteria. No blocker is marked closed by this packaging task.

The supplied [host capability probe](environment-capabilities.json) identifies `29609d47ba8e`: `/dev/kvm` absent, AF_UNIX `socket()` denied with EPERM, `socketpair()` succeeds, `CapEff=0`, `Seccomp=2`, and the observed virtualization flag list contains `npt` without `vmx`/`svm`. The distinction between socket APIs matters; a socketpair result cannot qualify the default UNIX socket-based OSDK cases. These probes were executed by the parent, not repeated here.

| ID | Remaining item | Owner | Snapshot state | This environment |
| --- | --- | --- | --- | --- |
| B01 | Strict ABI Clippy diagnostics | A02, A00 | open-source-diagnostics | yes, after owner integration; not an A01-owned source edit |
| B02 | Two default OSDK UNIX cases | A01, execution-platform owner | blocked-by-current-host-AF_UNIX-socket-policy | no for default profile; supported TCP/GDB profile is already an alternative passed scope |
| B03 | Three VMX/EPT kernel soft skips | A01, A09, isolated-hardware owner | hardware-path-not-exercised | no with the observed current host capabilities |
| B04 | Different compiler-visible source paths | A01, A00, comp-sys owner | unproven-needs-coordinated-identity-change | analysis/support normalization yes; actual arbitrary-path closure requires coordinated source work |
| B05 | Independent hosts and immutable environment | A01, A00, execution-platform owner, OSDK build owner | unproved-second-host-and-environment-lock | partial inventory/design only; one identified host is available here |
| B06 | GitHub Actions queued / unverified current state | A00, repository runner administrator | latest-historical-read-was-four-queued-current-not-queried-by-this-task | GitHub readback possible through existing connector; no runner admin action performed |
| B07 | A04 same-ELF four compatibility failures | A04, A00, kernel syscall/file/socket owner | two-completed-failures-two-timeouts | can replay historical proof with prepared rootfs; source corrections require owners |
| B08 | Historical external generated-manifest writer | A01, execution-platform owner | writer-unidentified | safe isolation and further bounded observation yes; retrospective attribution unavailable |
| B09 | G1 native HOS2 CapSpace/ioctl five operations | A05, A02, A03, A00 | project-implementation-and-acceptance-open | build infrastructure available; A01 must not overwrite core owners |
| B10 | G1 actual CPU budget final charge and scheduler coverage | A06, A05, A00 | owner-branch-work-not-equivalent-to-main-acceptance | can build/test coordinated owner head; not an A01 runtime source edit |
| B11 | G2 original Hepta durable owner integration | A07, A03, A05, A06, A00 | project-implementation-and-acceptance-open | support builds and host experiments possible; complete implementation is owner work |
| B12 | Bare-metal/GPU/Android/UI expansion | A08, A09, A10, A00 | separate-G3-future-acceptance | not provable from current TCG build environment |

The source and ownership boundary is the current agent plan (`docs/agents/PLAN.md`), not an implicit reassignment of A05/A06/A07 runtime code to A01. G1/G2 and G3 remain explicit project work; A01's real minimal build/boot does not establish those capabilities. Historical results retain their exact source, denominator and artifact. In particular, 362 reported kernel passes include three soft skips, leaving an exercised passed lower bound of359; the A04 historical 28-case run remains 24 matches, two completed failures and two timeouts. Neither set is rerun by this archive.

## Reproducibility and environment

The supplied [analysis](repro-analysis/REPORT.md), original [machine report](repro-analysis/report.json) and original [checksums](repro-analysis/SHA256SUMS) are copied without modification. They identify absolute Cargo package paths emitted as ordinary macro literals, `file!()` registration/runtime-key coupling and OSDK's whoami-derived embedded builder identity. Simple Rust compiler path remapping does not establish the required common component identity. A canonical fixed-root staging route can normalize origin checkouts while keeping the same compiler-visible path; that is a useful narrower property, not arbitrary-path proof. Genuine independent-host evidence also needs a second identified execution surface and a complete immutable environment. Tool presence does not prove namespace permission.

Native dependencies and real kernel/QEMU execution already worked in prior evidence. A missing Docker/Nix executable does not make an ISO download or privileged container a prerequisite for minimal boot. The baseline `build_container_digest=null` and `reproducible_kernel_build_ready=false` remain accurate for broad reproducibility; no value is fabricated here.

## Cloud configuration and CI scope

Read-only inspection of tracked project configuration found four top-level workflows selecting `ubuntu-24.04`; no project-owned self-hosted label, SSH/tunnel endpoint or IaC connection was identified. The upstream `.devcontainer` is a local development image using host bind mounts, not remote-cloud access. Historical paths or an old unavailable tunnel in STATUS are not credentials or a connection command. No credentials were read and no network was scanned.

This subtask did not fetch GitHub state. The last publication report said four jobs queued. The current exact-head state must be read through the existing GitHub connector; see B06's API routes. Local passing tests do not turn queued CI green, and neither security settings nor success statuses should be changed to manufacture closure.

## Historical external writer

Known source/driver inspection did not identify the process that recreated the historical manifest pathname as inode1581801 after the owned inode1581799 was removed. `kernel.sh` publishes its own temporary inode; cleanup has explicit custody and no-overwrite restoration of a foreign entry; OSDK manifest loading only reads; explicit `cargo osdk new` can write templates. The inspected followup/pair controllers do not provide causal attribution. Existing foreign entries remain preserved. Safe disposable worktrees and correct custody contain current operations but do not close the forensic question. B08 gives bounded follow-up scope without system-wide audit changes or interference with unknown processes.

## Integrity and verification

`ledger.json.inputs` binds the exact committed public source/configuration documents by Git blob, size and SHA256. Copied capability/repro inputs preserve original bytes. `SHA256SUMS` covers every other regular file in this directory, including nested original checksums. The packaging check verified all input bindings, original nested checksums, JSON parsing and all final archive bytes. Only this `blockers/` subtree was written; no Git commit was made.
