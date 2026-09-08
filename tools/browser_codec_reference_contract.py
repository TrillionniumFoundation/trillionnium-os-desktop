#!/usr/bin/env python3
"""Structural and executable-contract checks for the canonical Browser codec."""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    from tools.browser_codec_reference_security import (
        ROOT,
        load_json_nofollow,
        read_text_nofollow,
    )
except ModuleNotFoundError:
    from browser_codec_reference_security import (  # type: ignore[no-redef]
        ROOT,
        load_json_nofollow,
        read_text_nofollow,
    )

EXPECTED_RESOURCE_LIMITS = {
    "schema": "trillionnium.desktop.browser-codec-resource-limits.v1",
    "canonical_json": {
        "max_container_items": 20_000,
        "max_json_key_utf8_bytes": 128,
        "max_json_string_utf8_bytes": 131_072,
        "max_message_bytes": 262_144,
        "max_nesting_depth": 32,
    },
    "typed_fields": {
        "error_message_utf8_bytes_maximum": 1_024,
        "identifier_utf8_bytes_maximum": 128,
        "select_utf8_bytes_maximum": 65_536,
        "text_utf8_bytes_maximum": 131_072,
        "url_utf8_bytes_maximum": 8_192,
        "wait_text_utf8_bytes_maximum": 65_536,
    },
    "units": "UTF-8 bytes",
    "policy": "reject_before_dispatch_and_apply_the_same_budget_to_decode_and_encode",
}

EXPECTED_RUST_CONSTANTS = {
    "MAX_MESSAGE_BYTES": 262_144,
    "MAX_JSON_DEPTH": 32,
    "MAX_CONTAINER_ITEMS": 20_000,
    "MAX_JSON_STRING_BYTES": 131_072,
    "MAX_JSON_KEY_BYTES": 128,
}


def _expect_exact_object(
    value: object,
    expected: dict[str, object],
    path: str,
    errors: list[str],
) -> dict[str, object]:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object")
        return {}
    actual_keys = set(value)
    expected_keys = set(expected)
    missing = sorted(expected_keys - actual_keys)
    extra = sorted(actual_keys - expected_keys)
    if missing:
        errors.append(f"{path} is missing keys: {missing}")
    if extra:
        errors.append(f"{path} has unexpected keys: {extra}")
    for key, expected_value in expected.items():
        actual = value.get(key)
        if isinstance(expected_value, dict):
            _expect_exact_object(actual, expected_value, f"{path}.{key}", errors)
        elif type(actual) is not type(expected_value) or actual != expected_value:
            errors.append(
                f"{path}.{key} must equal {expected_value!r}, found {actual!r}"
            )
    return value


def strip_rust_noncode(source: str) -> str:
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
        prefix = 1 if source.startswith(('b"', 'c"'), index) else 0
        if source[index + prefix : index + prefix + 1] == '"':
            start = index
            index += prefix + 1
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
        if source[index] == "'":
            character = re.match(r"'(?:\\.|[^\\'\n])+'", source[index:])
            if character:
                start = index
                index += character.end()
                blank(start, index)
                continue
        index += 1
    return "".join(output)


def _rust_integer_constant(source: str, name: str) -> int | None:
    code = strip_rust_noncode(source)
    match = re.search(
        rf"(?m)^\s*pub\s+const\s+{re.escape(name)}\s*:\s*usize\s*=\s*"
        rf"([0-9][0-9_]*)\s*;",
        code,
    )
    if match is None:
        return None
    return int(match.group(1).replace("_", ""))


def _test_functions(source: str) -> set[str]:
    code = strip_rust_noncode(source)
    return set(
        re.findall(
            r"#\s*\[\s*test\s*\]\s*fn\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
            code,
        )
    )


