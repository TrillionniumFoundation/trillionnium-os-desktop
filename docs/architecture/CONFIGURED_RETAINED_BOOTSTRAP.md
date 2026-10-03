# Configured retained bootstrap

This source entry composes one original protected Control connection with its
root-owned configured mechanism document. It yields the existing
`ApprovedRetainedAdmission`, which the separate exact-PIN native startup can
consume without splitting its original Agent stream and private terminal
monitor. It does not start either installed executable, create a listener,
provision a policy file, initialize Servo or authorize an application action.

`ConfiguredRetainedBootstrap::from_control(connection, expected_agent_path)`
reads only `/etc/hepta/approved-mechanisms.v1.conf`. It uses the original opaque
connection `Instant` when opening the document. No environment variable, peer
snapshot, executable measurement or caller-supplied principal can replace the
configured approval source. Missing, changed or unsafe root custody refuses.

`from_root_document(connection, expected_agent_path, document)` is the explicit
installation/qualification alternative. Its document is the existing opaque
`ApprovedPolicyDocument`, whose constructor enforces root-owned path/file
custody and the original bounded source ceiling. Both Control and Agent role
selections use that same moved document. Opening a second equivalent file does
not supply the same role source: the underlying admission binds the original
shared policy owner, not just equal bytes.

`original_deadline(&mut self)` checks the creating process, retained document and
original Control scope before returning its unchanged initial ceiling. A
shorter configured source ceiling can cause earlier refusal. This API never
captures another accepted scope or restarts the accepted 20-second budget.

`into_admission(self)` consumes one original SCM_RIGHTS handoff, checks the moved
scope after the old receiver permanently retires, and uses the same document's
Agent selection. The existing admission checks the default live procfs/pidfd
identities, approved ELF/unit, original pathname, cancellation and deadline. The
result retains its own shared policy owner after this bootstrap is destroyed.
The existing Control receiver publishes its original authenticated handoff
challenge after configured admission. No AgentPort handshake, native request,
journal admission or durable completion is generated here. Errors expose
existing `ProductDispatchError`
categories; private process/path details are not included.

The bootstrap is not Clone. A forked child cannot inspect or consume it. Its
legacy owners retain their existing foreign-process destruction rules. No new
Drop bound or preemptive cancellation of filesystem/procfs/native work is
claimed. Refusal before transfer does not certify cleanup of an accepted Agent
stream still held by the remote custodian; that owner retains its original
ceiling and cleanup obligations.

The real Linux target is `configured_retained_bootstrap_kernel`. It uses three
independent processes, root pathname custody, an externally selected transient
systemd unit, a fixture ELF pinned before the peer processes launch, default live
procfs and original kernel credentials. It checks valid complete admission and
drop, policy drift before receive, a shorter source deadline without renewal,
and child refusal while parent custody remains valid. Each case checks complete
descriptor inventory return. Those are configured-ingress source observations,
not actual Servo, an installed service, headed input or hardware qualification.

Run the target with the repository's Rust 1.93 toolchain:

```sh
CARGO_PROFILE_TEST_DEBUG=0 CARGO_PROFILE_TEST_OPT_LEVEL=1 \
  cargo test --locked -p hepta-browserd --test configured_retained_bootstrap_kernel
cargo test --locked -p hepta-browserd --doc
```

The existing `ApprovedImmutableNativeStartup` still gives its native owner the
first packet's initial ceiling and refuses later ceilings beyond it. This
bootstrap preserves that bound. A long-lived installed daemon/session needs a
separate lifecycle design and fresh review; this entry does not close that gap.
The two installed mains remain default-disabled scaffolds and no systemd unit,
installer map, production policy or release claim changes in this package.
