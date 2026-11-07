"""Owned local files/IPC only; no device, Main, namespace, or lifecycle run.

LocalCapture replaces only the external init/peer admission with an explicit
seam. It does not qualify that admission or the reference Android protocol.
"""
import array
import errno
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import stat
import struct
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'candidate/source/crash_log.py'
spec = importlib.util.spec_from_file_location('private_crash_control_module', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
CLOSE = os.close
WRITE = os.write
rows = []


def need(value, message):
    if not value:
        raise AssertionError(message)


def closed(fd):
    try:
        os.fstat(fd)
    except OSError as error:
        return error.errno == errno.EBADF
    return False


def packet(lid=4, tag=b'DEBUG', message=b'synthetic control only'):
    payload = b'\x06' + tag + b'\0' + message + b'\0'
    return module.HEADER.pack(len(payload), 28, 17, 19, 123, 456, lid, 1000) + payload


class LocalCapture(module.Capture):
    def _bind_init(self, audit):
        self.record['external_init_admission_test_seam'] = True


class Fixture:
    def __enter__(self):
        self.directory = tempfile.TemporaryDirectory(prefix='owned-crash-prefix-control-')
        self.fd = os.open(self.directory.name, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        self.capture = LocalCapture(None, {'nonce': '1' * 64}, {}, self.fd,
                                    SimpleNamespace(), time.monotonic() + 5)
        need(self.capture.record['first_error'] is None, 'local output construction failed')
        return self

    def __exit__(self, *_):
        try:
            if not self.capture.finished:
                self.capture.finish('owned control teardown')
        finally:
            CLOSE(self.fd)
            self.directory.cleanup()

    def body(self):
        return (Path(self.directory.name) / module.OUTPUT).read_bytes()


def run(name, fn):
    begin = time.monotonic_ns()
    try:
        detail = fn()
        rows.append({'name': name, 'state': 'PASS', 'detail': detail,
                     'elapsed_ns': time.monotonic_ns() - begin})
    except BaseException as error:
        rows.append({'name': name, 'state': 'FAIL', 'error': repr(error),
                     'elapsed_ns': time.monotonic_ns() - begin})


def parser():
    value = module.packet_header(packet())
    need(value['buffer'] == 4 and value['public_tag'] == 'DEBUG', 'valid reference packet refused')
    rejected = []
    for label, data in [('wrong_buffer', packet(lid=0)), ('truncated', packet()[:-1]),
                        ('wrong_header', packet()[:2] + b'\x20\0' + packet()[4:]),
                        ('missing_terminator', packet()[:-1] + b'x')]:
        try:
            module.packet_header(data)
        except RuntimeError:
            rejected.append(label)
        else:
            raise AssertionError(label + ' was accepted')
    unknown = module.packet_header(packet(tag=b'private-tag'))
    need(unknown['public_tag'] is None and unknown['tag_sha256'] == hashlib.sha256(b'private-tag').hexdigest(),
         'unknown tag was disclosed or hash changed')
    return {'negative_inputs_rejected': rejected, 'actual_android_protocol_qualified': False}


def partial_file():
    with Fixture() as f:
        capture = f.capture
        initial = f.body()
        calls = []
        def short_then_fail(fd, raw):
            calls.append(fd)
            if len(calls) == 1:
                return WRITE(fd, raw[:3])
            raise OSError(errno.EIO, 'injected owned-file write failure')
        try:
            with patch.object(module.os, 'write', short_then_fail):
                capture._write(b'abcdef')
        except OSError as error:
            need(error.errno == errno.EIO, 'write first errno lost')
            capture._failure('owned_control_write', error)
        else:
            raise AssertionError('write failure disappeared')
        result = capture.finish('owned partial-file control')
        body = f.body()
        need(body == initial + b'abc' and result['held_fds_closed'] is True,
             'partial evidence or FD close differs')
        need(result['packet_file']['sha256'] == hashlib.sha256(body).hexdigest() and
             result['packet_file']['complete_packets_only'] is False and
             stat.S_IMODE((Path(f.directory.name) / module.OUTPUT).stat().st_mode) == 0o400,
             'partial prefix incorrectly qualified or not hash-bound')
        return {'partial_bytes_retained': 3, 'write_calls': len(calls), 'retry_after_error': False}


def walk_close_first_error():
    with Fixture() as f:
        capture = f.capture
        calls = []
        def close_then_fail(fd):
            calls.append(fd)
            CLOSE(fd)
            raise OSError(errno.EIO, 'injected close report after actual owned close')
        try:
            with patch.object(module.os, 'close', close_then_fail):
                capture._descendant(f.fd, ('does-not-exist',), 'controlled_walk')
        except FileNotFoundError as error:
            need(error.errno == errno.ENOENT and len(error.__notes__) == 1,
                 'walk ENOENT replaced by cleanup error')
            capture._failure('owned_control_walk', error)
        else:
            raise AssertionError('missing path was accepted')
        need(len(calls) == 1 and closed(calls[0]), 'walk close repeated or FD retained')
        result = capture.finish('owned walk close control')
        need(result['first_error']['errno'] == errno.ENOENT and result['first_error']['notes'] and
             result['held_fds_closed'] is False and not capture.fds,
             'uncertain close was falsely qualified')
        return {'primary_errno': errno.ENOENT, 'close_report_errno': errno.EIO,
                'actual_fd_closed': True, 'close_attempts': 1, 'all_close_success_claimed': False}


def duplicate_fd():
    with Fixture() as f:
        first = os.dup(f.fd); second = os.dup(f.fd)
        f.capture._take('duplicate_control', first)
        try:
            f.capture._take('duplicate_control', second)
        except RuntimeError:
            pass
        else:
            raise AssertionError('duplicate name accepted')
        need(closed(second) and not closed(first), 'duplicate ownership closed the wrong FD')
        result = f.capture.finish('owned duplicate control')
        need(closed(first) and result['held_fds_closed'], 'original owned FD did not close')
        return {'only_new_duplicate_closed_on_rejection': True}


def deadline_no_endpoint():
    with Fixture() as f:
        calls = []
        f.capture.deadline = time.monotonic() - 1
        f.capture._prepare_endpoint = lambda: calls.append('endpoint')
        f.capture.poll()
        result = f.capture.finish('owned admission deadline')
        need(not calls and result['connection_attempts'] == result['read_request_attempts'] == 0 and
             result['first_error']['stage'] == 'bounded_observation' and result['held_fds_closed'],
             'expired deadline admitted endpoint/connection')
        return {'endpoint_calls': 0, 'connection_calls': 0, 'request_calls': 0}


def first_error_finish():
    with Fixture() as f:
        f.capture._failure('original_control_error', OSError(errno.EPERM, 'primary'))
        with patch.object(module.os, 'fchmod', side_effect=OSError(errno.EIO, 'sealing failed')):
            result = f.capture.finish('owned finalization failure')
        need(result['first_error']['errno'] == errno.EPERM and
             result['secondary_errors'][0]['errno'] == errno.EIO and result['held_fds_closed'],
             'finalization replaced original error or failed to close')
        need(f.capture.finish('second call') is result and result['finish_reason'] == 'owned finalization failure',
             'finish was replayed')
        return {'primary_errno': errno.EPERM, 'secondary_errno': errno.EIO, 'finish_once': True}


def cell_uid_is_not_init_authority():
    snapshot = {'process': {'pid': 4242}, 'namespaces': [{'device': 1, 'inode': 2}] * 10,
                'executable': {'device': 3, 'inode': 4}, 'executable_sha256': 'a' * 64,
                'identity': {'uids': [61288] * 4, 'gids': [61288] * 4}}
    init = SimpleNamespace(snapshot=lambda: snapshot)
    audit = {'nonce': '1' * 64, 'records': [
        {'detail': {'event': 'init_hello', 'init': {k: snapshot[k] for k in
            ('process', 'namespaces', 'executable', 'executable_sha256')}}},
        {'detail': {'event': 'prepared', 'domain': {'device': 30, 'inode': 1}}}]}
    with tempfile.TemporaryDirectory(prefix='owned-init-uid-reject-') as directory:
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            with patch.object(module.os, 'open', side_effect=AssertionError('no FD acquisition after wrong init UID')):
                capture = module.Capture(init, audit, {}, fd, SimpleNamespace(), time.monotonic() + 1)
            result = capture.finish('wrong mapped-UID control')
            need(result['first_error']['stage'] == 'initial_binding' and
                 'unchanged initial-userns root' in result['first_error']['error'] and
                 result['connection_attempts'] == result['read_request_attempts'] == 0 and
                 result['held_fds_closed'] and list(Path(directory).iterdir()) == [],
                 'CellSpec UID was silently accepted as init authority')
            return {'synthetic_UID': 61288, 'identity_seam': True,
                    'new_FD_or_file': False, 'connection_or_send': False}
        finally:
            CLOSE(fd)


def peer_pidfd_unsupported_has_no_fallback():
    with Fixture() as f:
        calls = []
        class SocketSeam:
            def connect(self, path): calls.append('connect')
            def getsockopt(self, level, option, *rest):
                if option == socket.SO_PEERCRED:
                    return struct.pack('3i', 4243, 1036, 1036)
                need(option == module.SO_PEERPIDFD, 'unexpected socket option')
                calls.append('SO_PEERPIDFD')
                raise OSError(errno.ENOPROTOOPT, 'explicit unsupported-kernel seam')
            def send(self, *_): calls.append('send'); return len(module.COMMAND)
            def close(self): calls.append('close')
        f.capture.init = SimpleNamespace(value={'pid': 4242}, live=lambda: None)
        f.capture._take('socket_dir', os.dup(f.fd))
        f.capture._endpoint_unchanged = lambda: None  # Explicit external identity seam.
        try:
            with patch.object(module.socket, 'socket', return_value=SocketSeam()), \
                 patch.object(module.os, 'pidfd_open', side_effect=AssertionError('numeric fallback forbidden')):
                f.capture._connect_and_qualify()
        except OSError as error:
            need(error.errno == errno.ENOPROTOOPT, 'unsupported peer-pidfd first errno lost')
            f.capture._failure('owned_peer_pidfd_control', error)
        else:
            raise AssertionError('unsupported peer pidfd was accepted')
        result = f.capture.finish('unsupported peer-pidfd control')
        need(calls == ['connect', 'SO_PEERPIDFD', 'close'] and result['connection_attempts'] == 1 and
             result['read_request_attempts'] == 0 and not result['source_qualified_before_request'] and
             result['held_fds_closed'], 'unsupported peer pidfd caused send/reconnect/fallback')
        return {'explicit_socket_identity_seam': True, 'connection_admission_attempts': 1,
                'numeric_PID_fallback': False, 'read_requests': 0, 'error': 'ENOPROTOOPT'}


def protocol_raw_retained(pair):
    with Fixture() as f:
        reader, writer = pair()
        try:
            good, bad, unconsumed = packet(), packet(lid=0), packet(message=b'not consumed')
            for data in (good, bad, unconsumed):
                need(writer.send(data) == len(data), 'owned seqpacket send short')
            f.capture.sock = reader
            f.capture.poll()
            need(reader.recv(module.PACKET_LIMIT, socket.MSG_PEEK | socket.MSG_DONTWAIT) == unconsumed,
                 'a packet after the first protocol failure was read')
            result = f.capture.finish('owned protocol-rejection control')
            need(result['records'] == 1 and result['received_packets'] == 2 and result['first_error'] is not None,
                 'protocol failure was promoted')
            raw = f.body()
            expected = module.MAGIC + b'1' * 64 + b'\n' + struct.pack('<I', len(good)) + good + struct.pack('<I', len(bad)) + bad
            need(raw == expected and result['protocol_rejected_packet']['raw_packet_retained_in_private_file'] and
                 result['packet_file']['sha256'] == hashlib.sha256(raw).hexdigest() and result['held_fds_closed'],
                 'complete rejected packet not preserved or close incomplete')
            return {'accepted_packets': 1, 'rejected_complete_packets_retained': 1,
                    'subsequent_packet_left_unread': True, 'no_reconnect': True}
        finally:
            writer.close()
            reader.close()


def unexpected_rights(pair, zero_payload=False, close_error=False):
    reader, writer = pair()
    source = os.open(__file__, os.O_RDONLY | os.O_CLOEXEC)
    received = []
    try:
        payload = b'' if zero_payload else packet()
        need(writer.sendmsg([payload], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array('i', [source]))]) == len(payload),
             'owned rights send differs')
        def tracked_close(fd):
            received.append(fd)
            CLOSE(fd)
            if close_error:
                raise OSError(errno.EIO, 'injected received-FD close report')
        try:
            with patch.object(module.os, 'close', tracked_close):
                module.receive_packet(reader)
        except RuntimeError as error:
            need(isinstance(error, module.AncillaryCloseError) == close_error, 'wrong ancillary error class')
            if close_error:
                with Fixture() as f:
                    f.capture._failure('received_rights', error)
                    result = f.capture.finish('uncertain received-FD close')
                    need(result['held_fds_closed'] is False, 'received close uncertainty hidden')
        else:
            raise AssertionError('unexpected rights accepted, including empty-payload case')
        need(len(received) == 1 and closed(received[0]) and not closed(source), 'received rights close ownership differs')
        return {'received_descriptor_closed': True, 'original_descriptor_untouched': True,
                'zero_payload': zero_payload, 'close_failure_injected': close_error}
    finally:
        CLOSE(source); reader.close(); writer.close()


