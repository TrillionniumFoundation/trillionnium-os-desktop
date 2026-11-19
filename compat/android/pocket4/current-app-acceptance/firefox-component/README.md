# Firefox component binding

The browser flow previously resolved the current HTTPS handler and then sent
another implicit intent. A default-handler change between those two operations
could dispatch the request to a different application before the post-launch
checks rejected the observation.

This maintained source selects the one valid Firefox component returned by the
original resolver and passes that exact component to `start-activity -n`.
The Android user, complete URI, VIEW action, BROWSABLE category, physical
framework epoch, and complete pre/post package identity checks are preserved.
Malformed and ambiguous component responses fail before a launch is attempted.
The existing same-package launch-output rule is retained so that legitimate
activity aliases and forwarding do not acquire an unverified same-name gate.

## Validation

Run the self-contained host controls with:

```sh
cargo test --locked --manifest-path Cargo.toml
```

The complete current native source was also compiled in an isolated checkout
of `9ecce4f94dec80500c05322106907e48a0668b05`. The seven existing controls and
three new regression controls passed. Running the same new controls against
the original implementation produced the two expected failures: changed
default-handler dispatch and malformed-component dispatch. The alias control
passed before and after the change. The adjacent manifest binds the exact
source and retained private result bytes; build outputs and execution logs
are not included in this source packet.

## Integration and remaining runtime gates

This file replaces
`runtime/droidloom-supervisor/src/application_probe.rs` only when the existing
file has the base SHA-256 in `manifest.json`. Reconcile any later source change
before adoption. Keep the current production read worker, descriptor protocol,
runtime inputs, MAC policy and owner admission unchanged during this narrow
source replacement.

This repair does not enable the production OpenBrowser or Launch capability.
The current read-only query domain deliberately cannot find Android's Activity
service. A production browser action still needs a separate finite action role,
its sealed runtime executable provider, the corresponding policy and actual
owned-tree execution and retirement evidence. Do not reuse query-only authority
or turn a saved inspection receipt into permission to act.

The host controls use synthetic Android responses. They prove the dispatch
construction and rejection behavior, not rendering, app lifecycle, business
flows, account behavior or Android compatibility. A failed observation after
dispatch does not undo an Android action and does not authorize automatic replay.
Production readiness and all 42 application acceptances remain pending.
