# hepta-browser-actor-simulation

This crate retains the complete S06 actor mechanism and its large hostile/fault-injection test corpus as an **implementation-internal simulation substrate**.

## Security status

It is not a product entry point and it is not published. Repository policy permits exactly one direct dependent: the product-facing `hepta-browser-actor` wrapper. Applications and all other crates must not depend on this package directly.

The substrate still contains compatibility constructors and the ordinary `BrowserRequestHandler` implementation needed by its internal regression suite. Those APIs are deliberately not re-exported by the product wrapper and therefore cannot satisfy an authority-bearing product dispatch contract.

## What it owns

- deterministic PageOwner/session state transitions;
- bounded engine-thread and callback completion machinery;
- cancellation/deadline propagation;
- request-scoped peer verifier plumbing;
- receipt lifecycle observation;
- deterministic local runtime and hostile tests;
- fresh session-incarnation generation.

## What it does not establish

Presence or test success of this crate does not prove product activation, listener custody, authenticated caller admission, Servo integration, installed-image execution, physical-hardware qualification, signing, publication, or release readiness.

## Promotion boundary

Only `hepta-browser-actor::BrowserActor::from_attested` may construct the product-facing actor. Every product request must then enter through `handle_attested`, which refreshes the opaque `AttestedPeer` and retains request-scoped custody. Any repository package that imports this simulation crate directly fails the S06 gate.