def main():
    source_before = SOURCE.read_bytes()
    for name, fn in [('reference_parser_and_negative_packets', parser),
                     ('partial_file_preserves_bytes_and_first_errno', partial_file),
                     ('walk_close_preserves_ENOENT', walk_close_first_error),
                     ('duplicate_fd_closes_only_new_owner', duplicate_fd),
                     ('expired_deadline_has_no_endpoint_or_request', deadline_no_endpoint),
                     ('finish_error_keeps_primary_and_is_once', first_error_finish),
                     ('CellSpec_UID_cannot_replace_actual_init_UID', cell_uid_is_not_init_authority),
                     ('unsupported_peer_pidfd_never_falls_back_or_sends', peer_pidfd_unsupported_has_no_fallback)]:
        run(name, fn)
    ipc = {'state': 'NOT_ATTEMPTED'}
    try:
        first = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC | socket.SOCK_NONBLOCK)
    except OSError as error:
        ipc = {'state': 'ENVIRONMENT_UNAVAILABLE', 'errno': error.errno, 'error': repr(error),
               'actual_IPC_controls_passed': False}
    else:
        first[0].close(); first[1].close()
        ipc = {'state': 'ACTUAL_OWNED_SEQPACKET_AVAILABLE'}
        pair = lambda: socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC | socket.SOCK_NONBLOCK)
        run('protocol_error_retains_one_bad_packet_and_stops', lambda: protocol_raw_retained(pair))
        run('received_rights_rejected_after_close', lambda: unexpected_rights(pair))
        run('empty_payload_rights_rejected_after_close', lambda: unexpected_rights(pair, True))
        run('received_close_error_never_claims_all_FDs_closed', lambda: unexpected_rights(pair, False, True))
    need(SOURCE.read_bytes() == source_before, 'source changed during controls')
    result = {'schema': 1, 'scope': 'LOCAL_OWNED_FILES_AND_IPC_WITH_EXPLICIT_EXTERNAL_ADMISSION_SEAM',
              'source_bytes': len(source_before), 'source_sha256': hashlib.sha256(source_before).hexdigest(),
              'rows': rows, 'ipc_environment': ipc, 'passed': sum(r['state'] == 'PASS' for r in rows),
              'failed': sum(r['state'] == 'FAIL' for r in rows), 'device_calls': 0,
              'real_peer_or_init_admission_qualified': False, 'Android_logdr_protocol_qualified': False,
              'Main_accessed': False, 'Owner_runtime_executed': False}
    body = (json.dumps(result, sort_keys=True, indent=2) + '\n').encode()
    (ROOT / 'controls/result-03.json').open('xb').write(body)
    print(json.dumps({'passed': result['passed'], 'failed': result['failed'], 'ipc': ipc,
                      'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}))
    return 1 if result['failed'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
