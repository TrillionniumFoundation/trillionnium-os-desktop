from __future__ import annotations

import hashlib
import importlib.util
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


if __name__ == '__main__':
    unittest.main()
