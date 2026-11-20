"""Authenticate one read-only native image observation to the actual daemon.

The response exposes observations only. It does not recreate ReadyTreeWitness
or transfer a daemon command permit to Python. Numeric PIDs are used only to
observe and hold the already selected service/returned init, never as a guest
command entry mechanism. The only request is Gallery's fixed read-only inspect.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import select
import socket
import stat
import struct
import time

SOCKET = '/run/droidloom/control.sock'
REQUEST = {'command': 'inspect_application', 'package': 'com.android.gallery3d', 'user': 0}
MAX_RESPONSE = 4 * 1024 * 1024
RESPONSE_SECONDS = 330
SCHEMA = 'pocket4-authenticated-native-main-observation-v1'
META = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
        'st_size', 'st_mtime_ns', 'st_ctime_ns')


def need(value, code):
    if not value:
        raise RuntimeError(code)


def metadata(fd):
    value = os.fstat(fd)
    return {key: getattr(value, key) for key in META}


def decode(raw):
    need(type(raw) is bytes and 0 < len(raw) <= MAX_RESPONSE, 'BOUNDED_NATIVE_MAIN_RESPONSE_REQUIRED')
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'DUPLICATE_NATIVE_MAIN_RESPONSE_FIELD')
            result[key] = value
        return result
    def nonfinite(_):
        raise RuntimeError('NONFINITE_NATIVE_MAIN_RESPONSE_NUMBER')
    return json.loads(raw.decode('utf-8', 'strict'), object_pairs_hook=pairs, parse_constant=nonfinite)


def validate_response(value, image_validator):
    need(type(value) is dict and set(value) == {'ok', 'state', 'message', 'host_pid', 'inspection', 'image_custody'}
         and value['ok'] is True and value['state'] == 'running'
         and type(value['message']) is str and 0 < len(value['message'].encode()) <= 8192
         and type(value['host_pid']) is int and value['host_pid'] > 1,
         'EXACT_CURRENT_RUNNING_NATIVE_INSPECTION_REQUIRED')
    inspection = value['inspection']
    need(type(inspection) is dict and type(inspection.get('epoch')) is dict
         and inspection['epoch'].get('cell_host_pid') == value['host_pid'],
         'NATIVE_RESPONSE_AND_IMAGE_OWNER_INIT_DIFFER')
    wrapped = {'operation': 'inspect_installed_application', 'observation': inspection,
               'image_custody': value['image_custody'], 'data_continuity_qualified': False,
               'production_ready': False, 'runtime_qualified': False, 'app_launches': 0}
    image_validator(wrapped, inspection['epoch'])
    need(value['image_custody']['owner']['cell_host_pid'] == value['host_pid'],
         'IMAGE_CUSTODY_MUST_NAME_THE_ACTUAL_NATIVE_INIT')
    return copy.deepcopy(value)


def validate_record(value, daemon_identity, daemon_file, image_validator, *, _status_init=None):
    """Pure record validation; it cannot mint a connection or native permit."""
    need(type(value) is dict and set(value) == {
        'schema', 'request', 'response', 'response_sha256', 'response_bytes',
        'daemon', 'daemon_executable', 'peer', 'socket', 'started_monotonic_ns',
        'finished_monotonic_ns', 'native_execution_authority_transferred',
        'runtime_qualified', 'business_qualified', 'production_ready'},
        'EXACT_AUTHENTICATED_NATIVE_MAIN_OBSERVATION_REQUIRED')
    expected_schema=SCHEMA if _status_init is None else 'pocket4-authenticated-native-status-observation-v1'
    expected_request=REQUEST if _status_init is None else {'command':'status'}
    need(value['schema'] == expected_schema and value['request'] == expected_request
         and value['daemon'] == daemon_identity
         and value['peer'] == {'pid': daemon_identity['host_pid'], 'uid': 0, 'gid': 0}
         and all(type(value['peer'][key]) is int for key in ('pid', 'uid', 'gid')),
         'OBSERVATION_MUST_BIND_THE_ORIGINAL_ROOT_DAEMON')
    need(all(value[key] is False for key in ('native_execution_authority_transferred',
             'runtime_qualified', 'business_qualified', 'production_ready')),
         'NATIVE_MAIN_READ_HAS_NO_EXECUTION_OR_RELEASE_CREDIT')
    need(type(value['response_sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['response_sha256'])
         and type(value['response_bytes']) is int and 0 < value['response_bytes'] <= MAX_RESPONSE
         and all(type(value[key]) is int for key in ('started_monotonic_ns', 'finished_monotonic_ns'))
         and 0 < value['started_monotonic_ns'] < value['finished_monotonic_ns']
         and value['finished_monotonic_ns'] - value['started_monotonic_ns'] <= 390_000_000_000,
         'BOUNDED_ACTUAL_NATIVE_RESPONSE_OBSERVATION_REQUIRED')
    executable = value['daemon_executable']
    need(type(executable) is dict and set(executable) == {'path', 'bytes', 'sha256', 'file'}
         and all(executable[key] == daemon_file[key] for key in ('path', 'bytes', 'sha256')),
         'NATIVE_RESPONSE_DAEMON_MUST_MATCH_INSTALLED_RELEASE')
    info = executable['file']
    need(type(info) is dict and set(info) == set(META)
         and all(type(item) is int for item in info.values())
         and stat.S_ISREG(info['st_mode']) and info['st_uid'] == info['st_gid'] == 0
         and info['st_nlink'] == 1 and info['st_mode'] & 0o022 == 0
         and info['st_size'] == executable['bytes']
         and (info['st_dev'], info['st_ino']) == (daemon_file['device'], daemon_file['inode']),
         'RUNNING_AND_INSTALLED_DAEMON_INODES_DIFFER')
    sock = value['socket']
    need(type(sock) is dict and set(sock) == {'path', 'file'} and sock['path'] == SOCKET,
         'FIXED_NATIVE_CONTROL_SOCKET_REQUIRED')
    info = sock['file']
    need(type(info) is dict and set(info) == set(META)
         and all(type(item) is int for item in info.values())
         and stat.S_ISSOCK(info['st_mode']) and info['st_uid'] == info['st_gid'] == 0
         and info['st_nlink'] == 1 and stat.S_IMODE(info['st_mode']) == 0o666
         and info['st_dev'] > 0 and info['st_ino'] > 0,
         'ORIGINAL_ROOT_SOCKET_INODE_REQUIRED')
    if _status_init is None:
        validate_response(value['response'], image_validator)
    else:
        status=value['response']
        need(type(status) is dict and set(status)=={'ok','state','message','host_pid'}
             and status['ok'] is True and status['state']=='running'
             and type(status['message']) is str and len(status['message'].encode())<=8192
             and type(status['host_pid']) is int and status['host_pid']==_status_init['host_pid'],
             'ORIGINAL_NATIVE_MAIN_NO_LONGER_RUNNING')
    return copy.deepcopy(value)


def _pidfd_live(fd):
    poller = select.poll()
    poller.register(fd, select.POLLIN | select.POLLHUP | select.POLLERR)
    need(not poller.poll(0), 'ORIGINAL_DAEMON_PIDFD_EXITED')


def _hash_exe(fd, expected):
    before = metadata(fd)
    need(stat.S_ISREG(before['st_mode']) and before['st_nlink'] == 1
         and before['st_uid'] == before['st_gid'] == 0 and before['st_mode'] & 0o022 == 0
         and 0 < before['st_size'] == expected['bytes'] <= 256 * 1024 * 1024,
         'ROOT_OWNED_INSTALLED_NATIVE_DAEMON_REQUIRED')
    os.lseek(fd, 0, os.SEEK_SET)
    digest, count, deadline = hashlib.sha256(), 0, time.monotonic() + 20
    while True:
        need(time.monotonic() < deadline, 'DAEMON_EXECUTABLE_HASH_DEADLINE')
        raw = os.read(fd, min(131072, before['st_size'] + 1 - count))
        if not raw:
            break
        count += len(raw)
        need(count <= before['st_size'], 'DAEMON_EXECUTABLE_GREW')
        digest.update(raw)
    need(count == before['st_size'] and metadata(fd) == before and digest.hexdigest() == expected['sha256'],
         'RUNNING_DAEMON_DIFFERS_FROM_ADMITTED_INSTALLED_BYTES')
    return {'path': '/usr/bin/droidloomd', 'bytes': count, 'sha256': digest.hexdigest(), 'file': before}


def inspect(daemon_identity, daemon_file, epoch, host_guard, image_validator):
    return _observe(daemon_identity,daemon_file,epoch,host_guard,image_validator)


def status(daemon_identity, daemon_file, epoch, host_guard, init_identity):
    """Revocation observation only, before spawn or after actual child reap.

    This does not replace native dispatch's two real InspectApplication calls.
    It has no skip-status mode and admits no command supplied by a request.
    """
    return _observe(daemon_identity,daemon_file,epoch,host_guard,None,_status_init=init_identity)


def require_peer(stream, daemon_pid):
    peer=struct.unpack('3i',stream.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,struct.calcsize('3i')))
    need(peer==(daemon_pid,0,0),'NATIVE_SOCKET_PEER_IS_NOT_THE_HELD_ROOT_SYSTEMD_DAEMON')
    return peer


def _observe(daemon_identity, daemon_file, epoch, host_guard, image_validator, *, _status_init=None):
    """Read once through an actual same-peer socket and return unqualified facts.

    host_guard is the caller's pinned Main factory callback: it rechecks the
    same droidloomd systemd invocation, fixed resource limits and installed
    payload manifest. It is never supplied by a JSON request.
    """
    need(os.getuid() == os.geteuid() == 0, 'EXISTING_ROOT_MAIN_OBSERVER_REQUIRED')
    need(daemon_file['path'] == '/usr/bin/droidloomd'
         and type(daemon_file['bytes']) is int and type(daemon_file['sha256']) is str
         and re.fullmatch('[0-9a-f]{64}', daemon_file['sha256'])
         and daemon_identity['executable'] == '/usr/bin/droidloomd'
         and daemon_identity['uids'] == [0] * 4,
         'EXACT_SELECTED_NATIVE_DAEMON_REQUIRED')
    pid = daemon_identity['host_pid']
    need(type(pid) is int and pid > 1, 'ACTUAL_SYSTEMD_DAEMON_PID_REQUIRED')
    fds, stream = [], None
    def own(fd):
        fds.append(fd)
        need(fd >= 3 and not os.get_inheritable(fd), 'PRIVATE_NATIVE_OBSERVATION_DESCRIPTOR_REQUIRED')
        return fd
    before_guard = host_guard()
    request=REQUEST if _status_init is None else {'command':'status'}
    response_seconds=RESPONSE_SECONDS if _status_init is None else 8
    schema=SCHEMA if _status_init is None else 'pocket4-authenticated-native-status-observation-v1'
    started = time.monotonic_ns()
    try:
        need(epoch.process_identity(pid) == daemon_identity, 'DAEMON_CHANGED_BEFORE_SOCKET_OBSERVATION')
        pidfd = own(os.pidfd_open(pid, 0))
        proc = own(os.open('/proc/' + str(pid), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC))
        exe = own(os.open('exe', os.O_RDONLY | os.O_CLOEXEC, dir_fd=proc))
        original_exe = _hash_exe(exe, daemon_file)
        _pidfd_live(pidfd)
        host_user = own(os.open('/proc/self/ns/user', os.O_RDONLY | os.O_CLOEXEC))
        daemon_user = own(os.open('ns/user', os.O_RDONLY | os.O_CLOEXEC, dir_fd=proc))
        need((os.fstat(host_user).st_dev, os.fstat(host_user).st_ino) ==
             (os.fstat(daemon_user).st_dev, os.fstat(daemon_user).st_ino),
             'DAEMON_MUST_REMAIN_IN_THE_ORIGINAL_HOST_USER_NAMESPACE')
        run = own(os.open('/run', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC))
        directory = own(os.open('droidloom', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                dir_fd=run))
        for fd in (run, directory):
            info = os.fstat(fd)
            need(stat.S_ISDIR(info.st_mode) and info.st_uid == info.st_gid == 0 and info.st_mode & 0o022 == 0,
                 'ROOT_OWNED_SEALED_NATIVE_SOCKET_PARENT_REQUIRED')
        node = own(os.open('control.sock', os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory))
        node_before = metadata(node)
        need(stat.S_ISSOCK(node_before['st_mode']) and node_before['st_uid'] == node_before['st_gid'] == 0
             and node_before['st_nlink'] == 1 and stat.S_IMODE(node_before['st_mode']) == 0o666,
             'ORIGINAL_ROOT_NATIVE_CONTROL_SOCKET_REQUIRED')
        def recheck():
            _pidfd_live(pidfd)
            need(epoch.process_identity(pid) == daemon_identity and host_guard() == before_guard,
                 'ORIGINAL_DAEMON_OR_SERVICE_GENERATION_CHANGED')
            need(metadata(exe) == original_exe['file'], 'RUNNING_DAEMON_EXECUTABLE_CHANGED')
            named = os.stat('control.sock', dir_fd=directory, follow_symlinks=False)
            need({key: getattr(named, key) for key in META} == node_before == metadata(node),
                 'ORIGINAL_CONTROL_SOCKET_REPLACED')
            need(Path('/run').resolve() == Path('/run') and Path('/run/droidloom').resolve() == Path('/run/droidloom'),
                 'CANONICAL_NATIVE_SOCKET_PARENT_CHANGED')
            for path, fd in (('/run', run), ('/run/droidloom', directory)):
                actual, held = os.stat(path, follow_symlinks=False), os.fstat(fd)
                need((actual.st_dev, actual.st_ino, actual.st_uid, actual.st_gid, actual.st_mode) ==
                     (held.st_dev, held.st_ino, held.st_uid, held.st_gid, held.st_mode),
                     'NATIVE_SOCKET_PARENT_CHANGED')
            current = own(os.open('ns/user', os.O_RDONLY | os.O_CLOEXEC, dir_fd=proc))
            try:
                need((os.fstat(current).st_dev, os.fstat(current).st_ino) ==
                     (os.fstat(host_user).st_dev, os.fstat(host_user).st_ino),
                     'DAEMON_LEFT_ORIGINAL_HOST_USER_NAMESPACE')
            finally:
                os.close(current); fds.remove(current)
        recheck()
        stream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM | socket.SOCK_CLOEXEC)
        stream.settimeout(2)
        stream.connect('/proc/self/fd/' + str(directory) + '/control.sock')
        peer = require_peer(stream,pid)
        recheck()
        encoded = json.dumps(request, separators=(',', ':')).encode()
        stream.sendall(encoded)
        stream.shutdown(socket.SHUT_WR)
        end = time.monotonic() + response_seconds
        chunks, count = [], 0
        while True:
            remaining = end - time.monotonic()
            need(remaining > 0, 'NATIVE_MAIN_OBSERVATION_ABSOLUTE_DEADLINE')
            stream.settimeout(min(remaining, 10))
            try:
                raw = stream.recv(min(65536, MAX_RESPONSE + 1 - count))
            except socket.timeout:
                _pidfd_live(pidfd)
                continue
            if not raw:
                break
            count += len(raw)
            need(count <= MAX_RESPONSE, 'NATIVE_MAIN_RESPONSE_EXCEEDED_BOUND')
            chunks.append(raw)
        raw = b''.join(chunks)
        response = decode(raw)
        if _status_init is None:validate_response(response,image_validator)
        need(require_peer(stream,pid) == peer,
             'NATIVE_RESPONSE_PEER_CHANGED')
        recheck()
        need(_hash_exe(exe, daemon_file) == original_exe, 'DAEMON_EXECUTABLE_CHANGED_DURING_INSPECTION')
        finished = time.monotonic_ns()
        result = {'schema': schema, 'request': copy.deepcopy(request),
                'response': response, 'response_sha256': hashlib.sha256(raw).hexdigest(), 'response_bytes': len(raw),
                'daemon': copy.deepcopy(daemon_identity), 'daemon_executable': original_exe,
                'peer': {'pid': peer[0], 'uid': peer[1], 'gid': peer[2]},
                'socket': {'path': SOCKET, 'file': node_before},
                'started_monotonic_ns': started, 'finished_monotonic_ns': finished,
                'native_execution_authority_transferred': False, 'runtime_qualified': False,
                'business_qualified': False, 'production_ready': False}
        validate_record(result, daemon_identity, daemon_file, image_validator,_status_init=_status_init)
        return result
    finally:
        if stream is not None:
            stream.close()
        failures = []
        for fd in reversed(fds):
            try:
                os.close(fd)
            except OSError as error:
                failures.append(error)
        if failures:
            raise RuntimeError('NATIVE_MAIN_OBSERVATION_FD_CLOSE_FAILED') from failures[0]
