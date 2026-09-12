# Image workflow source binding and D1/D2I composition

## Scope and claim ceiling

This contract repairs executable source/evidence plumbing for the existing D1
and D2I substrate inside `.github/workflows/s10-production-debian-qemu.yml`.
It does not supply a product BrowserActor/Servo service path, install a product,
prove a boot, authenticate external evidence, grant promotion, or close S10.
A successful source test is not a successful image run.

## One current workflow

The former `d1-final-qualification.yml` and `d2i-integrated-image.yml` files were
removed during S10 reconstruction. Tests, runtime source checks, D1/D2I evidence
finalizers and the gate registry now reference the actual S10 workflow. No
empty historical workflow or success-only alias is introduced. The existing
image construction, exact e2fsprogs/Servo inputs, two-image comparison, QEMU
corpus, resource reclamation and bounded failure diagnostics remain executable
and required.

The source gate is unfiltered for pull requests and main pushes, including
transitive contract/tool/runtime changes. Explicit manual invocation remains
non-authoritative. D1 and D2I invalidation sets now cover workspace manifests,
Rust toolchain, every crate/application, contracts, runtime, package/image
inputs, workflows, helpers and fixture/QEMU corpora. Their current status,
evidence tier, prerequisites and claim ceilings are not promoted by this
source change.

## Event identity instead of a historical direct-parent constant

`tools/image_workflow_identity.py` checks one closed context. A PR binds the
repository, exact event head, event base, event merge, current canonical pull
head/merge refs and the current base ref. The exact-head source is the event
head. The prospective object must have exactly the ordered base/head parents.
Multiple commits in a bounded successor are valid: the candidate's immediate
parent need not equal its base. Head, base or merge movement makes evidence
stale and fails; deleting the old direct-S09-parent assumption does not permit
stale event evidence.

Main pushes bind the exact current main ref. Manual execution binds one
explicit current branch and never supplies a synthetic merge identity. Unknown
events, malformed identities, ambiguous refs and dirty checkouts are rejected.
Both source objects run the full top-level and D1 Python corpora before an
expensive image job is admitted. Live identity is checked again before and
after final image-evidence assembly.

The current S10 image lane still executes an exact-head, non-authoritative D1/
D2I qualification profile. The prospective source test cannot transfer its
result to a different image. Real product installation, protected promotion,
independent review and an exact-main product rerun remain separate work.

## Producer/consumer parity

The D1 producer emits schema `trillionnium.desktop.d1-final-qualification.v3`
with status `PASS`; it does not emit `PASS_D1_FINAL_QUALIFICATION`. The D2I
consumer now validates that actual schema/status rather than an impossible
legacy string. It additionally requires exact repository/base/head/tested/tree,
source ref, evidence role, authority boolean and current workflow digest.
Every D1 non-claim must remain explicitly false and product/fixture isolation
must remain intact. The qualification feature is the current explicit
`fixture` example graph, not the retired `d1-qualification` feature.

D2I records the bound `SOURCE_REF`/`SOURCE_REF_NAME` used by its embedded D1
receipt, not a different checkout/event ref. No old receipt is rewritten, and
changed source/workflow inputs invalidate old evidence. This is integrity and
correspondence checking; it is not an external signature or proof that a packet
was honestly produced. Independent attestation remains required at its gate.

The staging copy helper permits an already-created destination directory so
multiple QEMU/preparation files can be collected in the same directory. A
filesystem regression executes two real copies and verifies both bytes; this
fix does not accept a missing or symlinked source.

## Tests and failure handling

Run `python3 tools/validate_image_source_contract.py`, top-level Python
discovery and the complete `tests/d1` corpus. The added tests create a disposable
local Git repository and local bare remote to exercise multiple candidate
commits, an ordered prospective merge and live-ref movement without network or
production repository writes. Other tests reject mismatched source/workflow,
invalid or numeric authority booleans, widened/missing non-claims, qualification
target drift, obsolete paths, missing transitive invalidation and filtered or
writable source workflows.

These tests do not execute QEMU or manufacture a successful image. A failed
builder, changed lock, omitted command, failed source gate, timeout, missing
artifact or unfinished product entrypoint remains a blocker. Preserve bounded
diagnostics and keep higher claims false; do not weaken the gate or substitute
a fixture for the product path.
