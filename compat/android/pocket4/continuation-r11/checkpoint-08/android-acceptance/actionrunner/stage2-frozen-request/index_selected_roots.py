#!/usr/bin/env python3
"""Metadata-only direct-child index of three actually observed task roots."""
import argparse
import json
import os
import re
import signal
import stat
import time

FIRST_INDEX_SHA = '3191468e8cb1b36d464cf42f11a60e96b3a589f1d2174e70879d5ba23f6283b5'
ROOTS = {
    'pocket4-app-production-20261103': {
        'st_ctime_ns': 1793753425583292900, 'st_dev': 66306, 'st_gid': 1000,
        'st_ino': 42644125, 'st_mode': 16832, 'st_mtime_ns': 1793753425583292900,
        'st_nlink': 24, 'st_size': 4096, 'st_uid': 1000},
    'pocket4-app-production-20261104': {
        'st_ctime_ns': 1793765145896064326, 'st_dev': 66306, 'st_gid': 1000,
        'st_ino': 43542269, 'st_mode': 16832, 'st_mtime_ns': 1793765145896064326,
        'st_nlink': 23, 'st_size': 4096, 'st_uid': 1000},
    'pocket4-source-publication-20261104-r10': {
        'st_ctime_ns': 1793774698028842959, 'st_dev': 66306, 'st_gid': 1000,
        'st_ino': 43681637, 'st_mode': 16832, 'st_mtime_ns': 1793774698028842959,
        'st_nlink': 6, 'st_size': 4096, 'st_uid': 1000},
}
WORK = '/home/alex/work'
MAX_ENTRIES_PER_ROOT = 512
MAX_ROWS = 128
MAX_OUTPUT_BYTES = 131072
DEADLINE_SECONDS = 5
SKIP_DIRECTORIES = {
    '.git', '.gradle', '.cache', '__pycache__', 'node_modules',
    'data', 'app-data', 'app_data', 'userdata', 'user', 'apps', 'cache',
    'images', 'target', 'out', 'android-out', 'build-out', 'build-output',
    'business-flows', 'evidence', 'tombstones', 'logs', 'log', 'journals', 'journal',
    'apks', 'objects', 'blobs',
}
COMMERCIAL_DIRECTORY = re.compile(
    r'(^|[-_.])(bilibili|marriott|ceair|airchina|meituan|textnow|cathay|wechat|alipay|shenzhou)([-_.]|$)')
MANIFEST_NAMES = {
    'androidmanifest.xml', 'manifest.json', 'index.json', 'source_pins.json',
    'source-pins.json', 'source-manifest.json', 'source-index.json',
    'source-inventory.json', 'file-manifest.json', 'files.json',
    'build-result.json', 'build-receipt.json',
}
BUILD_NAMES = {'build.py', 'build.sh', 'build.gradle', 'build.gradle.kts',
               'settings.gradle', 'settings.gradle.kts', 'build.xml', 'pom.xml'}


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def identity(info):
    return {key: getattr(info, key) for key in (
        'st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_uid', 'st_gid',
        'st_size', 'st_mtime_ns', 'st_ctime_ns')}


def file_candidate(name):
    low = name.lower()
    if low == 'actionrunner.java' or re.search(r'action[-_]?runner', low):
        return 'action_runner_name'
    if low in MANIFEST_NAMES or re.search(r'(source|files?).*(manifest|inventory)|(manifest|inventory).*(source|files?)', low):
        return 'manifest_name'
    if low in BUILD_NAMES or ('build' in low and ('action' in low or 'runner' in low)):
        return 'build_recipe_name'
    if ('source' in low or 'action' in low) and low.endswith(('.tar', '.tar.gz', '.tgz', '.zip')):
        return 'source_archive_name'
    if 'action' in low and low.endswith('.apk'):
        return 'action_apk_name'
    return None


def index_root(descriptor, displayed_root, report, deadline):
    iterator = None
    seen = set()
    root_result = {'root': displayed_root, 'direct_entries_seen': 0,
                   'skipped_nondirectory_nonmatch': 0, 'skipped_directories': 0,
                   'skipped_symlink_or_special': 0, 'completed': False}
    report['roots'].append(root_result)
    try:
        iterator = os.scandir(descriptor)
        for item in iterator:
            require(time.monotonic() <= deadline, 'stage2 metadata deadline reached')
            root_result['direct_entries_seen'] += 1
            require(root_result['direct_entries_seen'] <= MAX_ENTRIES_PER_ROOT,
                    'fixed-root entry bound reached; no expansion or retry')
            name = item.name
            require(name not in seen and name not in ('', '.', '..') and '/' not in name,
                    'duplicate or invalid direct child name')
            seen.add(name)
            info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                low = name.lower()
                if low in SKIP_DIRECTORIES or COMMERCIAL_DIRECTORY.search(low):
                    root_result['skipped_directories'] += 1
                    continue
                kind, reason = 'directory', 'unentered_task_subdirectory'
            elif stat.S_ISREG(info.st_mode):
                kind, reason = 'regular_file', file_candidate(name)
                if reason is None:
                    root_result['skipped_nondirectory_nonmatch'] += 1
                    continue
            else:
                root_result['skipped_symlink_or_special'] += 1
                continue
            require(len(report['candidates']) < MAX_ROWS,
                    'candidate row bound reached; no expansion or retry')
            report['candidates'].append({
                'path': displayed_root + '/' + name, 'type': kind,
                'candidate_reason': reason, 'metadata': identity(info),
                'file_body_read': False, 'child_directory_entered': False,
                'source_ownership_qualified': False})
        require(time.monotonic() <= deadline, 'stage2 metadata deadline reached')
        root_result['completed'] = True
    except Exception as error:
        if report['primary_error'] is None:
            report['primary_error'] = {'type': type(error).__name__, 'message': str(error)}
        else:
            report['secondary_errors'].append({'operation': 'index_root',
                'type': type(error).__name__, 'message': str(error)})
    finally:
        if iterator is not None:
            try:
                iterator.close()
            except Exception as error:
                report['secondary_errors'].append({'operation': 'close_scandir',
                    'type': type(error).__name__, 'message': str(error)})


