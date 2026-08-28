# hepta-agent-port

`hepta-agent-port` is the connected-stream D0C-04 mechanism boundary between
`hepta-agent-transport` and the canonical Browser API codec.

It accepts an already connected `AF_UNIX/SOCK_STREAM`, authenticates the peer
through the transport layer, decodes exactly one canonical request, invokes a
typed handler at most once, binds the response identity to the validated
request, commits at most one response before the effective monotonic deadline,
and returns.

It deliberately does **not**:

- bind a filesystem or abstract socket;
- create a listener;
- map a peer to TaskFlow authority;
- dispatch a Servo `WebView` or `BrowserActor`;
- grant a capability or authorize an external effect;
- retry a request or an indeterminate operation.

The D0 fixture handler succeeds only for `health`, refuses every potential
external effect, and truthfully reports that the browser runtime is absent.
