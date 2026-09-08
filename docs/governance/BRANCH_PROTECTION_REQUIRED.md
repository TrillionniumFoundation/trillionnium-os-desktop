# Required GitHub repository protection

Source files cannot enable or prove GitHub repository controls. This checklist must be applied through repository/organization administration and then verified through live API readback and positive/negative probes.

## `main` branch

- prohibit direct pushes;
- prohibit force pushes and branch deletion;
- require pull requests;
- require review from CODEOWNERS;
- require at least two independent approvals for security-critical paths;
- dismiss approvals after every new push;
- require all selected status checks on the current head;
- require the branch to be current with `main` or use a merge queue;
- require conversation resolution;
- disallow administrator bypass for protected controls;
- require signed commits or a signed merge-commit policy;
- restrict branch updates to the merge service and approved maintainers.

## Security-critical paths

Changes under these paths require independent security review:

```text
.github/workflows/
contracts/
crates/hepta-agent-transport/
crates/hepta-peer-attestation/
crates/hepta-agent-port/
crates/hepta-session-core/
crates/hepta-browser-actor/
apps/hepta-agent-portd/
apps/hepta-browserd/
manifests/
packaging/
docs/adr/
docs/security/
docs/release/
```

## Release controls

- protect release environments;
- separate author, reviewer, builder, signer, attestor, and promoter identities;
- require immutable artifact digests;
- require signed tags and release metadata;
- use offline or HSM-backed keys with documented dual control;
- test key rotation, emergency revocation, and compromised-builder response.

## Verification

Closure requires both:

1. live readback showing the configured controls; and
2. negative probes showing that a direct push, stale approval, missing check, unauthorized environment deployment, and administrator bypass are rejected.

A CODEOWNERS file, workflow file, policy document, or successful hosted CI run is not closure by itself.
