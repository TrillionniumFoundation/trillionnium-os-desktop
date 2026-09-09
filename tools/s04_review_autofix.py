#!/usr/bin/env python3
"""One-shot, exact-shape S04 review remediation.

This file is temporary.  The workflow that invokes it removes it before
publishing the verified source repair.
"""
from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"{path}: expected one replacement, found {count}: {old[:100]!r}"
        )
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_facade() -> None:
    path = Path("crates/hepta-agent-transport/src/facade.rs")
    text = path.read_text(encoding="utf-8")
    for line in (
        "pub const DIGEST_BYTES: usize = wire::DIGEST_BYTES;\n",
        "pub const NONCE_BYTES: usize = wire::NONCE_BYTES;\n",
        "pub const PROTOCOL_MAGIC: [u8; 8] = *b\"HEPTA001\";\n",
        "pub const PROTOCOL_VERSION: u16 = 1;\n",
        "pub const HEADER_BYTES: usize = 88;\n",
        "pub const DEFAULT_OPERATION_TIMEOUT: Duration = Duration::from_secs(20);\n",
    ):
        if text.count(line) != 1:
            raise SystemExit(f"facade.rs: missing exact unused constant {line!r}")
        text = text.replace(line, "", 1)

    into_wire = """    const fn into_wire(self) -> wire::PeerIdentity {
        wire::PeerIdentity {
            pid: self.pid,
            uid: self.uid,
            gid: self.gid,
        }
    }
"""
    if text.count(into_wire) != 1:
        raise SystemExit("facade.rs: PeerIdentity::into_wire shape changed")
    path.write_text(text.replace(into_wire, "", 1), encoding="utf-8")


def patch_wire() -> None:
    path = Path("crates/hepta-agent-transport/src/facade/wire.rs")
    text = path.read_text(encoding="utf-8")

    timeout = "pub const DEFAULT_OPERATION_TIMEOUT: Duration = Duration::from_secs(20);\n"
    if text.count(timeout) != 1:
        raise SystemExit("wire.rs: obsolete timeout constant shape changed")
    text = text.replace(timeout, "", 1)

    for signature in (
        "    pub const fn new(expected_uid: u32) -> Self {",
        "    pub const fn exact(identity: PeerIdentity) -> Self {",
    ):
        if text.count(signature) != 1:
            raise SystemExit(f"wire.rs: missing test-only signature {signature}")
        text = text.replace(signature, "    #[cfg(test)]\n" + signature, 1)

    fixed = """#[derive(Debug, Clone, Copy)]
pub struct FixedNonceSource(pub [u8; NONCE_BYTES]);

impl NonceSource for FixedNonceSource {
"""
    fixed_replacement = """#[cfg(test)]
#[derive(Debug, Clone, Copy)]
pub struct FixedNonceSource(pub [u8; NONCE_BYTES]);

#[cfg(test)]
impl NonceSource for FixedNonceSource {
"""
    if text.count(fixed) != 1:
        raise SystemExit("wire.rs: FixedNonceSource shape changed")
    text = text.replace(fixed, fixed_replacement, 1)

    server_accessors = """    pub const fn peer_identity(&self) -> PeerIdentity {
        self.peer
    }

    pub const fn session_nonce(&self) -> SessionNonce {
        self.binding
    }

    pub fn receive_request(
"""
    server_replacement = """    pub const fn peer_identity(&self) -> PeerIdentity {
        self.peer
    }

    pub fn receive_request(
"""
    if text.count(server_accessors) != 1:
        raise SystemExit("wire.rs: server nonce accessor shape changed")
    text = text.replace(server_accessors, server_replacement, 1)

    client_accessors = """    pub const fn peer_identity(&self) -> PeerIdentity {
        self.peer
    }

    pub const fn session_nonce(&self) -> SessionNonce {
        self.binding
    }

    pub fn send_request(
"""
    client_replacement = """    pub const fn peer_identity(&self) -> PeerIdentity {
        self.peer
    }

    #[cfg(test)]
    pub const fn session_nonce(&self) -> SessionNonce {
        self.binding
    }

    pub fn send_request(
"""
    if text.count(client_accessors) != 1:
        raise SystemExit("wire.rs: client nonce accessor shape changed")
    text = text.replace(client_accessors, client_replacement, 1)

    marker = "pub fn self_check() -> Result<(), TransportError> {"
    if text.count(marker) != 1:
        raise SystemExit("wire.rs: self_check shape changed")
    text = text.replace(marker, "#[cfg(test)]\n" + marker, 1)
    path.write_text(text, encoding="utf-8")


