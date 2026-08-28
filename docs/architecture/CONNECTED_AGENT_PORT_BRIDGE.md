# Connected AgentPort bridge

**Checkpoint:** `TOS-D0C-04`  
**Implementation:** `crates/hepta-agent-port`  
**Contract:** `contracts/agent-port-bridge.v1.json`

## Path

```text
already-connected AF_UNIX stream
  -> SO_PEERCRED policy and per-connection nonce
  -> bounded sequence/digest-bound request frame
  -> strict canonical Browser API decoder
  -> immutable DispatchContext
  -> at most one typed handler invocation
  -> request-bound canonical response
  -> at most one response frame
```

This crate is a mechanism boundary. It does not create a listener, assign
semantic authority, dispatch Servo, grant a capability, or retry an operation.

## Identity binding

The handler cannot author the wire identity. Protocol, request ID, session ID,
session generation, transport sequence and connection nonce are derived from
the authenticated transport and validated request. A handler returns only an
object result or a normative typed Browser error.

## Deadline

The bridge samples wall and monotonic clocks once at connection acceptance. The
effective monotonic deadline is the earlier of the server ceiling and the
request's absolute deadline translated at that sample. Transport, decoding,
handler execution, response construction and response commit consume the same
budget. A late synchronous handler result is discarded without committing a
response.

## Effect ceiling

The D0 fixture handler permits only `health`. It returns `policy_denied` for
every `potential_external_effect` and `unsupported` for browser-dependent
operations. Navigation therefore remains classified as a potential effect and
is never downgraded to a read-only action.

## Result bounds

Handler-produced JSON is limited independently of the request decoder:

- 1,024 top-level members;
- 4,096 aggregate container items;
- depth 16;
- 128-byte keys;
- 131,072-byte strings.

These limits prevent an internal handler from bypassing the bounded carrier by
constructing an oversized response graph.

## Non-claims

Source presence and reference tests do not prove Rust compilation, a product
listener, TaskFlow identity mapping, a BrowserActor, Servo integration, a
visible frame, external navigation, or external-effect authority.
