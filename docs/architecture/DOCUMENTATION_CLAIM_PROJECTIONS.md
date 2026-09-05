# Canonical documentation status and claim projections

**Plan:** `2026-08-29-d6`
**Scope:** source-quality consistency only; no runtime or promotion authority

## Authority and format

`manifests/modules.v1.json` and `manifests/components.v1.json` own their
registered status and claim-ceiling values. The corresponding README must
render each value exactly once in the top-level `Status and claim ceiling`
section, before the next top-level section. The two existing formats remain
explicit and are not interchangeably normalized:

```text
Cargo module: **Current status:** `registry_status`
Component:    Current status: `registry_status`.
Both:         **Claim ceiling:** registry_claim_ceiling.
```

The final period on a claim, and on a component status, is display syntax,
not part of the registry value. There may be no leading/trailing whitespace,
case changes, alternate labels, extra emphasis, or a competing declaration.
The exact lines and section cannot live in a code fence or HTML comment.

`tools/documentation_claims.py` is shared by both documentation validators.
It bounds documents and registry values, checks original lines exactly, and
uses case folding, compatibility normalization, canonical decomposition,
HTML entity decoding, a focused Greek/Cyrillic homoglyph skeleton, and
whitespace/punctuation removal only to detect disguised duplicate labels.
A declaration-shaped prefix containing an unmapped non-ASCII letter also fails
closed when its ASCII remainder is within a bounded edit distance of an
authority label. This rule applies only before `:` or `=`; ordinary multilingual
prose remains valid. Normalization never repairs an invalid declaration into an
accepted one.

## Tests

`tests/test_documentation_claim_projection.py` and
`tests/test_validator_loader_stability.py` invoke both real validator entrypoints
against isolated fixtures. They reject README-only and registry-only
status/claim changes, missing and repeated values, contradictory declarations,
case/space/tab/newline/fullwidth/zero-width/entity spelling, Cyrillic/Greek
homoglyphs, combining marks, mixed-script labels, code fences, comments, and
declarations moved outside the designated section. All 12 module
and 14 component projections are checked against their committed registries.

The older fixtures now contain the same exact metadata as real documentation;
a fixture without status or with a different claim is not a valid baseline.
Run the focused tests, both CLI validators, repository/truth/governance checks,
and the authoritative whole-tree Python discovery before independent review.

## Limits and change protocol

This is a structured-field consistency check, not a natural-language truth
oracle or an authorization engine. Arbitrary prose still requires review.
Changing a registry and its projection together does not prove the new claim;
applicable gate evidence, independent review, and post-merge exact-main tests
remain required. No status, evidence tier, or production flag is promoted by
this repair. Historical evidence is never rewritten to manufacture a rerun.

A helper, format, registry, or validator change invalidates the documentation
source gate. Update the same regression corpus and both validator callers;
keep configuration and paths repository-owned rather than user-selected.

## Rendering-safe authority prefix

The prologue through the last authority declaration uses a restricted Markdown
subset: no raw HTML, fenced blocks, or multiline backtick spans. Inline code
must close on the same line. General code examples remain valid after the
metadata. This intentionally avoids a partial Markdown parser accepting a
four-backtick block after a three-backtick line or losing HTML comment state
when a close and a new open occur on the same line. Both validator entrypoints
exercise those regressions. Non-Cargo required sections are exact full lines,
unique, and ordered; the repository root cannot itself be a symlink.

## Explicit Cargo executable boundary

Every registered workspace package sets `autobins = false` and `build = false`.
The validator compares explicit `[[bin]]` declarations with the registry and
rejects orphan conventional binary sources and package build scripts. Existing
explicit feature-gated targets are unchanged; integration-test auto-discovery
remains enabled. A new build-script requirement needs a separately reviewed
policy/registry design, not removal of the safety switch. This source policy
must also pass Cargo checks on the pinned toolchain before integration.
