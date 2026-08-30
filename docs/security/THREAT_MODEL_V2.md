# Desktop threat model V2

**Revision:** `2026-08-29-d6`  
**Status:** normative baseline; controls become demonstrated only at their gates.

## Security objectives

Protect:

- trusted shell identity, consent, and recovery UI;
- PageOwner/session/reference integrity;
- user profile, cookies, storage, clipboard, files, devices, and credentials;
- AgentPort identity and request binding;
- receipt truth and privacy;
- private/link-local/metadata networks;
- capability permits and portal authority;
- update/signing keys, rollback state, and release provenance.

## Adversaries

1. hostile webpage, iframe, worker, service worker, download, or external scheme;
2. prompt-injected or compromised Agent context;
3. unprivileged local process impersonating the Agent;
4. same-UID or compromised service process;
5. compromised Servo content process;
6. compromised browser coordinator or trusted app publisher;
7. malicious DNS, redirect, proxy, captive portal, QUIC/WebSocket/WebRTC peer;
8. corrupted disk, journal, image, update metadata, or power-loss state;
9. compromised CI dependency, action, runner, package mirror, or build input;
10. privileged administrator/root;
11. accidental mobile/ADB/root-shell authority contamination.

Root/administrator compromise is not claimed to be fully contained. The model
still requires auditability, signing-key separation, offline recovery, and
minimal authority so a single browser or Agent compromise does not become
equivalent to root.

## Trust boundaries

- native trusted chrome vs untrusted Servo content;
- Agent semantic principal vs Unix/systemd mechanism identity;
- connected AgentPort stream vs BrowserActor semantic authorization;
- BrowserActor vs capability portals;
- browser namespace vs egress authority;
- application publisher vs platform signer;
- build CI vs offline release signing;
- active slot vs updater/recovery environment;
- source candidate vs integrated main vs signed release artifact.

## Primary attack paths and controls

### Trusted UI spoofing

Control with compositor/native trusted chrome, origin and publisher indicators,
no shared trusted/untrusted DOM, screenshot/overlay tests, and receipts that
record trust class.

### Local Agent impersonation

Control with systemd-owned socket, strict mode/ownership, `SO_PEERCRED`, pidfd,
proc start time, cgroup and unit attestation, explicit semantic-principal
mapping, connection nonce, sequence, digest, and absolute deadlines.

Residual risk: same-UID/service compromise until semantic identity and service
isolation are fully demonstrated.

### Stale or ambiguous target action

Control with session/document/snapshot generations, semantic re-resolution,
role/name/visibility/structure checks, ambiguity refusal, human preemption, and
no automatic replay after navigation/crash/disconnect.

### Renderer escape and ambient authority

Control with process sandbox, namespaces, cgroups, LSM/seccomp, no raw device or
secret/update authority, capability portals, and kill/recovery corpus.

### SSRF and network bypass

Control all DNS answers, rebinding changes, connected peer IPs, IPv4/IPv6,
private/link-local/metadata ranges, redirects, proxies, HTTP(S), WebSocket,
QUIC/WebTransport, WebRTC where present, workers, service workers, iframes,
prefetch, downloads, and external schemes.

### Effect duplication

Treat navigation and UI mutation as potential external effects. Persist
requested/dispatched/outcome facts, expose indeterminate state, require
reconciliation, and never blind-retry.

### Journal tampering or privacy leak

Use bounded versioned encoding, chain verification, single writer, file modes,
redacted export, retention rules, independent parser/fuzz corpus, and later
external signing/anchor where a stronger authenticity claim is required.

### Supply-chain compromise

Pin source commits, package closures, action SHAs, toolchains, workflow hashes,
and runner identity; generate SBOM/provenance; use least-privilege CI; keep
production signing keys out of CI.

### Update compromise

Separate updater authority, verify signed immutable artifacts and metadata,
enforce rollback, test failed update/power loss, provide offline recovery, and
support revocation/rotation.

### Mobile authority contamination

Keep Android, ADB, root-linux, and direct-shell dependencies outside the desktop
default graph. Only reviewed neutral contracts may be shared.

## Security control evidence

`docs/security/SECURITY_CONTROL_MATRIX.md` maps each control to implementation,
tests, workflow, evidence tier, current status, residual risk, and owner class.
No source-only control is described as runtime-enforced.
