#!/usr/bin/env python3
"""Fixed published-source metadata and Blueprint reads; no Git, subprocess or mutation."""
import datetime, hashlib, json, os, stat, time
from pathlib import Path

def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(info):
    return {'device': info.st_dev, 'inode': info.st_ino, 'mode': info.st_mode,
            'uid': info.st_uid, 'gid': info.st_gid, 'bytes': info.st_size,
            'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns}


def observe(relative, limit):
    path = BASE / relative
    row = {'path': str(path), 'relative': relative, 'maximum_bytes': limit,
           'started_utc': utc(), 'complete': False}
    try:
        parents = {}
        for parent in path.parents:
            info = parent.lstat()
            if not stat.S_ISDIR(info.st_mode):
                raise RuntimeError('source ancestor is not a real directory: ' + str(parent))
            parents[str(parent)] = (info.st_dev, info.st_ino, info.st_mode)
        named_before = path.lstat()
        row['named_before'] = identity(named_before)
        if not stat.S_ISREG(named_before.st_mode) or named_before.st_size > limit:
            raise RuntimeError('source is not regular or exceeds its fixed bound')
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            row['held_before'] = identity(os.fstat(stream.fileno()))
            if row['held_before'] != row['named_before']:
                raise RuntimeError('named/held source identity differs before read')
            raw = stream.read(limit + 1)
            row['held_after'] = identity(os.fstat(stream.fileno()))
            row['named_after'] = identity(path.lstat())
            if not (row['held_before'] == row['held_after'] == row['named_after']):
                raise RuntimeError('source changed while held')
            if len(raw) != row['held_before']['bytes'] or len(raw) > limit:
                raise RuntimeError('source read is incomplete or exceeds its fixed bound')
            for name, expected in parents.items():
                info = Path(name).lstat()
                if (info.st_dev, info.st_ino, info.st_mode) != expected:
                    raise RuntimeError('source ancestor identity changed: ' + name)
            row['bytes'] = len(raw)
            row['sha256'] = digest(raw)
            row['text'] = raw.decode('utf-8', errors='strict')
            row['complete'] = True
    except Exception as error:
        row['error'] = {'type': type(error).__name__, 'message': str(error),
                        'errno': getattr(error, 'errno', None),
                        'filename': getattr(error, 'filename', None)}
    row['finished_utc'] = utc()
    return row


BASE = Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-work-01-20261105')
SOURCE = BASE / 'aosp-source'
WORK_ID = (66306, 41861500, 1000, 1000, 0o40700)
SOURCE_ID = (66306, 41861660, 1000, 1000, 0o40700)
LOCK_SHA = 'ca62c69ff22eba9ff84992aaa18114b74c951802c084bd8cb25cfc22d741ae54'
PARENT_JOB = '1a1ae6b5a97-fc05-5f81'
INNER_SHA = '80f3508bab1884421af6db2f6d87537fd950100be009265b7e2efabc9b97fcdc'
OUTER_SHA = '2c36ab1cc9ff6f181855f195f9c5b7bc0f58e7fb99d9c76e4871e64b143bf059'
PROJECTS = (
    ('prebuilts/sdk', '0f07e8d60ab0aba46129e427101f96ba459a95c1'),
    ('prebuilts/tools', 'b157d1c3bff39161f34ccc44dffbe9568f3bece2'),
)
PAYLOADS = (
    ('aosp-source/prebuilts/sdk/current/Android.bp', 4194304),
    ('aosp-source/prebuilts/tools/common/m2/Android.bp', 4194304),
    ('aosp-source/prebuilts/tools/common/m2/robolectric.bp', 4194304),
)


def root_id(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode)


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def plan():
    return {'state': 'PLAN_FIXED_PUBLISHED_PROVIDER_SOURCES',
            'base': str(BASE), 'fixed_metadata_files': 3,
            'payloads': [{'relative': name, 'maximum_bytes': limit} for name, limit in PAYLOADS],
            'known_staging_identity_required_at_published_path': SOURCE_ID,
            'actual_parent_job': PARENT_JOB, 'source_lock_sha256': LOCK_SHA,
            'transport': 'plain JSON with exact complete UTF8 source text',
            'Git_commands': 0, 'subprocesses': 0, 'writes': 0, 'fetch_or_checkout': False,
            'missing_or_changed_source_is_preserved_failure': True,
            'whole_build_or_runtime_qualification': False}


def collect():
    started = utc()
    deadline = time.monotonic() + 5.0
    rows, errors, roots, held = [], [], {}, []
    authority = False
    try:
        for label, path, expected in (('work', BASE, WORK_ID), ('published_source', SOURCE, SOURCE_ID)):
            info = path.lstat()
            roots[label] = {'path': str(path), 'named_before': identity(info)}
            need(root_id(info) == expected, 'fixed owned source root identity differs: ' + label)
            fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            held.append((label, path, fd, identity(info)))
            need(identity(os.fstat(fd)) == identity(info), 'source root named/held differs: ' + label)
        def read(relative, maximum):
            need(time.monotonic() < deadline, 'fixed five-second qualification deadline')
            row = observe(relative, maximum)
            rows.append(row)
            need(time.monotonic() < deadline, 'fixed five-second qualification deadline')
            return row
        manifest = read('aosp-source/.droidloom-source-manifest.json', 1048576)
        need(manifest['complete'], 'published source manifest read failed')
        need(manifest['bytes'] == 97784 and manifest['sha256'] ==
             '73a4cc1da8371482164aab2bc149498d03f481f212bb85cb4fda22b6b10c958d',
             'actual published manifest byte pin differs')
        value = json.loads(manifest['text'])
        need(value.get('schema_version') == 1 and value.get('source_lock_sha256') == LOCK_SHA,
             'published manifest does not bind the actual normal lock')
        projects = value.get('plan', {}).get('projects')
        need(isinstance(projects, list) and len(projects) == 214,
             'published manifest project count differs')
        for project, revision in PROJECTS:
            selected = [row for row in projects if row.get('path') == project]
            need(len(selected) == 1 and selected[0].get('commit') == revision and
                 selected[0].get('url') == 'https://android.googlesource.com/platform/' + project,
                 'published manifest fixed project binding differs: ' + project)
            head = read('aosp-source/' + project + '/.git/HEAD', 256)
            need(head['complete'] and head['text'] == revision + '\n',
                 'fixed detached HEAD differs: ' + project)
        authority = True
        for relative, maximum in PAYLOADS:
            row = read(relative, maximum)
            if not row['complete']:
                errors.append({'path': row['path'], 'error': row.get('error')})
    except Exception as error:
        errors.append({'type': type(error).__name__, 'message': str(error),
                       'errno': getattr(error, 'errno', None)})
    finally:
        for label, path, fd, expected in reversed(held):
            try:
                roots[label]['held_after'] = identity(os.fstat(fd))
                roots[label]['named_after'] = identity(path.lstat())
                need(roots[label]['held_after'] == roots[label]['named_after'] == expected,
                     'fixed source root changed during collection: ' + label)
            except Exception as error:
                errors.append({'root': label, 'type': type(error).__name__, 'message': str(error)})
            finally:
                os.close(fd)
    if time.monotonic() >= deadline:
        errors.append({'type': 'RuntimeError', 'message': 'fixed five-second qualification deadline'})
    complete = authority and not errors and len(rows) == 6 and all(row['complete'] for row in rows)
    result = {'schema': 1, 'scope': 'fixed published source manifest, two HEADs and three provider Blueprint files',
              'source_sha256': SOURCE_SHA256, 'started_utc': started, 'finished_utc': utc(),
              'collection_complete': complete, 'authority_qualified': authority,
              'files': rows, 'roots': roots, 'errors': errors,
              'parent': {'job': PARENT_JOB, 'state': 'FAILED', 'inner_sha256': INNER_SHA,
                         'outer_sha256': OUTER_SHA, 'source_lock_sha256': LOCK_SHA},
              'source_identity_is_freshly_checked_not_assumed_from_rename': True,
              'missing_worktree_file_is_not_claimed_missing_from_locked_Git_commit': True,
              'full_file_only': True, 'transport': 'plain-json-exact-utf8-text',
              'Git_commands': 0, 'subprocesses': 0, 'network_calls': 0, 'files_written': 0,
              'directory_enumeration': False, 'Main_actions': 0, 'Android_actions': 0,
              'fetch_checkout_build_or_retry': False, 'prior_failures_preserved': True,
              'source_reuse_authorized_by_this_reader': False, 'production_ready': False}
    raw = (json.dumps(result, ensure_ascii=True, sort_keys=True) + '\n').encode()
    need(len(raw) <= 33554432, 'fixed plain JSON output bound')
    print(raw.decode('ascii'), end='', flush=True)
    return 0 if complete else 1


def main():
    import sys
    if sys.argv[1:] != ['--execute-once']:
        print(json.dumps(plan(), sort_keys=True))
        return 0
    return collect()


if __name__ == '__main__':
    raise SystemExit(main())
