#!/usr/bin/env python3
"""Fail-closed validation for the bounded S02 contract foundation.

This validator owns two deliberately separate checks:

* a closed, strictly decoded machine registry; and
* a syntax-scoped source audit that removes comments and literals before
  inspecting the exact Rust impl/function/match-arm that owns each invariant.

Rust behavior is additionally exercised by table-driven unit tests in the
contract and session crates. The source audit is a defense-in-depth guard, not
a substitute for compilation or tests.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

ROOT_KEYS = frozenset(
    {
        "schema",
        "bounded_identifiers",
        "dns_label",
        "revision_clock",
        "sha256_hex",
        "unix_millis",
    }
)
IDENTIFIER_KEYS = frozenset(
    {
        "allowed_ascii",
        "lease_id_max_utf8_bytes",
        "request_id_max_utf8_bytes",
        "session_id_max_utf8_bytes",
    }
)
DNS_KEYS = frozenset({"max_ascii_bytes", "pattern"})
REVISION_KEYS = frozenset({"counter_type", "initial", "overflow_policy"})
REVISION_INITIAL_KEYS = frozenset(
    {
        "document_generation",
        "mutation_epoch",
        "semantic_snapshot_revision",
        "session_generation",
    }
)
SHA_KEYS = frozenset({"alphabet", "length_ascii_bytes"})
UNIX_MILLIS_KEYS = frozenset({"rust_type"})

EXPECTED_REGISTRY = {
    "schema": "trillionnium.desktop.contract-core-constraints.v1",
    "bounded_identifiers": {
        "allowed_ascii": "A-Z a-z 0-9 . _ : -",
        "lease_id_max_utf8_bytes": 128,
        "request_id_max_utf8_bytes": 128,
        "session_id_max_utf8_bytes": 128,
    },
    "dns_label": {
        "max_ascii_bytes": 63,
        "pattern": "^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$",
    },
    "revision_clock": {
        "counter_type": "u64",
        "initial": {
            "document_generation": 1,
            "mutation_epoch": 0,
            "semantic_snapshot_revision": 0,
            "session_generation": 1,
        },
        "overflow_policy": "error_before_any_state_change",
    },
    "sha256_hex": {
        "alphabet": "0123456789abcdef",
        "length_ascii_bytes": 64,
    },
    "unix_millis": {"rust_type": "i64"},
}


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def reject_non_json_constant(value: str) -> None:
    raise ValueError(f"non-JSON numeric constant {value!r}")


def reject_float(value: str) -> None:
    # The registry contains integer bounds only. Rejecting every float also
    # rejects overflowing exponent spellings that Python would turn into inf.
    raise ValueError(f"floating-point value is forbidden: {value!r}")


def strict_json_loads(text: str) -> Any:
    return json.loads(
        text,
        object_pairs_hook=reject_duplicate_keys,
        parse_constant=reject_non_json_constant,
        parse_float=reject_float,
    )


def _expect_object(value: Any, path: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object")
        return {}
    return value


def _expect_exact_keys(
    value: dict[str, Any], expected: frozenset[str], path: str, errors: list[str]
) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        errors.append(f"{path} is missing keys: {missing}")
    if extra:
        errors.append(f"{path} has unexpected keys: {extra}")


def _expect_exact_value(
    value: Any, expected: Any, path: str, errors: list[str]
) -> None:
    # bool is a subclass of int in Python. Security bounds must not silently
    # accept true/false as 1/0.
    if type(value) is not type(expected) or value != expected:
        errors.append(f"{path} must equal {expected!r}, found {value!r}")


def validate_registry_data(value: Any) -> list[str]:
    errors: list[str] = []
    root = _expect_object(value, "$", errors)
    _expect_exact_keys(root, ROOT_KEYS, "$", errors)
    _expect_exact_value(
        root.get("schema"), EXPECTED_REGISTRY["schema"], "$.schema", errors
    )

    identifiers = _expect_object(
        root.get("bounded_identifiers"), "$.bounded_identifiers", errors
    )
    _expect_exact_keys(
        identifiers, IDENTIFIER_KEYS, "$.bounded_identifiers", errors
    )
    for key, expected in EXPECTED_REGISTRY["bounded_identifiers"].items():
        _expect_exact_value(
            identifiers.get(key),
            expected,
            f"$.bounded_identifiers.{key}",
            errors,
        )

    dns = _expect_object(root.get("dns_label"), "$.dns_label", errors)
    _expect_exact_keys(dns, DNS_KEYS, "$.dns_label", errors)
    for key, expected in EXPECTED_REGISTRY["dns_label"].items():
        _expect_exact_value(dns.get(key), expected, f"$.dns_label.{key}", errors)

    revision = _expect_object(
        root.get("revision_clock"), "$.revision_clock", errors
    )
    _expect_exact_keys(revision, REVISION_KEYS, "$.revision_clock", errors)
    _expect_exact_value(
        revision.get("counter_type"),
        EXPECTED_REGISTRY["revision_clock"]["counter_type"],
        "$.revision_clock.counter_type",
        errors,
    )
    _expect_exact_value(
        revision.get("overflow_policy"),
        EXPECTED_REGISTRY["revision_clock"]["overflow_policy"],
        "$.revision_clock.overflow_policy",
        errors,
    )
    initial = _expect_object(
        revision.get("initial"), "$.revision_clock.initial", errors
    )
    _expect_exact_keys(
        initial, REVISION_INITIAL_KEYS, "$.revision_clock.initial", errors
    )
    for key, expected in EXPECTED_REGISTRY["revision_clock"]["initial"].items():
        _expect_exact_value(
            initial.get(key),
            expected,
            f"$.revision_clock.initial.{key}",
            errors,
        )

    digest = _expect_object(root.get("sha256_hex"), "$.sha256_hex", errors)
    _expect_exact_keys(digest, SHA_KEYS, "$.sha256_hex", errors)
    for key, expected in EXPECTED_REGISTRY["sha256_hex"].items():
        _expect_exact_value(
            digest.get(key), expected, f"$.sha256_hex.{key}", errors
        )

    unix = _expect_object(root.get("unix_millis"), "$.unix_millis", errors)
    _expect_exact_keys(unix, UNIX_MILLIS_KEYS, "$.unix_millis", errors)
    _expect_exact_value(
        unix.get("rust_type"),
        EXPECTED_REGISTRY["unix_millis"]["rust_type"],
        "$.unix_millis.rust_type",
        errors,
    )
    return errors


def load_registry(root: Path) -> tuple[dict[str, Any], list[str]]:
    path = root / "contracts/contract-core-constraints.v1.json"
    try:
        value = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        return {}, [f"invalid contract constraint registry: {error}"]
    errors = validate_registry_data(value)
    return value if isinstance(value, dict) else {}, errors


def strip_rust_noncode(source: str) -> str:
    """Replace comments and string/character contents with spaces.

    Newlines and punctuation outside literals are preserved, so function and
    match-arm scopes can be extracted without accepting tokens from comments,
    documentation, strings, byte strings, character literals, or raw strings.
    """

    output = list(source)
    length = len(source)
    index = 0

    def blank(start: int, end: int) -> None:
        for position in range(start, end):
            if output[position] != "\n":
                output[position] = " "

    while index < length:
        if source.startswith("//", index):
            end = source.find("\n", index)
            if end < 0:
                end = length
            blank(index, end)
            index = end
            continue

        if source.startswith("/*", index):
            start = index
            depth = 1
            index += 2
            while index < length and depth:
                if source.startswith("/*", index):
                    depth += 1
                    index += 2
                elif source.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
            blank(start, index)
            continue

        raw = re.match(r'(?:b|c)?r(#{0,255})"', source[index:])
        if raw:
            hashes = raw.group(1)
            start = index
            index += raw.end()
            terminator = '"' + hashes
            end = source.find(terminator, index)
            index = length if end < 0 else end + len(terminator)
            blank(start, index)
            continue

        prefix_length = 0
        if source.startswith('b"', index) or source.startswith('c"', index):
            prefix_length = 1
        if source[index + prefix_length : index + prefix_length + 1] == '"':
            start = index
            index += prefix_length + 1
            escaped = False
            while index < length:
                character = source[index]
                index += 1
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    break
            blank(start, index)
            continue

        # A lifetime such as 'a is not a character literal.
        if source[index] == "'":
            match = re.match(r"'(?:\\.|[^\\'\n])+'", source[index:])
            if match:
                start = index
                index += match.end()
                blank(start, index)
                continue
        index += 1

    return "".join(output)


def _extract_braced(code: str, open_brace: int, label: str) -> str:
    if open_brace < 0 or open_brace >= len(code) or code[open_brace] != "{":
        raise ValueError(f"{label} has no opening brace")
    depth = 0
    for index in range(open_brace, len(code)):
        if code[index] == "{":
            depth += 1
        elif code[index] == "}":
            depth -= 1
            if depth == 0:
                return code[open_brace + 1 : index]
    raise ValueError(f"{label} has an unterminated body")


def extract_impl_body(source: str, type_name: str) -> str:
    code = strip_rust_noncode(source)
    match = re.search(rf"\bimpl\s+{re.escape(type_name)}\s*\{{", code)
    if match is None:
        raise ValueError(f"missing impl {type_name}")
    return _extract_braced(code, code.find("{", match.start()), f"impl {type_name}")


def extract_function_body(impl_body: str, function_name: str) -> str:
    match = re.search(
        rf"\b(?:pub\s+)?(?:const\s+)?fn\s+{re.escape(function_name)}\s*\(",
        impl_body,
    )
    if match is None:
        raise ValueError(f"missing function {function_name}")
    open_brace = impl_body.find("{", match.end())
    if open_brace < 0:
        raise ValueError(f"function {function_name} has no body")
    semicolon = impl_body.find(";", match.end(), open_brace)
    if semicolon >= 0:
        raise ValueError(f"function {function_name} has no body")
    return _extract_braced(impl_body, open_brace, f"function {function_name}")


def extract_match_arm(function_body: str, variant: str) -> str:
    match = re.search(
        rf"\b{re.escape(variant)}(?:\s*\{{[^=]*\}})?\s*=>\s*\{{",
        function_body,
    )
    if match is None:
        raise ValueError(f"missing match arm {variant}")
    return _extract_braced(
        function_body,
        function_body.find("{", match.end() - 1),
        f"match arm {variant}",
    )


def _require_pattern(
    text: str, pattern: str, label: str, errors: list[str]
) -> None:
    if re.search(pattern, text, re.S) is None:
        errors.append(f"{label} is missing required syntax {pattern!r}")


def audit_core_source(source: str) -> list[str]:
    errors: list[str] = []
    code = strip_rust_noncode(source)
    if "saturating_add" in code:
        errors.append("contract core silently saturates a revision")

    for name, value in {
        "MAX_REQUEST_ID_BYTES": 128,
        "MAX_SESSION_ID_BYTES": 128,
        "MAX_LEASE_ID_BYTES": 128,
    }.items():
        _require_pattern(
            code,
            rf"\bpub\s+const\s+{name}\s*:\s*usize\s*=\s*{value}\s*;",
            f"contract core constant {name}",
            errors,
        )

    try:
        impl_body = extract_impl_body(source, "RevisionClock")
    except ValueError as error:
        return errors + [str(error)]

    try:
        new_body = extract_function_body(impl_body, "new")
    except ValueError as error:
        errors.append(str(error))
    else:
        for field, value in {
            "session_generation": 1,
            "document_generation": 1,
            "semantic_snapshot_revision": 0,
            "mutation_epoch": 0,
        }.items():
            _require_pattern(
                new_body,
                rf"\b{field}\s*:\s*{value}\s*,?",
                f"RevisionClock::new {field}",
                errors,
            )

    methods: dict[str, tuple[tuple[str, str], ...]] = {
        "on_dom_commit": (("mutation_epoch", "MutationEpochExhausted"),),
        "on_semantic_snapshot": (
            ("semantic_snapshot_revision", "SemanticSnapshotRevisionExhausted"),
        ),
        "on_navigation_commit": (
            ("document_generation", "DocumentGenerationExhausted"),
            ("semantic_snapshot_revision", "SemanticSnapshotRevisionExhausted"),
            ("mutation_epoch", "MutationEpochExhausted"),
        ),
        "on_process_recovery": (
            ("session_generation", "SessionGenerationExhausted"),
            ("document_generation", "DocumentGenerationExhausted"),
            ("semantic_snapshot_revision", "SemanticSnapshotRevisionExhausted"),
            ("mutation_epoch", "MutationEpochExhausted"),
        ),
    }

    for method, fields in methods.items():
        try:
            body = extract_function_body(impl_body, method)
        except ValueError as error:
            errors.append(str(error))
            continue
        if re.search(
            rf"\bpub\s+fn\s+{method}\s*\([^)]*\)\s*->\s*"
            rf"Result\s*<\s*\(\s*\)\s*,\s*RevisionError\s*>",
            impl_body,
        ) is None:
            errors.append(f"{method} must return Result<(), RevisionError>")

        assignment_positions: list[int] = []
        preflight_positions: list[int] = []
        for field, variant in fields:
            checked = re.search(
                rf"\blet\s+{field}\s*=\s*self\s*\.\s*{field}\s*"
                rf"\.\s*checked_add\s*\(\s*1\s*\)\s*"
                rf"\.\s*ok_or\s*\(\s*RevisionError\s*::\s*{variant}\s*\)\s*\?",
                body,
                re.S,
            )
            if checked is None:
                errors.append(f"{method} does not preflight {field} with {variant}")
            else:
                preflight_positions.append(checked.start())
            assignment = re.search(
                rf"\bself\s*\.\s*{field}\s*=\s*{field}\s*;", body
            )
            if assignment is None:
                errors.append(f"{method} does not commit {field}")
            else:
                assignment_positions.append(assignment.start())

        if preflight_positions and assignment_positions:
            if min(assignment_positions) < max(preflight_positions):
                errors.append(
                    f"{method} mutates a revision before all fields are preflighted"
                )
    return errors


def audit_session_source(source: str) -> list[str]:
    errors: list[str] = []
    code = strip_rust_noncode(source)
    if "saturating_add" in code:
        errors.append("session machine silently saturates monotonic time")

    try:
        impl_body = extract_impl_body(source, "SessionMachine")
        apply_body = extract_function_body(impl_body, "apply")
    except ValueError as error:
        return [str(error)]

    for variant, method in {
        "SessionEvent::DomCommitted": "on_dom_commit",
        "SessionEvent::SemanticSnapshotPublished": "on_semantic_snapshot",
        "SessionEvent::NavigationCommitted": "on_navigation_commit",
        "SessionEvent::BrowserCrashed": "on_process_recovery",
    }.items():
        try:
            arm = extract_match_arm(apply_body, variant)
        except ValueError as error:
            errors.append(str(error))
            continue
        _require_pattern(
            arm,
            rf"\bself\s*\.\s*revisions\s*\.\s*{method}\s*\(\s*\)\s*"
            rf"\.\s*map_err\s*\(\s*TransitionError\s*::\s*RevisionExhausted\s*\)\s*\?",
            variant,
            errors,
        )

    for variant in (
        "SessionEvent::HumanFocusGained",
        "SessionEvent::HumanInput",
    ):
        try:
            arm = extract_match_arm(apply_body, variant)
        except ValueError as error:
            errors.append(str(error))
            continue
        _require_pattern(
            arm,
            r"\bnow_ms\s*\.\s*checked_add\s*\([^)]*\)\s*"
            r"\.\s*ok_or\s*\(\s*TransitionError\s*::\s*TimeOverflow\s*\)\s*\?",
            variant,
            errors,
        )
    return errors


def check_manifests(root: Path) -> list[str]:
    errors: list[str] = []
    manifests = {
        "contract core": root / "crates/trillionnium-contract-core/Cargo.toml",
        "browser contracts": root / "crates/hepta-browser-contracts/Cargo.toml",
    }
    parsed: dict[str, dict[str, Any]] = {}
    for label, path in manifests.items():
        try:
            parsed[label] = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
            errors.append(f"invalid {label} manifest: {error}")
            parsed[label] = {}

    for label, manifest in parsed.items():
        package = manifest.get("package")
        if not isinstance(package, dict):
            errors.append(f"{label} manifest has no package table")
            continue
        if package.get("autobins") is not False:
            errors.append(f"{label} must disable Cargo binary auto-discovery")
        if package.get("build") is not False:
            errors.append(f"{label} must disable package build scripts")

    if parsed["contract core"].get("dependencies"):
        errors.append("contract core must not gain dependencies")
    if parsed["browser contracts"].get("dependencies") != {
        "trillionnium-contract-core": {"path": "../trillionnium-contract-core"}
    }:
        errors.append("browser contracts dependency graph changed")
    return errors


def check_documentation(root: Path) -> list[str]:
    errors: list[str] = []
    required = {
        "crates/trillionnium-contract-core/README.md": (
            "## Responsibilities",
            "## Overflow and atomicity",
            "## Compatibility and change protocol",
        ),
        "crates/hepta-browser-contracts/README.md": (
            "## Responsibilities",
            "## Versioning and unknown values",
            "## Compatibility and change protocol",
        ),
    }
    for relative, headings in required.items():
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            errors.append(f"missing/unreadable module documentation {relative}: {error}")
            continue
        for heading in headings:
            if heading not in text:
                errors.append(f"{relative} is missing {heading!r}")
    return errors


def validate_root(root: Path = ROOT) -> list[str]:
    _, errors = load_registry(root)
    errors.extend(check_manifests(root))

    try:
        core_source = (
            root / "crates/trillionnium-contract-core/src/lib.rs"
        ).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        errors.append(f"cannot read contract core source: {error}")
    else:
        errors.extend(audit_core_source(core_source))

    try:
        session_source = (
            root / "crates/hepta-session-core/src/machine.rs"
        ).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        errors.append(f"cannot read session machine source: {error}")
    else:
        errors.extend(audit_session_source(session_source))

    errors.extend(check_documentation(root))
    return errors


def main() -> int:
    errors = validate_root()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(
            f"contract foundation validation failed with {len(errors)} error(s)",
            file=sys.stderr,
        )
        return 1
    print("contract foundation validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
