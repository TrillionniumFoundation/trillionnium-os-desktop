# D0C-04 failure semantics

The connected AgentPort fails closed at the first violated boundary:

- carrier/authentication/framing failures are transport failures;
- malformed, duplicate-member, non-canonical or semantically invalid payloads
  are codec failures and never reach the handler;
- an already expired request is rejected before handler dispatch;
- handler output exceeding independent bounds is rejected before response
  construction;
- a late handler result is discarded without response commit;
- a potential external effect receives a typed D0 policy refusal;
- an operation requiring the absent BrowserActor/Servo runtime receives typed
  `unsupported` rather than simulated success.

The mechanism never automatically retries a request after disconnect, timeout,
indeterminate dispatch or response failure.
