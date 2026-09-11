# d6 applicability of inherited detailed annexes

Status: documentation consistency contract, not implementation or gate promotion.

The active plan is `2026-08-29-d6`. The three detailed annexes below originated
in d5 and retain requirements only under the overrides in this document. Their
historical work-package labels do not report current main or candidate status.
`manifests/project-state.v1.json`, `manifests/gates.v1.json`, the d6 executive
lock and `PR73_DECOMPOSITION.md` retain their existing precedence.

| Detailed annex | Retained requirements | d6 override |
| --- | --- | --- |
| `PRODUCT_ARCHITECTURE.md` | Product promise, one PageOwner, distinct trusted origins, desktop/mobile separation, runtime authority split | Trusted chrome is native/compositor-owned; an older optional shell WebView is not an approved alternative implementation. |
| `CONTRACT_SECURITY_TESTING.md` | Typed Browser API, bounded authenticated transport, layered references, arbitration, no blind effect replay, security and test classes | D3 activation is development-profile only; external origins, credentials and effects require their own current gates. |
| `WORK_PACKAGES_AND_GATES.md` | Detailed task decomposition and acceptance requirements | Old IMPLEMENTED/candidate labels and ordering are historical; current d6 machine gates and the S01–S12 decomposition determine execution and closure. |

## Conflict resolution

An inherited option never expands current authority. The more restrictive
current gate wins until a reviewed ADR explicitly changes the requirement.
In particular, optional external rendering in an old D2 example is not an
implicit permission to add a network device to a no-network D2I image. D0 host
qualification, standalone Servo behavior, QEMU boot and installed product
operation remain different evidence classes.

The canonical d6 plan is at `../DESKTOP_PLAN-2026-08-29-d6.md`. Source status
comes from the current structured registries, not from copying a paragraph or
an IMPLEMENTED label out of an inherited annex. A future plan revision must
update applicability, gate mappings and affected tests together.

## Verification

`tests/test_development_documentation.py` checks the three annex headers against
the active plan in `docs/MANIFEST.json`, rejects the obsolete D3 production
activation phrase, and checks the receipt operations example against the
machine-defined managed-store permissions. These tests complement rather than
replace independent semantic review of the retained requirements.
