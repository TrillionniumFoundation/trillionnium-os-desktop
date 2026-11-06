#!/usr/bin/env python3
"""Read only the observed failed job's staging and exact locked HEAD metadata."""
import configparser
import hashlib
import json
import os
from pathlib import PurePosixPath
import re
import stat
import sys
import time

OWNER = '/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01'
ROOT = OWNER + '/typed-ingress-framework-build-01-20261105'
WORK = OWNER + '/typed-ingress-framework-work-01-20261105'
STAGING = '.droidloom-source-a2fqBK'
LOCK = '/home/alex/work/pocket4-native-typed-ingress-builder466-go5-compile-02-20261105/builder-source/android/manifest/m2-role-ingress-source-lock.json'
LOCK_SHA = 'ca62c69ff22eba9ff84992aaa18114b74c951802c084bd8cb25cfc22d741ae54'
INNER_SHA = '139163acad47d9db707faa950e4b4dcecaf3e72b655bce8b6b3db089ce542bdf'
OUTER_SHA = '3626270e88e72c4e46d8beee09b5351e1f7d53bab18043241204ca314855e04d'
PROGRESS_SHA = 'a9b8f63049c8bd2317e4757ac8c0a27b224f392dec729198ed8d9ae63d97db1d'
WORK_ID = (66306, 41861500, 1000, 1000, 0o40700)
SECONDS = 3.0
OUTPUT_LIMIT = 524288
STARTED = 0.0


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def budget():
    need(time.monotonic() - STARTED < SECONDS, 'FIXED_READ_DEADLINE')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(info):
    return {'device': info.st_dev, 'inode': info.st_ino, 'mode': info.st_mode,
            'uid': info.st_uid, 'gid': info.st_gid, 'bytes': info.st_size,
            'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns}


def error_row(error):
    # Never echo Git config, an unknown origin URL, or parser error text.
    return {'type': type(error).__name__, 'errno': getattr(error, 'errno', None),
            'reason': str(error) if isinstance(error, RuntimeError) else None,
            'failing_path': getattr(error, 'fixed_authority_path', None),
            'authority_metadata': getattr(error, 'authority_metadata', None)}


def directory(base, relative):
    parts = PurePosixPath(relative).parts
    need(parts and all(part not in ('/', '.', '..') for part in parts), 'FIXED_RELATIVE_DIRECTORY')
    fd = os.dup(base)
    try:
        for part in parts:
            budget()
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def absolute_directory(path):
    need(path.startswith('/'), 'FIXED_ABSOLUTE_DIRECTORY')
    root = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        return directory(root, path[1:])
    finally:
        os.close(root)


def regular(parent, name, maximum, expected_mode=None):
    budget()
    need('/' not in name and name not in ('.', '..'), 'FIXED_FILE_LEAF')
    named = os.stat(name, dir_fd=parent, follow_symlinks=False)
    mode_ok = (not named.st_mode & 0o022) if expected_mode is None else named.st_mode == expected_mode
    if not (stat.S_ISREG(named.st_mode) and named.st_nlink == 1 and named.st_uid == 1000
            and named.st_gid == 1000 and mode_ok and 0 <= named.st_size <= maximum):
        error = RuntimeError('OWNED_REGULAR_FILE_BOUND')
        error.authority_metadata = {**identity(named), 'nlink': named.st_nlink,
                                    'required_exact_mode': expected_mode}
        raise error
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=parent)
    try:
        held = os.fstat(fd)
        need(identity(named) == identity(held), 'FILE_NAMED_HELD_CHANGED')
        data = bytearray()
        while len(data) <= maximum:
            budget()
            block = os.read(fd, min(65536, maximum + 1 - len(data)))
            if not block:
                break
            data.extend(block)
        after = os.fstat(fd)
        named_after = os.stat(name, dir_fd=parent, follow_symlinks=False)
        need(identity(held) == identity(after) == identity(named_after)
             and len(data) == held.st_size, 'FILE_CHANGED_DURING_READ')
        raw = bytes(data)
        return raw, {'bytes': len(raw), 'sha256': sha(raw)}
    finally:
        os.close(fd)


def optional_regular(parent, name, maximum):
    try:
        os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return None, {'present': False, 'errno': 2}
    try:
        raw, pin = regular(parent, name, maximum)
    except FileNotFoundError as error:
        raise RuntimeError('PRESENT_FILE_DISAPPEARED') from error
    return raw, {'present': True, **pin}


def metadata(parent, name):
    budget()
    try:
        info = os.stat(name, dir_fd=parent, follow_symlinks=False)
        return {'present': True, **identity(info)}
    except FileNotFoundError:
        return {'present': False, 'errno': 2}


