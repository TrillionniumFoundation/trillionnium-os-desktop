"""Exact, non-authorizing status/claim projections for module and component docs.

Normalization is used only to *detect and reject* disguised duplicate labels.
Acceptance always compares the original, complete line with the registry value.
This checks structured declarations, not the truth of arbitrary natural language.
"""
from __future__ import annotations

import html
import re
import unicodedata

SECTION = "## Status and claim ceiling"
MAX_DOCUMENT_BYTES = 1_048_576
STATUS = re.compile(r"[a-z][a-z0-9_]{0,127}\Z")


def _detection_text(text: str) -> str:
    decoded = unicodedata.normalize("NFKC", html.unescape(text)).casefold()
    return "".join(c for c in decoded if c.isascii() and (c.isalnum() or c in ":="))


def validate_claim_projection(
    text: str,
    status: object,
    claim_ceiling: object,
    *,
    kind: str,
    label: str,
) -> list[str]:
    """Require unique exact declarations in the designated top-level section.

    Cargo: ``**Current status:** `value```; component: ``Current status: `value`.``.
    Both use ``**Claim ceiling:** value.``; the final period is display syntax,
    not part of the registry value. Declarations in fences/comments are invalid.
    Labels may not be repeated anywhere, even in examples or disguised spelling.
    Registry changes still need independent review; matching prose grants no tier.
    """
    errors: list[str] = []
    if kind not in {"module", "component"}:
        return [f"{label} unsupported documentation claim kind {kind!r}"]
    if not isinstance(text, str):
        return [f"{label} documentation must be UTF-8 text"]
    try:
        size = len(text.encode("utf-8")) if len(text) <= MAX_DOCUMENT_BYTES else MAX_DOCUMENT_BYTES + 1
    except UnicodeEncodeError:
        return [f"{label} documentation is not valid UTF-8 text"]
    if size > MAX_DOCUMENT_BYTES:
        return [f"{label} documentation exceeds the bounded claim parser limit"]
    if not isinstance(status, str) or STATUS.fullmatch(status) is None:
        errors.append(f"{label} registry status must be a canonical lowercase identifier")
    if (
        not isinstance(claim_ceiling, str)
        or not 1 <= len(claim_ceiling) <= 4096
        or claim_ceiling != claim_ceiling.strip()
        or any(unicodedata.category(c).startswith("C") or c in "\r\n\t<>`*" for c in claim_ceiling)
        or unicodedata.normalize("NFKC", claim_ceiling) != claim_ceiling
    ):
        errors.append(f"{label} registry claim_ceiling must be bounded single-line plain text")
    if errors:
        return errors

    expected = {
        "status": (
            f"**Current status:** `{status}`"
            if kind == "module" else f"Current status: `{status}`."
        ),
        "claim_ceiling": f"**Claim ceiling:** {claim_ceiling}.",
    }
    lines = text.splitlines()
    section_starts = [i for i, line in enumerate(lines) if line == SECTION]
    if len(section_starts) != 1:
        errors.append(f"{label} must contain the canonical claim section exactly once")
        start, end = -1, -1
    else:
        start = section_starts[0]
        end = next((i for i in range(start + 1, len(lines)) if re.match(r"^ {0,3}#{1,2}(?:[ \t]|$)", lines[i])), len(lines))

    # Scan the whole document, not just the canonical block. NFKC, HTML entities,
    # line breaks, emphasis, case, and zero-width characters cannot hide repeats.
    detected = _detection_text(text)
    for field, spelling in (("status", "currentstatus"), ("claim_ceiling", "claimceiling")):
        if len(re.findall(spelling + r"[:=]", detected)) != 1:
            errors.append(f"{label} {field} declaration must be unique and unambiguous")
        positions = [i for i, line in enumerate(lines) if line == expected[field]]
        if len(positions) != 1:
            errors.append(f"{label} {field} must exactly match its registry projection")
        elif not start < positions[0] < end:
            errors.append(f"{label} {field} must occur inside the canonical claim section")

    # Authority metadata uses a deliberately narrower grammar than general
    # Markdown. A parser approximation must not certify a declaration that the
    # renderer treats as code, an HTML block, or a multiline inline code span.
    # Nothing before or between the authoritative fields may open those scopes.
    # The remaining document is unrestricted except for competing declarations.
    authority_positions = [i for i, line in enumerate(lines) if line in expected.values()]
    prefix_end = max(authority_positions, default=-1)
    for index, line in enumerate(lines):
        if index <= prefix_end:
            if "<" in line or re.match(r"^ {0,3}(?:`{3,}|~{3,})", line):
                errors.append(f"{label} authority prefix cannot contain raw HTML or code fences")
            runs = re.findall(r"`+", line)
            pending = None
            for run in runs:
                if pending is None:
                    pending = len(run)
                elif len(run) == pending:
                    pending = None
            if pending is not None:
                errors.append(f"{label} authority prefix cannot contain multiline code spans")
        if re.match(r"status[:=]", _detection_text(line)):
            errors.append(f"{label} noncanonical competing status declaration")
    return errors
