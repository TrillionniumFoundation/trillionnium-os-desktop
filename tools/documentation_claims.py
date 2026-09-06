"""Exact documentation-claim validation with a rendering ambiguity guard.

The reviewed v17 line/bidi parser remains in ``documentation_claims_base``.
This module adds a bounded rendered-paragraph check for HTML, Markdown soft
wraps, invisible padding and C1 terminal controls, then re-exports the single
validator entrypoint used by the module and component documentation gates.
"""
from __future__ import annotations

import html
import unicodedata

from tools import documentation_claims_base as _base

_C1_TERMINAL_CONTROLS = frozenset(chr(value) for value in range(0x80, 0xA0))
_RENDER_BOUNDARIES = _base._DECLARATION_DELIMITERS | frozenset({";", "<"})
_VISIBLE_SUFFIX_LIMIT = 64


def _strip_html_rendering_markup(text: str) -> tuple[str, bool]:
    """Remove HTML tags/comments while retaining their rendered inner text."""
    output: list[str] = []
    saw_markup = False
    index = 0
    length = len(text)
    while index < length:
        if text.startswith("<!--", index):
            standard_end = text.find("-->", index + 4)
            bang_end = text.find("--!>", index + 4)
            ends = [end for end in (standard_end, bang_end) if end >= 0]
            saw_markup = True
            output.append(" ")
            if not ends:
                break
            end = min(ends)
            index = end + (4 if end == bang_end else 3)
            continue
        if text[index] == "<" and index + 1 < length and (
            text[index + 1].isalpha() or text[index + 1] in "/!?"
        ):
            saw_markup = True
            quote: str | None = None
            cursor = index + 1
            while cursor < length:
                character = text[cursor]
                if quote is not None:
                    if character == quote:
                        quote = None
                elif character in "'\"":
                    quote = character
                elif character == ">":
                    saw_markup = True
                    output.append(" ")
                    index = cursor + 1
                    break
                cursor += 1
            else:
                # Preserve the unclosed suffix once, rather than rescanning each
                # later ``<`` and turning malformed input into quadratic work.
                output.append(text[index:])
                break
            continue
        output.append(text[index])
        index += 1
    return "".join(output), saw_markup


def _near_suffix(candidate: str, authority: str, limit: int) -> bool:
    minimum = max(1, len(authority) - limit)
    maximum = min(len(candidate), len(authority) + limit)
    return any(
        _base._bounded_edit_distance(candidate[-size:], authority, limit) <= limit
        for size in range(minimum, maximum + 1)
    )


def _candidate_matches(candidate: str, *, saw_markup: bool) -> bool:
    for authority, limit in (("currentstatus", 2), ("claimceiling", 2), ("status", 1)):
        if _base._candidate_is_near_authority(candidate, authority, limit):
            return True
        if saw_markup and authority != "status" and _near_suffix(candidate, authority, limit):
            return True
    return False


def _unsafe_rendered_authority_text(text: str) -> bool:
    """Reject authority-shaped labels created by rendered paragraph semantics."""
    decoded = unicodedata.normalize("NFKC", html.unescape(text)).casefold()
    paragraphs: list[str] = []
    current: list[str] = []
    for line in decoded.splitlines():
        if line.strip():
            current.append(line)
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))

    for paragraph in paragraphs:
        rendered, saw_markup = _strip_html_rendering_markup(paragraph)
        skeleton: list[str] = []
        ascii_only: list[str] = []
        for character in rendered:
            category = unicodedata.category(character)
            if character in _base._INLINE_MARKUP or character.isspace():
                continue
            if category.startswith("M") or category.startswith("C"):
                continue
            if category[:1] in {"P", "S"}:
                if character in _RENDER_BOUNDARIES:
                    candidates = {"".join(skeleton), "".join(ascii_only)}
                    if saw_markup:
                        candidates.update(item[::-1] for item in tuple(candidates))
                    if any(_candidate_matches(item, saw_markup=saw_markup) for item in candidates):
                        return True
                skeleton.clear()
                ascii_only.clear()
                continue
            for decomposed in unicodedata.normalize("NFKD", character):
                if unicodedata.category(decomposed).startswith("M"):
                    continue
                if decomposed.isascii() and decomposed.isalnum():
                    skeleton.append(decomposed)
                    ascii_only.append(decomposed)
                else:
                    mapped = _base._CONFUSABLE_ASCII.get(decomposed)
                    if mapped is not None:
                        skeleton.append(mapped)
            del skeleton[:-_VISIBLE_SUFFIX_LIMIT]
            del ascii_only[:-_VISIBLE_SUFFIX_LIMIT]
    return False


def validate_claim_projection(
    text: str,
    status: object,
    claim_ceiling: object,
    *,
    kind: str,
    label: str,
) -> list[str]:
    """Run the v17 validator, then reject additional rendered ambiguity."""
    errors = list(
        _base.validate_claim_projection(
            text,
            status,
            claim_ceiling,
            kind=kind,
            label=label,
        )
    )
    if not isinstance(text, str):
        return errors
    try:
        if len(text.encode("utf-8")) > _base.MAX_DOCUMENT_BYTES:
            return errors
    except UnicodeEncodeError:
        return errors

    decoded = html.unescape(text)
    if any(character in _C1_TERMINAL_CONTROLS for character in decoded):
        message = f"{label} documentation contains terminal control characters"
        if message not in errors:
            errors.append(message)

    if isinstance(status, str) and isinstance(claim_ceiling, str) and kind in {"module", "component"}:
        expected_status = (
            f"**Current status:** `{status}`"
            if kind == "module"
            else f"Current status: `{status}`."
        )
        expected_claim = f"**Claim ceiling:** {claim_ceiling}."
        scan_lines = [
            "" if line in {expected_status, expected_claim} else line
            for line in text.splitlines()
        ]
        if _unsafe_rendered_authority_text("\n".join(scan_lines)):
            message = f"{label} ambiguous or rendering-shaped authority declaration"
            if message not in errors:
                errors.append(message)
    return errors
