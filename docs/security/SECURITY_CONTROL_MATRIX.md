# Security control matrix

**Revision:** `2026-08-29-d6`

| Control | Current implementation | Required test/evidence | Current status | Residual risk / next gate |
| --- | --- | --- | --- | --- |
| strict Browser API codec | Rust canonical parser/encoder | independent vectors, fuzz, exact-head Rust | host capability validated historically; evidence `STALE_EVIDENCE` | no BrowserActor/Servo dispatch; exact-head rerun required |
| bounded authenticated carrier | AF_UNIX connected stream, peer creds, nonce, digest, sequence, deadlines | malformed corpus, peer tests | host capability validated historically; evidence `STALE_EVIDENCE` | no product listener claim; exact-head rerun required |
| socket custody | systemd socket/service, default-disabled marker, sandbox | PID 1 QEMU activation corpus | host capability validated historically; evidence `STALE_EVIDENCE` | D1 runtime evidence missing; exact-head rerun required |
| semantic principal binding | development-only fixed root-owned executable path plus live pidfd/PID/UID/GID/start-time/cgroup/unit revalidation; no cross-UID procfs executable read | exact-image principal/dispatch/receipt corpus and independent security review | source implemented; live activation unpromoted | Servo-owned retained-node adapter, exact-image corpus, and review; static path binding is not live executable-image proof |
| stale-reference control | state-machine revisions plus fail-closed `PageRuntime::dispatch_page_act` resolver boundary | headed/runtime frame re-resolution, ambiguity, navigation and crash corpus | partial | Servo DOM/accessibility resolver and D3 integrated corpus |
| trusted shell separation | architecture/contracts | headed pixels, process and origin evidence | candidate | D2 |
| renderer sandbox | design only | namespace/seccomp/LSM escape corpus | open | D2/D6/D8 |
| durable receipts | bounded chained journal | independent parser, corruption, disk-full, crash corpus | host capability validated historically; evidence `STALE_EVIDENCE` | authenticity anchor and integration remain; exact-head rerun required |
| external-effect replay refusal | journal/plan rule | BrowserActor kill/disconnect/reconciliation corpus | source/host only | D3/D7 |
| controlled egress | source/reference policy only; no installed namespace/resolver/proxy | SSRF/rebinding/redirect/IPv6/protocol corpus | open | D6 |
| capability permits/portals | schemas and source policy; no installed portal authority | audience/resource/expiry and ambient-authority tests | open | D5/D6 |
| signed apps and trusted origins | v2 source verifier/policy aligned to publisher-qualified ADR 0004 origins; no installed runtime | signature/revocation/anti-downgrade/storage isolation | open | D5 |
| reproducible image | D1 candidate | two-build digest identity and QEMU boot | candidate | D1 |
| signed update/rollback | source/reference models only; no real slot or rollback counter | power loss, failed update, rollback, recovery | open | D7 |
| fixed hardware | none selected | exact BOM qualification and stability | open | D8 |
| supply-chain action pinning | d6 CI work | immutable-action audit | candidate | exact-head/main CI |
| protected review and signing separation | source policy only | repository settings and custody evidence | external gate | admin action required |

For D0C-02, D0C-03, D0C-05, and D0C-06, historical capability describes the
source-level control that remains present. It is separate from the bound host
observation: the machine gate records that observation as `STALE_EVIDENCE` with
`merge_ready: false` until the permanent workflow reruns on the exact
candidate head.