def _actionable_wire_minima(wire: dict[str, object]) -> dict[str, list[int]]:
    output: dict[str, list[int]] = {"page_act": [], "page_wait.element_present": []}
    clauses = wire.get("allOf")
    if not isinstance(clauses, list):
        return output
    for clause in clauses:
        if not isinstance(clause, dict):
            continue
        conditional = clause.get("if")
        then = clause.get("then")
        if not isinstance(conditional, dict) or not isinstance(then, dict):
            continue
        conditional_properties = conditional.get("properties")
        if not isinstance(conditional_properties, dict):
            continue
        operation = conditional_properties.get("operation")
        if not isinstance(operation, dict):
            continue
        op_properties = operation.get("properties")
        if not isinstance(op_properties, dict):
            continue
        op_type = op_properties.get("type")
        if not isinstance(op_type, dict):
            continue
        op_const = op_type.get("const")

        if op_const == "page_act":
            try:
                minimum = then["properties"]["operation"]["properties"]["target"][
                    "properties"
                ]["semantic_snapshot_revision"]["minimum"]
            except (KeyError, TypeError):
                continue
            if type(minimum) is int:
                output["page_act"].append(minimum)

        if op_const == "page_wait":
            condition = op_properties.get("condition")
            if not isinstance(condition, dict):
                continue
            condition_properties = condition.get("properties")
            if not isinstance(condition_properties, dict):
                continue
            condition_type = condition_properties.get("type")
            if not isinstance(condition_type, dict):
                continue
            if condition_type.get("const") != "element_present":
                continue
            try:
                minimum = then["properties"]["operation"]["properties"][
                    "condition"
                ]["properties"]["target"]["properties"][
                    "semantic_snapshot_revision"
                ]["minimum"]
            except (KeyError, TypeError):
                continue
            if type(minimum) is int:
                output["page_wait.element_present"].append(minimum)
    return output


