"""Run actual old/new main_classpaths; only environment/identity are seams.

Each HeldZygoteRoot fixture owns a real disposable FD and closes it exactly
once. No Main reads, namespace entry, Android commands or UI action occurs.
"""
import errno
import hashlib
import json
import os
from pathlib import Path
import types

HERE = Path(__file__).resolve().parents[1]
BASE = HERE / 'references'


def load(path, name):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


def one(module, label, primary_failure, close_failure):
    primary = RuntimeError('OWNED_CLASSPATH_PRIMARY_FAILURE')
    cleanup = OSError(errno.EBADF, 'owned classpath root close failure')
    counts = {'close': 0, 'guard': 0, 'target_verify': 0, 'view_verify': 0}
    expected = {'host_pid': 41001, 'namespaces': {'pid': {'device': 4, 'inode': 101}}}
    epoch = types.SimpleNamespace(process_identity=lambda pid: expected)
    values = {'BOOTCLASSPATH': '/owned/a.jar', 'DEX2OATBOOTCLASSPATH': '/owned/a.jar'}
    owned = os.open('/dev/null', os.O_RDONLY | os.O_CLOEXEC)

    class View:
        proc_fd = owned
        mnt_fd = owned
        root_record = {'owned': 'zygote-root'}

        def verify(self):
            counts['view_verify'] += 1

        def close(self):
            counts['close'] += 1
            os.close(owned)
            if close_failure:
                raise cleanup

    def selected(raw):
        if primary_failure:
            raise primary
        return dict(values)

    def guard():
        counts['guard'] += 1

    def target_verify():
        counts['target_verify'] += 1

    held = types.SimpleNamespace(
        CLASSPATH_SECONDS=2, ENV_LIMIT=100, PATH_COUNT_LIMIT=2, FILE_LIMIT=100,
        TOTAL_FILE_LIMIT=200, REQUIRED_CLASSPATHS=tuple(values),
        HeldZygoteRoot=lambda expected, deadline: View(),
        read_at=lambda *args: b'explicit-owned-environment-seam',
        selected_classpaths=selected,
        hash_classpaths_paired=lambda *args: ([{'owned': 'paired-file-seam'}], 4),
        fd_record=lambda fd: {'owned_descriptor': fd})
    target = types.SimpleNamespace(expected={'ns': expected['namespaces']},
        verify=target_verify, root_record={'owned': 'command-root'}, namespaces={'mnt': owned})
    returned = caught = None
    try:
        returned = module.main_classpaths(held, target,
            {'binding': {'processes': {'zygote64': expected}}}, epoch, guard)
    except BaseException as error:
        caught = error
    try:
        os.fstat(owned)
    except OSError as error:
        fd_closed = error.errno == errno.EBADF
    else:
        fd_closed = False
        os.close(owned)
    notes = list(getattr(caught, '__notes__', [])) if caught is not None else []
    return {'case': label, 'same_primary': caught is primary, 'same_cleanup': caught is cleanup,
        'returned': returned is not None, 'returned_values_match': returned is not None and returned[0] == values,
        'error_type': type(caught).__name__ if caught else None,
        'error_message': str(caught) if caught else None, 'notes': notes,
        'fd_closed': fd_closed, 'counts': counts}


def main():
    old_path = BASE / 'main_binding_r1.py'
    assert hashlib.sha256(old_path.read_bytes()).hexdigest() == 'aaca2029095816a70db353eb5c1060141373b36abfed4a19e61aec1bd55e82db'
    old, new = load(old_path, 'old_main_binding'), load(HERE / 'main_binding.py', 'new_main_binding')
    rows = [one(old, 'old-primary-plus-close', True, True),
            one(new, 'new-primary-plus-close', True, True),
            one(new, 'new-success-plus-close', False, True),
            one(new, 'new-success-normal-close', False, False)]
    assert rows[0]['same_cleanup'] and not rows[0]['same_primary']
    assert rows[1]['same_primary'] and not rows[1]['same_cleanup']
    assert len(rows[1]['notes']) == 1 and 'OSError' in rows[1]['notes'][0] and 'root close failure' in rows[1]['notes'][0]
    assert rows[2]['same_cleanup'] and not rows[2]['returned']
    assert rows[3]['returned_values_match'] and rows[3]['error_type'] is None
    assert all(row['fd_closed'] and row['counts']['close'] == 1 for row in rows)
    report = {'schema': 1, 'success': True, 'actual_function': 'main_binding.main_classpaths',
        'old_sha256': hashlib.sha256(old_path.read_bytes()).hexdigest(),
        'new_sha256': hashlib.sha256((HERE / 'main_binding.py').read_bytes()).hexdigest(),
        'rows': rows, 'Main_actions': 0, 'namespace_entry': False, 'ui_audio': False,
        'scope': 'one focused control with four actual-function arms; identity/environment/hash inputs are explicit seams; actual FD close',
        'whole_app_production_ready': False}
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