def pinned(path, maximum, expected, size, expected_mode):
    p = PurePosixPath(path)
    parent = absolute_directory(str(p.parent))
    try:
        raw, pin = regular(parent, p.name, maximum, expected_mode)
        need(pin == {'bytes': size, 'sha256': expected}, 'FIXED_AUTHORITY_PIN_CHANGED')
        return json.loads(raw)
    except Exception as error:
        error.fixed_authority_path = path
        raise
    finally:
        os.close(parent)


def project_row(staging, project, ordinal, remote):
    row = {'ordinal': ordinal, 'path': project['path'], 'expected_commit': project['commit'],
           'observed': False, 'HEAD_matches_lock': False, 'origin_matches_lock': False,
           'working_tree_verified': False, 'objects_verified': False, 'reuse_qualified': False}
    checkout = git = reopened = None
    try:
        try:
            checkout = directory(staging, project['path'])
        except FileNotFoundError:
            row['missing_fixed_directory'] = True
            row['errno'] = 2
            row['observed'] = True
            return row
        checkout_before = identity(os.fstat(checkout))
        row['checkout'] = checkout_before
        need(checkout_before['uid'] == checkout_before['gid'] == 1000
             and not checkout_before['mode'] & 0o022, 'OWNED_PROJECT_DIRECTORY_REQUIRED')
        git = directory(checkout, '.git')
        git_before = identity(os.fstat(git))
        row['git_directory'] = git_before
        need(git_before['uid'] == git_before['gid'] == 1000 and not git_before['mode'] & 0o022,
             'OWNED_GIT_DIRECTORY_REQUIRED')
        head, row['HEAD'] = optional_regular(git, 'HEAD', 256)
        if head is not None:
            if re.fullmatch(rb'[0-9a-f]{40}\n', head):
                row['HEAD'].update(kind='detached', commit=head[:-1].decode('ascii'))
                row['HEAD_matches_lock'] = head[:-1].decode('ascii') == project['commit']
            elif head == b'ref: refs/heads/droidloom\n':
                row['HEAD']['kind'] = 'symbolic_initial_branch_not_resolved'
            else:
                row['HEAD']['kind'] = 'other_bounded_content_not_exported'
        raw_config, row['config'] = optional_regular(git, 'config', 65536)
        if raw_config is not None:
            config = configparser.RawConfigParser(interpolation=None, strict=True)
            config.read_string(raw_config.decode('utf-8', 'strict'))
            origin = config.get('remote "origin"', 'url', fallback=None)
            if origin is not None:
                row['origin_sha256'] = sha(origin.encode('utf-8'))
                row['origin_matches_lock'] = origin == remote + project['name']
        fetch, row['FETCH_HEAD'] = optional_regular(git, 'FETCH_HEAD', 65536)
        if fetch is not None:
            fields = [line.split(b'\t', 1)[0] for line in fetch.splitlines()]
            row['FETCH_HEAD']['one_expected_commit'] = (
                len(fields) == 1 and fields[0] == project['commit'].encode('ascii'))
        row['index'] = metadata(git, 'index')
        row['index_lock'] = metadata(git, 'index.lock')
        need(identity(os.fstat(git)) == git_before, 'GIT_DIRECTORY_CHANGED')
        need(identity(os.fstat(checkout)) == checkout_before, 'PROJECT_DIRECTORY_CHANGED')
        reopened = directory(staging, project['path'])
        need(identity(os.fstat(reopened)) == checkout_before, 'PROJECT_PATH_CHANGED')
        row['observed'] = True
    except Exception as error:
        row['error'] = error_row(error)
    finally:
        for fd in (reopened, git, checkout):
            if fd is not None:
                os.close(fd)
    return row


