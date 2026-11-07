"""Two fixed candidate07 adapter sources, exact whole SHA; collection only.
No source execution, process creation, namespace entry, Main or Android access.
"""
import hashlib
import json
import os
import signal
import stat
import sys
import time

ROOT = '/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/overlay-reconstruction-11/candidate-07/engine/kernel_api/'
TARGETS = (
    ('open_emulation.cc', 'defb5fc77b870c36e6db0269179ffc14f17dce3896d069b552e6e4bd54ec9404'),
    ('unistd_emulation.cc', '7c1571f126fddabdb36272fbbc81e2a7fbd27cba6d286cecfb90b56dc4be0445'),
)
FILE_BOUND = 65536
OUTPUT_BOUND = 262144

def need(value, message):
    if not value:
        raise RuntimeError(message)

def metadata(fd):
    s = os.fstat(fd)
    return {'device': s.st_dev, 'inode': s.st_ino, 'mode': s.st_mode,
            'uid': s.st_uid, 'gid': s.st_gid, 'nlink': s.st_nlink,
            'bytes': s.st_size, 'mtime_ns': s.st_mtime_ns, 'ctime_ns': s.st_ctime_ns}

def collect():
    result = {'schema': 'marriott-fixed-candidate07-adapter-source-read01',
              'collection_complete': False, 'source_execution': False,
              'Main_actions': 0, 'Android_actions': 0, 'children_started': 0,
              'first_error': None, 'secondary_errors': [], 'files': [], 'fd_close_records': [],
              'all_owned_FDs_closed': False, 'current_App_reproduction_asserted': False,
              'source_manifest_sha256': 'e10024548a5b2b5a391ecc9ddb3ea2f19b95a6fea3437f40207a0f4721745a93'}
    started = time.monotonic_ns()
    deadline = started + 10_000_000_000
    owned = []
    old_handler = signal.getsignal(signal.SIGALRM)
    changed_alarm = False

    def error(stage, e):
        row = {'stage': stage, 'type': type(e).__name__, 'error': repr(e)[:512],
               'errno': getattr(e, 'errno', None)}
        if result['first_error'] is None:
            result['first_error'] = row
        elif len(result['secondary_errors']) < 16:
            result['secondary_errors'].append(row)
    def check():
        need(time.monotonic_ns() < deadline, 'SOURCE_READ_DEADLINE')
    def alarm(signum, frame):
        raise TimeoutError('SOURCE_READ_SELF_WATCHDOG')
    def take(label, fd):
        row = {'label': label, 'fd': fd, 'close_attempted_once': False, 'closed': False}
        owned.append(row)
        need(len(owned) <= 64, 'FIXED_FD_BOUND')
        return fd
    def close_all():
        for row in reversed(owned):
            if row['close_attempted_once']:
                continue
            row['close_attempted_once'] = True
            try:
                os.close(row['fd'])
                row['closed'] = True
            except BaseException as e:
                error('close:' + row['label'], e)
            result['fd_close_records'].append({k: row[k] for k in
                                               ('label', 'close_attempted_once', 'closed')})
    def open_fixed(path, label):
        need(path in tuple(ROOT + name for name, sha in TARGETS), 'FIXED_SOURCE_PATH')
        parts = path.split('/')[1:]
        need(parts and all(x not in ('', '.', '..') for x in parts), 'FIXED_PATH_COMPONENTS')
        current = take(label + ':root', os.open('/', os.O_RDONLY | os.O_DIRECTORY |
                                              os.O_CLOEXEC | os.O_NOFOLLOW))
        for index, part in enumerate(parts[:-1]):
            check()
            current = take(label + ':dir:' + str(index), os.open(part, os.O_RDONLY |
                os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=current))
        check()
        fd = take(label + ':file', os.open(parts[-1], os.O_RDONLY |
                  os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=current))
        return fd
    def full_read(fd):
        before = metadata(fd)
        need(stat.S_ISREG(before['mode']) and before['nlink'] == 1 and
             0 < before['bytes'] <= FILE_BOUND, 'FIXED_REGULAR_SOURCE_BOUND')
        raw = bytearray()
        while len(raw) < before['bytes']:
            check()
            block = os.pread(fd, min(16384, before['bytes'] - len(raw)), len(raw))
            need(block, 'SOURCE_SHORT_READ')
            raw.extend(block)
        check()
        need(os.pread(fd, 1, len(raw)) == b'' and metadata(fd) == before,
             'SOURCE_CHANGED_DURING_READ')
        return bytes(raw), before

    try:
        need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0,
             'FIXED_READONLY_ROOT_CONTEXT')
        need(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'NO_PREEXISTING_READER_TIMER')
        signal.signal(signal.SIGALRM, alarm)
        changed_alarm = True
        signal.setitimer(signal.ITIMER_REAL, 12, 0)
        for name, expected in TARGETS:
            path = ROOT + name
            fd = open_fixed(path, name + ':initial')
            raw, before = full_read(fd)
            need(hashlib.sha256(raw).hexdigest() == expected, 'FIXED_SOURCE_SHA:' + name)
            text = raw.decode('utf-8', 'strict')
            again, second = full_read(fd)
            need(again == raw and second == before, 'SECOND_FULL_SOURCE_READ:' + name)
            named = open_fixed(path, name + ':final-name')
            need(metadata(named) == before and metadata(fd) == before,
                 'FINAL_HELD_AND_NAMED_SOURCE:' + name)
            result['files'].append({'name': name, 'path': path, 'bytes': len(raw),
                'sha256': expected, 'metadata_before': before, 'metadata_after': second,
                'two_full_reads_equal': True, 'final_held_named_equal': True, 'utf8': text})
        check()
    except BaseException as e:
        error('collection', e)
    finally:
        close_all()
        if changed_alarm:
            try: signal.setitimer(signal.ITIMER_REAL, 0, 0)
            except BaseException as e: error('watchdog_disarm', e)
            try: signal.signal(signal.SIGALRM, old_handler)
            except BaseException as e: error('watchdog_restore', e)
        result['all_owned_FDs_closed'] = all(x['closed'] for x in owned)
    result['elapsed_ns'] = time.monotonic_ns() - started
    result['collection_complete'] = (result['first_error'] is None and
        len(result['files']) == 2 and result['all_owned_FDs_closed'])
    if not result['collection_complete']:
        for row in result['files']:
            row.pop('utf8', None)
    body = (json.dumps(result, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')
    need(len(body) <= OUTPUT_BOUND, 'SOURCE_READ_OUTPUT_BOUND')
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()
    return 0 if result['collection_complete'] else 1

if __name__ == '__main__':
    raise SystemExit(collect())
