# Runtime topology and failure model

**Revision:** `2026-08-29-d6`

## Target process topology

```text
firmware / bootloader
  -> Linux kernel + initramfs
  -> systemd PID 1
     -> compositor / Wayland session
        -> trusted workspace shell
           -> one logical Servo WebView
              -> browser coordinator
              -> sandboxed content process(es)
     -> PageOwner / BrowserActor service
     -> default-disabled AgentPort socket unit
        -> one short-lived connection process per accepted connection
     -> receipt journal service/library boundary
     -> capability portals and egress service (later gates)
     -> minimal update authority (later gate)
```

The trusted shell is compositor/native owned. Untrusted web content cannot
replace, overlap as trusted UI, or share the trusted-chrome DOM.

## Identities and authority

| Component | Identity | Ambient authority |
| --- | --- | --- |
| trusted shell | dedicated user/service | display/session and explicitly granted shell resources |
| Servo coordinator | dedicated browser identity | no raw device, secret, update, or unrestricted filesystem authority |
| content process | sandboxed child | content rendering only |
| AgentPort connection process | `hepta-browserd` plus attested `hepta-agent` peer policy | inherited AF_UNIX stream only |
| PageOwner/BrowserActor | dedicated service boundary | typed browser operations only |
| receipt journal | single writer | journal directory only; no execution API |
| egress service | dedicated network authority | controlled resolver/proxy policy only |
| updater | separate minimal authority | signed image/update slots only |

Exact UID/GID/cgroup/namespace assignments become normative at D1/D3 and are
recorded in the image manifest.

## Startup readiness

A service is ready only when its own gate-defined readiness file/message is
written after dependencies are healthy. Process existence is not readiness.

The product AgentPort remains disabled by preset. A development or
qualification profile may create a test-only marker, but the marker is removed
and audited absent from the final candidate.

## Failure semantics

### Content-process failure

- trusted chrome remains visible;
- PageOwner enters recovery;
- session generation advances;
- all prior element references and leases become stale;
- pending dispatched effects become typed interrupted or indeterminate;
- no automatic replay;
- exactly one replacement logical content surface is created.

### Browser coordinator failure

- AgentPort refuses new browser operations;
- receipt journal records interruption where facts are known;
- systemd restart budget is bounded;
- repeated failure enters degraded/recovery mode rather than a restart loop.

### AgentPort connection failure

- one connection process exits;
- no handler result is committed after deadline;
- a killed connection cannot affect later connections;
- the socket remains default-disabled outside an explicit profile.

### Journal/storage failure

- uncertain append poisons the writer until reopen;
- repair is limited to a verified torn tail;
- mid-log corruption fails hard;
- disk-full never invents completion;
- unresolved potential external effects are never replayed automatically.

### Compositor/session failure

- the system enters a typed recovery target;
- no hidden browser session remains authoritative;
- evidence distinguishes compositor restart from content restart.

### Update failure

- failed verification or boot does not promote the slot;
- rollback and recovery are explicit;
- updater authority is not shared with browser or AgentPort services.

## Observability

Structured events must bind:

- plan/image/build identity;
- session/document/snapshot generation;
- request and receipt identity;
- process/cgroup identity;
- deadline/cancellation;
- failure class and recovery generation.

Logs must not contain secrets, raw credentials, private page content, or
unredacted sensitive receipt detail.

## Optional in-process engine-thread dispatch

[ENGINE_THREAD_DISPATCH.md](ENGINE_THREAD_DISPATCH.md) defines the bounded
actor-to-engine scheduling mechanism and real connected-stream/receipt host
corpus. Its engine remains a fixture in tests; the mechanism is not installed
in the product, does not implement cross-process IPC, and does not prove live
Servo node resolution, native input or exact-image D3. Existing topology,
authority and promotion requirements remain unchanged.
