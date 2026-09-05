#!/usr/bin/env python3
"""Pure D6 capability and controlled-egress reference engine.

No network, filesystem portal, notification service, audio service, credential,
or external effect is accessed. DNS answers, proxy observations, and connected
peer identities are explicit inputs whose consistency is validated.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import ipaddress
import json
import re
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import SplitResult, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from trusted_app_bundle import (  # noqa: E402
    ed25519_public_from_seed,
    ed25519_sign_fixture,
    ed25519_verify,
)

CONTRACT_PATH = ROOT / "contracts" / "capability-egress.v1.json"
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
TOKEN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
MAX_URL_BYTES = 8192
MAX_TEXT_BYTES = 65536
MAX_JSON_BYTES = 4 * 1024 * 1024
PERMIT_SCHEMA = "trillionnium.desktop.capability-permit.v2"
SUBJECT_FIELDS = {
    "taskflow_principal",
    "mechanism_uid",
    "mechanism_unit",
    "session_id",
    "page_owner_id",
}
PERMIT_FIELDS = {
    "schema",
    "permit_id",
    "issuer_id",
    "issuer_key_id",
    "subject",
    "audience",
    "resource",
    "actions",
    "issued_at_epoch",
    "not_before_epoch",
    "expires_at_epoch",
    "nonce",
    "maximum_uses",
    "constraints",
    "signature",
}
METADATA_ADDRESSES = {
    "169.254.169.254",
    "169.254.170.2",
    "100.100.100.200",
    "192.0.0.192",
    "fd00:ec2::254",
}


class PolicyError(ValueError):
    def __init__(self, reason: str, detail: str | None = None) -> None:
        super().__init__(reason if detail is None else f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


def fail(reason: str, detail: str | None = None) -> None:
    raise PolicyError(reason, detail)


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json(value: Any) -> bytes:
    """Canonical signed/receipt data: no non-finite or non-JSON values."""
    try:
        return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise PolicyError("NON_CANONICAL_JSON", type(error).__name__) from error


def _no_duplicate_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in pairs:
        if key in result:
            fail("JSON_DUPLICATE_MEMBER", key)
        result[key] = item
    return result


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as source:
            raw = source.read(MAX_JSON_BYTES + 1)
        if len(raw) > MAX_JSON_BYTES:
            fail("JSON_BYTE_BOUND_EXCEEDED")
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_no_duplicate_members,
            parse_constant=lambda _value: fail("JSON_NONFINITE_NUMBER"),
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise PolicyError("INVALID_JSON", type(error).__name__) from error
    if not isinstance(value, dict):
        fail("JSON_OBJECT_REQUIRED", str(path))
    return value


def is_integer(value: Any) -> bool:
    # Python bool subclasses int; protocol integer fields must not accept it.
    return type(value) is int


def decode_b64(value: Any, size: int, reason: str) -> bytes:
    if not isinstance(value, str):
        fail(reason, "base64 string required")
    try:
        result = base64.b64decode(value, validate=True)
    except ValueError as error:
        raise PolicyError(reason, "invalid base64") from error
    if len(result) != size:
        fail(reason, f"expected {size} bytes")
    return result


def permit_payload(permit: dict[str, Any]) -> bytes:
    value = copy.deepcopy(permit)
    value.pop("signature", None)
    return canonical_json(value)


def canonical_subject(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != SUBJECT_FIELDS:
        fail("SUBJECT_FIELD_SET_MISMATCH")
    result = {
        "taskflow_principal": value["taskflow_principal"],
        "mechanism_uid": value["mechanism_uid"],
        "mechanism_unit": value["mechanism_unit"],
        "session_id": value["session_id"],
        "page_owner_id": value["page_owner_id"],
    }
    for key, item in result.items():
        if key == "mechanism_uid":
            if not is_integer(item) or item < 0:
                fail("INVALID_SUBJECT_UID")
        elif not isinstance(item, str) or not item or len(item.encode("utf-8")) > 256:
            fail("INVALID_SUBJECT_FIELD", key)
        if item == "*":
            fail("SUBJECT_WILDCARD_FORBIDDEN", key)
    return result


def canonical_dns_name(host: str) -> str:
    if not isinstance(host, str) or not host or len(host.encode("utf-8")) > 253:
        fail("INVALID_DNS_NAME")
    if host.endswith(".") or "%" in host or "\\" in host:
        fail("NON_CANONICAL_HOST", host)
    try:
        ipaddress.ip_address(host)
    except ValueError:
        try:
            ascii_host = host.encode("idna").decode("ascii").lower()
        except UnicodeError as error:
            raise PolicyError("INVALID_IDNA_HOST", host) from error
        if ascii_host != host:
            fail("NON_CANONICAL_HOST", host)
        labels = ascii_host.split(".")
        if any(not HOST_LABEL.fullmatch(label) for label in labels):
            fail("INVALID_DNS_NAME", host)
        if ascii_host == "localhost" or ascii_host.endswith(".localhost"):
            fail("LOCALHOST_NAME_FORBIDDEN", host)
        return ascii_host
    else:
        fail("DNS_NAME_EXPECTED_NOT_IP_LITERAL", host)


def canonical_host(host: str) -> tuple[str, ipaddress._BaseAddress | None]:
    if not isinstance(host, str) or not host:
        fail("HOST_REQUIRED")
    if host.endswith(".") or "%" in host or "\\" in host:
        fail("NON_CANONICAL_HOST", host)
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return canonical_dns_name(host), None
    canonical = address.compressed.lower()
    if canonical != host.lower():
        fail("NON_CANONICAL_IP_LITERAL", host)
    return canonical, address


def split_url(value: Any, allowed_schemes: Iterable[str]) -> tuple[SplitResult, str, int, str]:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > MAX_URL_BYTES:
        fail("INVALID_URL")
    if any(ord(character) <= 0x20 or ord(character) == 0x7F or character.isspace() for character in value) or "\\" in value:
        fail("URL_NON_CANONICAL_CHARACTER")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise PolicyError("INVALID_URL", str(error)) from error
    if parsed.scheme not in set(allowed_schemes):
        fail("SCHEME_NOT_AUTHORIZED", parsed.scheme)
    if parsed.username is not None or parsed.password is not None:
        fail("URL_USERINFO_FORBIDDEN")
    if "#" in value:
        fail("URL_FRAGMENT_FORBIDDEN")
    if not parsed.hostname:
        fail("URL_HOST_REQUIRED")
    host, address = canonical_host(parsed.hostname)
    default_port = 443 if parsed.scheme in {"https", "wss"} else 80
    effective_port = port if port is not None else default_port
    if not 1 <= effective_port <= 65535:
        fail("INVALID_URL_PORT")
    if address is not None:
        rendered_host = f"[{host}]" if address.version == 6 else host
    else:
        rendered_host = host
    expected_authority = rendered_host if port is None else f"{rendered_host}:{port}"
    if not value.startswith(f"{parsed.scheme}://") or parsed.netloc != expected_authority:
        fail("NON_CANONICAL_URL_AUTHORITY")
    origin = f"{parsed.scheme}://{rendered_host}:{effective_port}"
    return parsed, host, effective_port, origin


def canonical_origin(value: Any, allowed_schemes: Iterable[str]) -> str:
    parsed, _host, _port, origin = split_url(value, allowed_schemes)
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        fail("ORIGIN_MUST_NOT_HAVE_PATH_QUERY_OR_FRAGMENT", str(value))
    return origin


def validate_public_ip(value: Any) -> ipaddress._BaseAddress:
    if not isinstance(value, str):
        fail("INVALID_IP_ADDRESS")
    try:
        address = ipaddress.ip_address(value)
    except ValueError as error:
        raise PolicyError("INVALID_IP_ADDRESS", value) from error
    canonical = address.compressed.lower()
    if canonical in METADATA_ADDRESSES or value.lower() in METADATA_ADDRESSES:
        fail("METADATA_IP_FORBIDDEN", canonical)
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            fail("IPV4_MAPPED_IPV6_FORBIDDEN", canonical)
        if address.sixtofour is not None:
            fail("SIX_TO_FOUR_FORBIDDEN", canonical)
        if address.teredo is not None:
            fail("TEREDO_FORBIDDEN", canonical)
    if not address.is_global:
        if address.is_loopback:
            fail("LOOPBACK_IP_FORBIDDEN", canonical)
        if address.is_link_local:
            fail("LINK_LOCAL_IP_FORBIDDEN", canonical)
        if address.is_private:
            fail("PRIVATE_IP_FORBIDDEN", canonical)
        if address.is_multicast:
            fail("MULTICAST_IP_FORBIDDEN", canonical)
        if address.is_unspecified:
            fail("UNSPECIFIED_IP_FORBIDDEN", canonical)
        if address.is_reserved:
            fail("RESERVED_IP_FORBIDDEN", canonical)
        fail("NON_GLOBAL_IP_FORBIDDEN", canonical)
    return address


def issuer_public_key(trust: dict[str, Any], issuer_id: str, key_id: str, now_epoch: int) -> bytes:
    if trust.get("schema") != "trillionnium.desktop.capability-issuer-trust.v1":
        fail("ISSUER_TRUST_SCHEMA_MISMATCH")
    issuers = trust.get("issuers")
    if not isinstance(issuers, dict):
        fail("ISSUER_MAP_REQUIRED")
    issuer = issuers.get(issuer_id)
    if not isinstance(issuer, dict):
        fail("UNKNOWN_ISSUER", issuer_id)
    keys = issuer.get("keys")
    if not isinstance(keys, dict):
        fail("ISSUER_KEY_MAP_REQUIRED", issuer_id)
    record = keys.get(key_id)
    if not isinstance(record, dict):
        fail("UNKNOWN_ISSUER_KEY", key_id)
    if set(record) != {"status", "public_key_base64", "not_before_epoch", "expires_at_epoch"}:
        fail("ISSUER_KEY_FIELD_SET_MISMATCH")
    if record["status"] != "active":
        fail("ISSUER_KEY_NOT_ACTIVE", key_id)
    if not is_integer(record["not_before_epoch"]) or not is_integer(record["expires_at_epoch"]):
        fail("ISSUER_KEY_TIME_INVALID")
    if not 0 <= record["not_before_epoch"] <= now_epoch <= record["expires_at_epoch"]:
        fail("ISSUER_KEY_OUTSIDE_VALIDITY")
    return decode_b64(record["public_key_base64"], 32, "INVALID_ISSUER_PUBLIC_KEY")


def verify_permit(
    permit: dict[str, Any],
    trust: dict[str, Any],
    runtime_subject: dict[str, Any],
    contract: dict[str, Any],
    *,
    now_epoch: int,
) -> dict[str, Any]:
    if not is_integer(now_epoch) or now_epoch < 0:
        fail("RUNTIME_TIME_INVALID")
    if not isinstance(permit, dict) or set(permit) != PERMIT_FIELDS:
        fail("PERMIT_FIELD_SET_MISMATCH")
    if contract["permit"]["schema"] != PERMIT_SCHEMA or permit.get("schema") != PERMIT_SCHEMA:
        fail("PERMIT_SCHEMA_MISMATCH")
    for key in ("permit_id", "issuer_id", "issuer_key_id", "nonce", "audience"):
        if not isinstance(permit.get(key), str) or not TOKEN_ID.fullmatch(permit[key]):
            fail("INVALID_PERMIT_IDENTIFIER", key)
    subject = canonical_subject(permit.get("subject"))
    if subject != canonical_subject(runtime_subject):
        fail("SUBJECT_MISMATCH")
    issued = permit.get("issued_at_epoch")
    not_before = permit.get("not_before_epoch")
    expires = permit.get("expires_at_epoch")
    if not all(is_integer(item) for item in (issued, not_before, expires)):
        fail("PERMIT_TIME_FIELDS_REQUIRED")
    if not 0 <= issued <= not_before <= expires:
        fail("PERMIT_TIME_ORDER_INVALID")
    if expires - issued > int(contract["permit"]["maximum_lifetime_seconds"]):
        fail("PERMIT_LIFETIME_TOO_LONG")
    if now_epoch < not_before:
        fail("PERMIT_NOT_YET_VALID")
    if now_epoch > expires:
        fail("PERMIT_EXPIRED")
    maximum_uses = permit.get("maximum_uses")
    if not is_integer(maximum_uses) or not 1 <= maximum_uses <= int(contract["permit"]["maximum_uses"]):
        fail("INVALID_MAXIMUM_USES")
    actions = permit.get("actions")
    if not isinstance(actions, list) or not actions or not all(isinstance(item, str) and TOKEN_ID.fullmatch(item) for item in actions):
        fail("INVALID_PERMIT_ACTIONS")
    if len(actions) != len(set(actions)):
        fail("DUPLICATE_PERMIT_ACTION")
    if not isinstance(permit.get("resource"), dict) or not isinstance(permit.get("constraints"), dict):
        fail("PERMIT_RESOURCE_AND_CONSTRAINTS_REQUIRED")
    revoked = trust.get("revoked_permit_ids")
    if not isinstance(revoked, list) or not all(isinstance(item, str) for item in revoked):
        fail("REVOKED_PERMIT_SET_INVALID")
    if permit["permit_id"] in revoked:
        fail("PERMIT_REVOKED")
    public_key = issuer_public_key(trust, permit["issuer_id"], permit["issuer_key_id"], now_epoch)
    signature = permit.get("signature")
    if not isinstance(signature, dict) or set(signature) != {"algorithm", "value_base64"}:
        fail("PERMIT_SIGNATURE_FIELD_SET_MISMATCH")
    if signature["algorithm"] != "Ed25519":
        fail("PERMIT_SIGNATURE_ALGORITHM_UNSUPPORTED")
    signature_bytes = decode_b64(signature["value_base64"], 64, "INVALID_PERMIT_SIGNATURE")
    if not ed25519_verify(public_key, permit_payload(permit), signature_bytes):
        fail("PERMIT_SIGNATURE_REJECTED")
    return copy.deepcopy(permit)


@dataclass
class DecisionLedger:
    """In-memory source model; commit is transactional and serialized.

    Preliminary availability is advisory. The commit lock rechecks all limits
    and publishes counters plus receipt only after every encoding/copy succeeds.
    This does not provide durable storage or authorize an external operation.
    """
    uses: dict[str, int] = field(default_factory=dict)
    receipts: list[dict[str, Any]] = field(default_factory=list)
    _lock: Any = field(default_factory=threading.RLock, repr=False, compare=False)

    def available(self, permit: dict[str, Any]) -> None:
        with self._lock:
            used = self.uses.get(permit["permit_id"], 0)
            maximum = permit.get("maximum_uses")
            if not is_integer(used) or used < 0 or not is_integer(maximum) or maximum < 1:
                fail("INVALID_MAXIMUM_USES")
            if used >= maximum:
                fail("PERMIT_REPLAY_LIMIT_REACHED", permit["permit_id"])

    def commit(
        self,
        permits: list[dict[str, Any]],
        request: dict[str, Any],
        details: dict[str, Any],
        now_epoch: int,
    ) -> dict[str, Any]:
        with self._lock:
            if not is_integer(now_epoch) or now_epoch < 0:
                fail("RUNTIME_TIME_INVALID")
            if not permits:
                fail("PERMIT_REQUIRED")
            identities = [permit["permit_id"] for permit in permits]
            if len(set(identities)) != len(identities):
                fail("DUPLICATE_PERMIT_ID")
            next_uses = dict(self.uses)
            for permit in permits:
                self.available(permit)
                permit_id = permit["permit_id"]
                next_uses[permit_id] = next_uses.get(permit_id, 0) + 1
            previous = self.receipts[-1]["receipt_sha256"] if self.receipts else "0" * 64
            receipt: dict[str, Any] = {
                "schema": "trillionnium.desktop.capability-decision-receipt.v1",
                "sequence": len(self.receipts) + 1,
                "previous_receipt_sha256": previous,
                "decision": "ADMIT",
                "now_epoch": now_epoch,
                "permit_ids": identities,
                "permit_sha256": [sha256(canonical_json(permit)) for permit in permits],
                "request_sha256": sha256(canonical_json(request)),
                "details": copy.deepcopy(details),
                "external_effect_executed": False,
            }
            receipt["receipt_sha256"] = sha256(canonical_json(receipt))
            returned = copy.deepcopy(receipt)
            next_receipts = self.receipts + [receipt]
            self.uses, self.receipts = next_uses, next_receipts
            return returned

    @staticmethod
    def verify_receipts(receipts: Iterable[dict[str, Any]]) -> None:
        previous = "0" * 64
        for sequence, original in enumerate(receipts, start=1):
            receipt = copy.deepcopy(original)
            claimed = receipt.pop("receipt_sha256", None)
            if not is_integer(receipt.get("sequence")) or receipt["sequence"] != sequence:
                fail("DECISION_RECEIPT_SEQUENCE_MISMATCH")
            if receipt.get("previous_receipt_sha256") != previous:
                fail("DECISION_RECEIPT_CHAIN_MISMATCH")
            if receipt.get("decision") != "ADMIT" or receipt.get("external_effect_executed") is not False:
                fail("DECISION_RECEIPT_CLAIM_MISMATCH")
            actual = sha256(canonical_json(receipt))
            if claimed != actual:
                fail("DECISION_RECEIPT_HASH_MISMATCH")
            previous = actual


def require_audience_action(permit: dict[str, Any], audience: str, action: str) -> None:
    if permit["audience"] != audience:
        fail("AUDIENCE_MISMATCH")
    if action not in permit["actions"]:
        fail("ACTION_NOT_AUTHORIZED", action)


def authorize_file(
    permit: dict[str, Any], request: dict[str, Any]
) -> dict[str, Any]:
    if set(request) != {"kind", "action", "handle_id", "bytes"} or request.get("kind") != "file":
        fail("FILE_REQUEST_FIELD_SET_MISMATCH")
    action = request.get("action")
    require_audience_action(permit, "portal:file", str(action))
    resource = permit["resource"]
    if set(resource) != {"kind", "handle_id", "maximum_bytes"} or resource.get("kind") != "opaque_file_handle":
        fail("FILE_RESOURCE_FIELD_SET_MISMATCH")
    if any(not isinstance(value, str) or not TOKEN_ID.fullmatch(value)
           for value in (request.get("handle_id"), resource.get("handle_id"))):
        fail("FILE_HANDLE_MISMATCH")
    if request.get("handle_id") != resource.get("handle_id"):
        fail("FILE_HANDLE_MISMATCH")
    byte_count = request.get("bytes")
    maximum = resource.get("maximum_bytes")
    if not is_integer(byte_count) or byte_count < 0 or not is_integer(maximum) or maximum < 0:
        fail("FILE_BYTE_BOUND_INVALID")
    if byte_count > maximum:
        fail("FILE_BYTE_LIMIT_EXCEEDED")
    return {"portal": "file", "handle_id": resource["handle_id"], "bytes": byte_count}


def authorize_notification(permit: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    if set(request) != {"kind", "action", "channel_id", "title", "body"} or request.get("kind") != "notification":
        fail("NOTIFICATION_REQUEST_FIELD_SET_MISMATCH")
    require_audience_action(permit, "portal:notification", str(request.get("action")))
    resource = permit["resource"]
    if set(resource) != {"kind", "channel_id", "maximum_text_bytes"} or resource.get("kind") != "notification_channel":
        fail("NOTIFICATION_RESOURCE_FIELD_SET_MISMATCH")
    if any(not isinstance(value, str) or not TOKEN_ID.fullmatch(value)
           for value in (request.get("channel_id"), resource.get("channel_id"))):
        fail("NOTIFICATION_CHANNEL_MISMATCH")
    if request.get("channel_id") != resource.get("channel_id"):
        fail("NOTIFICATION_CHANNEL_MISMATCH")
    if any(not isinstance(request.get(key), str) for key in ("title", "body")):
        fail("NOTIFICATION_TEXT_TYPE_INVALID")
    maximum = resource["maximum_text_bytes"]
    if not is_integer(maximum) or maximum < 0:
        fail("NOTIFICATION_TEXT_BOUND_INVALID")
    total = sum(len(request[key].encode("utf-8")) for key in ("title", "body"))
    if total > min(maximum, MAX_TEXT_BYTES):
        fail("NOTIFICATION_TEXT_LIMIT_EXCEEDED")
    return {"portal": "notification", "channel_id": resource["channel_id"], "text_bytes": total}


def authorize_audio(permit: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    if set(request) != {"kind", "action", "stream_id", "duration_ms", "gain_millibel"} or request.get("kind") != "audio":
        fail("AUDIO_REQUEST_FIELD_SET_MISMATCH")
    require_audience_action(permit, "portal:audio", str(request.get("action")))
    resource = permit["resource"]
    if set(resource) != {"kind", "stream_id", "maximum_duration_ms", "maximum_gain_millibel"} or resource.get("kind") != "audio_stream":
        fail("AUDIO_RESOURCE_FIELD_SET_MISMATCH")
    if any(not isinstance(value, str) or not TOKEN_ID.fullmatch(value)
           for value in (request.get("stream_id"), resource.get("stream_id"))):
        fail("AUDIO_STREAM_MISMATCH")
    if request.get("stream_id") != resource.get("stream_id"):
        fail("AUDIO_STREAM_MISMATCH")
    duration = request.get("duration_ms")
    gain = request.get("gain_millibel")
    if not all(is_integer(item) for item in (
        duration, gain, resource["maximum_duration_ms"], resource["maximum_gain_millibel"],
    )):
        fail("AUDIO_BOUND_TYPE_INVALID")
    if duration < 0 or duration > resource["maximum_duration_ms"]:
        fail("AUDIO_DURATION_LIMIT_EXCEEDED")
    if gain > resource["maximum_gain_millibel"]:
        fail("AUDIO_GAIN_LIMIT_EXCEEDED")
    return {"portal": "audio", "stream_id": resource["stream_id"], "duration_ms": duration}


def network_resource(permit: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    resource = permit["resource"]
    required = {
        "kind",
        "origins",
        "resolver_id",
        "proxy_id",
        "contexts",
        "methods",
        "maximum_redirects",
        "maximum_dns_ttl_seconds",
        "maximum_request_bytes",
        "maximum_response_bytes",
    }
    if set(resource) != required or resource.get("kind") != "exact_origin_set":
        fail("NETWORK_RESOURCE_FIELD_SET_MISMATCH")
    allowed_schemes = contract["network"]["allowed_schemes"]
    origins = resource.get("origins")
    if not isinstance(origins, list) or not origins:
        fail("NETWORK_ORIGIN_SET_REQUIRED")
    canonical = [canonical_origin(item, allowed_schemes) for item in origins]
    if len(canonical) != len(set(canonical)) or canonical != origins:
        fail("NETWORK_ORIGIN_SET_NON_CANONICAL")
    contexts = resource.get("contexts")
    if not isinstance(contexts, list) or not contexts or any(not isinstance(item, str) for item in contexts) or len(contexts) != len(set(contexts)):
        fail("NETWORK_CONTEXT_SET_INVALID")
    if any(item not in contract["request_contexts"] for item in contexts):
        fail("NETWORK_CONTEXT_UNKNOWN")
    methods = resource.get("methods")
    if not isinstance(methods, list) or not methods or any(not isinstance(item, str) for item in methods) or len(methods) != len(set(methods)):
        fail("NETWORK_METHOD_SET_INVALID")
    if any(re.fullmatch(r"[A-Z]+", item) is None for item in methods):
        fail("NETWORK_METHOD_NON_CANONICAL")
    maximum_redirects = resource.get("maximum_redirects")
    if not is_integer(maximum_redirects) or not 0 <= maximum_redirects <= int(contract["network"]["maximum_redirects"]):
        fail("NETWORK_REDIRECT_BOUND_INVALID")
    for key in ("maximum_dns_ttl_seconds", "maximum_request_bytes", "maximum_response_bytes"):
        if not is_integer(resource.get(key)) or resource[key] < 0:
            fail("NETWORK_NUMERIC_BOUND_INVALID", key)
    for key in ("resolver_id", "proxy_id"):
        if not isinstance(resource.get(key), str) or not TOKEN_ID.fullmatch(resource[key]):
            fail("NETWORK_COMPONENT_ID_INVALID", key)
    return resource


def validate_dns(
    dns: Any,
    host: str,
    resource: dict[str, Any],
    contract: dict[str, Any],
    now_epoch: int,
) -> set[str]:
    required = {
        "resolver_id",
        "query_name",
        "addresses",
        "ttl_seconds",
        "observed_at_epoch",
        "cname_chain",
    }
    if not isinstance(dns, dict) or set(dns) != required:
        fail("DNS_EVIDENCE_FIELD_SET_MISMATCH")
    if dns.get("resolver_id") != resource["resolver_id"]:
        fail("RESOLVER_ID_MISMATCH")
    if dns.get("query_name") != host:
        fail("DNS_QUERY_NAME_MISMATCH")
    ttl = dns.get("ttl_seconds")
    observed = dns.get("observed_at_epoch")
    if not is_integer(ttl) or not 1 <= ttl <= resource["maximum_dns_ttl_seconds"]:
        fail("DNS_TTL_BOUND_VIOLATION")
    if not is_integer(observed) or not 0 <= observed <= now_epoch <= observed + ttl:
        fail("DNS_EVIDENCE_EXPIRED_OR_FUTURE")
    chain = dns.get("cname_chain")
    if not isinstance(chain, list) or len(chain) > int(contract["network"]["maximum_cname_depth"]):
        fail("CNAME_DEPTH_EXCEEDED")
    canonical_chain = [canonical_dns_name(item) for item in chain]
    if len(canonical_chain) != len(set(canonical_chain)):
        fail("CNAME_LOOP_REJECTED")
    addresses = dns.get("addresses")
    if not isinstance(addresses, list) or not 1 <= len(addresses) <= int(contract["network"]["maximum_dns_addresses"]):
        fail("DNS_ADDRESS_COUNT_INVALID")
    approved = {validate_public_ip(item).compressed.lower() for item in addresses}
    if len(approved) != len(addresses):
        fail("DUPLICATE_DNS_ADDRESS")
    return approved


def authorize_network(
    permit: dict[str, Any],
    request: dict[str, Any],
    contract: dict[str, Any],
    now_epoch: int,
) -> dict[str, Any]:
    required_request = {
        "kind",
        "action",
        "url",
        "method",
        "context",
        "request_bytes",
        "expected_response_bytes",
        "redirect_count",
        "previous_url",
        "dns",
        "connection",
        "transport",
        "response_observation",
    }
    if not isinstance(request, dict) or set(request) != required_request or request.get("kind") != "network":
        fail("NETWORK_REQUEST_FIELD_SET_MISMATCH")
    action = str(request.get("action"))
    require_audience_action(permit, "portal:network", action)
    resource = network_resource(permit, contract)
    parsed, host, port, origin = split_url(request.get("url"), contract["network"]["allowed_schemes"])
    if origin not in resource["origins"]:
        fail("NETWORK_ORIGIN_NOT_AUTHORIZED", origin)
    context = request.get("context")
    if context not in resource["contexts"]:
        fail("REQUEST_CONTEXT_NOT_AUTHORIZED", str(context))
    expected_context = {
        "websocket_connect": "websocket",
        "download": "download",
    }.get(action)
    if expected_context is not None and context != expected_context:
        fail("ACTION_CONTEXT_MISMATCH")
    method = request.get("method")
    if not isinstance(method, str) or method.upper() != method or method not in resource["methods"]:
        fail("HTTP_METHOD_NOT_AUTHORIZED")
    if action == "websocket_connect" and parsed.scheme != "wss":
        fail("WEBSOCKET_REQUIRES_WSS")
    if action in {"http_request", "download"} and parsed.scheme != "https":
        fail("HTTP_REQUEST_REQUIRES_HTTPS")
    for key, maximum_key in (
        ("request_bytes", "maximum_request_bytes"),
        ("expected_response_bytes", "maximum_response_bytes"),
    ):
        value = request.get(key)
        if not is_integer(value) or value < 0 or value > resource[maximum_key]:
            fail("NETWORK_BYTE_BOUND_EXCEEDED", key)
    redirects = request.get("redirect_count")
    if not is_integer(redirects) or not 0 <= redirects <= resource["maximum_redirects"]:
        fail("REDIRECT_BUDGET_EXCEEDED")
    previous_url = request.get("previous_url")
    if redirects == 0:
        if previous_url is not None:
            fail("UNEXPECTED_PREVIOUS_URL")
    else:
        if not isinstance(previous_url, str):
            fail("PREVIOUS_URL_REQUIRED")
        previous, _previous_host, _previous_port, previous_origin = split_url(
            previous_url, contract["network"]["allowed_schemes"]
        )
        if previous_origin not in resource["origins"]:
            fail("REDIRECT_SOURCE_ORIGIN_NOT_AUTHORIZED")
        if previous.scheme == "https" and parsed.scheme != "https":
            fail("HTTPS_REDIRECT_DOWNGRADE_REJECTED")
        if previous.scheme == "wss" and parsed.scheme != "wss":
            fail("WSS_REDIRECT_DOWNGRADE_REJECTED")

    approved = validate_dns(request.get("dns"), host, resource, contract, now_epoch)
    transport = request.get("transport")
    required_transport = {
        "mode",
        "proxy_id",
        "direct",
        "protocol",
        "tls_verified",
        "tls_intercepted",
        "certificate_host",
    }
    if not isinstance(transport, dict) or set(transport) != required_transport:
        fail("TRANSPORT_EVIDENCE_FIELD_SET_MISMATCH")
    if transport.get("mode") != "egress_proxy" or transport.get("proxy_id") != resource["proxy_id"]:
        fail("EGRESS_PROXY_MISMATCH")
    if transport.get("direct") is not False:
        fail("PROXY_BYPASS_REJECTED")
    if transport.get("protocol") in {"quic", "webtransport"}:
        fail("UNSUPPORTED_TRANSPORT_PROTOCOL")
    if transport.get("protocol") not in {"tcp", "websocket"}:
        fail("TRANSPORT_PROTOCOL_INVALID")
    if transport.get("tls_verified") is not True:
        fail("TLS_VERIFICATION_REQUIRED")
    if transport.get("tls_intercepted") is not False:
        fail("TLS_INTERCEPTION_REJECTED")
    if transport.get("certificate_host") != host:
        fail("TLS_CERTIFICATE_HOST_MISMATCH")

    connection = request.get("connection")
    if not isinstance(connection, dict) or set(connection) != {"peer_ip", "proxy_id", "observed_at_epoch"}:
        fail("CONNECTION_EVIDENCE_FIELD_SET_MISMATCH")
    if connection.get("proxy_id") != resource["proxy_id"]:
        fail("CONNECTION_PROXY_ID_MISMATCH")
    if not is_integer(connection.get("observed_at_epoch")) or not request["dns"]["observed_at_epoch"] <= connection["observed_at_epoch"] <= now_epoch:
        fail("CONNECTION_TIME_INVALID")
    peer = validate_public_ip(connection.get("peer_ip")).compressed.lower()
    if peer not in approved:
        fail("CONNECTED_PEER_NOT_IN_APPROVED_DNS_SET", peer)

    response = request.get("response_observation")
    if not isinstance(response, dict) or set(response) != {"captive_portal", "redirect_location", "tls_intercepted"}:
        fail("RESPONSE_OBSERVATION_FIELD_SET_MISMATCH")
    if response.get("captive_portal") is not False:
        fail("CAPTIVE_PORTAL_REJECTED")
    if response.get("tls_intercepted") is not False:
        fail("TLS_INTERCEPTION_REJECTED")
    location = response.get("redirect_location")
    if location is not None:
        _redirect, _rhost, _rport, redirect_origin = split_url(
            location, contract["network"]["allowed_schemes"]
        )
        if redirect_origin not in resource["origins"]:
            fail("REDIRECT_DESTINATION_REAUTHORIZATION_REQUIRED", redirect_origin)

    return {
        "portal": "network",
        "action": action,
        "origin": origin,
        "host": host,
        "port": port,
        "context": context,
        "resolver_id": resource["resolver_id"],
        "proxy_id": resource["proxy_id"],
        "approved_dns_sha256": sha256(canonical_json(sorted(approved))),
        "connected_peer_ip": peer,
        "redirect_count": redirects,
        "network_access_executed": False,
    }


def authorize(
    permits: list[dict[str, Any]],
    request: dict[str, Any],
    trust: dict[str, Any],
    runtime_subject: dict[str, Any],
    contract: dict[str, Any],
    ledger: DecisionLedger,
    *,
    now_epoch: int,
) -> dict[str, Any]:
    if not permits:
        fail("PERMIT_REQUIRED")
    verified = [
        verify_permit(item, trust, runtime_subject, contract, now_epoch=now_epoch)
        for item in permits
    ]
    for item in verified:
        ledger.available(item)
    kind = request.get("kind") if isinstance(request, dict) else None
    if kind == "file":
        if len(verified) != 1:
            fail("SINGLE_FILE_PERMIT_REQUIRED")
        details = authorize_file(verified[0], request)
        consumed = verified
    elif kind == "notification":
        if len(verified) != 1:
            fail("SINGLE_NOTIFICATION_PERMIT_REQUIRED")
        details = authorize_notification(verified[0], request)
        consumed = verified
    elif kind == "audio":
        if len(verified) != 1:
            fail("SINGLE_AUDIO_PERMIT_REQUIRED")
        details = authorize_audio(verified[0], request)
        consumed = verified
    elif kind == "network":
        network_permits = [item for item in verified if item["audience"] == "portal:network"]
        if len(network_permits) != 1:
            fail("SINGLE_NETWORK_PERMIT_REQUIRED")
        details = authorize_network(network_permits[0], request, contract, now_epoch)
        consumed = [network_permits[0]]
        if request.get("action") == "download":
            file_permits = [item for item in verified if item["audience"] == "portal:file"]
            if len(file_permits) != 1:
                fail("DOWNLOAD_REQUIRES_FILE_PERMIT")
            download_target = request.get("download_target")
            # Unknown request fields are rejected above; the file request is
            # carried inside the network permit constraints instead.
            target = network_permits[0]["constraints"].get("download_target")
            if not isinstance(target, dict):
                fail("DOWNLOAD_TARGET_CONSTRAINT_REQUIRED")
            authorize_file(file_permits[0], target)
            details["file_handle_id"] = target["handle_id"]
            consumed.append(file_permits[0])
    else:
        fail("UNKNOWN_PORTAL_REQUEST")
    return ledger.commit(consumed, request, details, now_epoch)


def build_fixture_permit(
    *,
    seed: bytes,
    subject: dict[str, Any],
    audience: str,
    resource: dict[str, Any],
    actions: list[str],
    permit_id: str,
    nonce: str,
    issued_at_epoch: int = 90,
    not_before_epoch: int = 90,
    expires_at_epoch: int = 200,
    maximum_uses: int = 1,
    constraints: dict[str, Any] | None = None,
    issuer_id: str = "fixture-issuer",
    issuer_key_id: str = "fixture-key-1",
) -> tuple[dict[str, Any], bytes]:
    permit: dict[str, Any] = {
        "schema": PERMIT_SCHEMA,
        "permit_id": permit_id,
        "issuer_id": issuer_id,
        "issuer_key_id": issuer_key_id,
        "subject": copy.deepcopy(subject),
        "audience": audience,
        "resource": copy.deepcopy(resource),
        "actions": list(actions),
        "issued_at_epoch": issued_at_epoch,
        "not_before_epoch": not_before_epoch,
        "expires_at_epoch": expires_at_epoch,
        "nonce": nonce,
        "maximum_uses": maximum_uses,
        "constraints": copy.deepcopy(constraints or {}),
        "signature": {"algorithm": "Ed25519", "value_base64": ""},
    }
    permit["signature"]["value_base64"] = base64.b64encode(
        ed25519_sign_fixture(seed, permit_payload(permit))
    ).decode("ascii")
    return permit, ed25519_public_from_seed(seed)


def fixture_subject() -> dict[str, Any]:
    return {
        "taskflow_principal": "taskflow:fixture-agent",
        "mechanism_uid": 1001,
        "mechanism_unit": "hepta-agent.service",
        "session_id": "session-fixture",
        "page_owner_id": "page-owner-fixture",
    }


def fixture_network_resource() -> dict[str, Any]:
    return {
        "kind": "exact_origin_set",
        "origins": ["https://example.com:443", "wss://socket.example.com:443"],
        "resolver_id": "resolver-fixture",
        "proxy_id": "proxy-fixture",
        "contexts": ["top_level", "iframe", "worker", "service_worker", "prefetch", "websocket", "download"],
        "methods": ["GET", "POST"],
        "maximum_redirects": 2,
        "maximum_dns_ttl_seconds": 300,
        "maximum_request_bytes": 1048576,
        "maximum_response_bytes": 8388608,
    }


def fixture_trust(public_key: bytes) -> dict[str, Any]:
    return {
        "schema": "trillionnium.desktop.capability-issuer-trust.v1",
        "revocation_epoch": 1,
        "issuers": {
            "fixture-issuer": {
                "keys": {
                    "fixture-key-1": {
                        "status": "active",
                        "public_key_base64": base64.b64encode(public_key).decode("ascii"),
                        "not_before_epoch": 1,
                        "expires_at_epoch": 1000,
                    }
                }
            }
        },
        "revoked_permit_ids": [],
    }


def fixture_network_request() -> dict[str, Any]:
    return {
        "kind": "network",
        "action": "http_request",
        "url": "https://example.com/resource",
        "method": "GET",
        "context": "top_level",
        "request_bytes": 0,
        "expected_response_bytes": 1024,
        "redirect_count": 0,
        "previous_url": None,
        "dns": {
            "resolver_id": "resolver-fixture",
            "query_name": "example.com",
            "addresses": ["93.184.216.34"],
            "ttl_seconds": 60,
            "observed_at_epoch": 100,
            "cname_chain": [],
        },
        "connection": {
            "peer_ip": "93.184.216.34",
            "proxy_id": "proxy-fixture",
            "observed_at_epoch": 100,
        },
        "transport": {
            "mode": "egress_proxy",
            "proxy_id": "proxy-fixture",
            "direct": False,
            "protocol": "tcp",
            "tls_verified": True,
            "tls_intercepted": False,
            "certificate_host": "example.com",
        },
        "response_observation": {
            "captive_portal": False,
            "redirect_location": None,
            "tls_intercepted": False,
        },
    }


def self_test(contract: dict[str, Any]) -> dict[str, Any]:
    seed = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
    subject = fixture_subject()
    permit, public = build_fixture_permit(
        seed=seed,
        subject=subject,
        audience="portal:network",
        resource=fixture_network_resource(),
        actions=["http_request"],
        permit_id="permit-self-test",
        nonce="nonce-self-test",
    )
    ledger = DecisionLedger()
    receipt = authorize(
        [permit],
        fixture_network_request(),
        fixture_trust(public),
        subject,
        contract,
        ledger,
        now_epoch=100,
    )
    DecisionLedger.verify_receipts(ledger.receipts)
    return {
        "schema": "trillionnium.desktop.capability-egress-self-test.v1",
        "status": "PASS_SOURCE_REFERENCE_ONLY",
        "decision_receipt_sha256": receipt["receipt_sha256"],
        "approved_dns_sha256": receipt["details"]["approved_dns_sha256"],
        "network_access_executed": False,
        "controlled_resolver_integrated": False,
        "egress_proxy_integrated": False,
        "kernel_peer_ip_observed": False,
        "production_credentials_available": False,
        "external_effects_enabled": False,
        "release_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    parser.add_argument("--write-result", type=Path)
    args = parser.parse_args()
    try:
        contract = load_json(args.contract)
        if contract.get("status") != "SOURCE_CANDIDATE_BLOCKED_UPSTREAM_D5":
            fail("D6_CONTRACT_STATUS_WIDENED")
        result = self_test(contract)
        payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.write_result:
            args.write_result.parent.mkdir(parents=True, exist_ok=True)
            args.write_result.write_text(payload, encoding="utf-8")
        print(payload, end="")
        return 0
    except PolicyError as error:
        print(json.dumps({"status": "REJECTED", "reason": error.reason, "detail": error.detail}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
