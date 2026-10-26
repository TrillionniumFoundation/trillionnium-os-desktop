#!/usr/bin/env python3
"""Prepare an original Root native profile from an actual local login session.

This is an explicit Root administrator/provider entry. It does not initialize
authority, create a writer/thread, read provider credentials, issue a grant, or
replace the original Root launcher's checks. The daemon pidfd must be inherited
from the original supervisor, never rediscovered by this program.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import select
import stat
import subprocess
import sys
import time

LOGINCTL = Path('/usr/bin/loginctl')
SYSTEM_BUS = Path('/run/dbus/system_bus_socket')
MAX_BYTES = 65536
MAX_LIFETIME_MS = 300000
TEMPLATE_KEYS = {'schema_version', 'program', 'program_sha256', 'arguments',
                 'working_directory', 'environment', 'socket_path', 'route',
                 'human_lifetime_ms', 'can_interrupt', 'can_resolve_approvals'}
SESSION_FIELDS = ('Id', 'User', 'Active', 'State', 'Remote', 'Class', 'Type',
                  'Leader', 'Seat')


class Refused(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise Refused(message)


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON field')
        result[key] = value
    return result


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(',', ':')) + '\n').encode()


def stable_metadata(info):
    # Reading may advance atime. Changes to the object or its contents do not.
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def sync_parent(path):
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def private_parent(path):
    require(path.is_absolute() and path.resolve(strict=True) == path,
            'Protected parent must be absolute and canonical')
    info = path.stat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0
            and stat.S_IMODE(info.st_mode) == 0o700,
            'Root0700 protected parent is required')


def read_root_json(path):
    path = Path(path)
    private_parent(path.parent)
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 0
                and stat.S_IMODE(before.st_mode) == 0o600 and before.st_nlink == 1,
                'Root0600 regular single-link configuration is required')
        require(0 < before.st_size <= MAX_BYTES, 'Configuration size bound')
        data = os.read(descriptor, MAX_BYTES + 1)
        after = os.fstat(descriptor)
        require(len(data) == before.st_size and stable_metadata(before) == stable_metadata(after),
                'Configuration changed while reading')
        result = json.loads(data, object_pairs_hook=no_duplicates)
        require(isinstance(result, dict), 'Configuration must be an object')
        return result
    finally:
        os.close(descriptor)


def trusted_program(path, expected_sha256=None):
    path = Path(path)
    require(path.is_absolute() and path.resolve(strict=True) == path,
            'Trusted program must be absolute and canonical')
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == 0
                and not info.st_mode & 0o022 and info.st_mode & 0o111,
                'Trusted program must be Root-owned and not shared writable')
        if expected_sha256 is not None:
            require(re.fullmatch('[0-9a-f]{64}', expected_sha256) is not None,
                    'Full trusted executable digest required')
            with os.fdopen(os.dup(descriptor), 'rb') as stream:
                require(hashlib.file_digest(stream, 'sha256').hexdigest() == expected_sha256,
                        'Trusted executable digest mismatch')
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def loginctl(arguments):
    info = SYSTEM_BUS.stat()
    require(stat.S_ISSOCK(info.st_mode) and info.st_uid == 0,
            'Original Root-owned system bus is required')
    program = trusted_program(LOGINCTL)
    try:
        # Execute the checked inode, not another pathname resolved after checking.
        result = subprocess.run([str(LOGINCTL), *arguments, '--no-pager'],
                                executable=f'/proc/self/fd/{program}',
                                pass_fds=(program,), capture_output=True, timeout=3,
                                env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C',
                                     'DBUS_SYSTEM_BUS_ADDRESS': 'unix:path=/run/dbus/system_bus_socket'})
        require(result.returncode == 0 and len(result.stdout) <= MAX_BYTES,
                'Original logind query failed or exceeded its bound')
        return result.stdout.decode('utf-8', errors='strict')
    finally:
        os.close(program)


def validate_session(properties, expected_uid):
    require(type(expected_uid) is int and 0 < expected_uid < 2**32,
            'An actual non-Root daemon owner UID is required')
    require(set(properties) == set(SESSION_FIELDS), 'Incomplete logind properties')
    require(re.fullmatch('[A-Za-z0-9_-]{1,64}', properties['Id']) is not None,
            'Invalid original logind session identity')
    require(properties['User'] == str(expected_uid)
            and properties['Active'] == 'yes' and properties['State'] == 'active'
            and properties['Remote'] == 'no' and properties['Class'] == 'user'
            and properties['Type'] in ('x11', 'wayland') and properties['Seat'],
            'A live local physical login for the original daemon UID is required')
    require(properties['Leader'].isdigit() and 1 < int(properties['Leader']) < 2**31,
            'An actual logind leader is required')
    return dict(properties)


def local_session(expected_uid, selected=None):
    candidates = []
    for row in loginctl(['list-sessions', '--no-legend']).splitlines():
        fields = row.split()
        if len(fields) < 2 or fields[1] != str(expected_uid):
            continue
        session_id = fields[0]
        require(re.fullmatch('[A-Za-z0-9_-]{1,64}', session_id) is not None,
                'Invalid logind session listing')
        if selected is not None and session_id != selected:
            continue
        text = loginctl(['show-session', session_id, '--property=' + ','.join(SESSION_FIELDS)])
        properties = no_duplicates(line.split('=', 1) for line in text.splitlines() if '=' in line)
        try:
            candidates.append(validate_session(properties, expected_uid))
        except Refused:
            continue
    require(len(candidates) == 1, 'Exactly one eligible original local human session is required')
    return candidates[0]


def process_start_ticks(pid):
    raw = Path(f'/proc/{pid}/stat').read_text()
    fields = raw.rpartition(')')[2].split()
    require(len(fields) > 19, 'Incomplete actual process stat')
    return int(fields[19])


def alive(descriptor):
    poll = select.poll()
    poll.register(descriptor, select.POLLIN | select.POLLHUP | select.POLLERR)
    require(not poll.poll(0), 'Original process lifetime has ended')


def inherited_owner(descriptor, registration):
    require(type(descriptor) is int and descriptor >= 0, 'Inherited original owner pidfd required')
    require(type(registration.get('peer_pid')) is int
            and 1 < registration['peer_pid'] < 2**31,
            'Original registered daemon PID is required')
    text = Path(f'/proc/self/fdinfo/{descriptor}').read_text()
    pids = [line.split(':', 1)[1].strip() for line in text.splitlines() if line.startswith('Pid:')]
    require(pids == [str(registration.get('peer_pid'))],
            'Inherited pidfd does not name the original registered daemon')
    alive(descriptor)


def profile_from_verified_session(template, config, session, machine_id, boot_id, leader_ticks, now):
    require(set(template) == TEMPLATE_KEYS and type(template['schema_version']) is int
            and template['schema_version'] == 1,
            'Exact native template required; human identity is not template input')
    require(re.fullmatch('[0-9a-f]{32}', machine_id) is not None
            and re.fullmatch('[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot_id) is not None,
            'Actual machine and boot identities required')
    require(type(leader_ticks) is int and leader_ticks > 0
            and type(now) is int and now > 0, 'Actual leader lifetime and clock required')
    require(type(template['human_lifetime_ms']) is int
            and 1 <= template['human_lifetime_ms'] <= MAX_LIFETIME_MS,
            'Human profile has a five-minute maximum lifetime')
    require(type(template['can_interrupt']) is bool
            and type(template['can_resolve_approvals']) is bool,
            'Explicit administrator permission choices required')
    require(type(config.get('peer_uid')) is int and config['peer_uid'] > 0,
            'Original registered daemon owner required')
    validate_session(session, config['peer_uid'])
    writer = config.get('writer')
    require(isinstance(writer, dict), 'Original protected writer configuration required')
    lease = writer.get('authority_lease')
    require(isinstance(lease, dict), 'Original protected writer lease required')
    revision = lease.get('revision')
    expiry = lease.get('expires_at_unix_ms')
    require(type(revision) is int and revision > 0 and type(expiry) is int and expiry > now,
            'Original live writer lease is required')
    profile = {name: template[name] for name in TEMPLATE_KEYS
               if name not in ('human_lifetime_ms',)}
    profile.update(principal_id='linux-user:' + hashlib.sha256(machine_id.encode()).hexdigest() + ':' + str(config['peer_uid']),
                   session_id='logind:' + boot_id + ':' + session['Id'] + ':' + str(leader_ticks),
                   permission_revision=revision,
                   expires_at_ms=min(expiry, now + template['human_lifetime_ms']))
    require(len(profile['principal_id']) <= 128 and len(profile['session_id']) <= 128,
            'Original native human identity bound')
    return profile


def prepare(args):
    require(sys.platform == 'linux' and os.geteuid() == 0,
            'Explicit original Root administrator execution is required')
    config = read_root_json(args.config)
    registration = read_root_json(args.registration)
    template = read_root_json(args.template)
    inherited_owner(args.owner_pidfd, registration)
    require(type(config.get('peer_uid')) is int and config['peer_uid'] > 0,
            'Original protected daemon UID required')
    session = local_session(config['peer_uid'], args.logind_session)
    leader = int(session['Leader'])
    start = process_start_ticks(leader)
    output = Path(args.output)
    private_parent(output.parent)
    require(not output.exists() and not output.is_symlink(), 'Provider never replaces an existing profile')
    pending = output.with_name('.' + output.name + '.pending-' + os.urandom(16).hex())
    with ExitStack() as resources:
        leader_fd = os.pidfd_open(leader, 0)
        resources.callback(os.close, leader_fd)
        program = trusted_program(args.authority_host, args.authority_host_sha256)
        resources.callback(os.close, program)
        # Only this invocation may create the unpredictable pending pathname.
        # A preexisting pathname is never deleted on failure.
        pending_created = False
        try:
            descriptor = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                                 | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
            os.close(descriptor)
            pending_created = True
            return prepare_profile(args, config, registration, template, session,
                                   leader, start, leader_fd, program, output, pending)
        finally:
            if pending_created:
                pending.unlink(missing_ok=True)


def prepare_profile(args, config, registration, template, session, leader, start,
                    leader_fd, program, output, pending):
    # Inputs to this helper were obtained by prepare from the actual system bus
    # and Root-protected files. It is not a separate trust or command entry.
    alive(leader_fd)
    profile = profile_from_verified_session(template, config, session,
                Path('/etc/machine-id').read_text().strip(),
                Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                start, time.time_ns() // 1_000_000)
    descriptor = os.open(pending, os.O_WRONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == 0
                and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
                and info.st_size == 0, 'Pending profile changed before writing')
        data = canonical(profile)
        with os.fdopen(os.dup(descriptor), 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)
    sync_parent(pending)
    result = subprocess.run([str(args.authority_host), 'diagnose-native',
                '--config', str(args.config), '--registration', str(args.registration),
                '--native-profile', str(pending), '--owner-pidfd-stdin'],
                executable=f'/proc/self/fd/{program}', pass_fds=(program,),
                stdin=args.owner_pidfd, capture_output=True, timeout=10,
                env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'})
    require(result.returncode == 0 and len(result.stdout) <= MAX_BYTES,
            'Original Root native diagnostic refused the prepared profile')
    diagnostic = json.loads(result.stdout, object_pairs_hook=no_duplicates)
    require(isinstance(diagnostic, dict)
            and diagnostic.get('protected_existing_inputs_verified') is True
            and diagnostic.get('original_daemon_lifetime_verified') is True
            and diagnostic.get('supplied_human_profile_within_writer_lease') is True
            and diagnostic.get('authority_state_opened') is False
            and diagnostic.get('production_ready') is False,
            'Unexpected original Root diagnostic scope')
    require(local_session(config['peer_uid'], session['Id']) == session
            and process_start_ticks(leader) == start,
            'Actual human session changed during preparation')
    inherited_owner(args.owner_pidfd, registration)
    alive(leader_fd)
    # link is no-replace. A concurrent consumer rejects the temporary
    # two-link interval; only the final single-link profile is acceptable.
    os.link(pending, output, follow_symlinks=False)
    pending.unlink()
    sync_parent(output)
    return {'schema': 'trill.original-root-native-human-provider.v1',
            'human_source': 'actual_local_systemd_logind_session',
            'source_session_id': session['Id'], 'source_uid': config['peer_uid'],
            'source_type': session['Type'], 'source_leader_start_ticks': start,
            'profile_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'original_daemon_pidfd_verified': True,
            'original_writer_lease_bound': True,
            'authority_initialized_or_renewed': False,
            'provider_credentials_read': False,
            'model_invoked': False, 'production_ready': False,
            'scope': 'Authenticated local-login capture and original native-profile preflight only; the original launch/Root/model/operation gates remain required.'}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--registration', type=Path, required=True)
    parser.add_argument('--template', type=Path, required=True)
    parser.add_argument('--authority-host', type=Path, required=True)
    parser.add_argument('--authority-host-sha256', required=True)
    parser.add_argument('--owner-pidfd', type=int, default=0)
    parser.add_argument('--logind-session')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args), sort_keys=True))
    except (Refused, OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(json.dumps({'error': str(error), 'production_ready': False}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
