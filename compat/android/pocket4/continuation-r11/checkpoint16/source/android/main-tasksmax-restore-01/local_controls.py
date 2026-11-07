#!/usr/bin/env python3
"""Owned temporary-file controls; never run execute_once or device commands."""
import base64
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
import types

HERE = Path(__file__).resolve().parent


def load(name):
    path = HERE / name
    result = types.ModuleType(name[:-3])
    result.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), result.__dict__)
    return result


def run():
    m, identity = load('restore_main.py'), load('read_main_identity.py')
    rows = []
    before_fds = sorted(os.listdir('/proc/self/fd'))

    class Journal:
        def __init__(self, path, fail_name=None):
            self.path, self.fail_name = path, fail_name
            path.mkdir()

        def save(self, name, value):
            if name == self.fail_name:
                raise OSError(28, 'owned evidence ENOSPC control')
            raw = json.dumps(value, sort_keys=True).encode()
            fd = os.open(self.path / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_CLOEXEC, 0o600)
            try:
                assert os.write(fd, raw) == len(raw)
                os.fsync(fd)
            finally:
                os.close(fd)

    def fixture(root, name):
        parent = root / name
        parent.mkdir()
        p = parent / m.NAME90
        p.write_bytes(m.OLD90)
        fd = os.open(p, os.O_RDONLY | os.O_CLOEXEC)
        try:
            meta = m.metadata(fd)
        finally:
            os.close(fd)
        spec = dict(path=str(p), before=meta, original_base64=base64.b64encode(m.OLD90).decode())
        anchor = m.ConfigAnchor(identity, spec, True, time.monotonic() + 5.0)
        # Evidence is a sibling, so its writes do not change the config parent.
        journal = Journal(root / (name + '-evidence'))
        return p, anchor, journal

    with tempfile.TemporaryDirectory(prefix='owned-tasksmax-controls-') as temporary:
        root = Path(temporary)
        p, anchor, journal = fixture(root, 'positive')
        try:
            record = {}
            m.write90(anchor, record, journal, time.monotonic() + 5)
            assert p.read_bytes() == m.NEW90 and p.stat().st_ino == anchor.spec['before']['inode']
            assert record['full_write'] and record['fsynced'] and record['returned_bytes'] == 133
            rollback = {}
            m.rollback90(anchor, record, rollback, journal, time.monotonic() + 5, False)
            assert rollback['restored'] and p.read_bytes() == m.OLD90
            rows.append(dict(name='actual held original inode write and exact pre-property rollback', passed=True))
        finally:
            anchor.close()

        p, anchor, journal = fixture(root, 'replaced-before-write')
        try:
            old = p.parent / 'original-kept'
            p.rename(old)
            p.write_bytes(b'third-party-named-object')
            record = {}
            try:
                m.write90(anchor, record, journal, time.monotonic() + 5)
                raise AssertionError('replacement accepted')
            except RuntimeError:
                pass
            assert not record['attempted'] and p.read_bytes() == b'third-party-named-object'
            assert old.read_bytes() == m.OLD90
            rows.append(dict(name='changed named inode before write rejected without touching either body', passed=True))
        finally:
            anchor.close()

        p, anchor, journal = fixture(root, 'replaced-before-rollback')
        try:
            written = {}
            m.write90(anchor, written, journal, time.monotonic() + 5)
            p.rename(p.parent / 'written-original-kept')
            p.write_bytes(b'third-party-after-write')
            rollback = {}
            try:
                m.rollback90(anchor, written, rollback, journal, time.monotonic() + 5, False)
                raise AssertionError('rollback overwrote replacement')
            except RuntimeError:
                pass
            assert not rollback['attempted'] and p.read_bytes() == b'third-party-after-write'
            rows.append(dict(name='changed named inode after write prevents rollback', passed=True))
        finally:
            anchor.close()

        p, anchor, journal = fixture(root, 'changed-before-rollback')
        try:
            written = {}
            m.write90(anchor, written, journal, time.monotonic() + 5)
            p.write_bytes(b'third-party-same-inode-body')
            rollback = {}
            try:
                m.rollback90(anchor, written, rollback, journal, time.monotonic() + 5, False)
                raise AssertionError('rollback overwrote external content')
            except RuntimeError:
                pass
            assert not rollback['attempted'] and p.read_bytes() == b'third-party-same-inode-body'
            rows.append(dict(name='changed same inode content and metadata prevents rollback', passed=True))
        finally:
            anchor.close()

        p, anchor, journal = fixture(root, 'partial-write')
        original_pwrite = os.pwrite
        calls = []
        try:
            def partial(fd, data, offset):
                calls.append(len(data))
                return original_pwrite(fd, data[:70], offset)
            os.pwrite = partial  # Explicit fault seam; the partial write uses a real owned FD.
            written = {}
            try:
                m.write90(anchor, written, journal, time.monotonic() + 5)
                raise AssertionError('partial accepted')
            except RuntimeError as error:
                assert str(error) == 'MAIN_CONFIG_PARTIAL_WRITE_NO_RETRY'
            finally:
                os.pwrite = original_pwrite
            rollback = {}
            m.rollback90(anchor, written, rollback, journal, time.monotonic() + 5, False)
            assert calls == [133] and written['returned_bytes'] == 70 and not written['full_write']
            assert written['new_claim'] is None and not rollback['attempted']
            rows.append(dict(name='one real partial pwrite remains failure with no retry or claimed rollback', passed=True,
                             seam='os.pwrite length injection, real owned FD'))
        finally:
            os.pwrite = original_pwrite
            anchor.close()

        p, anchor, journal = fixture(root, 'intent-save-failure')
        try:
            journal.fail_name = 'write90-intent.json'
            record = {}
            try:
                m.write90(anchor, record, journal, time.monotonic() + 5)
                raise AssertionError('evidence failure ignored')
            except OSError as error:
                assert error.errno == 28
            assert not record['attempted'] and p.read_bytes() == m.OLD90
            rows.append(dict(name='evidence intent failure precedes and prevents any config write', passed=True,
                             seam='owned journal save ENOSPC'))
        finally:
            anchor.close()

        p, anchor, journal = fixture(root, 'property-admitted')
        try:
            record = {}
            m.write90(anchor, record, journal, time.monotonic() + 5)
            rollback = {}
            m.rollback90(anchor, record, rollback, journal, time.monotonic() + 5, True)
            assert not rollback['attempted'] and not rollback['eligible'] and p.read_bytes() == m.NEW90
            rows.append(dict(name='after property admission no automatic reverse configuration or property action', passed=True))
        finally:
            anchor.close()

    binding = json.loads((HERE / 'binding.json').read_bytes())
    prior = (HERE / 'prior-main-identity-original.json').read_bytes()
    m.validate_binding(binding, prior)
    broken = copy.deepcopy(binding)
    broken['readiness'] = 'NOT_READY'
    try:
        m.validate_binding(broken, prior)
        raise AssertionError('NOT_READY accepted')
    except RuntimeError as error:
        assert str(error) == 'NOT_READY'
    bad_prior = prior[:-1] + b' '
    try:
        m.validate_binding(binding, bad_prior)
        raise AssertionError('changed actual receipt accepted')
    except RuntimeError as error:
        assert str(error) == 'ACTUAL_PRIOR_IDENTITY_PIN'
    assert m.plan()['device_access_performed'] is False
    rows.append(dict(name='actual complete prior binding passes; NOT_READY and changed original bytes rejected', passed=True))
    rfd, wfd = os.pipe()
    real_close = os.close
    close_calls = []
    try:
        def close_then_error(fd):
            close_calls.append(fd)
            real_close(fd)
            if fd == rfd:
                raise OSError(5, 'owned close failure after actual close')
        os.close = close_then_error
        try:
            try:
                raise RuntimeError('actual primary remains')
            finally:
                m.close_owned((rfd, wfd))
        except RuntimeError as error:
            assert str(error) == 'actual primary remains' and len(error.__notes__) == 1
        assert close_calls == [rfd, wfd]
    finally:
        os.close = real_close
    rows.append(dict(name='primary remains and both real owned FDs close after one injected close exception',
                     passed=True, seam='os.close raises only after closing the first actual owned FD'))
    tree = ast.parse((HERE / 'restore_main.py').read_bytes())
    evidence_names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'save':
            if node.args and isinstance(node.args[0], ast.Constant):
                name = node.args[0].value
                assert re.fullmatch('[a-z0-9][a-z0-9.-]{0,100}', name)
                evidence_names.append(name)
    assert len(evidence_names) == len(set(evidence_names)) and len(evidence_names) >= 10
    rows.append(dict(name='actual production evidence basenames all satisfy create-only writer contract',
                     passed=True, static_names=len(evidence_names)))
    with tempfile.TemporaryDirectory(prefix='owned-journal-constructor-') as temporary:
        for fault in ('path_fd_close', 'parent_first_fstat'):
            path_fd_seen = []
            class RedirectOnlyKnownParent:
                def open_fixed(self, path, directory, deadline):
                    assert path == '/home/alex/work' and directory is True
                    fd = os.open(temporary, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
                    path_fd_seen.append(fd)
                    return fd
            real_metadata, real_close = m.metadata, os.close
            fired = []
            try:
                if fault == 'path_fd_close':
                    def close_path_then_error(fd):
                        real_close(fd)
                        if not fired and fd in path_fd_seen:
                            fired.append(True)
                            raise OSError(5, 'owned constructor path FD close fault')
                    os.close = close_path_then_error
                else:
                    def fail_first_fstat(fd):
                        if not fired:
                            fired.append(True)
                            raise OSError(5, 'owned constructor first parent fstat fault')
                        return real_metadata(fd)
                    m.metadata = fail_first_fstat
                try:
                    m.Journal(RedirectOnlyKnownParent(), time.monotonic() + 5)
                    raise AssertionError('constructor fault accepted')
                except OSError as error:
                    assert error.errno == 5
                    if fault == 'path_fd_close':
                        assert 'owned FD close did not report success' in error.__notes__
                assert fired == [True] and not list(Path(temporary).iterdir())
            finally:
                m.metadata, os.close = real_metadata, real_close
            assert sorted(os.listdir('/proc/self/fd')) == before_fds
            rows.append(dict(name='Journal constructor closes actual parent after ' + fault,
                             passed=True, seam='fixed parent redirected only to owned temp; selected syscall fault'))
    assert sorted(os.listdir('/proc/self/fd')) == before_fds
    report = dict(schema=1, controls=rows, passed=len(rows), all_passed=True, owned_fds_restored=True,
                  production_source_sha256=hashlib.sha256((HERE / 'restore_main.py').read_bytes()).hexdigest(),
                  local_only=True, device_Main_IO_performed=False, execute_once_called=False,
                  subprocess_or_systemctl_called=False, original_collector_collect_called=False,
                  limitations=['no kernel TasksMax mutation', 'no systemd property command',
                               'no concurrent privileged writer between checked read and write',
                               'command lifecycle inherited pattern reviewed separately, not exercised here'])
    return report


if __name__ == '__main__':
    print(json.dumps(run(), sort_keys=True, indent=2))
