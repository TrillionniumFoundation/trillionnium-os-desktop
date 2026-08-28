# Connected AgentPort bridge

**Checkpoint:** `TOS-D0C-04`  
**Implementation:** `crates/hepta-agent-port`  
**Contract:** `contracts/agent-port-bridge.v1.json`

```text
already-connected AF_UNIX stream
  -> authenticated bounded transport
  -> strict canonical Browser API decoder
  -> immutable DispatchContext
  -> at most one typed handler invocation
  -> request-bound canonical response
  -> at most one response frame
```

The handler cannot author protocol, request ID, session ID/generation,
transport sequence or connection nonce. It returns only an object result or a
normative typed Browser error.

The bridge samples wall and monotonic clocks once at acceptance. The effective
monotonic deadline is the earlier of the server ceiling and the request's
absolute deadline translated at that sample. A late synchronous handler result
is discarded without response commit.

The D0 fixture permits health only. Potential external effects return
`policy_denied`; other browser-dependent operations return `unsupported`.
There is no listener, semantic authority mapping, BrowserActor, Servo runtime,
capability grant or external-effect authority in this checkpoint.
