# AgentPort product and qualification separation

The default `hepta-agent-portd` binary contains no `D0FixtureHandler` and fails
closed before request decoding. A source-level BrowserActor is available only
in the separately compiled, opt-in development profile; production activation
remains fail-closed until a promoted, integrated D3 implementation is
qualified.

The non-product binaries are available only through explicit, non-default
`fixture` or `d1-qualification` features:

- `hepta-agent-port-fixture`: bounded D0 source/self-check fixture;
- `hepta-agent-port-qualificationd`: one-connection D1/QEMU handler;
- `hepta-agent-d1-fixture`: D1 client corpus.

The standalone fixture uses `fixture`; the D1 client and qualification server
use `d1-qualification`, which is also the only graph that enables the
qualification-only static executable attestation helper. Neither feature is
enabled by default.

The D3 development profile is a separate opt-in graph, not a fixture
substitution.  `hepta-agent-port-developmentd` is compiled only with the
non-default `development` feature, requires the administrator-created
`/etc/hepta/enable-agent-port-development` marker and an explicit
`--profile development` argument, and uses the dedicated
`/run/hepta/browserd/agent-development.sock` socket.  It wires the attested
peer to `BrowserActor<DeterministicLocalRuntime>` and the durable receipt
observer.  Neither its binary nor its units are in the production Debian
install map; production remains default-disabled.

None is present in the Debian production installation map. The D1 image builder
may inject the qualification handler into its explicitly test-only image. This
does not enable AgentPort in the production profile and grants no external
effect authority.
