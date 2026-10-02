from __future__ import annotations

import hashlib
import gc
import importlib.util
import inspect
import json
import os
import select
import signal
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import weakref
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('controlled_egress', ROOT / 'platform/controlled_egress.py')
eg = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = eg
SPEC.loader.exec_module(eg)
KEYS = None
CA = None
OTHER_CA = None
SERVER_CONTEXT = None
ORIGIN = 'https://test.publisher.apps.hepta.invalid'
ONE = 'one.fixture.test'
TWO = 'two.fixture.test'


def source_line(function, fragment, occurrence=0):
    lines, first = inspect.getsourcelines(function)
    matches = [first + index for index, line in enumerate(lines) if fragment in line]
    return matches[occurrence]


def descriptor_inventory():
    entries = tuple(Path('/proc/self/fd').iterdir())
    values = {}
    for entry in entries:
        try:
            metadata = os.fstat(int(entry.name))
            values[int(entry.name)] = (os.readlink(entry), metadata.st_dev, metadata.st_ino)
        except (FileNotFoundError, OSError):
            # The temporary read_dir descriptor itself has already closed.
            pass
    return values


def setUpModule():
    global KEYS, CA, OTHER_CA, SERVER_CONTEXT
    if not Path('/usr/bin/openssl').is_file():
        raise RuntimeError('real OpenSSL is required; skipped TLS is not qualification')
    KEYS = tempfile.TemporaryDirectory(prefix='controlled-egress-test-only-')
    root = Path(KEYS.name)
    def openssl(*args):
        subprocess.run(['/usr/bin/openssl', *args], cwd=root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    for name in ('ca', 'other'):
        openssl('req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', name + '.key', '-out', name + '.pem', '-days', '1', '-sha256', '-subj', '/CN=Qualification-only', '-addext', 'basicConstraints=critical,CA:TRUE,pathlen:0', '-addext', 'keyUsage=critical,keyCertSign,cRLSign')
    openssl('req', '-newkey', 'rsa:2048', '-nodes', '-keyout', 'server.key', '-out', 'server.csr', '-subj', '/CN=' + ONE)
    (root / 'extensions').write_text('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:one.fixture.test,DNS:two.fixture.test,DNS:resolver.fixture.test\n')
    openssl('x509', '-req', '-in', 'server.csr', '-CA', 'ca.pem', '-CAkey', 'ca.key', '-CAcreateserial', '-out', 'server.pem', '-days', '1', '-sha256', '-extfile', 'extensions')
    CA = (root / 'ca.pem').read_bytes()
    OTHER_CA = (root / 'other.pem').read_bytes()
    SERVER_CONTEXT = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    SERVER_CONTEXT.minimum_version = ssl.TLSVersion.TLSv1_2
    SERVER_CONTEXT.load_cert_chain(str(root / 'server.pem'), str(root / 'server.key'))


def tearDownModule():
    KEYS.cleanup()


def exact(stream, count):
    data = bytearray()
    while len(data) < count:
        chunk = stream.recv(count - len(data))
        if not chunk:
            raise EOFError('fixture connection ended')
        data.extend(chunk)
    return bytes(data)


class LocalTLS:
    def __init__(self, handler, *, address='127.0.0.1', port=0):
        self.handler = handler
        self.stop = threading.Event()
        self.listener = socket.socket(socket.AF_INET6 if ':' in address else socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind((address, port))
        self.listener.listen(8)
        self.listener.settimeout(0.1)
        self.port = self.listener.getsockname()[1]
        self.workers = []
        self.accepted = 0
        self.accepted_event = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        while not self.stop.is_set():
            try:
                raw, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            self.accepted += 1
            self.accepted_event.set()
            worker = threading.Thread(target=self.connection, args=(raw,), daemon=True)
            self.workers.append(worker)
            worker.start()

    def connection(self, raw):
        raw.settimeout(2)
        try:
            with SERVER_CONTEXT.wrap_socket(raw, server_side=True) as stream:
                self.handler(stream)
        except (OSError, ssl.SSLError, EOFError):
            raw.close()

    def close(self):
        self.stop.set()
        self.listener.close()
        self.thread.join(2)
        for worker in self.workers:
            worker.join(2)
            if worker.is_alive():
                raise RuntimeError('qualification fixture worker did not stop')


class Fixture:
    def __init__(self, *, address='127.0.0.1'):
        self.answers = [address]
        self.dns_calls = []
        self.http_calls = []
        self.dns_delay = 0
        self.http_delay = 0
        self.dns_received = threading.Event()
        self.http_received = threading.Event()
        self.response = None
        self.dns_mutator = None
        self.on_http = None
        self.https = LocalTLS(self.http, address=address)
        self.dns = LocalTLS(self.resolve)

    def resolve(self, stream):
        for _ in range(2):
            size = struct.unpack('!H', exact(stream, 2))[0]
            query = exact(stream, size)
            host, offset = eg._dns_name(query, 12)
            kind, klass = struct.unpack_from('!2H', query, offset)
            self.dns_calls.append((host, kind))
            self.dns_received.set()
            if self.dns_delay:
                time.sleep(self.dns_delay)
            records = []
            for text in self.answers:
                address = eg.ipaddress.ip_address(text)
                if (address.version == 4 and kind == 1) or (address.version == 6 and kind == 28):
                    records.append(b'\xc0\x0c' + struct.pack('!2HIH', kind, klass, 30, len(address.packed)) + address.packed)
            packet = struct.pack('!6H', struct.unpack_from('!H', query)[0], 0x8180, 1, len(records), 0, 0) + query[12:] + b''.join(records)
            if self.dns_mutator:
                packet = self.dns_mutator(packet)
            stream.sendall(struct.pack('!H', len(packet)) + packet)

    def http(self, stream):
        data = bytearray()
        while b'\r\n\r\n' not in data and len(data) < eg.MAX_HEADER_BYTES:
            chunk = stream.recv(4096)
            if not chunk:
                return
            data.extend(chunk)
        text = data.decode('ascii')
        path = text.split(' ', 2)[1]
        self.http_calls.append(text)
        self.http_received.set()
        if self.on_http:
            self.on_http(path)
        if self.http_delay:
            time.sleep(self.http_delay)
        response = self.response(path) if callable(self.response) else self.response
        if response is None:
            response = b'HTTP/1.1 200 OK\r\nContent-Length: 5\r\nContent-Type: text/plain; charset=utf-8\r\nConnection: close\r\n\r\nhello'
        stream.sendall(response)

    def profile(self, *, hosts=None, ca=None, resolver_name='resolver.fixture.test'):
        allowed = ('127.0.0.1', '::1')
        return eg.QualificationProfile(tuple(hosts or (eg.ApprovedHost(ONE, self.https.port), eg.ApprovedHost(TWO, self.https.port))),
                                       frozenset({ORIGIN}), eg.ApprovedResolver('127.0.0.1', resolver_name, CA, self.dns.port), CA if ca is None else ca, frozenset(allowed))

    def client(self, **options):
        client = eg.QualificationEgressClient(self.profile(**options))
        session = eg.SessionBinding('session-1', 1, ORIGIN)
        client.bind_session(session)
        return client, session

    def url(self, path='/ok', host=ONE):
        return f'https://{host}:{self.https.port}{path}'

    def close(self):
        self.dns.close()
        self.https.close()


class ControlledEgressTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture()
        self.addCleanup(self.fixture.close)

    def fetch(self, client, session, path='/ok', *, host=ONE, redirects=frozenset(), **options):
        permit = client.issue_observation_permit(session, self.fixture.url(path, host), redirect_hosts=redirects)
        return client.observe(permit, session, **options)

    def test_default_empty_and_production_loopback_config_cannot_open_socket(self):
        with patch.object(eg.socket, 'socket', side_effect=AssertionError('disabled egress must not create a socket')):
            client = eg.ControlledEgress()
            with self.assertRaises(eg.EgressDenied):
                client.bind_session(eg.SessionBinding('s', 1, ORIGIN))
            with self.assertRaises(eg.EgressDenied):
                client.issue_observation_permit(eg.SessionBinding('s', 1, ORIGIN), 'https://example.com/')
            with self.assertRaises(eg.EgressDenied):
                eg.EgressConfiguration((eg.ApprovedHost(ONE),), frozenset({ORIGIN}), eg.ApprovedResolver('127.0.0.1', 'resolver.fixture.test', CA), CA)
            with self.assertRaises(eg.EgressDenied):
                eg.ControlledEgress(self.fixture.profile())
        self.assertEqual(self.fixture.dns_calls, [])

    def test_real_dns_tcp_tls_response_and_immutable_connection_receipt(self):
        client, session = self.fixture.client()
        response = self.fetch(client, session)
        self.assertEqual(response.body, b'hello')
        self.assertEqual(response.body_sha256, hashlib.sha256(b'hello').hexdigest())
        self.assertEqual(self.fixture.dns_calls, [(ONE, 1), (ONE, 28)])
        identity = response.hops[0].connection
        self.assertEqual(identity.connected_peer, '127.0.0.1')
        self.assertEqual(identity.dns_answers, ('127.0.0.1',))
        self.assertEqual(identity.session_id, session.session_id)
        self.assertEqual(identity.initiating_origin, ORIGIN)
        self.assertEqual(len(identity.certificate_sha256), 64)
        self.assertEqual(identity.resolver_peer, '127.0.0.1')
        self.assertEqual(identity.resolver_certificate_sha256, identity.certificate_sha256)
        self.assertEqual(len(identity.trust_policy_sha256), 64)
        self.assertTrue(response.qualification_only)
        self.assertFalse(response.browser_namespace_enforced)
        self.assertFalse(response.external_mutation_enabled)
        self.assertEqual(len(self.fixture.http_calls), 1)

    def test_public_ipv4_ipv6_special_ranges_mapped_and_metadata_policy(self):
        for value in ('8.8.8.8', '93.184.216.34', '2001:4860:4860::8888', '2606:4700:4700::1111'):
            self.assertEqual(eg.public_address(value), value)
        forbidden = ('0.0.0.0', '10.0.0.1', '100.64.0.1', '127.0.0.1', '169.254.169.254', '172.16.0.1', '192.0.0.9',
                     '192.168.1.1', '192.0.2.1', '198.18.0.1', '198.51.100.1', '203.0.113.1', '224.0.0.1', '255.255.255.255',
                     '::', '::1', '::ffff:8.8.8.8', '::ffff:127.0.0.1', '64:ff9b::808:808', '2002:808:808::1',
                     '2001::1', '2001:db8::1', '3fff::1', 'fc00::1', 'fd00:ec2::254', 'fe80::1', 'fe80::1%eth0', 'ff02::1')
        for value in forbidden:
            with self.subTest(value=value), self.assertRaises(eg.EgressDenied):
                eg.public_address(value)

    def test_mixed_answers_private_ipv6_mapped_and_rebinding_never_connect_to_target(self):
        for answers in (['127.0.0.1', '10.0.0.1'], ['127.0.0.1', '::ffff:127.0.0.1'], ['127.0.0.1', 'fd00:ec2::254']):
            client, session = self.fixture.client()
            self.fixture.answers = answers
            with self.subTest(answers=answers), self.assertRaises(eg.EgressDenied):
                self.fetch(client, session)
            self.assertEqual(self.fixture.http_calls, [])
        self.fixture.answers = ['127.0.0.1']
        self.fixture.response = lambda path: (f'HTTP/1.1 302 Found\r\nLocation: {self.fixture.url("/next")}\r\nContent-Length: 0\r\n\r\n').encode()
        self.fixture.on_http = lambda path: setattr(self.fixture, 'answers', ['10.0.0.1'])
        client, session = self.fixture.client()
        with self.assertRaises(eg.EgressIndeterminate) as caught:
            self.fetch(client, session)
        self.assertIsInstance(caught.exception.cause, eg.EgressDenied)
        self.assertEqual(len(self.fixture.http_calls), 1)
        self.assertEqual(caught.exception.connection.connected_peer, '127.0.0.1')

    def test_real_bad_certificate_roots_and_hostname_fail_before_http_request(self):
        client, session = self.fixture.client(ca=OTHER_CA)
        with self.assertRaises(eg.EgressDenied):
            self.fetch(client, session)
        hosts = (eg.ApprovedHost('wrong.fixture.test', self.fixture.https.port),)
        client, session = self.fixture.client(hosts=hosts)
        with self.assertRaises(eg.EgressDenied):
            self.fetch(client, session, host='wrong.fixture.test')
        client, session = self.fixture.client(resolver_name='wrong-resolver.fixture.test')
        with self.assertRaises(eg.EgressDenied):
            self.fetch(client, session)
        self.assertEqual(self.fixture.http_calls, [])

    def test_actual_peer_mismatch_is_checked_before_tls_or_request(self):
        alternative = LocalTLS(lambda stream: None, address='127.0.0.2', port=self.fixture.https.port)
        self.addCleanup(alternative.close)
        original = socket.socket
        target_port = self.fixture.https.port
        class RedirectedSocket(original):
            def connect_ex(self, address):
                if address[1] == target_port:
                    address = ('127.0.0.2', address[1])
                return super().connect_ex(address)
        client, session = self.fixture.client()
        with patch.object(eg.socket, 'socket', RedirectedSocket), self.assertRaisesRegex(eg.EgressDenied, 'connected peer'):
            self.fetch(client, session)
        self.assertEqual(self.fixture.http_calls, [])
        self.assertTrue(alternative.accepted_event.wait(1))

    def test_redirect_rechecks_host_session_permit_dns_peer_and_tls(self):
        self.fixture.response = lambda path: ((f'HTTP/1.1 302 Found\r\nLocation: {self.fixture.url("/ok", TWO)}\r\nContent-Length: 0\r\n\r\n').encode() if path == '/redirect' else None)
        # Explicitly supplied fixture default for final response.
        base = self.fixture.response
        self.fixture.response = lambda path: base(path) or b'HTTP/1.1 200 OK\r\nContent-Length: 5\r\nContent-Type: text/plain\r\n\r\nhello'
        client, session = self.fixture.client()
        with self.assertRaises(eg.EgressIndeterminate):
            self.fetch(client, session, '/redirect')
        self.assertEqual(len(self.fixture.http_calls), 1)
        self.assertFalse(any(host == TWO for host, _ in self.fixture.dns_calls))
        self.fixture.http_calls.clear()
        self.fixture.dns_calls.clear()
        client, session = self.fixture.client()
        response = self.fetch(client, session, '/redirect', redirects=frozenset({eg.ApprovedHost(TWO, self.fixture.https.port)}))
        self.assertEqual([hop.connection.host.hostname for hop in response.hops], [ONE, TWO])
        self.assertEqual(self.fixture.dns_calls, [(ONE, 1), (ONE, 28), (TWO, 1), (TWO, 28)])
        self.assertEqual(len(self.fixture.http_calls), 2)

    def test_redirect_downgrade_literal_metadata_loop_and_limit_refused(self):
        for location in ('http://one.fixture.test/', 'https://169.254.169.254/', 'https://[::1]/', self.fixture.url('/ok')):
            self.fixture.response = (f'HTTP/1.1 302 Found\r\nLocation: {location}\r\nContent-Length: 0\r\n\r\n').encode()
            client, session = self.fixture.client()
            with self.subTest(location=location), self.assertRaises(eg.EgressIndeterminate):
                self.fetch(client, session)
        calls_before = len(self.fixture.http_calls)
        self.fixture.response = lambda path: (f'HTTP/1.1 302 Found\r\nLocation: /{int(path[1:]) + 1}\r\nContent-Length: 0\r\n\r\n').encode()
        client, session = self.fixture.client()
        with self.assertRaises(eg.EgressIndeterminate):
            self.fetch(client, session, '/0')
        self.assertEqual(len(self.fixture.http_calls) - calls_before, eg.MAX_REDIRECTS + 1)

    def test_copied_cross_client_stale_origin_session_and_permit_reuse_refused(self):
        client, session = self.fixture.client()
        permit = client.issue_observation_permit(session, self.fixture.url())
        for bad in (replace(permit),):
            with self.assertRaises(eg.EgressDenied):
                client.observe(bad, session)
        other, _ = self.fixture.client()
        with self.assertRaises(eg.EgressDenied):
            other.observe(permit, session)
        with self.assertRaises(eg.EgressDenied):
            client.observe(permit, replace(session))
        client.observe(permit, session)
        with self.assertRaises(eg.EgressDenied):
            client.observe(permit, session)
        permit = client.issue_observation_permit(session, self.fixture.url())
        client.bind_session(eg.SessionBinding('new', 2, ORIGIN))
        with self.assertRaises(eg.EgressDenied):
            client.observe(permit, session)
        self.assertEqual(len(self.fixture.http_calls), 1)

    def test_missing_session_never_mints_a_permit_or_resolves(self):
        client = eg.QualificationEgressClient(self.fixture.profile())
        with self.assertRaises(eg.EgressDenied):
            client.issue_observation_permit(None, self.fixture.url())
        with self.assertRaises(eg.EgressDenied):
            client.issue_observation_permit(eg.SessionBinding('unbound', 1, ORIGIN), self.fixture.url())
        with self.assertRaises(eg.EgressDenied):
            client.bind_session(eg.SessionBinding('wrong-origin', 1, 'https://attacker.publisher.apps.hepta.invalid'))
        self.assertEqual(self.fixture.dns_calls, [])

    def test_frozen_synthetic_https_origins_and_no_public_dns_fallback(self):
        for origin in (ORIGIN, 'https://shell.system.hepta.invalid'):
            self.assertEqual(eg.SessionBinding('s', 1, origin).initiating_origin, origin)
        forbidden = ('hepta-app://publisher.app', 'http://test.publisher.apps.hepta.invalid',
                     'https://example.com', 'https://shell.system.hepta.invalid:443',
                     ORIGIN + '/', ORIGIN + '?', ORIGIN + '#', 'https://u@' + ORIGIN[8:],
                     'https://shared.apps.hepta.invalid', 'https://other.system.hepta.invalid',
                     'https://x.test.publisher.apps.hepta.invalid', 'https://TEST.publisher.apps.hepta.invalid')
        for origin in forbidden:
            with self.subTest(origin=origin), self.assertRaises(eg.EgressDenied):
                eg.SessionBinding('s', 1, origin)
        client, session = self.fixture.client()
        for host in ('hepta.invalid', 'shell.system.hepta.invalid', 'test.publisher.apps.hepta.invalid', 'anything.hepta.invalid'):
            with self.subTest(host=host), self.assertRaises(eg.EgressDenied):
                eg.ApprovedHost(host)
            with self.subTest(host=host), self.assertRaises(eg.EgressDenied):
                client.issue_observation_permit(session, 'https://' + host + '/')
            with self.subTest(host=host), self.assertRaises(eg.EgressDenied):
                eg.ApprovedResolver('127.0.0.1', host, CA)
        self.assertEqual(self.fixture.dns_calls, [])

    def test_real_fork_cannot_reuse_inherited_permit_session_or_cancel_snapshot(self):
        client, session = self.fixture.client()
        permit = client.issue_observation_permit(session, self.fixture.url())
        cancellation = eg.CancellationToken()
        ready_read, ready_write = os.pipe()
        result_read, result_write = os.pipe()
        pid = os.fork()
        if pid == 0:
            os.close(ready_write)
            os.close(result_read)
            try:
                if os.read(ready_read, 1) != b'g':
                    os._exit(2)
                calls = (lambda: client.observe(permit, session, cancellation=cancellation),
                         lambda: client.issue_observation_permit(session, self.fixture.url()),
                         lambda: client.bind_session(session), lambda: client.close(),
                         lambda: client._validate(permit, session, active=False))
                results = []
                with patch.object(eg.socket, 'socket', side_effect=AssertionError('fork inherited authority opened a socket')):
                    for call in calls:
                        try:
                            call()
                        except eg.EgressDenied as error:
                            results.append('creating process' in str(error))
                        else:
                            results.append(False)
                os.write(result_write, json.dumps(results).encode('ascii'))
                os._exit(0)
            except BaseException:
                os._exit(3)
        os.close(ready_read)
        os.close(result_write)
        try:
            client.close()
            client.bind_session(eg.SessionBinding('replacement', 2, ORIGIN))
            cancellation.cancel()
            os.write(ready_write, b'g')
            self.assertTrue(select.select([result_read], [], [], 3)[0], 'fork regression did not terminate')
            self.assertEqual(json.loads(os.read(result_read, 1024)), [True] * 5)
        finally:
            os.close(ready_write)
            os.close(result_read)
            # Reap even a failed child without waiting on a copied process lock.
            waited, status = os.waitpid(pid, os.WNOHANG)
            if not waited:
                os.kill(pid, signal.SIGKILL)
                _, status = os.waitpid(pid, 0)
        self.assertEqual(self.fixture.dns_calls, [])

    def test_clock_regression_or_nonfinite_time_permanently_revokes_authority(self):
        for bad in ('regression', float('nan'), float('inf')):
            client, session = self.fixture.client()
            permit = client.issue_observation_permit(session, self.fixture.url())
            value = client._last_monotonic - 1 if bad == 'regression' else bad
            with self.subTest(clock=bad), patch.object(eg.time, 'monotonic', return_value=value), self.assertRaisesRegex(eg.EgressDenied, 'clock'):
                client.observe(permit, session)
            # A later apparently healthy clock never repairs an authority owner.
            with self.assertRaisesRegex(eg.EgressDenied, 'clock'):
                client.bind_session(session)
            with self.assertRaisesRegex(eg.EgressDenied, 'clock'):
                client.issue_observation_permit(session, self.fixture.url())
            with self.assertRaisesRegex(eg.EgressDenied, 'clock'):
                client.observe(permit, session)
        self.assertEqual(self.fixture.dns_calls, [])

    def test_real_request_send_return_interrupt_is_indeterminate_and_single_use(self):
        original_send = eg._send
        for kind in (KeyboardInterrupt, SystemExit):
            client, session = self.fixture.client()
            permit = client.issue_observation_permit(session, self.fixture.url())
            def send_then_interrupt(stream, data, budget):
                original_send(stream, data, budget)
                if data.startswith(b'GET '):
                    raise kind('request sent before return')
            with patch.object(eg, '_send', side_effect=send_then_interrupt), self.subTest(kind=kind.__name__), self.assertRaises(eg.EgressIndeterminate) as caught:
                client.observe(permit, session)
            self.assertIsInstance(caught.exception.cause, kind)
            self.assertEqual(caught.exception.connection.connected_peer, '127.0.0.1')
            with self.assertRaises(eg.EgressDenied):
                client.observe(permit, session)
        self.assertTrue(self.fixture.http_received.wait(1))

    def test_actual_response_cleanup_trace_interrupts_preserve_facts_and_release_mutex(self):
        retire = eg.ControlledEgress._retire_observation
        observe = eg.ControlledEgress.observe
        acquire, close = eg._PolicyLease.acquire, eg._PolicyLease.close
        cases = (
            ('before-cleanup-call', observe, 'line', source_line(observe, 'self._retire_observation('), True),
            ('before-acquire', retire, 'line', source_line(retire, 'lease.acquire()'), True),
            ('actual-acquire-return', acquire, 'return', None, True),
            ('before-pop-with-real-lock-held', retire, 'line', source_line(retire, 'self._active.pop('), True),
            ('after-pop-before-release', retire, 'line', source_line(retire, 'lease.close()'), False),
            ('release-helper-entry', close, 'call', None, False),
            ('before-ownership-detach-and-release', close, 'line', source_line(close, 'self._held = False;'), False),
            ('actual-release-return', close, 'return', None, False),
            ('cleanup-helper-return', retire, 'return', None, False),
        )
        for name, function, event_kind, line, retained in cases:
            with self.subTest(boundary=name):
                client, session = self.fixture.client()
                permit = client.issue_observation_permit(session, self.fixture.url())
                before_http, before_dns = len(self.fixture.http_calls), len(self.fixture.dns_calls)
                snapshot = {}
                def trace(frame, event, value):
                    if not snapshot and frame.f_code is function.__code__ and event == event_kind and (line is None or frame.f_lineno == line):
                        caller = frame
                        while caller is not None and caller.f_code is not observe.__code__:
                            caller = caller.f_back
                        if caller is None or caller.f_locals.get('self') is not client or caller.f_locals.get('permit') is not permit:
                            return trace
                        if function is close and frame.f_locals['self'] is not caller.f_locals.get('cleanup_lease'):
                            return trace  # GC of a previous observer is not this lease.
                        if caller.f_locals['budget'].attempted is None:
                            return trace  # Admission uses the same empty lease.
                        snapshot.update(body=caller.f_locals['body'], status=caller.f_locals['status'],
                                        identity=caller.f_locals['budget'].attempted,
                                        stream_fd=caller.f_locals['stream'].fileno(),
                                        locked=client._lock.locked())
                        raise KeyboardInterrupt(name)
                    return trace
                previous = sys.gettrace()
                try:
                    sys.settrace(trace)
                    with self.assertRaises(eg.EgressIndeterminate) as caught:
                        client.observe(permit, session)
                finally:
                    sys.settrace(previous)
                error = caught.exception
                self.assertEqual(snapshot['body'], b'hello')
                self.assertEqual(snapshot['status'], 200)
                self.assertEqual(snapshot['stream_fd'], -1)
                self.assertEqual(error.operation_id, permit.operation_id)
                self.assertIs(error.connection, snapshot['identity'])
                self.assertEqual(error.connection.connected_peer, '127.0.0.1')
                self.assertEqual(error.hops, (eg.HopReceipt(error.connection, 200, 5),))
                self.assertIsInstance(error.cause, KeyboardInterrupt)
                self.assertFalse(client._lock.locked(), 'an actual cleanup acquisition was lost')
                self.assertEqual(permit.operation_id in client._active, retained)
                self.assertTrue(client._cleanup_broken)
                for call in (lambda: client.observe(permit, session), lambda: client.bind_session(session),
                             lambda: client.issue_observation_permit(session, self.fixture.url()), client.close):
                    with self.assertRaisesRegex(eg.EgressDenied, 'quarantined'):
                        call()
                self.assertEqual(len(self.fixture.http_calls) - before_http, 1)
                self.assertEqual(len(self.fixture.dns_calls) - before_dns, 2)

    def test_pre_send_cleanup_interrupt_is_quarantined_refusal_without_invented_connection(self):
        client, session = self.fixture.client()
        permit = client.issue_observation_permit(session, self.fixture.url())
        self.fixture.dns_mutator = lambda data: data + b'trailer'
        line = source_line(eg.ControlledEgress.observe, 'self._retire_observation(')
        fired = []
        def trace(frame, event, value):
            if not fired and frame.f_code is eg.ControlledEgress.observe.__code__ and event == 'line' and frame.f_lineno == line:
                fired.append(frame.f_locals['budget'].attempted)
                raise KeyboardInterrupt('cleanup after actual malformed DoT response')
            return trace
        previous = sys.gettrace()
        try:
            sys.settrace(trace)
            with self.assertRaisesRegex(eg.EgressDenied, 'quarantined') as caught:
                client.observe(permit, session)
        finally:
            sys.settrace(previous)
        self.assertEqual(fired, [None])
        self.assertNotIsInstance(caught.exception, eg.EgressIndeterminate)
        self.assertIsInstance(caught.exception.__cause__, KeyboardInterrupt)
        self.assertIs(client._active[permit.operation_id], permit)
        self.assertNotIn(permit.operation_id, client._permits)
        self.assertTrue(client._cleanup_broken)
        self.assertFalse(client._lock.locked())
        self.assertTrue(self.fixture.dns_calls)
        self.assertEqual(self.fixture.http_calls, [])
        with self.assertRaisesRegex(eg.EgressDenied, 'quarantined'):
            client.observe(permit, session)

    def test_actual_tls_socket_close_interrupt_preserves_completed_hop_and_no_replay(self):
        original = eg.ssl.SSLSocket.close
        for after_actual_close in (False, True):
            with self.subTest(after_actual_close=after_actual_close):
                client, session = self.fixture.client()
                permit = client.issue_observation_permit(session, self.fixture.url())
                before_http = len(self.fixture.http_calls)
                retained = []
                foreign = []
                sentinel = os.open('/dev/null', os.O_RDONLY | os.O_CLOEXEC)
                owned = [sentinel]
                def release_descriptors():
                    while owned:
                        os.close(owned.pop())
                self.addCleanup(release_descriptors)
                def interrupt(stream):
                    if stream.server_hostname == ONE and not retained:
                        retained.append(stream)
                        if after_actual_close:
                            descriptor = stream.fileno()
                            original(stream)
                            # Reuse the actual closed native socket number. The
                            # owned socket's second close/GC must not close it.
                            os.dup2(sentinel, descriptor)
                            foreign.append(descriptor)
                            owned.append(descriptor)
                        raise KeyboardInterrupt('actual HTTPS socket cleanup')
                    return original(stream)
                with patch.object(eg.ssl.SSLSocket, 'close', interrupt), self.assertRaises(eg.EgressIndeterminate) as caught:
                    client.observe(permit, session)
                error = caught.exception
                self.assertEqual(error.operation_id, permit.operation_id)
                self.assertEqual(error.hops, (eg.HopReceipt(error.connection, 200, 5),))
                self.assertIsInstance(error.cause, KeyboardInterrupt)
                self.assertEqual(retained[0].fileno(), -1)
                if foreign:
                    self.assertEqual(os.fstat(foreign[0]), os.fstat(sentinel))
                    retained.clear()
                    gc.collect()
                    self.assertEqual(os.fstat(foreign[0]), os.fstat(sentinel))
                self.assertEqual(client._active, {})
                self.assertFalse(client._lock.locked())
                self.assertFalse(client._cleanup_broken)
                with self.assertRaises(eg.EgressDenied):
                    client.observe(permit, session)
                self.assertEqual(len(self.fixture.http_calls) - before_http, 1)
                release_descriptors()

    def test_actual_pop_then_interrupt_releases_owned_mutex_and_quarantines(self):
        client, session = self.fixture.client()
        permit = client.issue_observation_permit(session, self.fixture.url())
        class InterruptedPop(dict):
            def pop(self, key, default=None):
                result = super().pop(key, default)
                raise KeyboardInterrupt('real active record removed before return')
        client._active = InterruptedPop()
        with self.assertRaises(eg.EgressIndeterminate) as caught:
            client.observe(permit, session)
        self.assertEqual(caught.exception.hops, (eg.HopReceipt(caught.exception.connection, 200, 5),))
        self.assertEqual(client._active, {})
        self.assertFalse(client._lock.locked())
        self.assertTrue(client._cleanup_broken)
        with self.assertRaisesRegex(eg.EgressDenied, 'quarantined'):
            client.observe(permit, session)
        self.assertEqual(len(self.fixture.http_calls), 1)

    def test_actual_release_interrupt_and_gc_never_unlock_foreign_reacquisition(self):
        client, session = self.fixture.client()
        permit = client.issue_observation_permit(session, self.fixture.url())
        mutex = client._lock
        held, finish = threading.Event(), threading.Event()
        threads, leases = [], []
        class InterruptedRelease:
            def acquire(self, **kwargs):
                return mutex.acquire(**kwargs)
            def release(self):
                mutex.release()
                def foreign_holder():
                    with mutex:
                        held.set()
                        finish.wait(3)
                thread = threading.Thread(target=foreign_holder)
                threads.append(thread)
                thread.start()
                if not held.wait(1):
                    raise AssertionError('foreign holder did not acquire the real released mutex')
                raise KeyboardInterrupt('real release completed and foreign thread reacquired')
        def trace(frame, event, value):
            if not leases and frame.f_code is eg.ControlledEgress._retire_observation.__code__ and event == 'call':
                lease = frame.f_locals['lease']
                leases.append(weakref.ref(lease))
                lease._lock = InterruptedRelease()
            return trace
        previous = sys.gettrace()
        try:
            sys.settrace(trace)
            with self.assertRaises(eg.EgressIndeterminate) as caught:
                client.observe(permit, session)
        finally:
            sys.settrace(previous)
        try:
            error = caught.exception
            self.assertEqual(error.operation_id, permit.operation_id)
            self.assertEqual(error.hops, (eg.HopReceipt(error.connection, 200, 5),))
            self.assertIsInstance(error.cause, KeyboardInterrupt)
            error.cause.__traceback__ = None
            error.__traceback__ = None
            gc.collect()
            self.assertIsNone(leases[0](), 'the cleanup owner was not collected')
            self.assertTrue(mutex.locked(), 'cleanup/GC released a foreign acquisition')
            self.assertFalse(mutex.acquire(blocking=False))
            with self.assertRaisesRegex(eg.EgressDenied, 'quarantined'):
                client.bind_session(session)
            self.assertEqual(client._active, {})
            self.assertEqual(len(self.fixture.http_calls), 1)
        finally:
            finish.set()
            for thread in threads:
                thread.join(2)
                self.assertFalse(thread.is_alive())
        self.assertFalse(mutex.locked())

    def test_cleanup_wait_is_bounded_and_quarantine_precedes_every_future_mutex(self):
        client, session = self.fixture.client()
        permit = client.issue_observation_permit(session, self.fixture.url())
        held, finish = threading.Event(), threading.Event()
        threads = []
        line = source_line(eg.ControlledEgress.observe, 'self._retire_observation(')
        def trace(frame, event, value):
            if not threads and frame.f_code is eg.ControlledEgress.observe.__code__ and event == 'line' and frame.f_lineno == line:
                def holder():
                    with client._lock:
                        held.set()
                        finish.wait(3)
                thread = threading.Thread(target=holder)
                threads.append(thread)
                thread.start()
                self.assertTrue(held.wait(1))
            return trace
        previous = sys.gettrace()
        started = time.monotonic()
        try:
            sys.settrace(trace)
            with self.assertRaises(eg.EgressIndeterminate) as caught:
                client.observe(permit, session)
        finally:
            sys.settrace(previous)
        try:
            self.assertLess(time.monotonic() - started, 1)
            self.assertIn('cleanup', str(caught.exception.cause))
            self.assertEqual(caught.exception.hops, (eg.HopReceipt(caught.exception.connection, 200, 5),))
            self.assertIs(client._active[permit.operation_id], permit)
            self.assertTrue(client._cleanup_broken)
            started = time.monotonic()
            for call in (lambda: client.observe(permit, session), lambda: client.bind_session(session),
                         lambda: client.issue_observation_permit(session, self.fixture.url()), client.close):
                with self.assertRaisesRegex(eg.EgressDenied, 'quarantined'):
                    call()
            self.assertLess(time.monotonic() - started, 0.2)
            self.assertEqual(len(self.fixture.http_calls), 1)
        finally:
            finish.set()
            for thread in threads:
                thread.join(2)
                self.assertFalse(thread.is_alive())
        self.assertFalse(client._lock.locked())

    def test_empty_cleanup_owner_constructor_interrupt_does_not_consume_permit(self):
        constructor = eg._PolicyLease.__init__
        for boundary, event_kind, line in (
                ('call', 'call', None),
                ('first-assignment', 'line', source_line(constructor, 'self._lock, self._owner_pid =')),
                ('return', 'return', None)):
            with self.subTest(boundary=boundary):
                client, session = self.fixture.client()
                permit = client.issue_observation_permit(session, self.fixture.url())
                before_http, before_dns = len(self.fixture.http_calls), len(self.fixture.dns_calls)
                fired = []
                def trace(frame, event, value):
                    if not fired and frame.f_code is constructor.__code__ and event == event_kind and (line is None or frame.f_lineno == line):
                        fired.append(True)
                        raise KeyboardInterrupt('empty owner construction')
                    return trace
                previous = sys.gettrace()
                try:
                    sys.settrace(trace)
                    with self.assertRaises(KeyboardInterrupt):
                        client.observe(permit, session)
                finally:
                    sys.settrace(previous)
                gc.collect()
                self.assertTrue(fired)
                self.assertIs(client._permits[permit.operation_id], permit)
                self.assertEqual(client._active, {})
                self.assertFalse(client._lock.locked())
                self.assertEqual(len(self.fixture.http_calls), before_http)
                self.assertEqual(len(self.fixture.dns_calls), before_dns)
                self.assertEqual(client.observe(permit, session).body, b'hello')

    def test_admission_owned_reservation_interrupts_close_slot_and_keep_consumption(self):
        admit, observe, close = eg.ControlledEgress._admit_observation, eg.ControlledEgress.observe, eg._PolicyLease.close
        cases = (
            ('reservation-before-consumption', admit, 'line', source_line(admit, 'del self._permits[')),
            ('consumed-before-active-insertion', admit, 'line', source_line(admit, 'self._active[')),
            ('active-inserted-before-release', admit, 'line', source_line(admit, 'lease.close()')),
            ('admission-release-call', close, 'call', None),
            ('admission-before-detach-and-release', close, 'line', source_line(close, 'self._held = False;')),
            ('admission-actual-release-return', close, 'return', None),
            ('admission-helper-return', admit, 'return', None),
            ('after-admission-before-target', observe, 'line', source_line(observe, 'target = _target(permit.initial_url)')),
        )
        for name, function, event_kind, line in cases:
            with self.subTest(boundary=name):
                client, session = self.fixture.client()
                permit = client.issue_observation_permit(session, self.fixture.url())
                before_http, before_dns = len(self.fixture.http_calls), len(self.fixture.dns_calls)
                before = descriptor_inventory()
                snapshot = {}
                def trace(frame, event, value):
                    if not snapshot and frame.f_code is function.__code__ and event == event_kind and (line is None or frame.f_lineno == line):
                        caller = frame
                        while caller is not None and caller.f_code is not observe.__code__:
                            caller = caller.f_back
                        if caller is None or caller.f_locals.get('self') is not client or caller.f_locals.get('permit') is not permit:
                            return trace
                        if function is close and frame.f_locals['self'] is not caller.f_locals.get('cleanup_lease'):
                            return trace
                        lease = caller.f_locals['cleanup_lease']
                        if not lease._reserved or caller.f_locals['budget'].attempted is not None:
                            return trace
                        snapshot.update(owned=lease._reserved, actual_lock_held=client._lock.locked(),
                                        active=client._active.get(permit.operation_id) is permit)
                        raise KeyboardInterrupt(name)
                    return trace
                previous = sys.gettrace()
                try:
                    sys.settrace(trace)
                    with self.assertRaisesRegex(eg.EgressDenied, 'permit remains consumed') as caught:
                        client.observe(permit, session)
                finally:
                    sys.settrace(previous)
                self.assertTrue(snapshot['owned'])
                self.assertNotIsInstance(caught.exception, eg.EgressIndeterminate)
                self.assertIsInstance(caught.exception.__cause__, KeyboardInterrupt)
                self.assertEqual(descriptor_inventory(), before)
                self.assertFalse(client._lock.locked())
                self.assertFalse(client._cleanup_broken)
                self.assertEqual(client._active, {})
                self.assertNotIn(permit.operation_id, client._permits)
                self.assertEqual(len(self.fixture.http_calls), before_http)
                self.assertEqual(len(self.fixture.dns_calls), before_dns)
                with self.assertRaises(eg.EgressDenied):
                    client.observe(permit, session)
                # A new explicitly issued permit runs once; the aborted permit
                # never becomes available again or leaves a stale active slot.
                fresh = client.issue_observation_permit(session, self.fixture.url())
                self.assertEqual(client.observe(fresh, session).body, b'hello')
                self.assertEqual(client._active, {})
                self.assertEqual(len(self.fixture.http_calls) - before_http, 1)
                self.assertEqual(len(self.fixture.dns_calls) - before_dns, 2)

    def test_admission_before_reservation_interrupt_releases_actual_mutex_without_authority(self):
        admit, acquire = eg.ControlledEgress._admit_observation, eg._PolicyLease.acquire
        for name, function, event_kind, line in (
                ('admission-entry', admit, 'call', None),
                ('real-acquire-return', acquire, 'return', None),
                ('before-capacity-and-permit-predicate', admit, 'line', source_line(admit, 'if len(self._active)'))):
            with self.subTest(boundary=name):
                client, session = self.fixture.client()
                permit = client.issue_observation_permit(session, self.fixture.url())
                before, before_http, before_dns = descriptor_inventory(), len(self.fixture.http_calls), len(self.fixture.dns_calls)
                fired = []
                def trace(frame, event, value):
                    if not fired and frame.f_code is function.__code__ and event == event_kind and (line is None or frame.f_lineno == line):
                        fired.append(client._lock.locked())
                        raise KeyboardInterrupt(name)
                    return trace
                previous = sys.gettrace()
                try:
                    sys.settrace(trace)
                    with self.assertRaises(KeyboardInterrupt):
                        client.observe(permit, session)
                finally:
                    sys.settrace(previous)
                self.assertTrue(fired)
                self.assertEqual(descriptor_inventory(), before)
                self.assertFalse(client._lock.locked())
                self.assertFalse(client._cleanup_broken)
                self.assertEqual(client._active, {})
                self.assertIs(client._permits[permit.operation_id], permit)
                self.assertEqual(len(self.fixture.http_calls), before_http)
                self.assertEqual(len(self.fixture.dns_calls), before_dns)
                self.assertEqual(client.observe(permit, session).body, b'hello')

    def test_competing_same_permit_admission_never_retires_real_winner(self):
        client, session = self.fixture.client()
        permit = client.issue_observation_permit(session, self.fixture.url())
        finish = threading.Event()
        self.fixture.on_http = lambda path: finish.wait(2)
        threads, result, errors = [], [], []
        def winner():
            try:
                result.append(client.observe(permit, session))
            except BaseException as error:
                errors.append(error)
        def trace(frame, event, value):
            if not threads and frame.f_code is eg.ControlledEgress._admit_observation.__code__ and event == 'call':
                # This caller already passed pending validation. Let a real
                # second caller win admission and send HTTP before this resumes.
                thread = threading.Thread(target=winner)
                threads.append(thread)
                thread.start()
                self.assertTrue(self.fixture.http_received.wait(1))
            return trace
        previous = sys.gettrace()
        try:
            sys.settrace(trace)
            with self.assertRaisesRegex(eg.EgressDenied, 'already consumed'):
                client.observe(permit, session)
            self.assertIs(client._active[permit.operation_id], permit)
            self.assertFalse(client._cleanup_broken)
        finally:
            sys.settrace(previous)
            finish.set()
            for thread in threads:
                thread.join(2)
                self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].body, b'hello')
        self.assertEqual(result[0].operation_id, permit.operation_id)
        self.assertEqual(client._active, {})
        self.assertEqual(len(self.fixture.http_calls), 1)
        self.assertEqual(len(self.fixture.dns_calls), 2)

    def test_admission_release_interrupt_quarantines_without_releasing_foreign_mutex_or_sending(self):
        client, session = self.fixture.client()
        permit = client.issue_observation_permit(session, self.fixture.url())
        before = descriptor_inventory()
        mutex = client._lock
        held, finish = threading.Event(), threading.Event()
        threads, leases = [], []
        class InterruptedRelease:
            def acquire(self, **kwargs):
                return mutex.acquire(**kwargs)
            def release(self):
                mutex.release()
                def foreign_holder():
                    with mutex:
                        held.set()
                        finish.wait(3)
                thread = threading.Thread(target=foreign_holder)
                threads.append(thread)
                thread.start()
                if not held.wait(1):
                    raise AssertionError('foreign holder did not acquire the actual admission mutex')
                raise KeyboardInterrupt('real admission release before foreign reacquisition')
        def trace(frame, event, value):
            if not leases and frame.f_code is eg.ControlledEgress._admit_observation.__code__ and event == 'call':
                lease = frame.f_locals['lease']
                leases.append(weakref.ref(lease))
                lease._lock = InterruptedRelease()
            return trace
        previous = sys.gettrace()
        try:
            sys.settrace(trace)
            with self.assertRaisesRegex(eg.EgressDenied, 'quarantined') as caught:
                client.observe(permit, session)
        finally:
            sys.settrace(previous)
        try:
            self.assertNotIsInstance(caught.exception, eg.EgressIndeterminate)
            pending, seen, causes = [caught.exception], set(), []
            while pending:
                error = pending.pop()
                if error is None or id(error) in seen:
                    continue
                seen.add(id(error))
                causes.append(type(error).__name__)
                pending.extend((error.__cause__, error.__context__))
                error.__traceback__ = None
            self.assertIn('KeyboardInterrupt', causes)
            gc.collect()
            self.assertIsNone(leases[0]())
            self.assertEqual(descriptor_inventory(), before)
            self.assertTrue(mutex.locked())
            self.assertFalse(mutex.acquire(blocking=False))
            self.assertIs(client._active[permit.operation_id], permit)
            self.assertTrue(client._cleanup_broken)
            self.assertNotIn(permit.operation_id, client._permits)
            for call in (lambda: client.observe(permit, session), lambda: client.bind_session(session), client.close):
                with self.assertRaisesRegex(eg.EgressDenied, 'quarantined'):
                    call()
            self.assertEqual(self.fixture.http_calls, [])
            self.assertEqual(self.fixture.dns_calls, [])
        finally:
            finish.set()
            for thread in threads:
                thread.join(2)
                self.assertFalse(thread.is_alive())
        self.assertFalse(mutex.locked())

    def test_real_fork_after_https_response_never_enters_inherited_cleanup_mutex(self):
        client, session = self.fixture.client()
        permit = client.issue_observation_permit(session, self.fixture.url())
        result_read, result_write = os.pipe()
        owned_fds = [result_read, result_write]
        held, finish = threading.Event(), threading.Event()
        state = {'pid': None, 'forked': False, 'reaped': False}
        threads = []
        def close_pipe(descriptor):
            owned_fds.remove(descriptor)
            os.close(descriptor)
        def cleanup_probe():
            finish.set()
            for thread in threads:
                thread.join(2)
            pid = state['pid']
            if pid and not state['reaped']:
                try:
                    waited, _ = os.waitpid(pid, os.WNOHANG)
                    if not waited:
                        # Only our unreaped child retains this PID identity.
                        os.kill(pid, signal.SIGKILL)
                        os.waitpid(pid, 0)
                except ChildProcessError:
                    pass
                state['reaped'] = True
            while owned_fds:
                os.close(owned_fds.pop())
        self.addCleanup(cleanup_probe)
        line = source_line(eg.ControlledEgress.observe, '_peer(stream, address, target.host.port)')
        def trace(frame, event, value):
            if not state['forked'] and frame.f_code is eg.ControlledEgress.observe.__code__ and event == 'line' and frame.f_lineno == line:
                self.assertEqual(frame.f_locals['body'], b'hello')
                self.assertEqual(frame.f_locals['status'], 200)
                def holder():
                    with client._lock:
                        held.set()
                        finish.wait(3)
                thread = threading.Thread(target=holder)
                threads.append(thread)
                thread.start()
                self.assertTrue(held.wait(1))
                state['forked'] = True
                state['pid'] = os.fork()
                if state['pid'] == 0:
                    close_pipe(result_read)
                else:
                    finish.set()
                    thread.join(2)
                    self.assertFalse(thread.is_alive())
            return trace
        previous = sys.gettrace()
        try:
            sys.settrace(trace)
            try:
                response = client.observe(permit, session)
            except BaseException as error:
                if state['pid'] == 0:
                    payload = {'typed': isinstance(error, eg.EgressIndeterminate),
                               'operation_id': getattr(error, 'operation_id', None),
                               'peer': getattr(getattr(error, 'connection', None), 'connected_peer', None),
                               'cause': str(getattr(error, 'cause', error)),
                               'inherited_mutex_still_locked': client._lock.locked()}
                    os.write(result_write, json.dumps(payload).encode('ascii'))
                    os._exit(0)
                raise
            if state['pid'] == 0:
                os._exit(4)
        finally:
            sys.settrace(previous)
        close_pipe(result_write)
        try:
            self.assertTrue(select.select([result_read], [], [], 2)[0], 'child blocked in inherited cleanup mutex')
            payload = json.loads(os.read(result_read, 4096))
            self.assertTrue(payload['typed'])
            self.assertEqual(payload['operation_id'], permit.operation_id)
            self.assertEqual(payload['peer'], '127.0.0.1')
            self.assertIn('creating process', payload['cause'])
            self.assertTrue(payload['inherited_mutex_still_locked'], 'child released a copied parent acquisition')
            self.assertEqual(response.body, b'hello')
            self.assertEqual(len(response.hops), 1)
            self.assertEqual(client._active, {})
            self.assertFalse(client._lock.locked())
            self.assertFalse(client._cleanup_broken)
            self.assertEqual(len(self.fixture.http_calls), 1)
            self.assertEqual(len(self.fixture.dns_calls), 2)
        finally:
            close_pipe(result_read)
            waited, status = os.waitpid(state['pid'], os.WNOHANG)
            if not waited:
                os.kill(state['pid'], signal.SIGKILL)
                _, status = os.waitpid(state['pid'], 0)
            state['reaped'] = True
        self.assertEqual(status, 0)

    def test_session_revocation_between_redirect_hops_prevents_new_target_connection(self):
        client, session = self.fixture.client()
        self.fixture.response = (f'HTTP/1.1 302 Found\r\nLocation: {self.fixture.url("/next", TWO)}\r\nContent-Length: 0\r\n\r\n').encode()
        self.fixture.on_http = lambda path: client.bind_session(eg.SessionBinding('replacement', 2, ORIGIN))
        with self.assertRaises(eg.EgressIndeterminate):
            self.fetch(client, session, redirects=frozenset({eg.ApprovedHost(TWO, self.fixture.https.port)}))
        self.assertEqual(len(self.fixture.http_calls), 1)
        self.assertFalse(any(host == TWO for host, _ in self.fixture.dns_calls))

    def test_proxy_and_ca_environment_have_no_authority_or_network_route(self):
        poison = {'HTTP_PROXY': 'http://127.0.0.1:1', 'HTTPS_PROXY': 'http://127.0.0.1:1', 'ALL_PROXY': 'socks5://127.0.0.1:1',
                  'http_proxy': 'http://127.0.0.1:1', 'https_proxy': 'http://127.0.0.1:1', 'NO_PROXY': '',
                  'SSL_CERT_FILE': '/missing/roots', 'SSL_CERT_DIR': '/missing/roots', 'REQUESTS_CA_BUNDLE': '/missing/roots'}
        with patch.dict(os.environ, poison):
            client, session = self.fixture.client()
            response = self.fetch(client, session)
        self.assertEqual(response.body, b'hello')
        self.assertEqual(response.hops[0].connection.connected_peer, '127.0.0.1')

    def test_unsupported_methods_protocols_resources_credentials_and_urls_do_not_resolve(self):
        client, session = self.fixture.client()
        for url in ('http://one.fixture.test/', 'wss://one.fixture.test/', 'https://u:p@one.fixture.test/', 'https://127.0.0.1/',
                    'https://[::ffff:127.0.0.1]/', 'https://one.fixture.test./', 'https://ONE.fixture.test/',
                    'https://one.fixture.test/#fragment', 'https://one.fixture.test/%0d%0aheader', 'https://one.fixture.test\\evil/',
                    'https://one.fixture.test/%XX', 'https://one.fixture.test/#'):
            with self.subTest(url=url), self.assertRaises(eg.EgressDenied):
                client.issue_observation_permit(session, url)
        permit = client.issue_observation_permit(session, self.fixture.url())
        for options in ({'method': 'POST'}, {'method': 'HEAD'}, {'resource_class': 'download'}, {'resource_class': 'websocket'},
                        {'resource_class': 'worker'}, {'resource_class': 'service_worker'}, {'resource_class': 'iframe'},
                        {'resource_class': 'prefetch'}, {'resource_class': 'subresource'}, {'resource_class': 'navigation'},
                        {'resource_class': 'quic'}, {'resource_class': 'effect'}):
            with self.subTest(options=options), self.assertRaises(eg.EgressDenied):
                client.observe(permit, session, **options)
        self.assertEqual(self.fixture.dns_calls, [])

    def test_dns_malformed_identity_compression_alias_and_trailing_bytes_refused(self):
        def alias(data):
            _, end = eg._dns_name(data, 12)
            end += 4
            return data[:end] + b'\xc0\x0c' + struct.pack('!2HIH', 5, 1, 30, 2) + b'\xc0\x0c'
        mutations = (lambda data: struct.pack('!H', struct.unpack_from('!H', data)[0] ^ 1) + data[2:], lambda data: data + b'trailer',
                     lambda data: data[:6] + b'\xff\xff' + data[8:],
                     lambda data: data[:12] + b'\xc0\x0c' + data[14:], alias)
        for mutate in mutations:
            self.fixture.dns_mutator = mutate
            client, session = self.fixture.client()
            with self.subTest(mutation=mutate), self.assertRaises(eg.EgressDenied):
                self.fetch(client, session)
        self.assertEqual(self.fixture.http_calls, [])

    def test_bounded_response_headers_body_framing_compression_download_and_upgrade_refused(self):
        responses = (
            b'HTTP/1.1 200 OK\r\nContent-Length: 1\r\nContent-Length: 1\r\nContent-Type: text/plain\r\n\r\nx',
            b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n',
            b'HTTP/1.1 200 OK\r\nContent-Length: 1\r\nContent-Type: text/plain\r\nContent-Encoding: gzip\r\n\r\nx',
            b'HTTP/1.1 200 OK\r\nContent-Length: 1\r\nContent-Type: application/octet-stream\r\n\r\nx',
            b'HTTP/1.1 200 OK\r\nContent-Length: 1\r\nContent-Type: text/plain\r\nContent-Disposition: attachment\r\n\r\nx',
            b'HTTP/1.1 200 OK\r\nContent-Length: 1\r\nContent-Type: text/plain\r\nSet-Cookie: x=y\r\n\r\nx',
            b'HTTP/1.1 101 Switching\r\nUpgrade: websocket\r\nContent-Length: 0\r\n\r\n',
            b'HTTP/1.1 200 OK\r\nContent-Length: 1048577\r\nContent-Type: text/plain\r\n\r\n',
            b'HTTP/1.1 200 OK\r\nContent-Length: 10\r\nContent-Type: text/plain\r\n\r\nx',
            b'HTTP/1.1 200 OK\r\nX-Long: ' + b'x' * eg.MAX_HEADER_BYTES + b'\r\n\r\n',
        )
        for response in responses:
            self.fixture.response = response
            client, session = self.fixture.client()
            with self.subTest(response_bytes=len(response)), self.assertRaises(eg.EgressIndeterminate):
                self.fetch(client, session)

    def test_single_deadline_spans_dns_tls_and_response_without_renewal(self):
        self.fixture.dns_delay = 0.065
        self.fixture.http_delay = 0.2
        client, session = self.fixture.client()
        started = time.monotonic()
        with self.assertRaises(eg.EgressIndeterminate) as caught:
            self.fetch(client, session, timeout_seconds=0.25)
        self.assertIsInstance(caught.exception.cause, eg.EgressDeadlineExceeded)
        self.assertLess(time.monotonic() - started, 0.65)
        self.assertEqual(len(self.fixture.http_calls), 1)

    def test_cancellation_before_during_dns_and_after_request_preserves_no_retry(self):
        token = eg.CancellationToken()
        token.cancel()
        client, session = self.fixture.client()
        with self.assertRaises(eg.EgressCancelled):
            self.fetch(client, session, cancellation=token)
        self.assertEqual(self.fixture.dns_calls, [])
        self.fixture.dns_delay = 0.2
        token = eg.CancellationToken()
        thread = threading.Thread(target=lambda: (self.fixture.dns_received.wait(1), token.cancel()))
        thread.start()
        with self.assertRaises(eg.EgressCancelled):
            self.fetch(client, session, cancellation=token)
        thread.join(2)
        self.assertEqual(self.fixture.http_calls, [])
        self.fixture.dns_delay = 0
        self.fixture.http_delay = 0.2
        self.fixture.http_received.clear()
        token = eg.CancellationToken()
        thread = threading.Thread(target=lambda: (self.fixture.http_received.wait(1), token.cancel()))
        thread.start()
        permit = client.issue_observation_permit(session, self.fixture.url())
        with self.assertRaises(eg.EgressIndeterminate) as caught:
            client.observe(permit, session, cancellation=token)
        thread.join(2)
        self.assertIsInstance(caught.exception.cause, eg.EgressCancelled)
        with self.assertRaises(eg.EgressDenied):
            client.observe(permit, session)
        self.assertEqual(len(self.fixture.http_calls), 1)

    def test_real_ipv6_loopback_socket_and_tls_uses_same_mediator(self):
        # Linux qualification requires IPv6; inability to bind fails this test.
        fixture = Fixture(address='::1')
        self.addCleanup(fixture.close)
        client, session = fixture.client()
        permit = client.issue_observation_permit(session, fixture.url())
        response = client.observe(permit, session)
        self.assertEqual(response.hops[0].connection.connected_peer, '::1')
        self.assertEqual(response.body, b'hello')

    def test_closed_source_contract_correspondence_and_disabled_product_claims(self):
        contract = json.loads((ROOT / 'contracts/controlled-egress.v1.json').read_text())
        self.assertEqual(set(contract), {'schema', 'status', 'implementation', 'default', 'authority', 'resolver',
                                        'address_policy', 'https', 'limits', 'outcome', 'qualification', 'remaining_installed_obligations'})
        self.assertEqual(contract['schema'], 'trillionnium.desktop.controlled-egress.v1')
        self.assertEqual(contract['status'], 'SOURCE_CANDIDATE')
        self.assertEqual(contract['implementation'], 'platform/controlled_egress.py')
        self.assertEqual(contract['default'], {'hosts': [], 'initiating_origins': [], 'resolver': None,
                                              'certificate_roots': None, 'external_mutation_enabled': False,
                                              'browser_namespace_enforced': False})
        self.assertEqual(contract['https']['method'], 'GET')
        self.assertEqual(contract['https']['resource_class'], 'observation')
        self.assertFalse(contract['authority']['approval_surface_implemented'])
        self.assertFalse(contract['authority']['persistent_permit_or_indeterminate_journal_implemented'])
        self.assertFalse(contract['outcome']['automatic_retry'])
        self.assertFalse(contract['outcome']['durable_delivery_or_external_effect_proof'])
        self.assertFalse(contract['qualification']['installed_browser_or_hardware_success'])
        expected = {'url_bytes': eg.MAX_URL_BYTES, 'ca_bytes_each': eg.MAX_CA_BYTES,
                    'dns_packet_bytes': eg.MAX_DNS_BYTES, 'dns_records_each_packet': eg.MAX_DNS_RECORDS,
                    'resolved_addresses_each_hop': eg.MAX_DNS_RECORDS, 'approved_hosts': eg.MAX_HOSTS,
                    'approved_origins': eg.MAX_HOSTS, 'header_bytes_each_hop': eg.MAX_HEADER_BYTES,
                    'header_count_each_hop': eg.MAX_HEADERS, 'body_bytes_each_hop': eg.MAX_BODY_BYTES,
                    'redirects': eg.MAX_REDIRECTS, 'pending_permits': eg.MAX_PERMITS,
                    'active_operations': eg.MAX_ACTIVE, 'deadline_seconds_min': 0.01,
                    'deadline_seconds_max': 30, 'cancellation_poll_seconds_max': eg.POLL_SECONDS}
        self.assertEqual(contract['limits'], expected)