def main():
    global STARTED
    if sys.argv[1:] != ['--execute-once']:
        print(json.dumps({'state': 'PLAN_ONLY', 'read_only': True, 'work': WORK,
                          'known_staging': STAGING, 'locked_projects': 214, 'seconds': SECONDS,
                          'no_Git_or_subprocess': True, 'reuse_authorized': False}))
        return 0
    STARTED = time.monotonic()
    result = {'schema': 1, 'scope': 'known failed framework staging and exact lock HEAD metadata only',
              'read_only': True, 'complete': False, 'error': None, 'projects': [],
              'observed_progress_sha256': PROGRESS_SHA, 'source_lock_sha256': LOCK_SHA,
              'prior_build_failure_preserved': True, 'recursive_scan': False,
              'Git_commands': 0, 'subprocesses': 0, 'network_calls': 0, 'files_written': 0,
              'Main_actions': 0, 'Android_actions': 0, 'retry_or_build_started': False,
              'reuse_authorized': False, 'production_ready': False}
    work = staging = rework = restaging = None
    try:
        need(os.getuid() == os.geteuid() == 1000, 'ORIGINAL_OPERATOR_REQUIRED')
        inner = pinned(ROOT + '/attempt-01/terminal.json', 65536, INNER_SHA, 28758, 0o100600)
        outer = pinned(ROOT + '/build-fences-01/terminal.json', 4096, OUTER_SHA, 1177, 0o100600)
        need(inner['state'] == 'FAILED' and inner['builder_returncode'] == -9
             and inner['cleanup']['complete'] is True and inner['cleanup']['errors'] == []
             and all(row['reaped'] for row in inner['cleanup']['children'])
             and inner['input_after_qualified'] is True, 'ACTUAL_FAILED_JOB_CLEANUP_NOT_BOUND')
        need(outer['state'] == 'FAILED' and outer['inner_returncode'] == 1
             and outer['main_fence_assessment']['main_fence_pass'] is True,
             'ACTUAL_FAILED_JOB_FENCES_NOT_BOUND')
        lock = pinned(LOCK, 131072, LOCK_SHA, 86293, 0o100664)
        need(lock['schema_version'] == 1 and len(lock['projects']) == 214
             and lock['remote_base'] == 'https://android.googlesource.com/', 'EXACT_LOCK_SHAPE')
        for project in lock['projects']:
            parts = PurePosixPath(project['path']).parts
            need(parts and all(part not in ('/', '.', '..') for part in parts)
                 and re.fullmatch('[0-9a-f]{40}', project['commit']) is not None,
                 'LOCK_PROJECT_SHAPE')
        work = absolute_directory(WORK)
        wi = os.fstat(work)
        need((wi.st_dev, wi.st_ino, wi.st_uid, wi.st_gid, wi.st_mode) == WORK_ID,
             'ACTUAL_WORK_DIRECTORY_IDENTITY_CHANGED')
        work_before = identity(wi)
        result['work'] = work_before
        result['staging_before'] = metadata(work, STAGING)
        result['aosp_source_before'] = metadata(work, 'aosp-source')
        result['projection_journal_before'] = metadata(work, 'source-projection.json')
        if result['staging_before']['present']:
            staging = directory(work, STAGING)
            before = identity(os.fstat(staging))
            need(before == {k: v for k, v in result['staging_before'].items() if k != 'present'}
                 and before['uid'] == before['gid'] == 1000
                 and stat.S_ISDIR(before['mode']) and before['mode'] & 0o777 == 0o700,
                 'KNOWN_STAGING_IDENTITY_OR_PRIVATE_MODE')
            result['staging_manifest'] = metadata(staging, '.droidloom-source-manifest.json')
            for ordinal, project in enumerate(lock['projects'], 1):
                budget()
                result['projects'].append(project_row(staging, project, ordinal, lock['remote_base']))
            restaging = directory(work, STAGING)
            need(identity(os.fstat(staging)) == identity(os.fstat(restaging)) == before,
                 'KNOWN_STAGING_CHANGED')
            result['complete'] = all(row['observed'] for row in result['projects'])
        else:
            result['complete'] = True
            result['staging_absent_no_projects_read'] = True
        rework = absolute_directory(WORK)
        need(identity(os.fstat(work)) == identity(os.fstat(rework)) == work_before,
             'WORK_CHANGED_DURING_READ')
        result['staging_after'] = metadata(work, STAGING)
        result['aosp_source_after'] = metadata(work, 'aosp-source')
        result['projection_journal_after'] = metadata(work, 'source-projection.json')
        for name in ('staging', 'aosp_source', 'projection_journal'):
            need(result[name + '_before'] == result[name + '_after'], 'FIXED_MILESTONE_CHANGED')
        pinned(ROOT + '/attempt-01/terminal.json', 65536, INNER_SHA, 28758, 0o100600)
        pinned(ROOT + '/build-fences-01/terminal.json', 4096, OUTER_SHA, 1177, 0o100600)
    except Exception as error:
        result['complete'] = False
        result['error'] = error_row(error)
    finally:
        for fd in (restaging, rework, staging, work):
            if fd is not None:
                os.close(fd)
    result['HEAD_and_origin_match_candidates'] = sum(
        row['observed'] and row['HEAD_matches_lock'] and row['origin_matches_lock']
        and not row.get('index_lock', {}).get('present', False) for row in result['projects'])
    result['elapsed_seconds'] = round(time.monotonic() - STARTED, 6)
    raw = json.dumps(result, ensure_ascii=True, separators=(',', ':'))
    need(len(raw.encode()) <= OUTPUT_LIMIT, 'FIXED_OUTPUT_BOUND')
    print(raw, flush=True)
    return 0 if result['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