def execute_once():
    report = {'schema': 1, 'state': 'ACTIONRUNNER_STAGE2_METADATA_FAILED',
              'first_index_sha256': FIRST_INDEX_SHA, 'roots': [], 'candidates': [],
              'primary_error': None, 'secondary_errors': [],
              'bounds': {'roots': 3, 'entries_per_root': MAX_ENTRIES_PER_ROOT,
                         'candidate_rows': MAX_ROWS, 'seconds': DEADLINE_SECONDS,
                         'output_bytes': MAX_OUTPUT_BYTES},
              'file_bodies_read': 0, 'recursive_walk_performed': False,
              'source_hashes_claimed': False, 'source_binding_qualified': False,
              'Android_UI_audio_actions': False, 'automatic_retry': False}
    descriptors = []
    started = time.monotonic()
    old_handler = signal.getsignal(signal.SIGALRM)

    def deadline_reached(signum, frame):
        raise TimeoutError('fixed stage2 metadata deadline reached')

    try:
        require(os.getuid() == 1000 and os.geteuid() == 1000,
                'original unprivileged operator UID1000 required')
        require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0),
                'unexpected inherited interval timer')
        signal.signal(signal.SIGALRM, deadline_reached)
        signal.setitimer(signal.ITIMER_REAL, DEADLINE_SECONDS)
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        descriptors.append(os.open('/', flags))
        for component in ('home', 'alex', 'work'):
            descriptors.append(os.open(component, flags, dir_fd=descriptors[-1]))
        work = descriptors[-1]
        require(os.fstat(work).st_uid == 1000, 'task parent ownership changed')
        for name, expected in ROOTS.items():
            descriptor = os.open(name, flags, dir_fd=work)
            descriptors.append(descriptor)
            before = identity(os.fstat(descriptor))
            require(before == expected, 'selected root differs from actual stage1: ' + name)
            index_root(descriptor, WORK + '/' + name, report, started + DEADLINE_SECONDS)
            after = identity(os.fstat(descriptor))
            report['roots'][-1]['before'] = before
            report['roots'][-1]['after'] = after
            require(before == after, 'selected root changed during metadata index: ' + name)
            if report['primary_error'] is not None or report['secondary_errors']:
                break
    except Exception as error:
        item = {'type': type(error).__name__, 'message': str(error)}
        if report['primary_error'] is None:
            report['primary_error'] = item
        else:
            report['secondary_errors'].append({'operation': 'root_guard', **item})
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except Exception as error:
                report['secondary_errors'].append({'operation': 'close_owned_directory_fd',
                    'type': type(error).__name__, 'message': str(error)})
    report['candidates'].sort(key=lambda row: row['path'])
    report['seconds'] = time.monotonic() - started
    report['success'] = (report['primary_error'] is None and not report['secondary_errors'] and
                         len(report['roots']) == 3 and all(r['completed'] for r in report['roots']))
    if report['success']:
        report['state'] = 'ACTIONRUNNER_STAGE2_FIXED_ROOT_METADATA_COMPLETE'
    raw = (json.dumps(report, ensure_ascii=False, sort_keys=True) + '\n').encode()
    if len(raw) > MAX_OUTPUT_BYTES:
        report = {'schema': 1, 'state': 'ACTIONRUNNER_STAGE2_METADATA_FAILED',
                  'success': False, 'error': 'bounded output would overflow',
                  'observed_output_bytes': len(raw), 'maximum': MAX_OUTPUT_BYTES,
                  'file_bodies_read': 0, 'recursive_walk_performed': False,
                  'source_binding_qualified': False, 'automatic_retry': False}
        raw = (json.dumps(report) + '\n').encode()
    import sys
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()
    return 0 if report['success'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index-once', action='store_true')
    args = parser.parse_args()
    if not args.index_once:
        print(json.dumps({'state': 'PLAN_ONLY', 'selected_roots': [WORK + '/' + n for n in ROOTS],
                          'first_index_sha256': FIRST_INDEX_SHA,
                          'entries_per_root': MAX_ENTRIES_PER_ROOT, 'candidate_rows': MAX_ROWS,
                          'deadline_seconds': DEADLINE_SECONDS, 'output_bytes': MAX_OUTPUT_BYTES,
                          'file_bodies_read': 0, 'recursive_walk_performed': False,
                          'Android_UI_audio_actions': False, 'source_binding_qualified': False}))
        return 0
    return execute_once()


if __name__ == '__main__':
    raise SystemExit(main())
