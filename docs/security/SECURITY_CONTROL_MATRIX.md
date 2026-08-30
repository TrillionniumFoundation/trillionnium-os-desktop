# Security control matrix

**Revision:** `2026-08-29-d6`

| Control | Current implementation | Required test/evidence | Current status | Residual risk / next gate |
| --- | --- | --- | --- | --- |
| strict Browser API codec | Rust canonical parser/encoder | independent vectors, fuzz, exact-head Rust | host validated | no BrowserActor/Servo dispatch |
| bounded authenticated carrier | AF_UNIX connected stream, peer creds, nonce, digest, sequence, deadlines | malformed corpus, peer tests | host validated | no product listener claim |
| socket custody | systemd socket/service, default-disabled marker, sandbox | PID 1 QEMU activation corpus | host validated only | D1 runtime evidence missing |
| semantic principal binding | not integrated | exact service identity and TaskFlow mapping | open | D3 |
| stale-reference control | state-machine revisions plus fail-closed `PageRuntime::dispatch_page_act` resolver boundary | headed/runtime frame re-resolution, ambiguity, navigation and crash corpus | partial | Servo DOM/accessibility resolver and D3 integrated corpus |
| trusted shell separation | architecture/contracts | headed pixels, process and origin evidence | candidate | D2 |
| renderer sandbox | design only | namespace/seccomp/LSM escape corpus | open | D2/D6/D8 |
| durable receipts | bounded chained journal | independent parser, corruption, disk-full, crash corpus | host validated | authenticity anchor and integration remain |
| external-effect replay refusal | journal/plan rule | BrowserActor kill/disconnect/reconciliation corpus | source/host only | D3/D7 |
| controlled egress | design only | SSRF/rebinding/redirect/IPv6/protocol corpus | open | D6 |
| capability permits/portals | schemas/design | audience/resource/expiry and ambient-authority tests | open | D5/D6 |
| signed apps and trusted origins | schemas/ADRs | signature/revocation/anti-downgrade/storage isolation | open | D5 |
| reproducible image | D1 candidate | two-build digest identity and QEMU boot | candidate | D1 |
| signed update/rollback | design only | power loss, failed update, rollback, recovery | open | D7 |
| fixed hardware | none selected | exact BOM qualification and stability | open | D8 |
| supply-chain action pinning | d6 CI work | immutable-action audit | candidate | exact-head/main CI |
| protected review and signing separation | source policy only | repository settings and custody evidence | external gate | admin action required |
