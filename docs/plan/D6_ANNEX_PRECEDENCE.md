# d6 annex inheritance and precedence

The active product plan is `docs/DESKTOP_PLAN-2026-08-29-d6.md`.
`manifests/project-state.v1.json` and `manifests/gates.v1.json` remain the
canonical status and gate authorities. This page selects design precedence;
it does not create another project-state registry or promote a candidate.

## Retained historical material

The original d5 annex bytes are retained alongside the active entry points as
`PRODUCT_ARCHITECTURE.d5-historical.md`,
`CONTRACT_SECURITY_TESTING.d5-historical.md`, and
`WORK_PACKAGES_AND_GATES.d5-historical.md`. Their historical headers, package
statuses, immediate execution order and former authority statements are part
of the snapshot, not current operational instructions. They must not be used
to reopen permissions or to report current completion.

## Controlling interpretation

| Concern | Retained design detail | Current controlling decision |
| --- | --- | --- |
| Visible workspace | One PageOwner and one logical untrusted content surface | d6 and the chosen native trusted-chrome composition; no automatic adoption of the historical two-WebView option |
| AgentPort | Local transport, bounded framing and identity custody | Default disabled; D3 activation is an explicitly selected development/qualification profile, not production activation |
| BrowserActor and Servo | Typed operation and semantic-reference design | S06/S07/S08 successor contracts; source bridge or mailbox does not prove the installed product path |
| Receipts | Requested/dispatched/outcome facts; no blind replay | Current receipt contracts and managed-store failure model; directory 0700, files 0600; hash chains alone do not establish authenticated anti-rollback |
| External navigation/effects | Controlled resolver, egress and effect reconciliation | No widening from a historical optional rendering corpus; current d6 profile, permit, egress and effect gates must pass |
| D1/D2 integration | Locked Debian inputs and headed content | D2I/S10 evidence on one exact installed image; a fixture image cannot stand in for product dispatch |
| Governance | Independent review and least privilege | D0T-03 live settings/readback; repository source cannot certify enforced protection |
| Hardware and release | Fixed BOM, reproducibility and recovery | S11/S12, protected independent promotion, real hardware/endurance/power/key evidence; no inference from source CI |
| Package completion | Historical IMPLEMENTED, NEXT, HOST VALIDATED labels | Only current machine truth plus exact-object evidence; historical labels are not status projections |

## Amendment rule

A design change must update its current contract, tests and applicable active
entry point together. A historical snapshot is never silently edited to look
current. A conflict is resolved by the narrower claim until the controlling
contract and its evidence are reviewed. New dates or new document names alone
do not authorize a broader product claim.

Run `python3 tools/validate_documentation_integrity.py` and the
`test_module_documentation_integrity` corpus after changes. The source gate
checks current annex headers, exact module-index projection and executable
receipt-permission guidance; it is not a formal proof of architectural
completeness and does not replace independent review.