def validate_codec_contract_data(
    resource_limits: object,
    codec_contract: object,
    browser_api: object,
    browser_wire: object,
    rust_lib: str,
    rust_tests: str,
) -> list[str]:
    errors: list[str] = []
    _expect_exact_object(
        resource_limits,
        EXPECTED_RESOURCE_LIMITS,
        "browser-codec-resource-limits",
        errors,
    )

    if not isinstance(codec_contract, dict):
        errors.append("browser-codec contract must be an object")
        codec_contract = {}
    canonical = EXPECTED_RESOURCE_LIMITS["canonical_json"]
    assert isinstance(canonical, dict)
    for contract_key, resource_key in {
        "max_container_items": "max_container_items",
        "max_message_bytes": "max_message_bytes",
        "max_nesting_depth": "max_nesting_depth",
    }.items():
        actual = codec_contract.get(contract_key)
        expected = canonical[resource_key]
        if type(actual) is not int or actual != expected:
            errors.append(
                f"browser-codec.{contract_key} must equal resource registry {expected!r}"
            )

    tightening = codec_contract.get("semantic_tightening")
    if not isinstance(tightening, dict):
        errors.append("browser-codec.semantic_tightening must be an object")
        tightening = {}
    typed = EXPECTED_RESOURCE_LIMITS["typed_fields"]
    assert isinstance(typed, dict)
    for codec_key, resource_key in {
        "select_utf8_bytes_maximum": "select_utf8_bytes_maximum",
        "text_utf8_bytes_maximum": "text_utf8_bytes_maximum",
        "url_utf8_bytes_maximum": "url_utf8_bytes_maximum",
        "wait_text_utf8_bytes_maximum": "wait_text_utf8_bytes_maximum",
    }.items():
        actual = tightening.get(codec_key)
        expected = typed[resource_key]
        if type(actual) is not int or actual != expected:
            errors.append(
                f"browser-codec.semantic_tightening.{codec_key} must equal {expected!r}"
            )
    if tightening.get("element_ref.semantic_snapshot_revision_minimum") != 1:
        errors.append("actionable semantic references must require a published snapshot")

    for name, expected in EXPECTED_RUST_CONSTANTS.items():
        actual = _rust_integer_constant(rust_lib, name)
        if actual != expected:
            errors.append(f"Rust {name} must equal {expected}, found {actual!r}")

    tests = _test_functions(rust_tests)
    for name in {
        "constructed_json_values_enforce_depth_and_container_item_bounds",
        "constructed_json_values_enforce_string_and_key_bounds",
        "semantic_reference_requires_a_published_snapshot",
        "loopback_fixture_url_rejects_noncanonical_scheme_and_empty_port",
        "external_url_rejects_ambiguous_authority_forms",
    }:
        if name not in tests:
            errors.append(f"missing executable codec boundary test {name}")

    if not isinstance(browser_api, dict):
        errors.append("browser-api schema must be an object")
        browser_api = {}
    definitions = browser_api.get("$defs")
    if not isinstance(definitions, dict):
        errors.append("browser-api schema has no $defs object")
        definitions = {}
    element = definitions.get("element_ref")
    if not isinstance(element, dict):
        errors.append("browser-api has no element_ref definition")
        element = {}
    required = element.get("required")
    if not isinstance(required, list) or set(required) != {
        "session_generation",
        "document_generation",
        "semantic_snapshot_revision",
        "frame_id",
        "structural_fingerprint",
    }:
        errors.append("element_ref required fields are not the exact reviewed set")
    properties = element.get("properties")
    if not isinstance(properties, dict):
        errors.append("element_ref properties are missing")
        properties = {}
    revision = properties.get("semantic_snapshot_revision")
    if not isinstance(revision, dict) or revision.get("type") != "integer":
        errors.append("element_ref semantic snapshot revision must be an integer")

    page_act = definitions.get("page_act")
    if not isinstance(page_act, dict):
        errors.append("browser-api has no page_act definition")
    else:
        try:
            target_ref = page_act["properties"]["target"]["$ref"]
        except (KeyError, TypeError):
            target_ref = None
        if target_ref != "#/$defs/element_ref":
            errors.append("page_act target must structurally reference element_ref")

    wait = definitions.get("wait_condition")
    if not isinstance(wait, dict):
        errors.append("browser-api has no wait_condition definition")
    else:
        options = wait.get("oneOf")
        element_options = []
        if isinstance(options, list):
            for option in options:
                if not isinstance(option, dict):
                    continue
                try:
                    if option["properties"]["type"]["const"] == "element_present":
                        element_options.append(option)
                except (KeyError, TypeError):
                    continue
        if len(element_options) != 1:
            errors.append("wait_condition must contain exactly one element_present branch")
        else:
            try:
                target_ref = element_options[0]["properties"]["target"]["$ref"]
            except (KeyError, TypeError):
                target_ref = None
            if target_ref != "#/$defs/element_ref":
                errors.append("element_present target must structurally reference element_ref")

    if not isinstance(browser_wire, dict):
        errors.append("browser-wire schema must be an object")
        browser_wire = {}
    try:
        operation_ref = browser_wire["properties"]["operation"]["$ref"]
    except (KeyError, TypeError):
        operation_ref = None
    if operation_ref != "browser-api.v1.schema.json#/properties/operation":
        errors.append("browser-wire operation must reference the reviewed Browser API operation")

    minima = _actionable_wire_minima(browser_wire)
    if minima["page_act"] != [1]:
        errors.append(
            "browser-wire page_act must contain exactly one snapshot minimum of 1"
        )
    if minima["page_wait.element_present"] != [1]:
        errors.append(
            "browser-wire element_present must contain exactly one snapshot minimum of 1"
        )
    return errors


def validate_root(root: Path = ROOT) -> list[str]:
    resource_limits = load_json_nofollow(
        root / "contracts/browser-codec-resource-limits.v1.json",
        label="codec resource-limit registry",
    )
    codec_contract = load_json_nofollow(
        root / "contracts/browser-codec.v1.json",
        label="codec contract",
    )
    browser_api = load_json_nofollow(
        root / "contracts/browser-api.v1.schema.json",
        label="Browser API schema",
    )
    browser_wire = load_json_nofollow(
        root / "contracts/browser-wire.v1.schema.json",
        label="Browser wire schema",
    )
    rust_lib = read_text_nofollow(
        root / "crates/hepta-browser-codec/src/lib.rs",
        label="codec Rust library",
    )
    rust_tests = read_text_nofollow(
        root / "crates/hepta-browser-codec/src/tests.rs",
        label="codec Rust tests",
    )
    return validate_codec_contract_data(
        resource_limits,
        codec_contract,
        browser_api,
        browser_wire,
        rust_lib,
        rust_tests,
    )


def main() -> int:
    errors = validate_root()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(
            f"browser codec structural validation failed with {len(errors)} error(s)",
            file=sys.stderr,
        )
        return 1
    print("browser codec structural validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
