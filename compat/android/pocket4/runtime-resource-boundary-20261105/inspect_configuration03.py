#!/usr/bin/python3 -I
"""Observe Main's configured task limit and systemd-manager reload history.

Read-only host queries only. No Android entry, service mutation, rebaseline,
process discovery, cgroup write, or existing-file modification is performed.
"""
from pathlib import Path
import datetime
import hashlib
import json
import os
import re
import stat
import subprocess
import types

ROOT = Path('/home/alex/work/pocket4-main-runtime-boundary-20261105-r12-03')
TX = Path('/home/alex/work/pocket4-camera-release08-20261105-r12/transaction-tools-01/camera_transaction.py')
TX_SHA = 'b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
ACTIVATION = Path('/home/alex/work/pocket4-app-production-20261104-r10/deployment-preparation/activation-after-01.json')
ACTIVATION_SHA = '7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'
EPOCH = Path('/home/alex/work/pocket4-framework-epoch-20261104-r10/framework_epoch.py')
EPOCH_SHA = 'f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288'
CELL_SHA = 'f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc'
CGROUP = Path('/sys/fs/cgroup/system.slice/droidloomd.service')
PROPERTIES = ('TasksMax', 'EffectiveTasksMax', 'TasksAccounting', 'ControlGroup', 'FragmentPath', 'DropInPaths', 'NeedDaemonReload', 'InvocationID', 'ExecMainPID', 'ActiveEnterTimestampMonotonic', 'CPUQuotaPerSecUSec', 'MemoryHigh', 'MemoryMax', 'MemorySwapMax')

