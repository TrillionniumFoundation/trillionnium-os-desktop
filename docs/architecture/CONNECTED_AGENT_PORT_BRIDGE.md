# Connected AgentPort bridge

S04 composes one authenticated connected stream with the canonical Browser API.
It admits at most one request, constructs an immutable context from transport and
canonical-request facts, invokes a typed handler at most once, and emits at most
one canonical response before the effective deadline.

Lifecycle observation is fail-closed: `requested` must be recorded before handler
entry; `dispatched` and terminal/interrupted facts must be recorded before response
publication. The observer has no execution authority. Durable persistence is S05;
real BrowserActor and request queueing are S06/S08.

The current fixture accepts health only. The product daemon does not link that
fixture and fails closed before decoding because no BrowserActor exists. No socket,
principal, capability, navigation, Servo, or external effect is enabled here.
