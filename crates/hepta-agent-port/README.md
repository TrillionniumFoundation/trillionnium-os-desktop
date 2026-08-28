# hepta-agent-port

Exactly-one connected-stream bridge from the authenticated bounded AF_UNIX
carrier to the strict Browser API codec and a typed handler. The handler
receives an admitted `DecodedRequest` with canonical digest, effect class and
engine-neutral domain operation. It cannot author wire identity fields.

The wall/monotonic deadline anchor is captured at connection acceptance and late
results are discarded without response commit. The D0 fixture succeeds only for
health, refuses potential external effects with `policy_denied`, and reports
browser-dependent operations as `unsupported`.

This crate creates no listener and contains no BrowserActor or Servo
implementation.
