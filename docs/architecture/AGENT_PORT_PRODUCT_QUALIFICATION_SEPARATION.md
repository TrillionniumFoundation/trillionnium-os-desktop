# AgentPort product and qualification separation

The default `hepta-agent-portd` binary contains no `D0FixtureHandler` and fails
closed before request decoding until D3 connects a real BrowserActor.

Three non-product binaries are available only through the non-default `fixture`
feature:

- `hepta-agent-port-fixture`: bounded D0 source/self-check fixture;
- `hepta-agent-port-qualificationd`: one-connection D1/QEMU handler;
- `hepta-agent-d1-fixture`: D1 client corpus.

None is present in the Debian production installation map. The D1 image builder
may inject the qualification handler into its explicitly test-only image. This
does not enable AgentPort in the production profile and grants no external
effect authority.