def require(value, reason):
    if not value:
        raise RuntimeError(reason)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def read(path, pin=None, maximum=1048576, single=True, require_root=True):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and (not single or before.st_nlink == 1) and (not require_root or (before.st_uid == 0 and not before.st_mode & 0o022)) and before.st_size <= maximum, 'READ_SCOPE')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(maximum + 1)
        after = os.fstat(fd)
        require(len(raw) == before.st_size and all(getattr(before, k) == getattr(after, k) for k in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')), 'READ_CHANGED')
        require(pin is None or sha(raw) == pin, 'READ_PIN_CHANGED')
        return raw, {'bytes': len(raw), 'sha256': sha(raw), 'device': before.st_dev, 'inode': before.st_ino, 'mtime_ns': str(before.st_mtime_ns), 'ctime_ns': str(before.st_ctime_ns), 'mode': oct(stat.S_IMODE(before.st_mode)), 'nlink': before.st_nlink, 'uid': before.st_uid, 'gid': before.st_gid}
    finally:
        os.close(fd)

def tool_query(argv):
    canonical = Path(argv[0]).resolve(strict=True)
    require(str(canonical).startswith(('/usr/bin/', '/usr/lib/')), 'QUERY_TOOL_SCOPE')
    original, identity = read(canonical, maximum=16 * 1048576, single=False)
    p = subprocess.run(argv, executable=str(canonical), stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10,
                       env={'PATH': '/usr/bin:/usr/sbin', 'LANG': 'C.UTF-8', 'SYSTEMD_PAGER': ''},
                       start_new_session=True)
    require(len(p.stdout) <= 65536 and len(p.stderr) <= 8192, 'QUERY_OUTPUT_BOUND')
    after, after_id = read(canonical, identity['sha256'], maximum=16 * 1048576, single=False)
    require(identity == after_id and original == after, 'QUERY_TOOL_CHANGED')
    return {'argv': argv, 'executable': str(canonical), 'tool': identity, 'exit_code': p.returncode, 'joined': True,
            'stdout': p.stdout.decode('utf-8', 'strict'), 'stderr': p.stderr.decode('utf-8', 'strict')}

def write_result(value):
    ROOT.mkdir(mode=0o750)
    os.chown(ROOT, 0, 1000)
    os.chmod(ROOT, 0o750)
    raw = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    fd = os.open(ROOT / 'result.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o640)
    try:
        os.fchown(fd, 0, 1000)
        os.fchmod(fd, 0o640)
        with os.fdopen(os.dup(fd), 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)
    return {'path': str(ROOT / 'result.json'), 'bytes': len(raw), 'sha256': sha(raw)}

def main():
    require(os.geteuid() == 0, 'ROOT_READ_ONLY_QUERY')
    read(TX, TX_SHA, require_root=False)
    activation = json.loads(read(ACTIVATION, ACTIVATION_SHA, require_root=False)[0])
    epoch = types.ModuleType('fixed_original_epoch_read_only')
    epoch.__file__ = str(EPOCH)
    exec(compile(read(EPOCH, EPOCH_SHA, require_root=False)[0], str(EPOCH), 'exec'), epoch.__dict__)
    def boundary():
        read('/etc/droidloom/cell.json', CELL_SHA)
        epoch.require_unchanged(activation['framework_epoch'])
        for key in ('daemon_process', 'launcher_process', 'presenter_process'):
            require(epoch.process_identity(activation[key]['host_pid']) == activation[key], 'FIXED_HOST_PROCESS_CHANGED')
        return {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'epoch_sha256': activation['framework_epoch']['sha256'],
                'limits': {key: (CGROUP / key).read_text().strip() for key in activation['limits']},
                'pids_current': (CGROUP / 'pids.current').read_text().strip(),
                'pids_events': (CGROUP / 'pids.events').read_text().strip()}
    before = boundary()
    query = tool_query(['/usr/bin/systemctl', '--system', 'show', 'droidloomd.service', '--no-pager', '--property=' + ','.join(PROPERTIES)])
    require(query['exit_code'] == 0, 'SYSTEMD_QUERY_FAILED')
    props = dict(line.split('=', 1) for line in query['stdout'].splitlines())
    require(set(props) <= set(PROPERTIES) and props.get('ControlGroup') == '/system.slice/droidloomd.service' and props.get('TasksMax', '').isdigit(), 'SYSTEMD_PROPERTY_SCOPE')
    names = [props['FragmentPath'], *props['DropInPaths'].split()]
    require(0 < len(names) <= 16 and len(set(names)) == len(names), 'UNIT_FILE_COUNT')
    configs = []
    for name in names:
        require(name.startswith(('/usr/lib/systemd/system/', '/etc/systemd/system/', '/run/systemd/system/', '/run/systemd/system.control/', '/etc/systemd/system.control/')) and '..' not in Path(name).parts, 'UNIT_FILE_SCOPE')
        canonical = Path(name).resolve(strict=True)
        raw, identity = read(canonical, maximum=65536, single=False)
        selected = []
        section = ''
        for n, line in enumerate(raw.decode('utf-8', 'strict').splitlines(), 1):
            if line.strip().startswith('['):
                section = line.strip()
            if re.match(r'^\s*(TasksMax|TasksAccounting|CPUQuota|CPUQuotaPeriodSec|MemoryHigh|MemoryMax|MemorySwapMax)\s*=', line):
                selected.append({'line': n, 'section': section, 'text': line})
        configs.append({'path': name, 'canonical': str(canonical), **identity, 'selected_resource_directives': selected})
    journal = tool_query(['/usr/bin/journalctl', '--system', '--no-pager', '--utc', '-o', 'short-iso-precise',
                          '--since=2026-11-05 14:45:00 UTC', '--until=2026-11-05 15:45:00 UTC',
                          '_PID=1', '--grep=Reload|droidloomd|TasksMax', '-n', '160'])
    require(journal['exit_code'] in (0, 1), 'SYSTEM_MANAGER_JOURNAL_QUERY_FAILED')
    after = boundary()
    read(TX, TX_SHA, require_root=False)
    read(ACTIVATION, ACTIVATION_SHA, require_root=False)
    read(EPOCH, EPOCH_SHA, require_root=False)
    for config in configs:
        _, current = read(config['canonical'], config['sha256'], maximum=65536, single=False)
        require(all(current[k] == config[k] for k in current), 'UNIT_SOURCE_CHANGED_DURING_READ')
    result = {'schema': 'pocket4-main-configured-task-limit-readonly/v1', 'before': before, 'after': after,
              'expected_frozen_limits': activation['limits'], 'limit_consistency': before['limits'] == after['limits'],
              'fixed_framework_and_host_identity_verified_twice': True,
              'systemd_properties': props, 'optional_unreported_properties': sorted(set(PROPERTIES) - set(props)), 'systemd_query': query, 'resource_configuration_files': configs,
              'system_manager_journal_query': journal, 'journal_scope': 'PID1 manager records matching resource/reload/unit names; bounded160 entries in fixed UTC window. Absence is not proof of no direct cgroup writes.',
              'source_pins': {'transaction': TX_SHA, 'activation': ACTIVATION_SHA, 'epoch': EPOCH_SHA},
              'pinned_input_metadata': {str(path): read(path, pin, require_root=False)[1] for path, pin in ((TX, TX_SHA), (ACTIVATION, ACTIVATION_SHA), (EPOCH, EPOCH_SHA))},
              'scope': {'android_commands': 0, 'ui_actions': 0, 'service_actions': 0, 'cgroup_writes': 0, 'guard_updates': 0, 'package_actions': 0, 'signals_to_existing_processes': 0},
              'new_runtime_baseline_authorized_or_created': False}
    record = write_result(result)
    print(json.dumps({'state': 'READ_ONLY_CONFIGURATION_OBSERVED', 'result': record,
                      'configured_tasks_max': props['TasksMax'], 'kernel_pids_max': after['limits']['pids.max'],
                      'limits_stable': result['limit_consistency']}), flush=True)

if __name__ == '__main__':
    main()
