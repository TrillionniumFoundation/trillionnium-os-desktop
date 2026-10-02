"""Bounded offline-configured HTTPS observation mediator candidate.

No ambient resolver, proxy, cookies, credentials or caller socket is accepted.
Only this mediator's sockets are controlled; browser namespace confinement and
resource-class integration remain separate installed obligations.
"""
from __future__ import annotations

import hashlib
import errno
import ipaddress
import math
import json
import os
import re
import secrets
import select
import socket
import ssl
import struct
import threading
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

MAX_URL_BYTES = 8192
MAX_CA_BYTES = 128 * 1024
MAX_DNS_BYTES = 16384
MAX_DNS_RECORDS = 64
MAX_HOSTS = 32
MAX_HEADER_BYTES = 16384
MAX_HEADERS = 64
MAX_BODY_BYTES = 1024 * 1024
MAX_REDIRECTS = 3
MAX_PERMITS = 64
MAX_ACTIVE = 4
POLL_SECONDS = 0.05
_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z", re.ASCII)
_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z", re.ASCII)
_HEADER = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+\Z", re.ASCII)
_BAD_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})|%(?:0[0-9a-fA-F]|1[0-9a-fA-F]|7[fF]|5[cC])")
_V4_DENY = tuple(ipaddress.ip_network(value) for value in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
    "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24", "192.88.99.0/24", "192.168.0.0/16",
    "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4"))
_V6_DENY = tuple(ipaddress.ip_network(value) for value in ("2001::/23", "2001:db8::/32", "2002::/16", "3fff::/20"))


class EgressDenied(RuntimeError):
    """Redacted policy/protocol refusal; never an automatic retry instruction."""


class EgressCancelled(EgressDenied):
    pass


class EgressDeadlineExceeded(EgressDenied):
    pass


class EgressIndeterminate(EgressDenied):
    def __init__(self, operation_id: str, connection: "ConnectionIdentity", hops: tuple["HopReceipt", ...], cause: BaseException):
        super().__init__("an HTTPS request was attempted with uncertain outcome; this permit is consumed")
        self.operation_id, self.connection, self.hops, self.cause = operation_id, connection, hops, cause


def _host(value: object) -> str:
    if type(value) is not str or not value or len(value) > 253 or value != value.lower() or value.endswith("."):
        raise EgressDenied("host must be one canonical bounded ASCII DNS name")
    labels = value.split(".")
    if len(labels) < 2 or any(_LABEL.fullmatch(label) is None for label in labels):
        raise EgressDenied("host must be one canonical bounded ASCII DNS name")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return value
    raise EgressDenied("literal destination addresses are unsupported")


def _port(value: object) -> int:
    if type(value) is not int or not 1 <= value <= 65535:
        raise EgressDenied("approved port is invalid")
    return value


def _external_host(value: object) -> str:
    name = _host(value)
    if name == "hepta.invalid" or name.endswith(".hepta.invalid"):
        raise EgressDenied("synthetic local origins must never reach external DNS or sockets")
    return name


def public_address(value: str) -> str:
    """Conservative version-independent policy including transition mechanisms."""
    if type(value) is not str or "%" in value:
        raise EgressDenied("scoped or malformed IP address")
    try:
        address = ipaddress.ip_address(value)
    except ValueError as error:
        raise EgressDenied("malformed IP address") from error
    if not address.is_global or address.is_multicast or address.is_reserved:
        raise EgressDenied("non-public address is forbidden")
    if isinstance(address, ipaddress.IPv4Address):
        if any(address in network for network in _V4_DENY):
            raise EgressDenied("special-use IPv4 address is forbidden")
    elif address not in ipaddress.ip_network("2000::/3") or address.ipv4_mapped is not None or any(address in network for network in _V6_DENY):
        raise EgressDenied("special-use or transition IPv6 address is forbidden")
    return str(address)


def _origin(value: str) -> str:
    if type(value) is not str or not 0 < len(value) <= MAX_URL_BYTES or any(ord(c) <= 32 or ord(c) >= 127 for c in value) or "\\" in value:
        raise EgressDenied("initiating origin is invalid")
    try:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or parsed.path or parsed.query or parsed.fragment or parsed.username is not None or parsed.password is not None:
            raise EgressDenied("initiating origin is not an exact synthetic HTTPS tuple")
        name = _host(parsed.hostname)
        port = parsed.port
    except ValueError as error:
        raise EgressDenied("origin port is invalid") from error
    labels = name.split(".")
    if name != "shell.system.hepta.invalid" and not (len(labels) == 5 and labels[2:] == ["apps", "hepta", "invalid"]):
        raise EgressDenied("initiating origin is outside the frozen synthetic origin namespace")
    normalized = f"https://{name}"
    if port is not None or value != normalized:
        raise EgressDenied("initiating origin must be a canonical port-free tuple")
    return normalized


