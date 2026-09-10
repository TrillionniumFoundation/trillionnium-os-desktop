"""Canonical JSON and bounded primitive validation."""
from __future__ import annotations

import hmac, ipaddress, json, re

PROTOCOL = "trillionnium.desktop.browser-api.v1"
MAX_BYTES, MAX_DEPTH, MAX_ITEMS = 262_144, 32, 20_000
MIN_INTEGER, MAX_INTEGER = -(2**63), 2**63 - 1
ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$", re.ASCII)
DNS_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.ASCII)
SHA_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)

class CodecError(ValueError): pass
class DuplicateMember(CodecError): pass

def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out: raise DuplicateMember(f"duplicate JSON member: {key}")
        out[key] = value
    return out

def measure(value, depth=0):
    if depth > MAX_DEPTH: raise CodecError("JSON nesting exceeds maximum")
    if isinstance(value, float): raise CodecError("floating-point numbers are forbidden")
    if type(value) is int and not MIN_INTEGER <= value <= MAX_INTEGER:
        raise CodecError("integer exceeds signed 64-bit domain")
    if isinstance(value, dict):
        count, high = len(value), depth
        for key, child in value.items():
            if not isinstance(key, str): raise CodecError("object key is not a string")
            child_count, child_depth = measure(child, depth + 1)
            count += child_count; high = max(high, child_depth)
        return count, high
    if isinstance(value, list):
        count, high = len(value), depth
        for child in value:
            child_count, child_depth = measure(child, depth + 1)
            count += child_count; high = max(high, child_depth)
        return count, high
    return 0, depth

def decode_unique(encoded: bytes):
    if not encoded or len(encoded) > MAX_BYTES: raise CodecError("message byte bound")
    if encoded.startswith(b"\xef\xbb\xbf"): raise CodecError("UTF-8 BOM is forbidden")
    try:
        value = json.loads(
            encoded.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_float=lambda _: (_ for _ in ()).throw(CodecError("floating-point numbers are forbidden")),
            parse_constant=lambda _: (_ for _ in ()).throw(CodecError("non-finite numbers are forbidden")),
        )
    except UnicodeDecodeError as error: raise CodecError("invalid UTF-8") from error
    except json.JSONDecodeError as error: raise CodecError(f"invalid JSON: {error.msg}") from error
    count, _ = measure(value)
    if count > MAX_ITEMS: raise CodecError("container item bound")
    return value

def canonical(value) -> bytes:
    measure(value)
    try:
        encoded = json.dumps(
            value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    except (TypeError, ValueError) as error: raise CodecError("not canonical JSON") from error
    if len(encoded) > MAX_BYTES: raise CodecError("message byte bound")
    return encoded

def exact_object(value, required, optional=()):
    if not isinstance(value, dict): raise CodecError("expected object")
    keys = set(value)
    if not set(required) <= keys: raise CodecError("missing required member")
    extra = keys - set(required) - set(optional)
    if extra: raise CodecError(f"unknown members: {sorted(extra)}")
    return value

def integer(value, minimum=0, maximum=None):
    if type(value) is not int: raise CodecError("expected integer")
    if value < minimum or (maximum is not None and value > maximum):
        raise CodecError("integer out of range")
    return value

def text(value, minimum=0, maximum=128):
    if not isinstance(value, str): raise CodecError("expected string")
    size = len(value.encode("utf-8"))
    if size < minimum or size > maximum or "\x00" in value: raise CodecError("string byte bound")
    return value

def identifier(value, maximum=128):
    value = text(value, 1, maximum)
    if not ID_RE.fullmatch(value): raise CodecError("invalid identifier")
    return value

def sha256_hex(value):
    value = text(value, 64, 64)
    if not SHA_RE.fullmatch(value): raise CodecError("invalid SHA-256")
    return value

def safe_url(value, external):
    value = text(value, 1, 8192)
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise CodecError("URL control character")
    expected_prefix = "https://" if external else "http://"
    if not value.startswith(expected_prefix):
        raise CodecError("URL scheme is not canonical")
    # Keep this parser deliberately isomorphic to the product Rust codec.
    # ``urllib.parse.urlsplit`` normalizes several ambiguous authorities (for
    # example six-digit leading-zero ports and IPv6 zone identifiers), which
    # would make the independent reference accept a URL the product rejects.
    remainder = value[len(expected_prefix) :]
    authority_end = len(remainder)
    for delimiter in "/?#":
        position = remainder.find(delimiter)
        if position >= 0:
            authority_end = min(authority_end, position)
    authority = remainder[:authority_end]
    if not authority or "@" in authority or "\\" in authority:
        raise CodecError("URL authority is invalid")

    if authority.startswith("["):
        rest = authority[1:]
        close = rest.find("]")
        if close < 0:
            raise CodecError("unterminated IPv6 host")
        host = rest[:close]
        # Python accepts RFC 6874 scope identifiers, while Rust's
        # ``Ipv6Addr::from_str`` intentionally does not.  Reject them before
        # delegating to the standard-library address parser.
        if "%" in host:
            raise CodecError("invalid IPv6 host")
        try:
            ipaddress.IPv6Address(host)
        except ValueError as error:
            raise CodecError("invalid IPv6 host") from error
        suffix = rest[close + 1 :]
        if suffix:
            if not suffix.startswith(":"):
                raise CodecError("invalid authority suffix")
            _validate_port(suffix[1:])
        normalized_host = host.lower()
    else:
        if authority.count(":") > 1:
            raise CodecError("IPv6 host must use brackets")
        if ":" in authority:
            host, port = authority.rsplit(":", 1)
            _validate_port(port)
        else:
            host = authority
        if not host or any(character.isspace() or character in "/?#" for character in host):
            raise CodecError("URL host is invalid")
        normalized_host = _ascii_lower(host)

    if not external and normalized_host not in {"127.0.0.1", "localhost", "::1"}:
        raise CodecError("fixture URL must be loopback HTTP")
    return value


def _validate_port(port):
    if not port or len(port) > 5 or not all("0" <= character <= "9" for character in port):
        raise CodecError("invalid URL port")
    if int(port) > 65535:
        raise CodecError("URL port is out of range")


def _ascii_lower(value):
    return "".join(
        chr(ord(character) + (ord("a") - ord("A")))
        if "A" <= character <= "Z"
        else character
        for character in value
    )

def require_canonical(encoded, value, label):
    expected = canonical(value)
    if not hmac.compare_digest(encoded, expected):
        raise CodecError(f"{label} is not canonical JSON")
    return expected
