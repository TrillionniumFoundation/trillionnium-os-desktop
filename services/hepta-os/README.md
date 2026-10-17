# Hepta read-only host observer

`hepta-os-observer` is the first concrete A10 Session → Hepta client slice. It
speaks the existing, fixed Agentd v2 JSON-over-UDS control wire and exposes only
`health`, `capabilities`, `events`, and `run_status`. The public API projects
bounded metadata and omits the upstream workspace paths, signing inputs,
session-ingress address, and arbitrary payloads.

**Current evidence:** the compiled Linux host client, real Unix-socket fixture
roundtrips, strict negative cases and source-derived wire conformance are now
joined by an [executed original Agentd ARM64 read-only gate](../../tests/integration/hepta/evidence/2026-10-17-original-agentd-arm/README.md).
Fixed Hepta `f8c9419df6ddeb36ff8b522a50219981fb8d9345` was built and run unchanged;
all eight lifecycle/read checks passed, and three downloaded ELF hashes match
the executed receipt. This gate uses fresh observer CLI instances. Continuous
Session-to-original-Agentd observation and Shell projection remain unqualified;
model turns, HOS2 delivery, device actions and Asterinas execution are not claimed.
This is a candidate for owner adoption, not completion of A07's durable effect
acceptance gate. [Evidence and remaining gates](../../tests/integration/hepta/EVIDENCE.md)
are recorded separately.

| Surface | Current behavior |
| --- | --- |
| Linux Session worker | Explicit trusted endpoint; real UDS client with peer UID/PID checks |
| Shell renderer | Receives safe observation projection through Session IPC; no Agentd endpoint or generic RPC API |
| Health/capabilities | Observations and advertisements; neither grants effect authority |
| Events | Bounded process-local lifecycle metadata with exact cursor/gap validation |
| Known run lookup | Existing owner state; historical generation preserved; no task listing |
| Objective input | Remains an offline UI draft until the authenticated owner adapter is assembled |
| Device control/HOS2 | Not provided by this crate |
| Windows/Android/Asterinas | No qualified transport here; non-Linux builds return `unsupported_platform` |

## Placement and ownership

The trusted Session process owns `ObserverClient` on a dedicated background
worker. The renderer consumes an application projection, never this crate's
endpoint configuration. The crate has no raw JSON request API, no process
launcher, no discovery of sockets or credentials, no signing code, and no
persistent state. It does not copy Agentd, a policy owner, or an operation
ledger.

This observer performs host I/O outside the organ boundary. It is **not** an
implementation of `TrustedReadOnlyOrganV1`, whose handler must not perform I/O or
hold capabilities. A future organ can consume a bounded owner-produced snapshot;
an effect must still follow the original authority/operations owners and the
separate restricted OS adapter.

The host configuration must identify the expected Agent UUID, spawn generation,
and OS UID from a separately trusted supervisor record. Reusing values returned
by an arbitrary socket to configure that same socket would defeat identity
checking. The same configured UID, privileged host processes, and the Session
process remain in the host trust boundary. Socket permissions and `SO_PEERCRED`
do not authenticate a binary, defeat an attacker under the same UID, or sandbox
a renderer that is otherwise able to access the UDS through its OS credentials.
The Session must be launched with the intended process isolation and access
policy; this client is not a complete sandbox.

## Public API

```rust,ignore
let endpoint = EndpointConfig::new(socket_path, agent_uuid, generation, peer_uid)?;
let mut observer = ObserverClient::new(endpoint)?;
let observation = observer.poll(after_cursor, 16)?;
let known_run = observer.run_status("a-known-owner-run-id")?;
```

These methods block their calling worker. Calling them inside a Tokio runtime
returns `invalid_execution_context`. Keep one client per Session observer;
repeatedly creating new clients after timeouts would bypass the per-client
bound on outstanding metadata work. A poll has one five-second asynchronous
deadline for filesystem validation and all four socket exchanges. It returns
no partial successful observation. The Session must independently expire its
last-success timestamp so a stalled worker or host scheduler cannot leave a
green status indefinitely.

The filesystem job owns a one-slot permit until its actual syscalls finish.
Timing out the waiter does not interrupt a syscall. While that job remains
outstanding, later polls return `unavailable` without queuing more jobs. Client
drop does not wait for such a worker. The process may still contain that one
blocked job until the OS returns it.

Read [RUN.md](RUN.md) for reproducible commands, [CONTRACT.md](CONTRACT.md) for
wire and projection rules, and [UPSTREAM_CONTRACT.json](UPSTREAM_CONTRACT.json)
for the reviewed source hashes. Root `README.md` remains intentionally empty.
