#!/usr/bin/env python3
"""Read five fixed locked Git objects from the already published private source."""
import configparser
import datetime
import hashlib
import json
import os
import selectors
import stat
import subprocess
import time
from pathlib import Path

BASE = Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-work-01-20261105')
SOURCE = BASE / 'aosp-source'
PROJECT = SOURCE / 'prebuilts/misc'
GITDIR = PROJECT / '.git'
WORK_ID = (66306, 41861500, 1000, 1000, 0o40700)
SOURCE_ID = (66306, 41861660, 1000, 1000, 0o40700)
LOCK_SHA = 'ca62c69ff22eba9ff84992aaa18114b74c951802c084bd8cb25cfc22d741ae54'
MANIFEST_BYTES = 97784
MANIFEST_SHA = '73a4cc1da8371482164aab2bc149498d03f481f212bb85cb4fda22b6b10c958d'
REVISION = 'be7c3a630b5dc5eb3260035d77a81b2f322754f8'
ORIGIN = 'https://android.googlesource.com/platform/prebuilts/misc'
GIT = Path('/usr/bin/git')
GIT_BYTES = 4547768
GIT_SHA = 'ed8b2df973b28c0fb773b9c0dc0816d3ee2b3835bb932d9153c21417bb51b362'
GIT_ID = (66306, 108004715, 0o100755)
OBJECTS = (
    ('common', 'tree', 65536),
    ('common/robolectric', 'tree', 65536),
    ('common/robolectric/Android.bp', 'blob', 131072),
    ('common/ub-uiautomator', 'tree', 65536),
    ('common/ub-uiautomator/Android.bp', 'blob', 65536),
)
MAX_STDOUT = 524288
MAX_STDERR = 16384
QUALIFICATION_SECONDS = 5.0
PARENT_JOB = '1a1ae6b5a97-fc05-5f81'
INNER_SHA = '80f3508bab1884421af6db2f6d87537fd950100be009265b7e2efabc9b97fcdc'
OUTER_SHA = '2c36ab1cc9ff6f181855f195f9c5b7bc0f58e7fb99d9c76e4871e64b143bf059'


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def git_oid(kind, raw):
    return hashlib.sha1(kind.encode('ascii') + b' ' + str(len(raw)).encode('ascii') + b'\0' + raw).hexdigest()


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def identity(info):
    return {'device': info.st_dev, 'inode': info.st_ino, 'mode': info.st_mode,
            'uid': info.st_uid, 'gid': info.st_gid, 'nlink': info.st_nlink,
            'bytes': info.st_size, 'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns}


def root_id(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode)


def error_record(error):
    return {'type': type(error).__name__, 'message': str(error),
            'errno': getattr(error, 'errno', None),
            'filename': getattr(error, 'filename', None)}


def check_deadline(deadline):
    need(time.monotonic() < deadline, 'five-second qualification deadline exceeded')


def parent_snapshot(path):
    result = {}
    for parent in path.parents:
        info = parent.lstat()
        need(stat.S_ISDIR(info.st_mode), 'fixed ancestor is not a real directory: ' + str(parent))
        result[str(parent)] = (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)
    return result


def verify_parents(parents):
    for name, expected in parents.items():
        info = Path(name).lstat()
        need((info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid) == expected,
             'fixed ancestor changed: ' + name)


def hold_regular(path, maximum, held, records, deadline, label):
    check_deadline(deadline)
    row = {'label': label, 'path': str(path), 'maximum_bytes': maximum, 'complete': False}
    records.append(row)
    parents = parent_snapshot(path)
    before = path.lstat()
    row['named_before'] = identity(before)
    need(stat.S_ISREG(before.st_mode) and before.st_size <= maximum,
         'fixed regular-file shape or bound differs: ' + label)
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    held.append((path, fd, identity(before), parents, row))
    row['held_before'] = identity(os.fstat(fd))
    need(row['held_before'] == row['named_before'], 'named/held mismatch: ' + label)
    pieces, count = [], 0
    while True:
        check_deadline(deadline)
        part = os.read(fd, min(65536, maximum + 1 - count))
        if not part:
            break
        pieces.append(part)
        count += len(part)
        need(count <= maximum, 'fixed read bound exceeded: ' + label)
    raw = b''.join(pieces)
    row['held_after_read'] = identity(os.fstat(fd))
    row['named_after_read'] = identity(path.lstat())
    need(row['held_before'] == row['held_after_read'] == row['named_after_read'],
         'fixed file changed during read: ' + label)
    need(len(raw) == before.st_size, 'fixed read length differs: ' + label)
    verify_parents(parents)
    row.update({'bytes': len(raw), 'sha256': digest(raw), 'complete': True})
    check_deadline(deadline)
    return fd, raw, row


def absent_fixed(path, observations):
    parents = parent_snapshot(path)
    row = {'path': str(path)}
    observations.append(row)
    try:
        info = path.lstat()
    except FileNotFoundError as error:
        need(error.filename == str(path), 'unexpected missing ancestor')
        row['state'] = 'ABSENT'
        verify_parents(parents)
        return
    row['state'] = 'PRESENT_REJECTED'
    row['identity'] = identity(info)
    raise RuntimeError('fixed Git alternate or graft input unexpectedly exists: ' + str(path))


def qualify_config(raw):
    parser = configparser.RawConfigParser(strict=True, interpolation=None)
    parser.read_string(raw.decode('utf-8', errors='strict'))
    need(set(parser.sections()) <= {'core', 'remote "origin"', 'extensions'},
         'Git config contains an unexpected section')
    need(parser.has_section('core') and parser.has_section('remote "origin"'),
         'Git config missing original local repository or origin')
    core = dict(parser.items('core', raw=True))
    need(set(core) <= {'repositoryformatversion', 'filemode', 'bare', 'logallrefupdates',
                       'sparsecheckout', 'sparsecheckoutcone'},
         'Git core config contains an unexpected key')
    need(core.get('repositoryformatversion') in ('0', '1') and core.get('bare') == 'false',
         'Git repository format or bare setting differs')
    remote = dict(parser.items('remote "origin"', raw=True))
    need(set(remote) <= {'url', 'fetch', 'promisor', 'partialclonefilter'} and
         remote.get('url') == ORIGIN and remote.get('promisor', 'true') == 'true' and
         remote.get('partialclonefilter', 'blob:none') == 'blob:none',
         'Git origin or filtered-fetch configuration differs from the producer')
    extensions = dict(parser.items('extensions', raw=True)) if parser.has_section('extensions') else {}
    need(set(extensions) <= {'worktreeconfig', 'partialclone'} and
         extensions.get('worktreeconfig', 'true') == 'true' and
         extensions.get('partialclone', 'origin') == 'origin',
         'Git extensions differ from the fixed worktree or origin')
    return {'section_names': sorted(parser.sections()), 'origin_matches_fixed_lock': True,
            'promisor': remote.get('promisor'), 'partialclonefilter': remote.get('partialclonefilter'),
            'partialclone_remote': extensions.get('partialclone'),
            'lazy_fetch_disabled_by_mandatory_cli_flag_and_environment': True,
            'worktree_config_expected': extensions.get('worktreeconfig') == 'true'}


def qualify_worktree_config(raw):
    parser = configparser.RawConfigParser(strict=True, interpolation=None)
    parser.read_string(raw.decode('utf-8', errors='strict'))
    need(parser.sections() == ['core'], 'worktree config contains unexpected sections')
    core = dict(parser.items('core', raw=True))
    need(set(core) <= {'sparsecheckout', 'sparsecheckoutcone'} and
         all(value in ('true', 'false') for value in core.values()),
         'worktree config has unqualified settings')
    return {'section_names': ['core'], 'keys': sorted(core), 'no_other_settings': True}


def bounded_git(git_fd, deadline, command):
    child = None
    selector = None
    first_error = None
    secondary = []
    data = {'stdout': bytearray(), 'stderr': bytearray()}
    try:
        check_deadline(deadline)
        argv = [str(GIT), '--no-pager', '--no-replace-objects', '--no-optional-locks', '--no-lazy-fetch',
                '-c', 'protocol.allow=never', '-c', 'gc.auto=0',
                '-c', 'maintenance.auto=false', '-c', 'core.fsmonitor=false',
                '--git-dir=' + str(GITDIR), 'cat-file', '--batch']
        env = {'PATH': '/nonexistent', 'LANG': 'C', 'LC_ALL': 'C',
               'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_SYSTEM': '/dev/null',
               'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_NO_REPLACE_OBJECTS': '1',
               'GIT_NO_LAZY_FETCH': '1', 'GIT_OPTIONAL_LOCKS': '0',
               'GIT_TERMINAL_PROMPT': '0', 'GIT_ALLOW_PROTOCOL': '',
               'GIT_PROTOCOL_FROM_USER': '0', 'GIT_EXEC_PATH': '/nonexistent',
               'GIT_PAGER': '', 'PAGER': ''}
        batch = ''.join(REVISION + ':' + path + '\n' for path, _, _ in OBJECTS).encode('ascii')
        command['argv'] = argv
        command['input_sha256'] = digest(batch)
        command['input_bytes'] = len(batch)
        child = subprocess.Popen(argv, executable='/proc/self/fd/' + str(git_fd),
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 cwd='/', env=env, close_fds=True, pass_fds=(git_fd,), start_new_session=True)
        command['pid'] = child.pid
        command['spawned'] = True
        child.stdin.write(batch)
        child.stdin.close()
        selector = selectors.DefaultSelector()
        for name, stream in (('stdout', child.stdout), ('stderr', child.stderr)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name)
        while selector.get_map():
            check_deadline(deadline)
            for event, _ in selector.select(min(0.05, max(0.0, deadline - time.monotonic()))):
                name = event.data
                stream = event.fileobj
                limit = MAX_STDOUT if name == 'stdout' else MAX_STDERR
                block = os.read(stream.fileno(), min(65536, limit + 1 - len(data[name])))
                if not block:
                    selector.unregister(stream)
                    continue
                data[name].extend(block)
                need(len(data[name]) <= limit, 'fixed Git ' + name + ' capture bound exceeded')
        child.wait(timeout=max(0.001, deadline - time.monotonic()))
        command['returncode'] = child.returncode
        command['direct_child_joined'] = True
        need(child.returncode == 0, 'fixed Git cat-file returned nonzero')
        check_deadline(deadline)
    except BaseException as error:
        first_error = error
    finally:
        if selector is not None:
            try:
                selector.close()
            except BaseException as error:
                secondary.append(error_record(error))
        if child is not None:
            if child.poll() is None:
                try:
                    child.kill()
                    command['owned_direct_child_kill_used'] = True
                except BaseException as error:
                    secondary.append(error_record(error))
            try:
                child.wait(timeout=2.0)
                command['returncode'] = child.returncode
                command['direct_child_joined'] = True
            except BaseException as error:
                secondary.append(error_record(error))
            for stream in (child.stdin, child.stdout, child.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except BaseException as error:
                        secondary.append(error_record(error))
        command['cleanup_errors'] = secondary
        command['stdout'] = {'bytes': len(data['stdout']), 'sha256': digest(data['stdout'])}
        command['stderr'] = {'bytes': len(data['stderr']), 'sha256': digest(data['stderr']),
                             'text': bytes(data['stderr']).decode('utf-8', errors='replace')}
        if first_error is not None:
            command['first_error'] = error_record(first_error)
    if first_error is not None:
        raise first_error
    need(not secondary and command.get('direct_child_joined') is True and
         command.get('owned_direct_child_kill_used') is not True, 'fixed Git cleanup did not qualify')
    return bytes(data['stdout'])


def parse_objects(raw, rows):
    offset = 0
    for path, wanted_kind, limit in OBJECTS:
        spec = REVISION + ':' + path
        row = {'revision': REVISION, 'path_at_commit': path,
               'expected_kind': wanted_kind, 'maximum_bytes': limit, 'complete': False}
        rows.append(row)
        end = raw.find(b'\n', offset)
        need(end >= 0 and end - offset <= 512, 'Git batch header bound or EOF')
        header = raw[offset:end].decode('ascii', errors='strict')
        offset = end + 1
        row['batch_header'] = header
        if header == spec + ' missing':
            row['state'] = 'MISSING_FROM_FIXED_GIT_OBJECT_EXPRESSION'
            continue
        fields = header.split(' ')
        need(len(fields) == 3 and len(fields[0]) == 40 and
             all(c in '0123456789abcdef' for c in fields[0]) and fields[1] == wanted_kind and
             fields[2].isdigit(), 'Git object header differs from fixed request')
        size = int(fields[2])
        need(size <= limit and offset + size < len(raw), 'Git object length bound or EOF')
        body = raw[offset:offset + size]
        need(raw[offset + size:offset + size + 1] == b'\n', 'Git batch object terminator')
        offset += size + 1
        need(git_oid(wanted_kind, body) == fields[0], 'Git object content SHA1 differs from header')
        row.update({'bytes': size, 'sha256': digest(body), 'git_object_sha1': fields[0]})
        if wanted_kind == 'blob':
            row['text'] = body.decode('utf-8', errors='strict')
        else:
            entries, position = [], 0
            while position < len(body):
                sep = body.find(b' ', position)
                nul = body.find(b'\0', sep + 1)
                need(sep > position and nul > sep and nul + 21 <= len(body), 'Git tree framing')
                mode = body[position:sep].decode('ascii', errors='strict')
                name = body[sep + 1:nul].decode('utf-8', errors='strict')
                need(mode in ('40000', '100644', '100755', '120000') and
                     name not in ('', '.', '..') and '/' not in name and '\n' not in name,
                     'fixed common tree entry shape')
                entries.append({'name': name, 'mode': mode, 'git_object_sha1': body[nul + 1:nul + 21].hex()})
                need(len(entries) <= 256, 'fixed common tree entry count')
                position = nul + 21
            row['entries'] = entries
            row['raw_tree_bytes_not_exported'] = True
        row['complete'] = True
        row['state'] = 'READ_COMPLETE_FROM_FIXED_LOCKED_COMMIT'
    need(offset == len(raw), 'trailing Git batch output')
    return rows


def collect():
    started = utc()
    deadline = time.monotonic() + QUALIFICATION_SECONDS
    held, roots, records, absent, errors = [], [], [], [], []
    objects = []
    command = {'spawned': False, 'direct_child_joined': False,
               'owned_direct_child_kill_used': False, 'cleanup_errors': []}
    authority = False
    config_summary = None
    try:
        for label, path, expected in (('work', BASE, WORK_ID), ('published_source', SOURCE, SOURCE_ID)):
            check_deadline(deadline)
            info = path.lstat()
            row = {'label': label, 'path': str(path), 'named_before': identity(info)}
            roots.append(row)
            need(root_id(info) == expected, 'fixed owned source root identity differs: ' + label)
            parents = parent_snapshot(path)
            fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            held.append((path, fd, identity(info), parents, row))
            need(identity(os.fstat(fd)) == identity(info), 'source root named/held differs: ' + label)
        _, raw, _ = hold_regular(SOURCE / '.droidloom-source-manifest.json', 1048576,
                                 held, records, deadline, 'actual_published_manifest')
        need(len(raw) == MANIFEST_BYTES and digest(raw) == MANIFEST_SHA,
             'actual published manifest byte pin differs')
        value = json.loads(raw)
        projects = value.get('plan', {}).get('projects')
        need(value.get('schema_version') == 1 and value.get('source_lock_sha256') == LOCK_SHA and
             isinstance(projects, list) and len(projects) == 214, 'actual source lock or plan differs')
        selected = [row for row in projects if row.get('path') == 'prebuilts/misc']
        need(len(selected) == 1 and selected[0].get('commit') == REVISION and
             selected[0].get('url') == ORIGIN, 'fixed project manifest binding differs')
        _, raw, _ = hold_regular(GITDIR / 'HEAD', 256, held, records, deadline, 'detached_HEAD')
        need(raw == (REVISION + '\n').encode('ascii'), 'actual detached HEAD differs')
        _, raw, _ = hold_regular(GITDIR / 'config', 65536, held, records, deadline, 'Git_config')
        config_summary = qualify_config(raw)
        if config_summary['worktree_config_expected']:
            _, raw, _ = hold_regular(GITDIR / 'config.worktree', 65536, held, records,
                                     deadline, 'Git_worktree_config')
            config_summary['worktree'] = qualify_worktree_config(raw)
        for relative in ('commondir', 'objects/info/alternates', 'objects/info/http-alternates', 'info/grafts'):
            absent_fixed(GITDIR / relative, absent)
        git_fd, raw, git_row = hold_regular(GIT, GIT_BYTES, held, records, deadline, 'actual_Git_ELF')
        need((git_row['held_before']['device'], git_row['held_before']['inode'],
              git_row['held_before']['mode']) == GIT_ID and len(raw) == GIT_BYTES and
             digest(raw) == GIT_SHA, 'actual Git tool identity or whole content pin differs')
        authority = True
        parse_objects(bounded_git(git_fd, deadline, command), objects)
        for row in objects:
            if not row['complete']:
                errors.append({'path_at_commit': row['path_at_commit'], 'state': row['state']})
    except BaseException as error:
        errors.append(error_record(error))
    finally:
        for path, fd, expected, parents, row in reversed(held):
            try:
                row['held_final'] = identity(os.fstat(fd))
                row['named_final'] = identity(path.lstat())
                need(row['held_final'] == row['named_final'] == expected,
                     'fixed held or named input changed: ' + str(path))
                verify_parents(parents)
            except BaseException as error:
                errors.append(error_record(error))
            finally:
                try:
                    os.close(fd)
                except BaseException as error:
                    errors.append(error_record(error))
        for observation in absent:
            if observation.get('state') == 'ABSENT':
                try:
                    final = []
                    absent_fixed(Path(observation['path']), final)
                    observation['final_state'] = final[0]['state']
                except BaseException as error:
                    observation['final_error'] = error_record(error)
                    errors.append(error_record(error))
        if time.monotonic() >= deadline:
            errors.append({'type': 'RuntimeError', 'message': 'five-second qualification deadline exceeded'})
    complete = authority and not errors and len(objects) == len(OBJECTS) and all(r['complete'] for r in objects)
    result = {'schema': 1, 'scope': 'five fixed locked Git expressions; one bounded cat-file child',
              'source_sha256': SOURCE_SHA256, 'started_utc': started, 'finished_utc': utc(),
              'collection_complete': complete, 'authority_qualified': authority,
              'objects': objects, 'input_files': records, 'roots': roots,
              'absent_fixed_git_inputs': absent, 'qualified_config_summary': config_summary,
              'command': command, 'errors': errors,
              'parent': {'job': PARENT_JOB, 'state': 'FAILED', 'inner_sha256': INNER_SHA,
                         'outer_sha256': OUTER_SHA, 'source_lock_sha256': LOCK_SHA,
                         'actual_manifest_sha256': MANIFEST_SHA},
              'transport': 'plain-json-exact-utf8-source-and-safe-tree-metadata',
              'qualification_deadline_seconds': QUALIFICATION_SECONDS,
              'cleanup_join_allowance_seconds': 2.0,
              'network_or_fetch_checkout_build_or_retry': False, 'source_files_written': 0,
              'tool_searches': 0, 'Main_actions': 0, 'Android_actions': 0,
              'directory_or_Git_object_enumeration': 'Only common and two fixed child tree objects, at most 256 entries each',
              'prior_failed_worktree_read_preserved': True,
              'source_reuse_or_build_authorized': False, 'production_ready': False}
    output = (json.dumps(result, sort_keys=True, ensure_ascii=True) + '\n').encode('ascii')
    need(len(output) <= 2097152, 'fixed plain JSON output bound')
    print(output.decode('ascii'), end='', flush=True)
    return 0 if complete else 1


def main():
    import sys
    if sys.argv[1:] != ['--execute-once']:
        print(json.dumps({'state': 'PLAN_FIXED_LOCKED_GIT_OBJECTS', 'objects': OBJECTS,
                          'subprocesses_maximum': 1, 'read_only': True,
                          'source_reuse_or_build_authorized': False}, sort_keys=True))
        return 0
    return collect()


if __name__ == '__main__':
    raise SystemExit(main())
