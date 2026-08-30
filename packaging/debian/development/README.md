# D3 development-profile AgentPort

The development profile is deliberately outside the production Debian install
map.  Build the opt-in binary with:

```text
cargo build --release --locked -p hepta-agent-portd \
  --features development --bin hepta-agent-port-developmentd
```

Install that binary as `/usr/libexec/hepta-agent-port-developmentd` together
with the `hepta-browserd-agent-development.socket` and
`hepta-browserd-agent-development@.service` units.  Create the marker only on a
developer image after selecting the profile:

```text
install -o root -g root -m 0644 /dev/null \
  /etc/hepta/enable-agent-port-development
```

The service also requires `/etc/hepta/agent-port-development.conf` containing
the exact SHA-256 of the intended `hepta-agent.service` executable:

```text
HEPTA_D3_EXPECTED_EXECUTABLE_SHA256=<lowercase-64-hex-digest>
```

Optional variables are `HEPTA_D3_PRINCIPAL_ID`, `HEPTA_D3_IMAGE_ID`, and
`HEPTA_D3_RECEIPT_JOURNAL`.  The default journal is
`/var/lib/hepta-browserd/development/receipts.journal`.

The development socket is `/run/hepta/browserd/agent-development.sock`; it is
not the production `/run/hepta/browserd/agent.sock`.  The binary never binds a
listener, accepts only systemd's already-connected AF_UNIX stream, and maps the
validated peer through `ProcfsPeerAttestor` → `PrincipalBinding::bind_attested`
→ `BrowserActor<DeterministicLocalRuntime>` → `ReceiptLifecycleObserver` →
`serve_one_with_observer`.  Only ephemeral loopback fixtures are enabled.

The `--self-check` output is explicitly source-wiring evidence: it reports the
typed actor and observer as wired and exercises the in-memory actor policy, but
sets `browser_actor_connected`, `receipt_observer_connected`,
`attestation_exercised`, `journal_exercised`, and
`integrated_image_qualified` to `false`.  It must not be read as live
integrated-image or product-agent evidence.

No marker, development binary, or development unit is installed by
`packaging/debian/hepta-agent-portd.install`.