@dataclass(frozen=True)
class ApprovedHost:
    hostname: str
    port: int = 443

    def __post_init__(self):
        _external_host(self.hostname)
        _port(self.port)


@dataclass(frozen=True)
class ApprovedResolver:
    address: str
    tls_hostname: str
    ca_pem: bytes
    port: int = 853

    def __post_init__(self):
        _external_host(self.tls_hostname)
        _port(self.port)
        _ca(self.ca_pem)
        try:
            if "%" in self.address or str(ipaddress.ip_address(self.address)) != self.address:
                raise EgressDenied("resolver address is not canonical")
        except (ValueError, TypeError) as error:
            raise EgressDenied("approved resolver address is malformed") from error


def _ca(data: bytes) -> None:
    if type(data) is not bytes or not data or len(data) > MAX_CA_BYTES:
        raise EgressDenied("explicit approved CA roots are empty or over limit")


@dataclass(frozen=True)
class EgressConfiguration:
    hosts: tuple[ApprovedHost, ...] = ()
    initiating_origins: frozenset[str] = frozenset()
    resolver: ApprovedResolver | None = None
    ca_pem: bytes | None = None

    def __post_init__(self):
        _configuration(self.hosts, self.initiating_origins, self.resolver, self.ca_pem)
        if self.resolver is not None:
            public_address(self.resolver.address)


@dataclass(frozen=True)
class QualificationProfile:
    """Explicit loopback-only test profile; never accepted as production config."""
    hosts: tuple[ApprovedHost, ...]
    initiating_origins: frozenset[str]
    resolver: ApprovedResolver
    ca_pem: bytes
    loopback_addresses: frozenset[str]

    def __post_init__(self):
        _configuration(self.hosts, self.initiating_origins, self.resolver, self.ca_pem)
        if type(self.loopback_addresses) is not frozenset or not self.loopback_addresses or len(self.loopback_addresses) > 2:
            raise EgressDenied("qualification addresses must be explicit and bounded")
        for value in self.loopback_addresses:
            try:
                address = ipaddress.ip_address(value)
            except ValueError as error:
                raise EgressDenied("qualification address is invalid") from error
            if value not in {"127.0.0.1", "::1"} or str(address) != value or not address.is_loopback:
                raise EgressDenied("qualification permits only reviewed localhost literals")
        if self.resolver.address not in self.loopback_addresses:
            raise EgressDenied("qualification resolver is not an approved loopback endpoint")


def _configuration(hosts, origins, resolver, ca):
    if type(hosts) is not tuple or len(hosts) > MAX_HOSTS or any(type(item) is not ApprovedHost for item in hosts) or len(set(hosts)) != len(hosts):
        raise EgressDenied("approved host set is not a bounded exact configuration")
    if type(origins) is not frozenset or len(origins) > MAX_HOSTS:
        raise EgressDenied("approved initiating-origin set is invalid")
    for origin in origins:
        _origin(origin)
    if resolver is not None and type(resolver) is not ApprovedResolver:
        raise EgressDenied("approved resolver configuration is invalid")
    if ca is not None:
        _ca(ca)
    if hosts and (not origins or resolver is None or ca is None):
        raise EgressDenied("enabled egress requires explicit origins, resolver and certificate roots")


@dataclass(frozen=True)
class SessionBinding:
    session_id: str
    generation: int
    initiating_origin: str

    def __post_init__(self):
        if type(self.session_id) is not str or _ID.fullmatch(self.session_id) is None or type(self.generation) is not int or not 1 <= self.generation < 1 << 63:
            raise EgressDenied("session binding is invalid")
        _origin(self.initiating_origin)


@dataclass(frozen=True)
class ObservationPermit:
    operation_id: str
    initial_url: str
    hosts: frozenset[ApprovedHost]
    session: SessionBinding
    epoch: int
    _issuer: object


