#!/usr/bin/env python3
"""Fixed direct-child task-directory metadata index. Default is PLAN_ONLY."""
import argparse
import json
import os
import signal
import stat
import time

ROOT = '/home/alex/work'
PREFIXES = ('pocket4-', 'droidloom-')
MAX_ENTRIES = 2048
MAX_DIRECTORIES = 256
MAX_OUTPUT_BYTES = 262144
DEADLINE_SECONDS = 5


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def identity(info):
    return {key: getattr(info, key) for key in (
        'st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_uid', 'st_gid',
        'st_size', 'st_mtime_ns', 'st_ctime_ns')}


def scan_directories(descriptor, report, deadline):
    iterator = None
    seen = set()
    try:
        iterator = os.scandir(descriptor)
        for item in iterator:
            require(time.monotonic() <= deadline, 'directory index deadline reached')
            report['direct_entries_seen'] += 1
            require(report['direct_entries_seen'] <= MAX_ENTRIES,
                    'direct-entry limit reached; no wider scan or automatic retry')
            name = item.name
            require(name not in seen, 'duplicate directory entry; census is not stable')
            seen.add(name)
            if not name.startswith(PREFIXES):
                continue
            require(name not in ('', '.', '..') and '/' not in name,
                    'invalid direct entry name')
            info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode):
                report['matching_nondirectory_entries_skipped'] += 1
                continue
            require(len(report['directories']) < MAX_DIRECTORIES,
                    'matching-directory limit reached; no wider scan or automatic retry')
            report['directories'].append({
                'path': ROOT + '/' + name, 'type': 'directory',
                'metadata': identity(info), 'file_body_read': False,
                'children_enumerated': False, 'source_ownership_qualified': False})
        require(time.monotonic() <= deadline, 'directory index deadline reached')
    except Exception as error:
        report['primary_error'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        if iterator is not None:
            try:
                iterator.close()
            except Exception as error:
                report['secondary_errors'].append({'operation': 'close_scandir',
                    'type': type(error).__name__, 'message': str(error)})


def execute_once():
    report = {'schema': 1, 'state': 'READONLY_DIRECTORY_INDEX_FAILED',
              'root': ROOT, 'prefixes': list(PREFIXES),
              'bounds': {'direct_entries': MAX_ENTRIES,
                         'matching_directories': MAX_DIRECTORIES,
                         'seconds': DEADLINE_SECONDS, 'output_bytes': MAX_OUTPUT_BYTES},
              'direct_entries_seen': 0, 'matching_nondirectory_entries_skipped': 0,
              'directories': [], 'primary_error': None, 'secondary_errors': [],
              'recursive_walk_performed': False, 'file_bodies_read': 0,
              'source_content_hashes_claimed': False, 'source_binding_qualified': False,
              'Main_or_UI_actions': False, 'automatic_retry': False}
    descriptors = []
    started = time.monotonic()
    old_handler = signal.getsignal(signal.SIGALRM)
    old_timer = None

    def deadline_reached(signum, frame):
        raise TimeoutError('fixed directory index exceeded its five-second deadline')

    try:
        require(os.getuid() == 1000 and os.geteuid() == 1000,
                'original unprivileged operator UID1000 required')
        signal.signal(signal.SIGALRM, deadline_reached)
        old_timer = signal.setitimer(signal.ITIMER_REAL, DEADLINE_SECONDS)
        require(old_timer == (0.0, 0.0), 'unexpected inherited interval timer')
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        descriptors.append(os.open('/', flags))
        for component in ('home', 'alex', 'work'):
            descriptors.append(os.open(component, flags, dir_fd=descriptors[-1]))
        descriptor = descriptors[-1]
        before = os.fstat(descriptor)
        require(stat.S_ISDIR(before.st_mode) and before.st_uid == 1000,
                'fixed task root is not an operator-owned ordinary directory')
        report['root_before'] = identity(before)
        scan_directories(descriptor, report, started + DEADLINE_SECONDS)
        report['root_after'] = identity(os.fstat(descriptor))
        require(report['root_before'] == report['root_after'],
                'task-root directory metadata changed during the census')
    except Exception as error:
        item = {'type': type(error).__name__, 'message': str(error)}
        if report['primary_error'] is None:
            report['primary_error'] = item
        else:
            report['secondary_errors'].append({'operation': 'index_finalization', **item})
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)
        if old_timer and old_timer != (0.0, 0.0):
            signal.setitimer(signal.ITIMER_REAL, *old_timer)
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except Exception as error:
                report['secondary_errors'].append({'operation': 'close_owned_directory_fd',
                    'type': type(error).__name__, 'message': str(error)})
    report['directories'].sort(key=lambda row: row['path'])
    report['seconds'] = time.monotonic() - started
    report['success'] = report['primary_error'] is None and not report['secondary_errors']
    if report['success']:
        report['state'] = 'READONLY_DIRECT_TASK_DIRECTORY_INDEX_COMPLETE'
    raw = (json.dumps(report, ensure_ascii=False, sort_keys=True) + '\n').encode()
    if len(raw) > MAX_OUTPUT_BYTES:
        report = {'schema': 1, 'state': 'READONLY_DIRECTORY_INDEX_FAILED',
                  'success': False, 'error': 'bounded output would overflow',
                  'observed_output_bytes': len(raw), 'max_output_bytes': MAX_OUTPUT_BYTES,
                  'file_bodies_read': 0, 'recursive_walk_performed': False,
                  'source_binding_qualified': False, 'Main_or_UI_actions': False,
                  'automatic_retry': False}
        raw = (json.dumps(report, sort_keys=True) + '\n').encode()
    import sys
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()
    return 0 if report['success'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index-once', action='store_true')
    args = parser.parse_args()
    if not args.index_once:
        print(json.dumps({'state': 'PLAN_ONLY', 'root': ROOT, 'direct_child_prefixes': PREFIXES,
                          'max_entries': MAX_ENTRIES, 'max_directories': MAX_DIRECTORIES,
                          'deadline_seconds': DEADLINE_SECONDS, 'max_output_bytes': MAX_OUTPUT_BYTES,
                          'recursive_walk_performed': False, 'file_bodies_read': 0,
                          'Main_or_UI_actions': False, 'source_binding_qualified': False}))
        return 0
    return execute_once()


if __name__ == '__main__':
    raise SystemExit(main())
