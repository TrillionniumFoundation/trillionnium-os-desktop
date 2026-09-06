# Documentation rendering ambiguity guard

## Scope

`tools/documentation_claims.py` remains the only validator entrypoint imported by
the module and component documentation gates. The reviewed v17 line and bidi
parser is retained in `tools/documentation_claims_base.py`; the entrypoint adds
a bounded rendered-paragraph guard before returning its combined diagnostics.

The guard is detection-only. It does not normalize any untrusted declaration
into an accepted claim and grants no runtime, repository-administration,
hardware, signing, promotion, or release authority.

## Rejected rendering paths

The supplemental guard rejects declaration-shaped alternatives that can become
visible only after Markdown or HTML rendering, including:

- tags or comments inserted inside an authority label;
- HTML-wrapped or reversed labels and hidden-prefix spans;
- entity-decoded markup;
- Markdown soft-wraps that join a split label across source lines;
- inline, image, and full/collapsed reference links whose rendered labels
  assemble an authority declaration while their destinations remain invisible;
- long zero-width or combining-mark prefixes that attempt to exhaust a raw-byte
  scan budget;
- C1 terminal control strings in addition to the existing C0/DEL checks.

Only exact ASCII registry-bound `Current status` and `Claim ceiling` lines in the
canonical section remain accepted. Ordinary multilingual, RTL, HTML-emphasized,
statistics, state, estimate, ratio, and non-authority link prose remains
permitted when it is not declaration-shaped.

## Bounds and failure behavior

Input retains the one-mebibyte document limit. HTML scanning is linear, quote
aware, does not follow links, and never executes markup. Markdown square and
link-target delimiters are indexed with bounded one-pass stacks; destinations
are never fetched or interpreted. Candidate state retains only a 64-character
visible suffix, so invisible padding does not consume that budget. Unterminated
markup stays visible rather than causing the remainder of the document to
disappear from detection.

Any rendered ambiguity is a deterministic validation failure. Existing errors
from the v17 parser are preserved and de-duplicated by exact message text.

## Verification

`tests/test_documentation_rendering_guard.py` drives both real validator
entrypoints with HTML wrappers, comments, reversed markup, C1 controls,
soft-wraps, split inline/reference links, nested HTML link labels, angle and
balanced link destinations, and long invisible/tag padding. It also verifies
that ordinary multilingual, linked, and non-authority prose remains valid. The
existing claim-projection corpus and the authoritative full Python discovery
remain mandatory.