@dataclass(frozen=True)
class ConnectionIdentity:
    session_id: str
    session_generation: int
    initiating_origin: str
    url_sha256: str
    host: ApprovedHost
    dns_answers: tuple[str, ...]
    connected_peer: str
    certificate_sha256: str
    resolver_peer: str
    resolver_certificate_sha256: str
    trust_policy_sha256: str


@dataclass(frozen=True)
class HopReceipt:
    connection: ConnectionIdentity
    status: int
    body_bytes: int


@dataclass(frozen=True)
class ObservationResponse:
    operation_id: str
    body: bytes
    body_sha256: str
    headers: tuple[tuple[str, str], ...]
    hops: tuple[HopReceipt, ...]
    qualification_only: bool
    browser_namespace_enforced: bool = False
    external_mutation_enabled: bool = False


class CancellationToken:
    def __init__(self):
        self._event = threading.Event()

    def cancel(self):
        self._event.set()

    @property
    def cancelled(self):
        return self._event.is_set()


class _Budget:
    def __init__(self, seconds, cancellation, validate, clock):
        if type(seconds) not in {int, float} or not math.isfinite(seconds) or not 0.01 <= seconds <= 30:
            raise EgressDenied("operation deadline must be finite and between 0.01 and 30 seconds")
        if type(cancellation) is not CancellationToken:
            raise EgressDenied("explicit cancellation token is required")
        self.deadline = clock() + seconds
        self.cancellation, self.validate, self.clock = cancellation, validate, clock
        self.attempted: ConnectionIdentity | None = None

    def check(self):
        self.validate()
        if self.cancellation.cancelled:
            raise EgressCancelled("operation cancelled")
        remaining = self.deadline - self.clock()
        if remaining <= 0:
            raise EgressDeadlineExceeded("whole-operation deadline expired")
        return remaining

    def wait(self, stream, writable=False):
        timeout = min(POLL_SECONDS, self.check())
        select.select([] if writable else [stream], [stream] if writable else [], [], timeout)
        self.check()


@dataclass(frozen=True)
class _Target:
    url: str
    host: ApprovedHost
    path: str


@dataclass(frozen=True)
class _Resolution:
    answers: tuple[str, ...]
    resolver_peer: str
    resolver_certificate_sha256: str


def _target(url: str) -> _Target:
    if type(url) is not str or not 0 < len(url) <= MAX_URL_BYTES or any(ord(c) <= 32 or ord(c) >= 127 for c in url) or "\\" in url or _BAD_ESCAPE.search(url):
        raise EgressDenied("URL is not a bounded strict ASCII HTTPS target")
    try:
        value = urlsplit(url)
        if value.scheme != "https" or value.username is not None or value.password is not None or "#" in url:
            raise EgressDenied("only credential-free fragment-free HTTPS is supported")
        host = ApprovedHost(_host(value.hostname), value.port or 443)
    except ValueError as error:
        raise EgressDenied("HTTPS target is malformed") from error
    path = (value.path or "/") + ("?" + value.query if value.query else "")
    authority = host.hostname + (f":{host.port}" if host.port != 443 else "")
    canonical = f"https://{authority}{path}"
    if value.netloc != authority or not path.startswith("/"):
        raise EgressDenied("HTTPS authority is not canonical")
    return _Target(canonical, host, path)


def _context(ca: bytes, protocol: str) -> ssl.SSLContext:
    _ca(ca)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    try:
        context.load_verify_locations(cadata=ca.decode("ascii", "strict"))
    except (UnicodeError, ssl.SSLError) as error:
        raise EgressDenied("explicit certificate roots are invalid") from error
    context.set_alpn_protocols([protocol])
    return context


def _peer(stream, expected, port):
    actual = stream.getpeername()
    if "%" in actual[0] or str(ipaddress.ip_address(actual[0])) != expected or actual[1] != port or (len(actual) == 4 and actual[3] != 0):
        raise EgressDenied("connected peer does not match the approved resolved address")


