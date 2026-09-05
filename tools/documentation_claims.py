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

# Focused UTS #39-style skeleton for the two authority labels.  NFKC already
# handles fullwidth and mathematical compatibility forms; this table covers
# common Greek/Cyrillic/IPA homoglyphs that do not compatibility-normalize.
# The fallback below rejects close declaration prefixes containing any other
# non-ASCII letter, so the table is not treated as an exhaustive allow-list.
_CONFUSABLE_ASCII = {
    "а": "a", "α": "a", "ɑ": "a",
    "с": "c", "ϲ": "c", "ᴄ": "c",
    "е": "e", "ε": "e", "ɛ": "e",
    "ɡ": "g", "ց": "g",
    "һ": "h", "н": "h",
    "і": "i", "ι": "i", "ı": "i", "ɩ": "i",
    "ӏ": "l", "ⅼ": "l", "Ɩ": "l",
    "м": "m", "μ": "m", "ᴍ": "m",
    "п": "n", "η": "n", "ո": "n",
    "о": "o", "ο": "o", "օ": "o",
    "р": "p", "ρ": "p",
    "г": "r", "ᴦ": "r",
    "ѕ": "s", "ꜱ": "s",
    "т": "t", "τ": "t", "ᴛ": "t",
    "υ": "u", "ս": "u", "ᴜ": "u",
    "х": "x", "χ": "x",
    "у": "y", "γ": "y",
}
_AUTHORITY_LABELS = ("currentstatus", "claimceiling", "status")


def _normalized_characters(text: str) -> str:
    decoded = unicodedata.normalize("NFKC", html.unescape(text)).casefold()
    # A second decomposition makes accents/combining overlays detection-only:
    # ``Currént`` and ``C̸urrent`` cannot hide a competing authority label.
    return unicodedata.normalize("NFKD", decoded)


def _detection_text(text: str) -> str:
    output: list[str] = []
    for character in _normalized_characters(text):
        if unicodedata.category(character).startswith("M"):
            continue
        if character.isascii() and (character.isalnum() or character in ":="):
            output.append(character)
            continue
        mapped = _CONFUSABLE_ASCII.get(character)
        if mapped is not None:
            output.append(mapped)
    return "".join(output)


def _bounded_edit_distance(left: str, right: str, limit: int) -> int:
    """Return a bounded Levenshtein distance without unbounded allocation."""
    if abs(len(left) - len(right)) > limit:
        return limit + 1
    previous = list(range(len(right) + 1))
    for row, left_character in enumerate(left, 1):
        current = [row]
        for column, right_character in enumerate(right, 1):
            current.append(min(
                current[-1] + 1,
                previous[column] + 1,
                previous[column - 1] + (left_character != right_character),
            ))
        previous = current
    return previous[-1]


def _non_ascii_claim_like_prefix(line: str) -> bool:
    """Reject visually claim-like declaration labels outside the ASCII grammar.

    Exact accepted declarations are ASCII.  This check is deliberately scoped
    to the prefix before ``:``/``=`` so ordinary multilingual prose remains
    valid.  Known homoglyphs map to a focused skeleton; unknown non-ASCII
    letters fail closed when deleting them leaves a near-authority label.
    """
    normalized = unicodedata.normalize("NFKC", html.unescape(line)).casefold()
    delimiters = [
        index
        for index in (normalized.find(":"), normalized.find("="))
        if index >= 0
    ]
    if not delimiters:
        return False
    prefix = normalized[:min(delimiters)]
    if not any(
        not character.isascii()
        and (unicodedata.category(character).startswith("L")
             or unicodedata.category(character).startswith("M"))
        for character in prefix
    ):
        return False

    skeleton = _detection_text(prefix)
    ascii_only = "".join(
        character
        for character in _normalized_characters(prefix)
        if character.isascii() and character.isalnum()
    )
    for authority in _AUTHORITY_LABELS:
        if skeleton == authority:
            return True
        limit = 1 if authority == "status" else 2
        # Markdown markers carry no letters, so declaration prefixes normally
        # reduce to the label itself.  A bounded suffix also catches blockquote
        # or list prose without treating arbitrary Unicode paragraphs as claims.
        for candidate in (skeleton, ascii_only):
            if not candidate:
                continue
            windows = {candidate}
            maximum = len(authority) + limit
            if len(candidate) > maximum:
                windows.add(candidate[-maximum:])
            if any(
                _bounded_edit_distance(window, authority, limit) <= limit
                for window in windows
            ):
                return True
    return False


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
    confusable_reported = False
    for index, line in enumerate(lines):
        if not confusable_reported and _non_ascii_claim_like_prefix(line):
            errors.append(f"{label} non-ASCII confusable authority declaration")
            confusable_reported = True
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
