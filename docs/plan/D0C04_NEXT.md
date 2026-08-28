# D0C-04 immediate next action

The only permitted next action for this candidate is exact-head validation and
repair under Rust 1.93.0. After that gate passes, the branch may be rebased or
retargeted for merge and D0C-05 socket custody may be rebuilt on top.

It is not permitted to enable a listener, create BrowserActor success fixtures,
start Servo, navigate an external origin, or authorize an effect to compensate
for a missing compiler/runner result.