def _tls(address: str, port: int, name: str, context: ssl.SSLContext, budget: _Budget, protocol: str):
    budget.check()
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    raw = socket.socket(family, socket.SOCK_STREAM, socket.IPPROTO_TCP)
    stream = raw
    try:
        raw.setblocking(False)
        endpoint = (address, port, 0, 0) if family == socket.AF_INET6 else (address, port)
        result = raw.connect_ex(endpoint)
        if result not in {0, errno.EINPROGRESS, errno.EALREADY, errno.EWOULDBLOCK}:
            raise EgressDenied("approved endpoint connect was refused")
        while True:
            budget.wait(raw, writable=True)
            error = raw.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
            if error:
                raise EgressDenied("approved endpoint connect failed")
            try:
                _peer(raw, address, port)
                break
            except OSError:
                continue
        stream = context.wrap_socket(raw, server_hostname=name, do_handshake_on_connect=False)
        stream.setblocking(False)
        while True:
            budget.check()
            try:
                stream.do_handshake()
                break
            except ssl.SSLWantReadError:
                budget.wait(stream)
            except ssl.SSLWantWriteError:
                budget.wait(stream, writable=True)
        _peer(stream, address, port)
        if stream.selected_alpn_protocol() not in {None, protocol} or not stream.getpeercert(binary_form=True):
            raise EgressDenied("TLS protocol or certificate identity is unsupported")
        return stream
    except BaseException:
        stream.close()
        if stream is not raw:
            raw.close()
        raise


def _send(stream, data: bytes, budget: _Budget):
    offset = 0
    while offset < len(data):
        budget.check()
        try:
            count = stream.send(data[offset:])
            if count <= 0:
                raise EgressDenied("TLS send made no progress")
            offset += count
        except (ssl.SSLWantWriteError, BlockingIOError):
            budget.wait(stream, writable=True)
        except ssl.SSLWantReadError:
            budget.wait(stream)


def _receive(stream, size, budget):
    while True:
        budget.check()
        try:
            return stream.recv(size)
        except (ssl.SSLWantReadError, BlockingIOError):
            budget.wait(stream)
        except ssl.SSLWantWriteError:
            budget.wait(stream, writable=True)


def _exact(stream, size, budget):
    result = bytearray()
    while len(result) < size:
        chunk = _receive(stream, size - len(result), budget)
        if not chunk:
            raise EgressDenied("TLS response was truncated")
        result.extend(chunk)
    return bytes(result)


def _dns_name(data: bytes, offset: int):
    position, end, visited, labels = offset, None, set(), []
    for _ in range(128):
        if position >= len(data) or position in visited:
            raise EgressDenied("DNS name is truncated or cyclic")
        visited.add(position)
        length = data[position]
        if length & 0xC0 == 0xC0:
            if position + 1 >= len(data):
                raise EgressDenied("DNS compression pointer is truncated")
            pointer = ((length & 0x3F) << 8) | data[position + 1]
            if pointer >= position:
                raise EgressDenied("DNS compression must point backwards")
            if end is None:
                end = position + 2
            position = pointer
            continue
        if length & 0xC0:
            raise EgressDenied("DNS label encoding is unsupported")
        position += 1
        if length == 0:
            return ".".join(labels), end if end is not None else position
        if length > 63 or position + length > len(data):
            raise EgressDenied("DNS label is truncated or over limit")
        try:
            label = data[position:position + length].decode("ascii").lower()
        except UnicodeError as error:
            raise EgressDenied("DNS label is not ASCII") from error
        if _LABEL.fullmatch(label) is None:
            raise EgressDenied("DNS label is malformed")
        labels.append(label)
        if sum(map(len, labels)) + len(labels) - 1 > 253:
            raise EgressDenied("DNS name is over limit")
        position += length
    raise EgressDenied("DNS name exceeded its traversal bound")


def _dns_response(data, query_id, host, query_type, address_policy):
    if len(data) < 12 or len(data) > MAX_DNS_BYTES:
        raise EgressDenied("DNS packet size is invalid")
    identity, flags, questions, answers, authority, additional = struct.unpack_from("!6H", data)
    if identity != query_id or flags & 0x8000 == 0 or flags & 0x784F or flags & 0x0200 or questions != 1 or answers + authority + additional > MAX_DNS_RECORDS:
        raise EgressDenied("DNS response identity, status or count is invalid")
    name, offset = _dns_name(data, 12)
    if offset + 4 > len(data) or name != host or struct.unpack_from("!2H", data, offset) != (query_type, 1):
        raise EgressDenied("DNS question does not bind the approved host")
    offset += 4
    result = []
    for index in range(answers + authority + additional):
        owner, offset = _dns_name(data, offset)
        if offset + 10 > len(data):
            raise EgressDenied("DNS record header is truncated")
        record_type, record_class, _, length = struct.unpack_from("!2HIH", data, offset)
        offset += 10
        if offset + length > len(data) or record_class != 1:
            raise EgressDenied("DNS record length or class is invalid")
        if record_type in {1, 28}:
            if length != (4 if record_type == 1 else 16):
                raise EgressDenied("DNS address encoding has the wrong length")
            address = address_policy(str(ipaddress.ip_address(data[offset:offset + length])))
            if index < answers:
                if owner != host or record_type != query_type:
                    raise EgressDenied("DNS address answer is not bound to this question")
                result.append(address)
        elif index < answers:
            raise EgressDenied("DNS aliases and non-address answers are unsupported")
        offset += length
    if offset != len(data):
        raise EgressDenied("DNS packet contains unparsed trailing bytes")
    return result


