import base64
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import socket
import stat
import subprocess
import sys
import time

ROOT = Path('/home/alex/work/pocket4-android-final/qualification/camera-video-current-merged-20261108-8b88-r2')
BUNDLE = ROOT / 'source-bundle'
INVENTORY = '28e61371c50638a3ac33d4e28b0466754bc2b81c9f5d015f262d43e60243dd00'
TRANSFER = 'afc830b8fed505934e880071152ba4ccf9038a3771ad71eb580c0fec9aeae170'


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def ref(path):
    path = Path(path)
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def write_new(path, raw, mode=0o400):
    path = Path(path)
    if type(raw) is not bytes:
        raw = (json.dumps(raw, indent=2, sort_keys=True) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, mode)
    try:
        with os.fdopen(os.dup(fd), 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)
    return ref(path)


def run(label, argv, timeout):
    result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
    stdout = write_new(ROOT / (label + '.stdout'), result.stdout)
    stderr = write_new(ROOT / (label + '.stderr'), result.stderr)
    value = {'argv': argv, 'returncode': result.returncode, 'stdout': stdout, 'stderr': stderr}
    write_new(ROOT / (label + '-terminal.json'), value)
    need(result.returncode == 0, 'CURRENT_SOURCE_CONTROL_FAILED:' + label)
    return result, value


def absent_unit(unit):
    result = subprocess.run(['/usr/bin/systemctl', 'show', unit,
        '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup'],
        capture_output=True, text=True, timeout=10)
    fields = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    need(result.returncode in (0, 4) and fields.get('LoadState') == 'not-found'
         and fields.get('ActiveState') == 'inactive' and fields.get('SubState') == 'dead'
         and fields.get('MainPID') == '0' and fields.get('ControlGroup') == '',
         'OWNED_CURRENT_UNIT_NOT_ABSENT:' + unit)
    return fields


def run_unit(label, unit, command, cpu, affinity, tasks, nice):
    absent_unit(unit)
    properties = [f'CPUQuota={cpu}%', f'CPUAffinity={affinity}', 'MemoryMax=536870912',
        'MemorySwapMax=0', f'TasksMax={tasks}', f'Nice={nice}', 'RuntimeMaxSec=90',
        'TimeoutStartSec=10', 'TimeoutStopSec=10', 'KillMode=control-group',
        'NoNewPrivileges=yes', 'UMask=0077', 'Restart=no', 'MemoryAccounting=yes',
        'CPUAccounting=yes', 'TasksAccounting=yes']
    observed_names = ['RuntimeMaxUSec', 'TimeoutStartUSec', 'TimeoutStopUSec',
                      'KillMode', 'NoNewPrivileges', 'InvocationID', 'ControlGroup']
    properties.append('ExecStartPre=/usr/bin/systemctl show ' + unit
                      + ' --property=' + ','.join(observed_names))
    argv = ['/usr/bin/systemd-run', '--unit=' + unit, '--wait', '--pipe', '--collect',
            '--service-type=exec', '--working-directory=' + str(ROOT)]
    for value in properties:
        argv += ['--property=' + value]
    argv += command
    result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=120)
    stdout = write_new(ROOT / (label + '.stdout'), result.stdout)
    stderr = write_new(ROOT / (label + '.stderr'), result.stderr)
    # Every inner actor stays inside the explicitly bounded unit, including
    # failure paths. A successful client exit is not used as retirement proof.
    after = absent_unit(unit)
    text = result.stdout.decode('utf-8', 'strict')
    manager = {}
    for name in observed_names:
        values = re.findall('^' + name + '=(.*)$', text, re.M)
        need(len(values) == 1, 'ONE_ACTUAL_MANAGER_PROPERTY:' + name)
        manager[name] = values[0]
    need(manager['RuntimeMaxUSec'] == '1min 30s'
         and manager['TimeoutStartUSec'] == manager['TimeoutStopUSec'] == '10s'
         and manager['KillMode'] == 'control-group' and manager['NoNewPrivileges'] == 'yes'
         and manager['ControlGroup'] == '/system.slice/' + unit
         and re.fullmatch('[0-9a-f]{32}', manager['InvocationID']),
         'CURRENT_UNIT_MANAGER_LIMITS_MISMATCH')
    terminal = {'returncode': result.returncode, 'stdout': stdout, 'stderr': stderr,
                'actual_manager': manager, 'unit_after': after,
                'owned_unit_gone_observed': True, 'runtime_qualified': False}
    write_new(ROOT / (label + '-terminal.json'), terminal)
    need(result.returncode == 0, 'CURRENT_HOST_CONTROL_FAILED:' + label)
    return terminal


