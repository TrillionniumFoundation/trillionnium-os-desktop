#!/usr/bin/env python3
"""Fail-closed source/contract audit for the bounded S04 mechanism slice."""

from __future__ import annotations

import hashlib
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

try:
    from tools.browser_codec_reference_contract import strip_rust_noncode
    from tools.browser_codec_reference_security import (
        ROOT,
        load_json_nofollow,
        read_bytes_nofollow,
        read_text_nofollow,
    )
except ModuleNotFoundError:
    from browser_codec_reference_contract import strip_rust_noncode  # type: ignore[no-redef]
    from browser_codec_reference_security import (  # type: ignore[no-redef]
        ROOT,
        load_json_nofollow,
        read_bytes_nofollow,
        read_text_nofollow,
    )


def _read(relative: str) -> str:
    return read_text_nofollow(ROOT / relative, label=relative)


def _json(relative: str) -> dict[str, Any]:
    value = load_json_nofollow(ROOT / relative, label=relative)
    if not isinstance(value, dict):
        raise ValueError(f"{relative} root must be an object")
    return value


def _toml(relative: str) -> dict[str, Any]:
    value = tomllib.loads(_read(relative))
    if not isinstance(value, dict):
        raise ValueError(f"{relative} root must be a table")
    return value


def _require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


PUBLIC_API_FINDING = "S04-PUBLIC-API-CONTRACT"
PUBLIC_SURFACE_FINDING = "S04-PUBLIC-API-EXPOSES"
EXPECTED_TRANSPORT_PUBLIC_API: dict[str, object] = {
    "connected_stream_only": True,
    "listener_type_exposed": False,
    "raw_frame_types_exposed": False,
    "session_nonce_value_exposed": False,
    "nonce_source_trait_exposed": False,
    "deterministic_nonce_source_exposed": False,
    "server_acceptance": "operating_system_entropy_only",
    "peer_identity_debug": "redacted",
    "peer_policy_debug": "redacted",
    "connection_debug_and_display": "redacted",
    "unauthorized_peer_error_formatting": "redacted",
    "handler_error_text_formatting": "redacted_by_agent_port",
}


def _require_exact_typed_object(
    value: object,
    expected: dict[str, object],
    label: str,
    errors: list[str],
) -> None:
    if not isinstance(value, dict):
        errors.append(f"{PUBLIC_API_FINDING}:{label}:not-an-object")
        return
    actual_keys = set(value)
    expected_keys = set(expected)
    for key in sorted(expected_keys - actual_keys):
        errors.append(f"{PUBLIC_API_FINDING}:{label}:missing:{key}")
    for key in sorted(actual_keys - expected_keys):
        errors.append(f"{PUBLIC_API_FINDING}:{label}:unexpected:{key}")
    for key in sorted(actual_keys & expected_keys):
        actual = value[key]
        wanted = expected[key]
        if type(actual) is not type(wanted):
            errors.append(
                f"{PUBLIC_API_FINDING}:{label}:type:{key}:"
                f"{type(actual).__name__}!={type(wanted).__name__}"
            )
        elif actual != wanted:
            errors.append(f"{PUBLIC_API_FINDING}:{label}:value:{key}")


def _impl_body(source: str, type_name: str) -> str:
    code = strip_rust_noncode(source)
    match = re.search(rf"\bimpl\s+{re.escape(type_name)}\s*\{{", code)
    if match is None:
        raise ValueError(f"missing impl {type_name}")
    open_brace = code.find("{", match.start())
    depth = 0
    for index in range(open_brace, len(code)):
        if code[index] == "{":
            depth += 1
        elif code[index] == "}":
            depth -= 1
            if depth == 0:
                return code[open_brace + 1 : index]
    raise ValueError(f"unterminated impl {type_name}")


def _test_functions(source: str) -> set[str]:
    code = strip_rust_noncode(source)
    return set(
        re.findall(
            r"#\s*\[\s*test\s*\]\s*fn\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
            code,
        )
    )


def _public_definition_or_export(code: str, identifier: str) -> bool:
    return (
        re.search(
            rf"\bpub\s+(?:struct|enum|trait|type|const)\s+{re.escape(identifier)}\b",
            code,
        )
        is not None
        or re.search(
            rf"\bpub\s+use\b[^;]*\b{re.escape(identifier)}\b[^;]*;",
            code,
            re.S,
        )
        is not None
    )