def _resolve(host, resolver, context, budget, address_policy):
    address_policy(resolver.address)
    stream = _tls(resolver.address, resolver.port, resolver.tls_hostname, context, budget, "dot")
    try:
        encoded = b"".join(bytes([len(label)]) + label.encode("ascii") for label in host.split(".")) + b"\0"
        answers = []
        for query_type in (1, 28):
            budget.check()
            query_id = secrets.randbelow(65536)
            query = struct.pack("!6H", query_id, 0x0100, 1, 0, 0, 0) + encoded + struct.pack("!2H", query_type, 1)
            _send(stream, struct.pack("!H", len(query)) + query, budget)
            length = struct.unpack("!H", _exact(stream, 2, budget))[0]
            if not 12 <= length <= MAX_DNS_BYTES:
                raise EgressDenied("DNS-over-TLS response is over limit")
            answers.extend(_dns_response(_exact(stream, length, budget), query_id, host, query_type, address_policy))
        if not answers or len(answers) > MAX_DNS_RECORDS:
            raise EgressDenied("approved resolver returned no bounded usable addresses")
        _peer(stream, resolver.address, resolver.port)
        budget.check()
        return _Resolution(tuple(sorted(set(answers), key=lambda value: (ipaddress.ip_address(value).version, ipaddress.ip_address(value).packed))),
                           resolver.address, hashlib.sha256(stream.getpeercert(binary_form=True)).hexdigest())
    finally:
        stream.close()


def _response(stream, budget):
    data = bytearray()
    while True:
        split = data.find(b"\r\n\r\n")
        if split >= 0:
            if split + 4 > MAX_HEADER_BYTES:
                raise EgressDenied("HTTPS headers exceed their byte bound")
            break
        if len(data) > MAX_HEADER_BYTES:
            raise EgressDenied("HTTPS headers exceed their byte bound")
        chunk = _receive(stream, 4096, budget)
        if not chunk:
            raise EgressDenied("HTTPS headers are truncated")
        data.extend(chunk)
    try:
        lines = bytes(data[:split]).decode("ascii", "strict").split("\r\n")
    except UnicodeError as error:
        raise EgressDenied("HTTPS headers are not ASCII") from error
    if re.fullmatch(r"HTTP/1\.1 [1-5][0-9]{2} [\x20-\x7e]*", lines[0]) is None or len(lines) - 1 > MAX_HEADERS:
        raise EgressDenied("HTTPS status line or header count is unsupported")
    status = int(lines[0][9:12])
    headers = {}
    for line in lines[1:]:
        name, separator, value = line.partition(":")
        if not separator or _HEADER.fullmatch(name) is None or any(ord(c) < 32 or ord(c) > 126 for c in value):
            raise EgressDenied("HTTPS header is malformed or folded")
        name, value = name.lower(), value.strip()
        if name in headers:
            raise EgressDenied("duplicate HTTPS headers are forbidden")
        headers[name] = value
    if any(name in headers for name in ("transfer-encoding", "set-cookie", "content-disposition", "upgrade")) or headers.get("content-encoding", "identity").lower() != "identity":
        raise EgressDenied("streaming, cookies, downloads, upgrade or compressed content is unsupported")
    length = headers.get("content-length", "")
    if re.fullmatch(r"0|[1-9][0-9]{0,6}", length) is None or int(length) > MAX_BODY_BYTES:
        raise EgressDenied("one exact bounded Content-Length is required")
    size = int(length)
    body = bytearray(data[split + 4:])
    if len(body) > size:
        raise EgressDenied("HTTPS response exceeds its declared length")
    while len(body) < size:
        chunk = _receive(stream, min(65536, size - len(body)), budget)
        if not chunk:
            raise EgressDenied("HTTPS response body is truncated")
        body.extend(chunk)
    return status, headers, bytes(body)


