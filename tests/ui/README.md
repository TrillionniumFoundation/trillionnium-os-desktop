# Rust UI verification layers

The dependency-free `trillionnium-ui-contracts` crate contains executable host
models for process, compositor, input and observation contracts. Its
[src/lib.rs](src/lib.rs) and the separate [support model](../../support/ui/README.md)
have no real window or permission authority. The surrounding Python/shell tools
also exercise actual Session, private Notes transports, renderers and recovery
processes; each tool's evidence scope stays explicit.

## Development entry

```sh
cargo test --locked --manifest-path tests/ui/Cargo.toml
bash tests/ui/check-host.sh
```

The first command needs no display. The second requires the owned graphical
environment in [RUN](../../support/ui/RUN.md). The
[test plan](TESTPLAN.md) maps real process, Weston, font and input checks;
[original Objective](ORIGINAL_OBJECTIVE_SHELL.md) explains the trusted bridge.
For a Notes change follow [durability](../../support/ui/NOTES_DURABILITY.md)
and [Notes organ](../../support/ui/NOTES_ORGAN.md), selecting the tests that
cover storage ambiguity, independent readback and the original receipt owner.

## Failure and recovery assertions

Session generation, target identity, exact revision and original owner receipt
must remain distinct. A lost connection can follow a real mutation. A new
process must recover the original identity's status before any possible new
operation; UI success text, a first-frame marker or an application receipt
cannot manufacture Hepta terminality. Corrupt/foreign/busy storage must be
refused and left available for explicit diagnosis.

Record actual source, features, renderer, executable hashes, full test counts,
ignored checks and raw exits. Models, Xvfb, owned compositor windows and physical
devices prove different things. Keep fixtures and test issuers confined to the
test run; they do not configure production authorization.
