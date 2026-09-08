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

# Delimiters that can render as a colon/equality declaration boundary but do
# not all compatibility-normalize to ASCII.  A canonical declaration still
# accepts only literal ASCII ``:``; these are detection-only and fail closed.
_DECLARATION_DELIMITERS = frozenset({
    ":", "=", "ː", "ˑ", "˸", "׃", "։", "܃", "܄", "܅", "܆", "܇",
    "܈", "܉", "፥", "፦", "᠄", "⁚", "⁝", "∶", "⦂", "⠒", "ꓽ", "꞉",
    "︓", "﹕", "：", "⁼", "₌", "≔", "≕", "⩴", "⩵", "﹦", "＝",
})
# Inline Markdown decoration may surround an authority label.  It is not itself
# a declaration boundary; other punctuation/symbols after a near-authority
# prefix are treated as ambiguous rather than maintained as an exhaustive list.
_INLINE_MARKUP = frozenset("*_`~")
MAX_AUTHORITY_PREFIX_CHARS = 256
_BIDI_EMBEDDING_OPENERS = frozenset({"‪", "‫", "‭", "‮"})
_BIDI_ISOLATE_OPENERS = frozenset({"⁦", "⁧", "⁨"})
_BIDI_OPENERS = _BIDI_EMBEDDING_OPENERS | _BIDI_ISOLATE_OPENERS
_BIDI_REVERSE_OPENERS = frozenset({"‫", "‮", "⁧", "⁨"})
_TERMINAL_CONTROLS = frozenset(
    chr(value)
    for value in (*range(0x00, 0x09), *range(0x0B, 0x20), 0x7F)
)


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


def _apply_bidi_controls(stack: list[str], text: str) -> bool:
    """Update explicit bidi state and report malformed or excessive nesting."""
    valid = True
    for character in unicodedata.normalize("NFKC", html.unescape(text)):
        if character in _BIDI_OPENERS:
            if len(stack) >= 125:
                valid = False
            else:
                stack.append(character)
            continue
        if character == "\u202c":  # PDF cannot cross an isolate boundary.
            matched = False
            for index in range(len(stack) - 1, -1, -1):
                if stack[index] in _BIDI_ISOLATE_OPENERS:
                    break
                if stack[index] in _BIDI_EMBEDDING_OPENERS:
                    del stack[index]
                    matched = True
                    break
            if not matched:
                valid = False
            continue
        if character == "\u2069":  # PDI closes the innermost isolate and nested state.
            matched = False
            for index in range(len(stack) - 1, -1, -1):
                if stack[index] in _BIDI_ISOLATE_OPENERS:
                    del stack[index:]
                    matched = True
                    break
            if not matched:
                valid = False
    return valid


def _candidate_is_near_authority(candidate: str, authority: str, limit: int) -> bool:
    """Match a complete declaration prefix, never an arbitrary prose substring."""
    return bool(candidate) and _bounded_edit_distance(candidate, authority, limit) <= limit


def _unsafe_claim_like_prefix(
    line: str,
    *,
    inherited_bidi: tuple[str, ...] = (),
) -> bool:
    """Reject declaration-shaped alternatives outside the exact ASCII grammar.

    The exact canonical labels remain valid and are checked separately against
    the registry. Detection rejects near-ASCII typos, non-ASCII homoglyphs,
    visually confusable delimiters, and labels affected by bidi state inherited
    from a prior source line. It never normalizes an invalid line into an
    accepted declaration. Work is linear in the bounded prefix length.
    """
    normalized = unicodedata.normalize("NFKC", html.unescape(line)).casefold()
    prefix_region = normalized[:MAX_AUTHORITY_PREFIX_CHARS]
    bidi_stack = list(inherited_bidi)
    has_control = bool(bidi_stack)
    has_non_ascii_letter_or_mark = False
    reverse_sensitive = any(
        character in _BIDI_REVERSE_OPENERS for character in bidi_stack
    )
    skeleton: list[str] = []
    ascii_only: list[str] = []

    for character in prefix_region:
        is_boundary = (
            character in _DECLARATION_DELIMITERS
            or (
                character not in _INLINE_MARKUP
                and unicodedata.category(character)[:1] in {"P", "S"}
            )
        )
        if is_boundary:
            candidates = {"".join(skeleton), "".join(ascii_only)}
            if reverse_sensitive:
                candidates.update(candidate[::-1] for candidate in tuple(candidates))

            # An exact ASCII label with an ASCII delimiter is handled by the
            # unique/exact projection checks below. Every near spelling or
            # visually alternative delimiter is ambiguous and rejected.
            exact_ascii = (
                character in {":", "="}
                and not has_control
                and not has_non_ascii_letter_or_mark
                and "".join(skeleton) in _AUTHORITY_LABELS
            )
            if not exact_ascii:
                for authority in _AUTHORITY_LABELS:
                    limit = 1 if authority == "status" else 2
                    for candidate in candidates:
                        if _candidate_is_near_authority(candidate, authority, limit):
                            return True
                        # Rendering controls can erase/interpose bytes. Requiring
                        # the authority as a subsequence catches decorated labels
                        # without treating control-free prose as metadata.
                        if has_control:
                            iterator = iter(candidate)
                            if all(
                                any(item == expected for item in iterator)
                                for expected in authority
                            ):
                                return True

        category = unicodedata.category(character)
        if category.startswith("C"):
            has_control = True
        if character in _BIDI_REVERSE_OPENERS:
            reverse_sensitive = True
        if not _apply_bidi_controls(bidi_stack, character):
            return True
        reverse_sensitive = reverse_sensitive or any(
            opener in _BIDI_REVERSE_OPENERS for opener in bidi_stack
        )
        if not character.isascii() and (
            category.startswith("L") or category.startswith("M")
        ):
            has_non_ascii_letter_or_mark = True

        for decomposed in unicodedata.normalize("NFKD", character):
            decomposed_category = unicodedata.category(decomposed)
            if decomposed_category.startswith("M"):
                continue
            if decomposed.isascii() and decomposed.isalnum():
                skeleton.append(decomposed)
                ascii_only.append(decomposed)
                continue
            if decomposed.isascii() and decomposed in ":=":
                skeleton.append(decomposed)
                continue
            mapped = _CONFUSABLE_ASCII.get(decomposed)
            if mapped is not None:
                skeleton.append(mapped)
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
    decoded_text = html.unescape(text)
    if any(character in _TERMINAL_CONTROLS for character in decoded_text):
        errors.append(f"{label} documentation contains terminal control characters")
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
    bidi_stack: list[str] = []
    bidi_sequence_valid = True
    for index, line in enumerate(lines):
        if not confusable_reported and _unsafe_claim_like_prefix(
            line, inherited_bidi=tuple(bidi_stack)
        ):
            errors.append(f"{label} ambiguous or rendering-shaped authority declaration")
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
        if not _apply_bidi_controls(bidi_stack, line):
            bidi_sequence_valid = False
    if not bidi_sequence_valid:
        errors.append(f"{label} documentation contains malformed bidi formatting controls")
    if bidi_stack:
        errors.append(f"{label} documentation contains unbalanced bidi formatting controls")
    return errors