class ControlledEgress:
    def __init__(self, configuration: EgressConfiguration = EgressConfiguration()):
        if type(configuration) is not EgressConfiguration:
            raise EgressDenied("production client requires exact production configuration")
        self._initialize(configuration, None)

    def _initialize(self, configuration, qualification):
        self._owner_pid = os.getpid()
        self._clock_broken = False
        self._last_monotonic = time.monotonic()
        if not math.isfinite(self._last_monotonic):
            raise EgressDenied("monotonic operation clock is invalid")
        self._configuration, self._qualification = configuration, qualification
        self._https_context = _context(configuration.ca_pem, "http/1.1") if configuration.ca_pem is not None else None
        self._dns_context = _context(configuration.resolver.ca_pem, "dot") if configuration.resolver is not None else None
        self._issuer = object()
        self._session = None
        self._epoch = 0
        self._permits = {}
        self._active = {}
        self._lock = threading.Lock()
        resolver = configuration.resolver
        policy = {"hosts": sorted((host.hostname, host.port) for host in configuration.hosts),
                  "origins": sorted(configuration.initiating_origins),
                  "ca_sha256": hashlib.sha256(configuration.ca_pem).hexdigest() if configuration.ca_pem else None,
                  "resolver": {"address": resolver.address, "port": resolver.port, "tls_hostname": resolver.tls_hostname,
                               "ca_sha256": hashlib.sha256(resolver.ca_pem).hexdigest()} if resolver else None,
                  "qualification_addresses": sorted(qualification.loopback_addresses) if qualification else None}
        self._policy_sha256 = hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()

    def _owner(self):
        # This check precedes any lock: a fork may inherit a locked mutex.
        if os.getpid() != self._owner_pid:
            raise EgressDenied("egress authority belongs to its creating process")
        if self._clock_broken:
            raise EgressDenied("egress authority has a permanently invalid monotonic clock")

    def _clock(self):
        self._owner()
        with self._lock:
            value = time.monotonic()
            if self._clock_broken or not math.isfinite(value) or value < self._last_monotonic:
                self._clock_broken = True
                self._session = None
                self._permits.clear()
                raise EgressDenied("monotonic clock regressed or became nonfinite; authority revoked")
            self._last_monotonic = value
            return value

    def bind_session(self, session: SessionBinding):
        self._owner()
        if type(session) is not SessionBinding or session.initiating_origin not in self._configuration.initiating_origins:
            raise EgressDenied("session origin is not externally approved")
        with self._lock:
            if self._epoch >= (1 << 63) - 1:
                raise EgressDenied("egress session epoch exhausted")
            self._epoch += 1
            self._session = session
            self._permits.clear()

    def close(self):
        self._owner()
        with self._lock:
            self._session = None
            self._permits.clear()

    def issue_observation_permit(self, session: SessionBinding, url: str, *, redirect_hosts: frozenset[ApprovedHost] = frozenset()) -> ObservationPermit:
        self._owner()
        if type(session) is not SessionBinding:
            raise EgressDenied("an actual bound session is required")
        target = _target(url)
        configured = frozenset(self._configuration.hosts)
        if target.host not in configured or type(redirect_hosts) is not frozenset or any(type(host) is not ApprovedHost for host in redirect_hosts) or not redirect_hosts <= configured:
            raise EgressDenied("observation or redirect host is not externally approved")
        with self._lock:
            if self._session is not session or len(self._permits) >= MAX_PERMITS:
                raise EgressDenied("session is stale or pending permit capacity is full")
            permit = ObservationPermit(secrets.token_hex(32), target.url, redirect_hosts | {target.host}, session, self._epoch, self._issuer)
            self._permits[permit.operation_id] = permit
            return permit

    def _validate(self, permit, session, *, active):
        self._owner()
        with self._lock:
            records = self._active if active else self._permits
            if type(session) is not SessionBinding or self._session is None or type(permit) is not ObservationPermit or permit._issuer is not self._issuer or records.get(permit.operation_id) is not permit or self._session is not session or permit.session is not session or permit.epoch != self._epoch:
                raise EgressDenied("permit, session, origin or issuer is stale or unrelated")

    def _address(self, value):
        if self._qualification is None:
            return public_address(value)
        if type(value) is not str or value not in self._qualification.loopback_addresses:
            raise EgressDenied("qualification network is restricted to its exact loopback set")
        return value

    def observe(self, permit: ObservationPermit, session: SessionBinding, *, timeout_seconds=10,
                cancellation: CancellationToken | None = None, method="GET", resource_class="observation") -> ObservationResponse:
        if type(method) is not str or type(resource_class) is not str or method != "GET" or resource_class != "observation":
            raise EgressDenied("only explicit GET observation is supported; effects and resource protocols are disabled")
        self._validate(permit, session, active=False)
        token = CancellationToken() if cancellation is None else cancellation
        budget = _Budget(timeout_seconds, token, lambda: self._validate(permit, session, active=True), self._clock)
        with self._lock:
            if len(self._active) >= MAX_ACTIVE or self._permits.get(permit.operation_id) is not permit:
                raise EgressDenied("active observation capacity is full or permit was already consumed")
            del self._permits[permit.operation_id]
            self._active[permit.operation_id] = permit
        hops = []
        try:
            target = _target(permit.initial_url)
            visited = set()
            for hop in range(MAX_REDIRECTS + 1):
                budget.check()
                if target.host not in permit.hosts or target.host not in self._configuration.hosts or target.url in visited:
                    raise EgressDenied("redirect escapes its approved scope or repeats a URL")
                visited.add(target.url)
                resolution = _resolve(target.host.hostname, self._configuration.resolver, self._dns_context, budget, self._address)
                answers = resolution.answers
                budget.check()
                address = answers[0]  # One exact connection attempt; no automatic fallback/retry.
                stream = _tls(address, target.host.port, target.host.hostname, self._https_context, budget, "http/1.1")
                try:
                    identity = ConnectionIdentity(session.session_id, session.generation, session.initiating_origin,
                                                  hashlib.sha256(target.url.encode("ascii")).hexdigest(), target.host,
                                                  answers, address, hashlib.sha256(stream.getpeercert(binary_form=True)).hexdigest(),
                                                  resolution.resolver_peer, resolution.resolver_certificate_sha256, self._policy_sha256)
                    budget.check()
                    authority = target.host.hostname + (f":{target.host.port}" if target.host.port != 443 else "")
                    request = (f"GET {target.path} HTTP/1.1\r\nHost: {authority}\r\nConnection: close\r\n"
                               "Accept: text/plain, text/html, application/json\r\nAccept-Encoding: identity\r\n\r\n").encode("ascii")
                    budget.attempted = identity  # Before send, including return-boundary interruptions.
                    _send(stream, request, budget)
                    status, headers, body = _response(stream, budget)
                    _peer(stream, address, target.host.port)
                    budget.check()
                finally:
                    stream.close()
                hops.append(HopReceipt(identity, status, len(body)))
                if status in {301, 302, 303, 307, 308}:
                    if hop == MAX_REDIRECTS or "location" not in headers:
                        raise EgressDenied("redirect limit exceeded or Location absent")
                    location = headers["location"]
                    if not location or any(ord(c) <= 32 or ord(c) >= 127 for c in location) or "\\" in location:
                        raise EgressDenied("redirect Location is malformed")
                    target = _target(urljoin(target.url, location))
                    continue
                if status != 200 or "location" in headers:
                    raise EgressDenied("response status is unsupported; challenges are not bypassed")
                content_type = headers.get("content-type", "").lower()
                if re.fullmatch(r'(?:text/plain|text/html|application/json)(?:;\s*charset\s*=\s*(?:utf-8|us-ascii|"utf-8"|"us-ascii"))?', content_type) is None:
                    raise EgressDenied("response type is unsupported; downloads are disabled")
                return ObservationResponse(permit.operation_id, body, hashlib.sha256(body).hexdigest(), tuple(headers.items()),
                                           tuple(hops), self._qualification is not None)
            raise EgressDenied("redirect bound exhausted")
        except BaseException as error:
            if budget.attempted is not None:
                raise EgressIndeterminate(permit.operation_id, budget.attempted, tuple(hops), error) from error
            if isinstance(error, EgressDenied):
                raise
            if isinstance(error, (OSError, ssl.SSLError)):
                raise EgressDenied("controlled resolver/connect/TLS operation failed") from error
            raise
        finally:
            with self._lock:
                self._active.pop(permit.operation_id, None)


class QualificationEgressClient(ControlledEgress):
    def __init__(self, profile: QualificationProfile):
        if type(profile) is not QualificationProfile:
            raise EgressDenied("explicit qualification profile is required")
        self._initialize(profile, profile)