def main():
    need(os.getuid() == os.geteuid() == 0 and socket.gethostname() == 'alex-G1628-04',
         'ACTUAL_POCKET4_ROOT_REQUIRED')
    encoded = sys.stdin.buffer.read(1048577)
    need(len(encoded) <= 1048576, 'BOUNDED_TRANSFER_REQUIRED')
    raw = gzip.decompress(base64.b64decode(encoded, validate=True))
    need(len(raw) <= 2097152 and sha(raw) == TRANSFER, 'EXACT_CANONICAL_TRANSFER_REQUIRED')
    packet = json.loads(raw)
    need(packet['schema'] == 'current-camera-canonical-source-transfer-v2'
         and len(packet['files']) == 76, 'EXACT_CANONICAL_FILE_SET_REQUIRED')
    prepared = {}
    for name, row in packet['files'].items():
        relative = PurePosixPath(name)
        need(not relative.is_absolute() and '..' not in relative.parts
             and str(relative) == name and '\\' not in name, 'EXACT_RELATIVE_FILE_REQUIRED')
        if 'content' in row:
            data = row['content'].encode()
        else:
            old_bundle = Path('/home/alex/work/pocket4-android-final/qualification/camera-video-current-merged-20261108-8b88-r1/source-bundle')
            need(packet['old_bundle'] == str(old_bundle), 'EXACT_PREVIOUS_STAGED_SOURCE_ROOT_REQUIRED')
            prior = old_bundle / name
            need(prior.resolve(strict=True) == prior and stat.S_ISREG(prior.lstat().st_mode),
                 'REGULAR_HELD_SOURCE_REUSE_REQUIRED')
            data = prior.read_bytes()
        need(len(data) == row['bytes'] and sha(data) == row['sha256'], 'SOURCE_FILE_PIN_CHANGED')
        if relative.suffix == '.py':
            compile(data, name, 'exec')
        prepared[name] = data
    need(ROOT.parent.resolve(strict=True) == ROOT.parent
         and not ROOT.exists() and not ROOT.is_symlink(), 'CREATE_ONLY_CURRENT_GENERATION_REQUIRED')
    ROOT.mkdir(mode=0o700)
    BUNDLE.mkdir(mode=0o700)
    for name, data in prepared.items():
        target = BUNDLE / name
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        write_new(target, data)
    write_new(ROOT / 'source-transfer.json', {'sha256': TRANSFER, 'bytes': len(raw),
        'production_source_commit': packet['production_source_commit'],
        'additional_host_tools_published': False, 'file_count': len(prepared),
        'runtime_qualified': False, 'Main_actions': 0, 'Android_actions': 0})
    print(json.dumps({'state': 'CANONICAL_MERGED_SOURCE_STAGED', 'root': str(ROOT),
                      'file_count': len(prepared)}), flush=True)
    run('source38', ['/usr/bin/python3', '-I', '-B', str(BUNDLE / 'tests/run_current_source_controls.py'),
        '--report', str(ROOT / 'current-source-controls.json')], 45)
    source = json.loads((ROOT / 'current-source-controls.json').read_bytes())
    need(source['passed'] is True and source['tests_run'] == source['expected_tests'] == 38
         and source['source_bytes_unchanged'] is True and source['uid'] == source['euid'] == 0,
         'ALL_CURRENT_SOURCE_CONSTRUCTION_CONTROLS_REQUIRED')
    run('prepare', ['/usr/bin/python3', '-I', '-B', str(BUNDLE / 'tools/prepare_camera_video.py'),
        '--source', str(BUNDLE / 'source'), '--inventory', str(BUNDLE / 'reviewed-source-inventory.json'),
        '--expect-inventory-sha256', INVENTORY, '--output', str(ROOT / 'prepared')], 30)
    control = BUNDLE / 'host-controls/current_decoder'
    control_sha = sha((control / 'source-packet.json').read_bytes())
    unit = 'p4-camera-r4-decoder-host-canonical-8b88-20261108-r2.service'
    decoder_output = ROOT / 'camera-r4-decoder-host-qualification-current'
    decoder_terminal = run_unit('decoder8', unit,
        ['/usr/bin/python3', '-I', '-B', str(control / 'qualify_decoder_host.py'), 'qualify-host',
         '--packet', str(control / 'source-packet.json'), '--expect-packet-sha256', control_sha,
         '--source-dir', str(BUNDLE / 'source'), '--output-root', str(decoder_output),
         '--expected-cgroup', '/system.slice/' + unit], 100, 2, 128, 15)
    decoder = json.loads((decoder_output / 'qualification.json').read_bytes())
    need(decoder['host_component_qualified'] is True and len(decoder['controls']) == 8
         and not decoder['not_run'] and decoder['final_host_idle_checked'] is True,
         'ALL_CURRENT_CANONICAL_DECODER_CONTROLS_REQUIRED')
    display_unit = 'hepta-runtime-job-camera-current-display-8b88-20261108-r2.service'
    display_output = ROOT / 'owned-display-controls'
    display_terminal = run_unit('display4', display_unit,
        ['/usr/bin/python3', '-I', '-B', str(BUNDLE / 'tests/run_video_display_owned_controls.py'),
         '--output', str(display_output)], 50, 19, 64, 10)
    display = json.loads((display_output / 'result.json').read_bytes())
    need(display['passed'] is True and len(display['cases']) == 4
         and display['actual_display_qualified'] is False and display['runtime_qualified'] is False,
         'ALL_OWNED_DISPLAY_NEGATIVE_CONTROLS_REQUIRED')
    for name, data in prepared.items():
        need((BUNDLE / name).read_bytes() == data, 'CURRENT_BUNDLE_CHANGED_DURING_QUALIFICATION')
    result = {'schema': 'pocket4-camera-current-canonical-host-preparation-v1',
        'state': 'CURRENT_SOURCE38_DECODER8_DISPLAY4_AND_FORMAL_PREPARATION_PASSED',
        'source_controls': ref(ROOT / 'current-source-controls.json'),
        'preparation': ref(ROOT / 'prepared/preparation.json'),
        'source_inspection': ref(ROOT / 'prepared/source-inspection.json'),
        'decoder_qualification': ref(decoder_output / 'qualification.json'),
        'decoder_terminal': ref(ROOT / 'decoder8-terminal.json'),
        'display_controls': ref(display_output / 'result.json'),
        'display_terminal': ref(ROOT / 'display4-terminal.json'),
        'source_files_unchanged': True, 'prior_host_qualification_transferred': False,
        'real_display_qualified': False, 'Main_actions': 0, 'Android_actions': 0,
        'physical_audio_actions': 0, 'runtime_qualified': False,
        'whole_app_business_accepted': False}
    result_ref = write_new(ROOT / 'result.json', result)
    print(json.dumps({'state': result['state'], 'result': result_ref,
                      'runtime_qualified': False}), flush=True)


if __name__ == '__main__':
    main()