def validate_transport_sources(
    root_lib: str,
    facade: str,
    agent_port: str,
    transport_manifest: dict[str, Any],
    contract: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    root_code = strip_rust_noncode(root_lib)
    facade_code = strip_rust_noncode(facade)
    agent_code = strip_rust_noncode(agent_port)

    package = transport_manifest.get("package")
    _require(isinstance(package, dict), "transport manifest has no package table", errors)
    if isinstance(package, dict):
        _require(package.get("autobins") is False, "transport autobins must be false", errors)
        _require(package.get("build") is False, "transport build script must be disabled", errors)
    _require(not transport_manifest.get("features"), "transport default graph must expose no test feature", errors)

    _require(re.search(r"(?m)^\s*mod\s+facade\s*;", root_code) is not None, "transport facade must remain private", errors)
    _require("pub mod facade" not in root_code, "transport facade became public", errors)
    _require(re.search(r"(?m)^\s*mod\s+wire\s*;", facade_code) is not None, "raw wire module must remain private", errors)
    _require("pub mod wire" not in facade_code, "raw wire module became public", errors)

    public_surface = root_code + "\n" + facade_code
    for forbidden in (
        "FixedNonceSource",
        "NonceSource",
        "OsNonceSource",
        "SessionNonce",
        "FrameKind",
        "Frame",
    ):
        _require(
            not _public_definition_or_export(public_surface, forbidden),
            f"{PUBLIC_SURFACE_FINDING}:{forbidden}",
            errors,
        )
    _require(
        re.search(r"\bpub\s+fn\s+accept_with_nonce_source\s*\(", public_surface)
        is None,
        f"{PUBLIC_SURFACE_FINDING}:accept_with_nonce_source",
        errors,
    )
    _require(
        re.search(r"\bpub\s+(?:const\s+)?fn\s+session_nonce\s*\(", public_surface)
        is None,
        f"{PUBLIC_SURFACE_FINDING}:session_nonce",
        errors,
    )

    for type_name in (
        "PeerIdentity",
        "PeerPolicy",
        "ServerConnection",
        "ClientConnection",
        "TransportError",
    ):
        _require(
            re.search(
                rf"\bimpl\s+fmt\s*::\s*Debug\s+for\s+{type_name}\b",
                facade_code,
            )
            is not None,
            f"{type_name} lacks custom redacted Debug",
            errors,
        )
    for type_name in ("ServerConnection", "ClientConnection", "TransportError"):
        _require(
            re.search(
                rf"\bimpl\s+fmt\s*::\s*Display\s+for\s+{type_name}\b",
                facade_code,
            )
            is not None,
            f"{type_name} lacks custom Display",
            errors,
        )

    try:
        server_impl = _impl_body(facade, "ServerConnection")
    except ValueError as error:
        errors.append(str(error))
    else:
        _require(
            len(re.findall(r"\bpub\s+fn\s+accept\s*\(", server_impl)) == 1,
            "ServerConnection must expose exactly one production accept method",
            errors,
        )
        _require(
            "wire::ServerConnection::accept(" in server_impl,
            "production accept must use the wire OS-entropy path",
            errors,
        )

    facade_tests = _test_functions(facade)
    for required_test in (
        "public_identity_policy_connection_and_error_formatting_are_redacted",
        "unauthorized_peer_error_does_not_reveal_runtime_identity",
        "response_sequence_mismatch_permanently_poisoned_client",
    ):
        _require(
            required_test in facade_tests,
            f"missing transport test {required_test}",
            errors,
        )

    for forbidden in (
        "NonceSource",
        "FixedNonceSource",
        "OsNonceSource",
        "serve_one_with_nonce_source",
        "accept_with_nonce_source",
    ):
        _require(
            re.search(rf"\b{re.escape(forbidden)}\b", agent_code) is None,
            f"AgentPort exposes or consumes {forbidden}",
            errors,
        )
    _require(
        len(
            re.findall(
                r"\bhandler\s*\.\s*handle\s*\(\s*&context\s*,\s*&request\s*\)",
                agent_code,
            )
        )
        == 1,
        "AgentPort handler invocation must occur exactly once",
        errors,
    )
    _require(
        re.search(r"Self\s*::\s*Handler\s*\(\s*_\s*\)\s*=>", agent_code)
        is not None,
        "AgentPort handler error formatting must discard handler text",
        errors,
    )
    _require(
        re.search(
            r"\bimpl\s+fmt\s*::\s*Debug\s+for\s+AgentPortError\b",
            agent_code,
        )
        is not None,
        "AgentPort error Debug must be custom and redacted",
        errors,
    )
    _require(
        "handler_error_text_is_not_formatted_into_logs" in _test_functions(agent_port),
        "missing AgentPort handler-text redaction test",
        errors,
    )

    public_api = contract.get("public_api")
    _require_exact_typed_object(
        public_api,
        EXPECTED_TRANSPORT_PUBLIC_API,
        "agent-transport.public_api",
        errors,
    )
    authentication = contract.get("authentication")
    _require(
        isinstance(authentication, dict),
        "transport authentication contract is missing",
        errors,
    )
    if isinstance(authentication, dict):
        _require(
            authentication.get("product_nonce_source")
            == "operating_system_entropy_only",
            "product nonce source is not OS-only",
            errors,
        )
        _require(
            authentication.get("deterministic_nonce_injection")
            == "private_wire_tests_only",
            "deterministic nonce injection is not private-test-only",
            errors,
        )
    _require(
        contract.get("evidence_freshness") == "STALE_EVIDENCE",
        "changed transport inherited fresh evidence",
        errors,
    )
    _require(
        contract.get("merge_ready") is False,
        "transport preclaims merge readiness",
        errors,
    )
    return errors


def validate_attestation() -> list[str]:
    errors: list[str] = []
    lib = strip_rust_noncode(_read("crates/hepta-peer-attestation/src/lib.rs"))
    lease = strip_rust_noncode(
        _read("crates/hepta-peer-attestation/src/request_lease.rs")
    )
    manifest = _toml("crates/hepta-peer-attestation/Cargo.toml")
    package = manifest.get("package", {})
    _require(
        package.get("autobins") is False,
        "attestation autobins must be false",
        errors,
    )
    _require(
        package.get("build") is False,
        "attestation build script must be disabled",
        errors,
    )
    _require(
        manifest.get("dependencies", {}).get("sha2") == "=0.10.9",
        "attestation sha2 pin changed",
        errors,
    )
    for token in (
        "executable_sha256",
        "refresh_snapshot",
        "AttestorSourceChanged",
        "O_NOFOLLOW",
        "parse_nspid",
        "pidfd_open",
    ):
        _require(token in lib, f"attestation missing {token}", errors)
    for token in (
        "PeerRequestCustody",
        "PeerRequestVerifier",
        "RequestCustodyRevoked",
        "verify_current",
        "impl Drop for PeerRequestCustody",
    ):
        _require(token in lease, f"request custody missing {token}", errors)
    _require(
        "#[derive(Debug)]\npub struct PeerRequestCustody"
        in _read("crates/hepta-peer-attestation/src/request_lease.rs"),
        "custody owner became cloneable",
        errors,
    )
    contract = _json("contracts/request-peer-custody.v1.json")
    _require(
        contract.get("browser_actor_integrated") is False,
        "S04 custody claims BrowserActor",
        errors,
    )
    _require(
        contract.get("production_listener_enabled") is False,
        "S04 custody claims listener",
        errors,
    )
    _require(
        contract.get("external_effect_authority") is False,
        "S04 custody claims effect authority",
        errors,
    )
    _require(
        contract.get("required_sources")
        == [
            "crates/hepta-peer-attestation/src/lib.rs",
            "crates/hepta-peer-attestation/src/request_lease.rs",
        ],
        "S04 custody contract crosses a later work package",
        errors,
    )
    return errors


def _parse_assignments(relative: str) -> list[tuple[str, str, str]]:
    section = ""
    result: list[tuple[str, str, str]] = []
    for raw in _read(relative).splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if not section or "=" not in line:
            raise ValueError(f"malformed unit line in {relative}: {raw!r}")
        key, value = line.split("=", 1)
        result.append((section, key, value))
    return result


def _list_value(
    assignments: list[tuple[str, str, str]], section: str, key: str
) -> list[str]:
    values: list[str] = []
    for candidate_section, candidate_key, value in assignments:
        if candidate_section == section and candidate_key == key:
            if value == "":
                values.clear()
            else:
                values.extend(value.split())
    return values


def _last_value(
    assignments: list[tuple[str, str, str]], section: str, key: str
) -> str | None:
    value = None
    for candidate_section, candidate_key, candidate_value in assignments:
        if candidate_section == section and candidate_key == key:
            value = candidate_value
    return value


def validate_product_graph_and_path_custody() -> list[str]:
    errors: list[str] = []
    app_manifest = _toml("apps/hepta-agent-portd/Cargo.toml")
    product = strip_rust_noncode(_read("apps/hepta-agent-portd/src/main.rs"))
    fixture = strip_rust_noncode(
        _read("apps/hepta-agent-portd/src/bin/hepta-agent-port-fixture.rs")
    )
    _require(
        app_manifest.get("features")
        == {
            "default": [],
            "fixture": [
                "dep:hepta-agent-port",
                "dep:hepta-browser-codec",
                "hepta-peer-attestation/qualification-static-attestation",
            ],
        },
        "product feature graph widened",
        errors,
    )
    dependencies = app_manifest.get("dependencies", {})
    for forbidden in ("hepta-browser-actor", "hepta-session-core", "servo"):
        _require(
            forbidden not in dependencies,
            f"product graph contains {forbidden}",
            errors,
        )
    bins = app_manifest.get("bin", [])
    _require(
        [entry.get("name") for entry in bins]
        == ["hepta-agent-portd", "hepta-agent-port-fixture"],
        "unexpected AgentPort binary inventory",
        errors,
    )
    _require(
        "D0FixtureHandler" not in product,
        "product binary links fixture handler",
        errors,
    )
    _require(
        "hepta_agent_port::" not in product,
        "product binary links fixture crate path",
        errors,
    )
    _require(
        "ProductHandlerUnavailable" in product,
        "product binary no longer fails closed",
        errors,
    )
    _require(
        "D0FixtureHandler" in fixture,
        "fixture binary lost explicit handler",
        errors,
    )

    product_raw = _read("apps/hepta-agent-portd/src/main.rs")
    report_start = product_raw.index("fn self_check_report")
    report_end = product_raw.index("#[derive(Debug)]", report_start)
    report_source = product_raw[report_start:report_end]
    _require(
        "peer_identity_redacted" in report_source,
        "product self-check lacks redaction marker",
        errors,
    )
    for secret in ("peer_pid", "peer_uid", "peer_gid"):
        _require(
            secret not in report_source,
            f"product self-check exposes {secret}",
            errors,
        )

    socket = _parse_assignments(
        "packaging/debian/systemd/hepta-browserd-agent.socket"
    )
    socket += _parse_assignments(
        "packaging/debian/systemd/hepta-browserd-agent.socket.d/10-root-path-custody.conf"
    )
    service = _parse_assignments(
        "packaging/debian/systemd/hepta-browserd-agent@.service"
    )
    service += _parse_assignments(
        "packaging/debian/systemd/hepta-browserd-agent@.service.d/10-root-path-custody.conf"
    )
    _require(
        _last_value(socket, "Unit", "ConditionPathExists")
        == "/etc/hepta/enable-agent-port",
        "activation marker changed",
        errors,
    )
    _require(
        _last_value(socket, "Socket", "ListenStream")
        == "/run/hepta/browserd/agent.sock",
        "socket path changed",
        errors,
    )
    _require(
        _last_value(socket, "Socket", "Accept") == "yes",
        "socket must use Accept=yes",
        errors,
    )
    _require(
        _last_value(socket, "Socket", "Backlog") == "8",
        "backlog is not bounded",
        errors,
    )
    _require(
        _last_value(socket, "Socket", "MaxConnections") == "8",
        "connection count is not bounded",
        errors,
    )
    _require(
        _list_value(service, "Service", "SupplementaryGroups") == [],
        "effective supplementary groups not cleared",
        errors,
    )
    _require(
        _list_value(service, "Service", "ReadWritePaths") == [],
        "effective writable paths not cleared",
        errors,
    )
    _require(
        _list_value(service, "Service", "ReadOnlyPaths")
        == ["/run/hepta/browserd"],
        "effective read-only path changed",
        errors,
    )

    sysusers = _read("packaging/debian/sysusers.d/trillionnium-desktop.conf")
    tmpfiles = _read("packaging/debian/tmpfiles.d/trillionnium-desktop.conf")
    install = _read("packaging/debian/hepta-agent-portd.install")
    preset = _read("packaging/debian/systemd-preset/90-trillionnium-desktop.preset")
    _require(
        "m      hepta-agent      hepta-agent-socket" in sysusers,
        "Agent lacks parent traversal group",
        errors,
    )
    _require(
        "m      hepta-browserd   hepta-agent-socket" not in sysusers,
        "browser mechanism gained parent custody group",
        errors,
    )
    _require(
        "/run/hepta/browserd          0750 root            hepta-agent-socket"
        in tmpfiles,
        "root parent custody mapping changed",
        errors,
    )
    _require(
        "hepta-agent-port-fixture" not in install,
        "production package installs fixture",
        errors,
    )
    _require(
        "enable-agent-port" not in install,
        "production package installs activation marker",
        errors,
    )
    _require(
        "disable hepta-browserd-agent.socket" in preset,
        "product socket is not disabled",
        errors,
    )

    custody = _json("contracts/agent-port-custody.v1.json")
    bridge = _json("contracts/agent-port-bridge.v1.json")
    for label, contract in (("custody", custody), ("bridge", bridge)):
        _require(
            contract.get("evidence_freshness") == "STALE_EVIDENCE",
            f"{label} inherited fresh evidence",
            errors,
        )
        _require(
            contract.get("merge_ready") is False,
            f"{label} preclaims merge readiness",
            errors,
        )
    _require(
        custody.get("activation", {}).get("enabled_by_default") is False,
        "custody enables product by default",
        errors,
    )
    _require(
        custody.get("path_custody", {}).get(
            "browser_service_socket_path_mutation_authority"
        )
        is False,
        "browser can mutate socket path",
        errors,
    )
    return errors


def validate_reference_binding() -> list[str]:
    errors: list[str] = []
    contract_bytes = read_bytes_nofollow(
        ROOT / "contracts/agent-transport.v1.json",
        label="agent transport contract",
    )
    result = _json(
        "docs/evidence/generated/d0c02-agent-transport-reference-result.json"
    )
    expected = hashlib.sha256(contract_bytes).hexdigest()
    actual = result.get("contract_sha256")
    _require(
        actual == expected,
        f"transport reference result contract_sha256 must be {expected}, found {actual!r}",
        errors,
    )
    _require(
        result.get("status") == "PASS",
        "transport reference result is not PASS",
        errors,
    )
    _require(
        result.get("product_listener_created") is False,
        "transport reference claims a listener",
        errors,
    )
    _require(
        result.get("browser_payload_interpreted") is False,
        "transport reference interprets Browser payloads",
        errors,
    )
    return errors


def validate_docs_and_lock() -> list[str]:
    errors: list[str] = []
    lock = _toml("Cargo.lock")
    packages = [
        entry
        for entry in lock.get("package", [])
        if entry.get("name") == "hepta-peer-attestation"
    ]
    _require(
        len(packages) == 1,
        "peer attestation lock identity is missing or ambiguous",
        errors,
    )
    if len(packages) == 1:
        _require(
            set(packages[0].get("dependencies", []))
            == {"hepta-agent-transport", "libc", "sha2"},
            "peer attestation lock dependencies drifted",
            errors,
        )
    for relative in (
        "crates/hepta-agent-transport/README.md",
        "crates/hepta-peer-attestation/README.md",
        "crates/hepta-agent-port/README.md",
        "apps/hepta-agent-portd/README.md",
        "docs/architecture/REQUEST_PEER_CUSTODY.md",
        "docs/architecture/AGENT_PORT_PATHNAME_CUSTODY.md",
        "docs/architecture/AUTHENTICATED_AGENT_TRANSPORT.md",
    ):
        text = _read(relative)
        _require(
            "Claim ceiling" in text or "claim ceiling" in text,
            f"{relative} lacks claim ceiling",
            errors,
        )
    return errors


def validate_root() -> list[str]:
    errors: list[str] = []
    errors.extend(
        validate_transport_sources(
            _read("crates/hepta-agent-transport/src/lib.rs"),
            _read("crates/hepta-agent-transport/src/facade.rs"),
            _read("crates/hepta-agent-port/src/lib.rs"),
            _toml("crates/hepta-agent-transport/Cargo.toml"),
            _json("contracts/agent-transport.v1.json"),
        )
    )
    errors.extend(validate_attestation())
    errors.extend(validate_product_graph_and_path_custody())
    errors.extend(validate_reference_binding())
    errors.extend(validate_docs_and_lock())
    return errors


def main() -> int:
    try:
        errors = validate_root()
    except (
        OSError,
        UnicodeError,
        ValueError,
        KeyError,
        tomllib.TOMLDecodeError,
    ) as error:
        errors = [str(error)]
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"S04 validation failed with {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("S04 transport, peer custody, AgentPort, and product-path validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