def patch_validator() -> None:
    path = Path("tools/validate_s04_transport_custody.py")
    text = path.read_text(encoding="utf-8")

    insertion = """def _require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


"""
    helper = """def _require(condition: bool, message: str, errors: list[str]) -> None:
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


"""
    if text.count(insertion) != 1:
        raise SystemExit("validator: _require insertion point changed")
    text = text.replace(insertion, helper, 1)

    old = """    public_api = contract.get("public_api")
    expected_public_api = {
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
    _require(
        public_api == expected_public_api,
        "agent-transport public_api contract drifted",
        errors,
    )
"""
    new = """    public_api = contract.get("public_api")
    _require_exact_typed_object(
        public_api,
        EXPECTED_TRANSPORT_PUBLIC_API,
        "agent-transport.public_api",
        errors,
    )
"""
    if text.count(old) != 1:
        raise SystemExit("validator: public_api comparison shape changed")
    text = text.replace(old, new, 1)

    replacements = {
        'f"public transport surface exposes {forbidden}"': (
            'f"{PUBLIC_SURFACE_FINDING}:{forbidden}"'
        ),
        '"public transport surface exposes accept_with_nonce_source"': (
            'f"{PUBLIC_SURFACE_FINDING}:accept_with_nonce_source"'
        ),
        '"public transport surface exposes session nonce material"': (
            'f"{PUBLIC_SURFACE_FINDING}:session_nonce"'
        ),
    }
    for old_message, new_message in replacements.items():
        if text.count(old_message) != 1:
            raise SystemExit(f"validator: diagnostic shape changed: {old_message}")
        text = text.replace(old_message, new_message, 1)
    path.write_text(text, encoding="utf-8")


def patch_tests() -> None:
    path = Path("tests/test_s04_transport_custody.py")
    text = path.read_text(encoding="utf-8")

    old = """        for token in (
            "FixedNonceSource",
            "NonceSource",
            "SessionNonce",
            "FrameKind",
            "pub struct Frame",
        ):
            with self.subTest(token=token):
                mutated = root + f"\\npub use facade::{token};\\n"
                errors = VALIDATOR.validate_transport_sources(
                    mutated, facade, agent, manifest, contract
                )
                self.assertTrue(any(token in error for error in errors), errors)
"""
    new = """        for token in (
            "FixedNonceSource",
            "NonceSource",
            "SessionNonce",
            "FrameKind",
            "Frame",
        ):
            with self.subTest(token=token):
                mutated = root + f"\\npub use facade::{token};\\n"
                errors = VALIDATOR.validate_transport_sources(
                    mutated, facade, agent, manifest, contract
                )
                self.assertIn(
                    f"{VALIDATOR.PUBLIC_SURFACE_FINDING}:{token}",
                    errors,
                )
"""
    if text.count(old) != 1:
        raise SystemExit("tests: public export mutation test shape changed")
    text = text.replace(old, new, 1)

    old = """        for candidate in mutations:
            errors = VALIDATOR.validate_transport_sources(
                root, facade, agent, manifest, candidate
            )
            self.assertTrue(any("public_api" in error for error in errors), errors)
"""
    new = """        for candidate in mutations:
            errors = VALIDATOR.validate_transport_sources(
                root, facade, agent, manifest, candidate
            )
            self.assertTrue(
                any(error.startswith(VALIDATOR.PUBLIC_API_FINDING + ":") for error in errors),
                errors,
            )

    def test_every_public_api_field_is_type_and_value_bound(self) -> None:
        root, facade, agent, manifest, contract = sources()
        expected = VALIDATOR.EXPECTED_TRANSPORT_PUBLIC_API
        self.assertEqual(contract["public_api"], expected)
        for key, value in expected.items():
            with self.subTest(key=key, mutation="missing"):
                candidate = copy.deepcopy(contract)
                del candidate["public_api"][key]
                errors = VALIDATOR.validate_transport_sources(
                    root, facade, agent, manifest, candidate
                )
                self.assertIn(
                    f"{VALIDATOR.PUBLIC_API_FINDING}:agent-transport.public_api:missing:{key}",
                    errors,
                )
            with self.subTest(key=key, mutation="type"):
                candidate = copy.deepcopy(contract)
                candidate["public_api"][key] = 1 if isinstance(value, bool) else False
                errors = VALIDATOR.validate_transport_sources(
                    root, facade, agent, manifest, candidate
                )
                self.assertTrue(
                    any(
                        error.startswith(
                            f"{VALIDATOR.PUBLIC_API_FINDING}:agent-transport.public_api:type:{key}:"
                        )
                        for error in errors
                    ),
                    errors,
                )
            with self.subTest(key=key, mutation="value"):
                candidate = copy.deepcopy(contract)
                if isinstance(value, bool):
                    candidate["public_api"][key] = not value
                else:
                    candidate["public_api"][key] = value + "-mutated"
                errors = VALIDATOR.validate_transport_sources(
                    root, facade, agent, manifest, candidate
                )
                self.assertIn(
                    f"{VALIDATOR.PUBLIC_API_FINDING}:agent-transport.public_api:value:{key}",
                    errors,
                )
"""
    if text.count(old) != 1:
        raise SystemExit("tests: public_api strictness test shape changed")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    patch_facade()
    patch_wire()
    patch_validator()
    patch_tests()


if __name__ == "__main__":
    main()
