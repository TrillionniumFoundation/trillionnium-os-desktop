# hepta-agent-port

`hepta-agent-port` is the connected-stream D0C-04 mechanism boundary between
the authenticated transport, canonical Browser API codec, and a future typed
BrowserActor adapter.

It accepts an already connected `AF_UNIX/SOCK_STREAM`, authenticates the peer,
decodes exactly one canonical request, invokes a typed handler at most once,
binds response identity to the validated request, commits at most one response
before the effective monotonic deadline, and returns.

It deliberately does **not** bind a socket, create a listener, map a peer to
TaskFlow authority, dispatch Servo, grant a capability, authorize an external
effect, or retry an indeterminate operation.

The D0 fixture succeeds only for `health`, denies every potential external
effect, and truthfully reports that the browser runtime is absent.
