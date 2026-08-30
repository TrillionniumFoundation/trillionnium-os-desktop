# Security control matrix

**Revision:** `2026-08-29-d6`

| Control | Current implementation | Required test/evidence | Current status | Residual risk / next gate |
| --- | --- | --- | --- | --- |
| strict Browser API codec | Rust canonical parser/encoder | independent vectors, fuzz, exact-head Rust | host capability validated historically; evidence `STALE_EVIDENCE` | no BrowserActor/Servo dispatch; exact-head rerun required |
| bounded authenticated carrier | AF_UNIX connected stream, peer creds, nonce, digest, sequence, deadlines | malformed corpus, peer tests | host capability validated historically; evidence `STALE_EVIDENCE` | no product listener claim; exact-head rerun required |
| socket custody | systemd socket/service, default-disabled marker, sandbox | PID 1 QEMU activation corpus | host capability validated historically; evidence `STALE_EVIDENCE` | D1 runtime evidence missing; exact-head rerun required |
| semantic principal binding | source-level TaskFlow/BrowserActor binding; live D3 activation blocked by cross-UID procfs attestation | exact service identity and TaskFlow mapping in an integrated image | blocked upstream | D3 integrated corpus plus an approved same-UID or fixed-root-owned executable resolution |
| stale-reference control | state-machine revisions plus fail-closed `PageRuntime::dispatch_page_act` resolver boundary | headed/runtime frame re-resolution, ambiguity, navigation and crash corpus | partial | Servo DOM/accessibility resolver and D3 integrated corpus |
| trusted shell separation | architecture/contracts | headed pixels, process and origin evidence | candidate | D2 |
| renderer sandbox | design only | namespace/seccomp/LSM escape corpus | open | D2/D6/D8 |
| durable receipts | bounded chained journal | independent parser, corruption, disk-full, crash corpus | host capability validated historically; evidence `STALE_EVIDENCE` | authenticity anchor and integration remain; exact-head rerun required |
| external-effect replay refusal | journal/plan rule | BrowserActor kill/disconnect/reconciliation corpus | source/host only | D3/D7 |
| controlled egress | design only | SSRF/rebinding/redirect/IPv6/protocol corpus | open | D6 |
| capability permits/portals | schemas/design | audience/resource/expiry and ambient-authority tests | open | D5/D6 |
| signed apps and trusted origins | schemas/ADRs | signature/revocation/anti-downgrade/storage isolation | open | D5 |
| reproducible image | D1 candidate | two-build digest identity and QEMU boot | candidate | D1 |
| signed update/rollback | design only | power loss, failed update, rollback, recovery | open | D7 |
| fixed hardware | none selected | exact BOM qualification and stability | open | D8 |
| supply-chain action pinning | d6 CI work | immutable-action audit | candidate | exact-head/main CI |
| protected review and signing separation | source policy only | repository settings and custody evidence | external gate | admin action required |

For D0C-02, D0C-03, D0C-05, and D0C-06, historical capability describes the
source-level control that remains present. It is separate from the bound host
observation: the machine gate records that observation as `STALE_EVIDENCE` with
`merge_ready: false` until the permanent workflow reruns on the exact
candidate head.
