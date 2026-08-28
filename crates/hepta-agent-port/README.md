# hepta-agent-port

`hepta-agent-port` is the D0C-04 connected-stream product boundary between the authenticated AF_UNIX carrier and a typed Browser API handler.

It accepts one already-connected stream, authenticates and bounds one request, decodes canonical Browser API bytes, builds an immutable dispatch context, invokes one handler at most once, binds the response to the validated request, and commits only before the effective deadline.

This crate deliberately does not create a listener, dispatch a BrowserActor, call Servo, grant a capability, authorize an external effect, or perform an automatic retry.
