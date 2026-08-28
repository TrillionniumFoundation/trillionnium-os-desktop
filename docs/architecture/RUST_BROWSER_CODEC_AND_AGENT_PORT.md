# Rust Browser codec and connected AgentPort

**Work packages:** `TOS-D0C-03` / `TOS-D0C-04`
**Status:** source implemented; Rust 1.93 exact-head execution remains open.

## Pipeline

```text
already-connected AF_UNIX stream
  -> SO_PEERCRED / nonce / sequence / digest transport
  -> recursive duplicate-member rejection
  -> bounded canonical Browser API decode
  -> conversion into the existing engine-neutral domain contract
  -> immutable DispatchContext
  -> exactly one typed handler invocation
  -> request-bound canonical response
  -> response frame
```

The transport, codec and bridge remain separate crates so that framing cannot
interpret browser authority and the browser handler cannot author transport or
wire identity.

## Canonical request identity

The codec hashes the canonical typed re-encoding, not attacker-selected JSON.
It also converts each admitted wire operation into the existing
`hepta-browser-contracts` domain type, so a future BrowserActor does not need to
reinterpret JSON or maintain a second semantic model. The bridge passes the
complete `DecodedRequest`, including that domain operation, to the handler.

The bridge copies protocol, request ID, session ID and session generation from
the validated request. A handler returns only an object result or a normative
typed error.

## Deadline

The effective deadline is the earlier of the server ceiling and the request's
absolute Unix deadline. Wall and monotonic clocks are sampled once at connection
acceptance; transport and decode time therefore consume the same request budget.
A handler result that
arrives after the monotonic deadline is discarded without a response commit.

## Effect ceiling

Navigation and click/type/press/select are potential external effects. The D0
fixture returns `policy_denied` for those operations. It returns a successful,
mechanism-only result only for `health`; browser-dependent observations and
local session operations return `unsupported` until a real BrowserActor exists.
This layer cannot grant authority or automatically retry.

## Explicit non-claims

No socket path, listener, TaskFlow principal mapping, BrowserActor, Servo
runtime, window, navigation, input or external effect is implemented here.