class NativeEgressGateTests(unittest.TestCase):
    def test_completed_revocation_after_clock_prevents_actual_get(self):
        for kind in ('cancel', 'close'):
            with self.subTest(kind=kind):
                before = descriptor_inventory()
                fixture = Fixture()
                client, session = fixture.client()
                permit = client.issue_observation_permit(session, fixture.url())
                token = eg.CancellationToken()
                fired, workers, failures, stale_returns = [], [], [], []
                line = source_line(eg._Budget.check, 'remaining = self.deadline - self.clock()')
                def trace(frame, event, value):
                    caller = frame.f_back
                    if fired and event == 'return' and frame.f_code is eg._Budget.check.__code__ and caller is not None and caller.f_code is eg._send.__code__ and caller.f_locals['data'].startswith(b'GET ') and value is not None:
                        stale_returns.append(value)
                    if not fired and event == 'line' and frame.f_code is eg._Budget.check.__code__ and frame.f_lineno == line and caller is not None and caller.f_code is eg._send.__code__ and caller.f_locals['data'].startswith(b'GET '):
                        fired.append(caller.f_locals['stream'])
                        done = threading.Event()
                        def revoke():
                            try:
                                token.cancel() if kind == 'cancel' else client.close()
                            except BaseException as error:
                                failures.append(error)
                            finally:
                                done.set()
                        worker = threading.Thread(target=revoke)
                        workers.append(worker)
                        worker.start()
                        self.assertTrue(done.wait(1), 'revocation did not actually complete')
                    return trace
                previous = sys.gettrace()
                try:
                    sys.settrace(trace)
                    with self.assertRaises(eg.EgressIndeterminate) as caught:
                        client.observe(permit, session, cancellation=token)
                    self.assertEqual(caught.exception.operation_id, permit.operation_id)
                    self.assertEqual(caught.exception.connection.connected_peer, '127.0.0.1')
                    self.assertEqual(caught.exception.hops, ())
                finally:
                    sys.settrace(previous)
                    for worker in workers:
                        worker.join(2)
                    fixture.close()
                self.assertEqual(failures, [])
                self.assertEqual(stale_returns, [], 'a revoked budget check returned an authorization interval')
                self.assertEqual(len(fired), 1)
                self.assertEqual(fired[0].fileno(), -1)
                self.assertEqual(fixture.http_calls, [])
                self.assertEqual(len(fixture.dns_calls), 2)
                self.assertEqual(client._active, {})
                self.assertNotIn(permit.operation_id, client._permits)
                self.assertFalse(client._lock.locked())
                self.assertFalse(token._io_lock.locked())
                self.assertEqual(descriptor_inventory(), before)

    def test_admitted_native_call_finishes_before_revocation_barrier_returns(self):
        for kind in ('cancel', 'close'):
            with self.subTest(kind=kind):
                fixture = Fixture()
                client, session = fixture.client()
                permit = client.issue_observation_permit(session, fixture.url())
                token = eg.CancellationToken()
                entered, done = threading.Event(), threading.Event()
                fired, workers, failures = [], [], []
                line = source_line(eg._NativeIOGate.perform, 'return getattr(stream._current(), method)')
                def trace(frame, event, value):
                    if not fired and event == 'line' and frame.f_code is eg._NativeIOGate.perform.__code__ and frame.f_lineno == line and frame.f_locals['method'] == 'send' and frame.f_locals['arguments'][0].startswith(b'GET '):
                        fired.append(frame.f_locals['stream'])
                        self.assertTrue(client._lock.locked())
                        self.assertTrue(token._io_lock.locked())
                        def revoke():
                            entered.set()
                            try:
                                token.cancel() if kind == 'cancel' else client.close()
                            except BaseException as error:
                                failures.append(error)
                            finally:
                                done.set()
                        worker = threading.Thread(target=revoke)
                        workers.append(worker)
                        worker.start()
                        self.assertTrue(entered.wait(1))
                        self.assertFalse(done.wait(0.005), 'barrier returned while an admitted call was pending')
                    return trace
                previous = sys.gettrace()
                try:
                    sys.settrace(trace)
                    with self.assertRaises(eg.EgressIndeterminate):
                        client.observe(permit, session, cancellation=token)
                    self.assertTrue(done.wait(1))
                    self.assertTrue(fixture.http_received.wait(1))
                finally:
                    sys.settrace(previous)
                    for worker in workers:
                        worker.join(2)
                    fixture.close()
                self.assertEqual(failures, [])
                self.assertEqual(len(fixture.http_calls), 1, 'the call was admitted before revocation completed')
                self.assertEqual(len(fixture.dns_calls), 2)
                self.assertEqual(client._active, {})
                self.assertFalse(client._lock.locked())
                self.assertFalse(token._io_lock.locked())
                self.assertEqual(fired[0].fileno(), -1)

    def test_actual_fork_after_last_socket_pid_guard_closes_child_and_preserves_parent(self):
        for stage in ('connect_ex', 'do_handshake', 'send'):
            with self.subTest(stage=stage):
                before = descriptor_inventory()
                fixture = Fixture()
                client, session = fixture.client()
                permit = client.issue_observation_permit(session, fixture.url())
                token = eg.CancellationToken()
                read_fd, write_fd = os.pipe()
                state = {'fired': False, 'pid': None, 'reaped': False}
                def trace(frame, event, value):
                    caller = frame.f_back
                    if not state['fired'] and event == 'return' and frame.f_code is eg._SocketOwner._current.__code__ and caller is not None and caller.f_code is eg._NativeIOGate.perform.__code__ and caller.f_locals['method'] == stage and (stage != 'send' or caller.f_locals['arguments'][0].startswith(b'GET ')):
                        state['fired'] = True
                        state['descriptor'] = value.fileno()
                        metadata = os.fstat(state['descriptor'])
                        self.assertTrue(client._lock.locked())
                        self.assertTrue(token._io_lock.locked())
                        state['pid'] = os.fork()
                        if state['pid'] == 0:
                            os.close(read_fd)
                            try:
                                os.fstat(state['descriptor'])
                                state['child_closed'] = False
                            except OSError as error:
                                state['child_closed'] = error.errno == eg.errno.EBADF
                            state['child_alias_closed'] = value.fileno() == -1
                        else:
                            os.close(write_fd)
                            self.assertTrue(select.select([read_fd], [], [], 2)[0], 'child blocked on an inherited authority mutex')
                            state['child'] = json.loads(os.read(read_fd, 8192))
                            _, status = os.waitpid(state['pid'], 0)
                            state['reaped'] = True
                            self.assertEqual(os.waitstatus_to_exitcode(status), 0)
                            current = os.fstat(state['descriptor'])
                            self.assertEqual((current.st_dev, current.st_ino), (metadata.st_dev, metadata.st_ino))
                            state['parent_still_live'] = value.fileno() == state['descriptor']
                    return trace
                previous = sys.gettrace()
                try:
                    sys.settrace(trace)
                    try:
                        response = client.observe(permit, session, cancellation=token)
                        error = None
                    except BaseException as caught:
                        response, error = None, caught
                    finally:
                        sys.settrace(previous)
                    if state['pid'] == 0:
                        payload = {'closed': state['child_closed'], 'alias_closed': state['child_alias_closed'],
                                   'error': type(error).__name__, 'parent_owner_unchanged': client._owner_pid != os.getpid()}
                        os.write(write_fd, json.dumps(payload).encode())
                        os.close(write_fd)
                        os._exit(0)
                    self.assertIsNone(error)
                    self.assertEqual(response.body, b'hello')
                    self.assertTrue(state['parent_still_live'])
                    self.assertEqual(state['child'], {'closed': True, 'alias_closed': True,
                                                     'error': 'EgressIndeterminate' if stage == 'send' else 'EgressDenied',
                                                     'parent_owner_unchanged': True})
                    self.assertEqual(len(fixture.http_calls), 1)
                    self.assertEqual(len(fixture.dns_calls), 2)
                    self.assertEqual(client._active, {})
                    self.assertFalse(client._lock.locked())
                    self.assertFalse(token._io_lock.locked())
                    self.assertFalse(client._cleanup_broken)
                finally:
                    sys.settrace(previous)
                    if state['pid'] and not state['reaped']:
                        waited, _ = os.waitpid(state['pid'], os.WNOHANG)
                        if not waited:
                            os.kill(state['pid'], signal.SIGKILL)
                            os.waitpid(state['pid'], 0)
                    os.close(read_fd)
                    if not state['fired']:
                        os.close(write_fd)
                    fixture.close()
                self.assertTrue(state['fired'])
                self.assertEqual(descriptor_inventory(), before)

    def test_native_gate_contention_is_bounded_and_cannot_restart_original_deadline(self):
        for held_mutex, near_deadline in (('token', False), ('policy', False), ('token', True)):
            with self.subTest(held_mutex=held_mutex, near_deadline=near_deadline):
                fixture = Fixture()
                client, session = fixture.client()
                permit = client.issue_observation_permit(session, fixture.url())
                token = eg.CancellationToken()
                held, release = threading.Event(), threading.Event()
                fired, workers = [], []
                line = source_line(eg._NativeIOGate.perform, 'token_lease.acquire_before(budget)')
                def trace(frame, event, value):
                    if not fired and event == 'line' and frame.f_code is eg._NativeIOGate.perform.__code__ and frame.f_lineno == line and frame.f_locals['method'] == 'send' and frame.f_locals['arguments'][0].startswith(b'GET '):
                        fired.append({'deadline': frame.f_locals['budget'].deadline, 'owner': frame.f_locals['stream']})
                        def holder():
                            with token._io_lock if held_mutex == 'token' else client._lock:
                                held.set()
                                release.wait(2)
                        worker = threading.Thread(target=holder)
                        workers.append(worker)
                        worker.start()
                        self.assertTrue(held.wait(1))
                        if near_deadline:
                            delay = fired[0]['deadline'] - time.monotonic() - 0.012
                            self.assertGreater(delay, 0)
                            time.sleep(delay)
                        fired[0]['wait_started'] = time.monotonic()
                    return trace
                previous = sys.gettrace()
                started = time.monotonic()
                try:
                    sys.settrace(trace)
                    with self.assertRaises(eg.EgressIndeterminate):
                        client.observe(permit, session, cancellation=token, timeout_seconds=0.5)
                    ended = time.monotonic()
                    self.assertLess(ended - started, 0.8)
                    self.assertLess(ended - fired[0]['wait_started'], 0.15)
                    if near_deadline:
                        self.assertGreaterEqual(ended, fired[0]['deadline'])
                    self.assertEqual(fixture.http_calls, [])
                    self.assertEqual(len(fixture.dns_calls), 2)
                    self.assertEqual(fired[0]['owner'].fileno(), -1)
                    self.assertFalse(token._io_lock.locked() if held_mutex == 'policy' else client._lock.locked())
                finally:
                    sys.settrace(previous)
                    release.set()
                    for worker in workers:
                        worker.join(2)
                        self.assertFalse(worker.is_alive())
                    fixture.close()
                self.assertFalse(token._io_lock.locked())
                self.assertFalse(client._lock.locked())

    def test_cancel_timeout_requests_revocation_without_claiming_completed_barrier(self):
        token = eg.CancellationToken()
        held, release = threading.Event(), threading.Event()
        def holder():
            with token._io_lock:
                held.set()
                release.wait(2)
        worker = threading.Thread(target=holder)
        worker.start()
        try:
            self.assertTrue(held.wait(1))
            started = time.monotonic()
            with self.assertRaises(eg.EgressDenied):
                token.cancel()
            self.assertLess(time.monotonic() - started, 0.2)
            self.assertTrue(token.cancelled)
            self.assertTrue(token._io_lock.locked(), 'failed cancellation released a foreign mutex')
        finally:
            release.set()
            worker.join(2)
        token.cancel()
        self.assertFalse(token._io_lock.locked())

    def test_real_signal_callback_policy_entrypoints_refuse_without_deadlock_or_mutation(self):
        for operation in ('close', 'bind', 'issue', 'observe', 'clock'):
            with self.subTest(operation=operation):
                fixture = Fixture()
                client, session = fixture.client()
                permit = client.issue_observation_permit(session, fixture.url())
                pending = client.issue_observation_permit(session, fixture.url('/second'))
                replacement = eg.SessionBinding('replacement', 2, ORIGIN)
                epoch = client._epoch
                fired, refusals = [], []
                line = source_line(eg._NativeIOGate.perform, 'return getattr(stream._current(), method)')
                def callback(signum, frame):
                    started = time.monotonic()
                    try:
                        if operation == 'close':
                            client.close()
                        elif operation == 'bind':
                            client.bind_session(replacement)
                        elif operation == 'issue':
                            client.issue_observation_permit(session, fixture.url('/third'))
                        elif operation == 'observe':
                            client.observe(pending, session)
                        else:
                            client._clock()
                    except eg.EgressDenied as error:
                        refusals.append((error, time.monotonic() - started))
                def trace(frame, event, value):
                    if not fired and event == 'line' and frame.f_code is eg._NativeIOGate.perform.__code__ and frame.f_lineno == line and frame.f_locals['method'] == 'send' and frame.f_locals['arguments'][0].startswith(b'GET '):
                        fired.append(True)
                        os.kill(os.getpid(), signal.SIGUSR1)
                    return trace
                previous = sys.gettrace()
                previous_signal = signal.signal(signal.SIGUSR1, callback)
                try:
                    sys.settrace(trace)
                    response = client.observe(permit, session)
                    self.assertEqual(response.body, b'hello')
                    self.assertEqual(len(refusals), 1, 'a busy/reentrant entrypoint falsely returned success')
                    self.assertIsInstance(refusals[0][0], eg.EgressDenied)
                    self.assertLess(refusals[0][1], 0.2)
                    self.assertIs(client._session, session)
                    self.assertEqual(client._epoch, epoch)
                    self.assertEqual(client._permits, {pending.operation_id: pending})
                    self.assertEqual(client._active, {})
                    self.assertFalse(client._cleanup_broken)
                    self.assertFalse(client._lock.locked())
                    self.assertEqual(len(fixture.dns_calls), 2)
                    self.assertEqual(len(fixture.http_calls), 1)
                finally:
                    sys.settrace(previous)
                    signal.signal(signal.SIGUSR1, previous_signal)
                    fixture.close()

    def test_native_gate_refuses_wrong_thread_before_real_mutex_acquisition(self):
        fixture = Fixture()
        client, session = fixture.client()
        token = eg.CancellationToken()
        permit = client.issue_observation_permit(session, fixture.url())
        gate = eg._NativeIOGate(client, permit, session, token)
        errors = []
        client._lock.acquire()
        token._io_lock.acquire()
        def invoke():
            try:
                gate.perform(None, None, 'send', b'GET / HTTP/1.1\r\n\r\n')
            except BaseException as error:
                errors.append(error)
        worker = threading.Thread(target=invoke)
        try:
            worker.start()
            worker.join(0.2)
            self.assertFalse(worker.is_alive(), 'wrong-thread gate entered a foreign mutex')
            self.assertEqual(len(errors), 1)
            self.assertRegex(str(errors[0]), 'observing thread')
            self.assertTrue(client._lock.locked())
            self.assertTrue(token._io_lock.locked())
            self.assertEqual(fixture.dns_calls, [])
            self.assertEqual(fixture.http_calls, [])
        finally:
            token._io_lock.release()
            client._lock.release()
            fixture.close()

    def test_forked_cancel_is_noop_before_inherited_mutex_and_parent_flag_unchanged(self):
        token = eg.CancellationToken()
        read_fd, write_fd = os.pipe()
        token._io_lock.acquire()
        child, reaped = None, False
        try:
            child = os.fork()
            if child == 0:
                os.close(read_fd)
                result = token.cancel()
                os.write(write_fd, json.dumps({'returned_none': result is None, 'cancelled': token.cancelled,
                                              'copied_mutex_still_held': token._io_lock.locked()}).encode())
                os.close(write_fd)
                os._exit(0)
            os.close(write_fd)
            self.assertTrue(select.select([read_fd], [], [], 1)[0], 'child cancellation entered a copied mutex')
            facts = json.loads(os.read(read_fd, 4096))
            _, status = os.waitpid(child, 0)
            reaped = True
            self.assertEqual(os.waitstatus_to_exitcode(status), 0)
            self.assertEqual(facts, {'returned_none': True, 'cancelled': False, 'copied_mutex_still_held': True})
            self.assertFalse(token.cancelled)
            self.assertTrue(token._io_lock.locked(), 'child released the parent mutex')
        finally:
            if child and not reaped:
                waited, _ = os.waitpid(child, os.WNOHANG)
                if not waited:
                    os.kill(child, signal.SIGKILL)
                    os.waitpid(child, 0)
            token._io_lock.release()
            os.close(read_fd)
            if child is None:
                os.close(write_fd)

    def test_empty_socket_owner_constructor_interrupt_precedes_native_open(self):
        constructor = eg._SocketOwner.__init__
        for boundary, event_kind, line in (('call', 'call', None),
                ('first-line', 'line', source_line(constructor, 'self._owner_pid =')),
                ('return', 'return', None)):
            with self.subTest(boundary=boundary):
                fixture = Fixture()
                client, session = fixture.client()
                permit = client.issue_observation_permit(session, fixture.url())
                before = descriptor_inventory()
                fired = []
                def trace(frame, event, value):
                    if not fired and frame.f_code is constructor.__code__ and event == event_kind and (line is None or frame.f_lineno == line):
                        fired.append(True)
                        raise KeyboardInterrupt('empty socket owner')
                    return trace
                previous = sys.gettrace()
                try:
                    sys.settrace(trace)
                    with self.assertRaises(eg.EgressDenied) as caught:
                        client.observe(permit, session)
                    self.assertNotIsInstance(caught.exception, eg.EgressIndeterminate)
                    self.assertIsInstance(caught.exception.__cause__, KeyboardInterrupt)
                finally:
                    sys.settrace(previous)
                gc.collect()
                self.assertTrue(fired)
                self.assertEqual(descriptor_inventory(), before)
                self.assertNotIn(permit.operation_id, client._permits)
                self.assertEqual(client._active, {})
                self.assertEqual(fixture.dns_calls, [])
                self.assertEqual(fixture.http_calls, [])
                fixture.close()

    def test_closed_socket_owner_gc_never_closes_reused_foreign_descriptor(self):
        before = descriptor_inventory()
        fixture = Fixture()
        client, session = fixture.client()
        permit = client.issue_observation_permit(session, fixture.url())
        retained, identities = [], []
        original = eg._tls
        def retain(*args, **kwargs):
            owner = original(*args, **kwargs)
            if args[2] == ONE:
                retained.append(owner)
                identities.append((owner.fileno(), weakref.ref(owner)))
            return owner
        foreign = None
        sentinel = os.open('/dev/null', os.O_RDONLY | os.O_CLOEXEC)
        try:
            with patch.object(eg, '_tls', retain):
                self.assertEqual(client.observe(permit, session).body, b'hello')
            descriptor, reference = identities[0]
            self.assertEqual(retained[0].fileno(), -1)
            os.dup2(sentinel, descriptor)
            foreign = descriptor
            retained[0].close()
            retained.clear()
            gc.collect()
            self.assertIsNone(reference(), 'tracked owner remained retained')
            self.assertEqual(os.fstat(foreign), os.fstat(sentinel))
        finally:
            if foreign is not None:
                os.close(foreign)
            os.close(sentinel)
            fixture.close()
        self.assertEqual(descriptor_inventory(), before)


if __name__ == '__main__':
    unittest.main()
