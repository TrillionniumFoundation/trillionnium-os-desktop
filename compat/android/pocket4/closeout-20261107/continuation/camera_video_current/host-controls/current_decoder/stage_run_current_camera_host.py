#!/usr/bin/env python3
"""Stage one exact independent host-only source packet and run a bounded unit."""
import base64
import hashlib
import json
import lzma
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys

ROOT = Path('/home/alex/work/pocket4-camera-current-host-8b88-20261108-r2')
UNIT = 'p4-camera-r4-decoder-host-current-8b88-20261108-r2.service'
NAMES = {'qualify_decoder_host.py', 'source-packet.json',
    'source/camera_decode.py', 'source/camera_video_media.py', 'source/camera_audio_challenge.py'}


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_new(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o400)
    try:
        rest = memoryview(raw)
        while rest:
            count = os.write(fd, rest)
            need(count > 0, 'source transfer made no progress')
            rest = rest[count:]
        os.fsync(fd)
    finally:
        os.close(fd)


def checked_source(path, row):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 < before.st_size < 1048576,
             'bounded regular single-link exact source required')
        raw = os.read(fd, 1048576)
        after = os.fstat(fd)
        need((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
             == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
             'source changed during read')
    finally:
        os.close(fd)
    need(len(raw) == row['bytes'] and sha(raw) == row['sha256'], 'source pin differs: ' + str(path))
    return raw


def main():
    need(os.getuid() == os.geteuid() == 0 and socket.gethostname() == 'alex-G1628-04',
         'exact Pocket4 host and normal root authority required')
    encoded = sys.stdin.buffer.read(1048577)
    need(len(encoded) <= 1048576, 'bounded transfer required')
    compressed = base64.b64decode(encoded, validate=True)
    decoder = lzma.LZMADecompressor(format=lzma.FORMAT_XZ, memlimit=64 * 1024**2)
    raw = decoder.decompress(compressed, max_length=2 * 1024**2 + 1)
    need(len(raw) <= 2 * 1024**2 and decoder.eof and not decoder.unused_data,
         'bounded complete single XZ transfer required')
    transfer_sha = sha(raw)
    need(transfer_sha == sys.argv[1], 'exact externally reviewed transfer required')
    packet = json.loads(raw)
    need(packet['schema'] == 'camera-r4-independent-host-stage-v1'
         and set(packet['files']) == NAMES and packet['root'] == str(ROOT) and packet['unit'] == UNIT,
         'exact isolated staging scope required')
    need(ROOT.parent.resolve() == ROOT.parent and not ROOT.exists() and not ROOT.is_symlink(),
         'new exclusive own staging root required; reconcile an existing action')
    prior = subprocess.run(['/usr/bin/systemctl', 'show', UNIT, '--property=LoadState', '--value'],
                           capture_output=True, text=True, timeout=15)
    need(prior.stdout.strip() == 'not-found' and prior.returncode in (0, 1, 4), 'unit name is already owned')
    predecessor = subprocess.run(['/usr/bin/systemctl', 'show',
        'p4-camera-r4-decoder-host-347ef2-20261108-r1.service',
        '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup'],
        capture_output=True, text=True, timeout=15)
    previous_fields = dict(line.split('=', 1) for line in predecessor.stdout.splitlines() if '=' in line)
    need(predecessor.returncode in (0, 4)
        and previous_fields.get('LoadState') == 'not-found'
        and previous_fields.get('ActiveState') == 'inactive'
        and previous_fields.get('SubState') == 'dead'
        and previous_fields.get('MainPID') == '0'
        and previous_fields.get('ControlGroup') == '',
        'previous component unit must not be live during fresh current-source controls')
    available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
                         if line.startswith('MemAvailable:'))) * 1024
    need(available >= 2 * 1024**3, 'independent host control needs two GiB of fresh available margin')
    prepared = {}
    for relative, row in packet['files'].items():
        raw = row['content'].encode('utf-8')
        need(b'\x00' not in raw and len(raw) == row['bytes'] and sha(raw) == row['sha256'],
             'reviewed transfer bytes differ')
        if relative.endswith('.py'):
            compile(raw, relative, 'exec')
        prepared[relative] = raw
    control = json.loads(prepared['source-packet.json'])
    need(sha(prepared['source-packet.json']) == packet['control_packet_sha256'], 'exact control packet required')
    need(control['runner']['bytes'] == len(prepared['qualify_decoder_host.py'])
         and control['runner']['sha256'] == sha(prepared['qualify_decoder_host.py']), 'runner pin differs')
    for name, ref in control['production_sources'].items():
        need(name in ('camera_decode.py', 'camera_video_media.py', 'camera_audio_challenge.py'), 'unexpected component')
        data = prepared['source/' + name]
        need(len(data) == ref['bytes'] and sha(data) == ref['sha256'], 'production component changed')
    for ref in control['fixed_sources'].values():
        checked_source(ref['path'], ref)
    ROOT.mkdir(mode=0o700)
    (ROOT / 'source').mkdir(mode=0o700)
    for relative, data in prepared.items():
        write_new(ROOT / relative, data)
        checked_source(ROOT / relative, packet['files'][relative])
    output = ROOT / 'camera-r4-decoder-host-qualification-p4-r2'
    properties = ['CPUQuota=100%', 'CPUAffinity=2', 'MemoryMax=536870912', 'MemorySwapMax=0',
        'TasksMax=128', 'RuntimeMaxSec=90', 'TimeoutStartSec=10', 'TimeoutStopSec=10', 'KillMode=control-group',
        'Restart=no', 'NoNewPrivileges=yes', 'UMask=0077', 'Nice=15',
        'CPUAccounting=yes', 'MemoryAccounting=yes', 'TasksAccounting=yes']
    observed_properties = ['RuntimeMaxUSec', 'TimeoutStartUSec', 'TimeoutStopUSec', 'KillMode',
        'NoNewPrivileges', 'InvocationID', 'ControlGroup']
    properties.append('ExecStartPre=/usr/bin/systemctl show ' + UNIT
                      + ' --property=' + ','.join(observed_properties))
    argv = ['/usr/bin/systemd-run', '--unit=' + UNIT, '--wait', '--pipe', '--collect',
            '--service-type=exec', '--working-directory=' + str(ROOT)]
    for prop in properties:
        argv += ['--property=' + prop]
    argv += ['/usr/bin/python3', '-I', '-B', str(ROOT / 'qualify_decoder_host.py'), 'qualify-host',
             '--packet', str(ROOT / 'source-packet.json'), '--expect-packet-sha256', packet['control_packet_sha256'],
             '--source-dir', str(ROOT / 'source'), '--output-root', str(output),
             '--expected-cgroup', '/system.slice/' + UNIT]
    launch = {'schema': 'camera-r4-host-control-owned-launch-v1', 'unit': UNIT, 'argv': argv,
        'source_transfer_sha256': transfer_sha,
        'available_memory_before': available, 'Main_actions': 0, 'Android_actions': 0,
        'shared_locks_taken': 0, 'runtime_qualified': False,
        'previous_unit_observed_before': previous_fields,
        'previous_launch_unknown_terminal_inferred': False,
        'source_generation': 'merged-current-20261108-8b88-r1'}
    write_new(ROOT / 'launch.json', (json.dumps(launch, indent=2, sort_keys=True) + '\n').encode())
    print(json.dumps({'state': 'EXACT_HOST_COMPONENT_SOURCE_STAGED_STARTING_OWNED_UNIT',
                      'root': str(ROOT), 'unit': UNIT}), flush=True)
    try:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=125)
        out, err, code = result.stdout, result.stderr, result.returncode
        terminal = {'client_wait_timed_out': False, 'returncode': code}
    except subprocess.TimeoutExpired as error:
        out, err, code = error.stdout or b'', error.stderr or b'', None
        terminal = {'client_wait_timed_out': True, 'returncode': None,
            'state': 'UNKNOWN_CLIENT_TIMEOUT_RECONCILE_THIS_UNIT_DO_NOT_RESTART',
            'unit_retirement_inferred_from_client_exit': False}
    write_new(ROOT / 'systemd-run.stdout', out)
    write_new(ROOT / 'systemd-run.stderr', err)
    terminal.update(stdout={'bytes': len(out), 'sha256': sha(out)},
                    stderr={'bytes': len(err), 'sha256': sha(err)})
    manager = {}
    manager_ok = False
    try:
        text = out.decode('utf-8', 'strict')
        for name in observed_properties:
            values = re.findall('^' + name + '=(.*)$', text, re.M)
            need(len(values) == 1, 'one actual manager property required: ' + name)
            manager[name] = values[0]
        def usec(value):
            tokens = value.split()
            scale = {'us': 1, 'ms': 1000, 's': 1000000, 'min': 60000000, 'h': 3600000000}
            total = 0
            for token in tokens:
                match = re.fullmatch(r'([0-9]+)(us|ms|s|min|h)', token)
                need(match is not None, 'explicit finite manager duration required')
                total += int(match.group(1)) * scale[match.group(2)]
            need(bool(tokens), 'manager duration is empty')
            return total
        manager_ok = (usec(manager['RuntimeMaxUSec']) == 90000000
            and usec(manager['TimeoutStartUSec']) == 10000000
            and usec(manager['TimeoutStopUSec']) == 10000000
            and manager['KillMode'] == 'control-group' and manager['NoNewPrivileges'] == 'yes'
            and manager['ControlGroup'] == '/system.slice/' + UNIT
            and re.fullmatch('[0-9a-f]{32}', manager['InvocationID']) is not None)
    except (RuntimeError, UnicodeDecodeError) as error:
        terminal['manager_property_error'] = str(error)
    terminal['manager_properties_from_own_ExecStartPre'] = manager
    terminal['hard_unit_constraints_read_back'] = manager_ok
    gone = False
    try:
        after = subprocess.run(['/usr/bin/systemctl', 'show', UNIT, '--property=LoadState,ActiveState,SubState,MainPID,Result'],
                               capture_output=True, text=True, timeout=15)
        fields = dict(line.split('=', 1) for line in after.stdout.splitlines() if '=' in line)
        gone = (after.returncode in (0, 4) and fields.get('LoadState') == 'not-found'
                and fields.get('ActiveState') == 'inactive' and fields.get('SubState') == 'dead'
                and fields.get('MainPID') == '0')
        terminal['unit_after'] = {'exit_code': after.returncode, 'stdout': after.stdout, 'stderr': after.stderr}
    except subprocess.TimeoutExpired as error:
        terminal['unit_after'] = {'query_timed_out': True,
            'partial_stdout': (error.stdout or b'').decode('utf-8', 'replace'),
            'partial_stderr': (error.stderr or b'').decode('utf-8', 'replace')}
    terminal['owned_unit_gone_observed'] = gone
    terminal['owned_host_job_complete'] = code == 0 and gone and manager_ok
    if code == 0 and not gone:
        terminal['state'] = 'UNKNOWN_UNIT_RETIREMENT_RECONCILE_WITHOUT_RESTART'
    elif code == 0 and not manager_ok:
        terminal['state'] = 'HOST_UNIT_CONSTRAINT_READBACK_NOT_QUALIFIED'
    write_new(ROOT / 'launch-terminal.json', (json.dumps(terminal, indent=2, sort_keys=True) + '\n').encode())
    print(json.dumps({'state': 'OWNED_HOST_COMPONENT_UNIT_RETURNED', 'terminal': terminal,
                      'qualification_path': str(output / 'qualification.json'),
                      'runtime_qualified': False, 'whole_app_business_accepted': False}), flush=True)
    return 0 if terminal['owned_host_job_complete'] else (code if code else 1)


if __name__ == '__main__':
    raise SystemExit(main())
