#!/usr/bin/env python3
"""Read-only content bookends for the original 651 projects and complete CMake.
Called only by the fixed reviewed controller while its original source locks are held.
"""
from pathlib import Path, PurePosixPath
from contextlib import contextmanager
import os, stat, hashlib, json, subprocess, tempfile, time, signal

def need(value, message):
    if not value:
        raise RuntimeError(message)

def f9(s):
    return [s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns]

def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()

def safe_relative(value):
    path = PurePosixPath(value)
    need(type(value) is str and value and not path.is_absolute()
         and all(p not in ('', '.', '..') for p in path.parts)
         and str(path) == value and '\0' not in value, 'canonical relative source path')
    return path

def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, 'duplicate JSON field: ' + key)
            result[key] = value
        return result
    def invalid_constant(value):
        raise RuntimeError('non-JSON numeric constant: ' + value)
    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)

def lower_hex(value, length):
    return (type(value) is str and len(value) == length
            and all(c in '0123456789abcdef' for c in value))

def normalized_project(value):
    # Match PlannedProject's deny_unknown_fields and its one serde default.
    # Explicit null, false, a string or any unknown key is not an empty Vec.
    required = {'path', 'url', 'commit', 'purpose'}
    need(type(value) is dict and required <= set(value)
         and set(value) <= required | {'sparse_paths'}, 'exact PlannedProject fields')
    for key in ('path', 'url', 'purpose'):
        need(type(value[key]) is str and value[key] and '\0' not in value[key],
             'nonempty PlannedProject string: ' + key)
    safe_relative(value['path'])
    need(lower_hex(value['commit'], 40), 'exact planned Git commit')
    cones = value['sparse_paths'] if 'sparse_paths' in value else []
    need(type(cones) is list and len(cones) <= 534, 'bounded explicit sparse Vec')
    for cone in cones:
        need(type(cone) is str, 'sparse path must be a string')
        safe_relative(cone)
    need(len(cones) == len(set(cones)), 'unique ordered sparse paths')
    return {**value, 'sparse_paths': list(cones)}

def normalized_projects(values):
    need(type(values) is list and 0 < len(values) <= 652, 'bounded ordered project list')
    result = [normalized_project(value) for value in values]
    need(len({value['path'] for value in result}) == len(result), 'unique project paths')
    return result

def normalized_plan(value):
    need(type(value) is dict and set(value) == {'schema_version', 'superproject_commit',
         'projects', 'links', 'unrestricted_repo_sync'}, 'exact MaterializationPlan fields')
    need(type(value['schema_version']) is int and value['schema_version'] == 1
         and lower_hex(value['superproject_commit'], 40)
         and value['unrestricted_repo_sync'] is False, 'bounded schema-v1 exact plan')
    links = value['links']
    need(type(links) is list and len(links) <= 8, 'bounded ordered root links')
    for link in links:
        need(type(link) is dict and set(link) == {'source', 'target'}, 'exact RootLink fields')
        for key in ('source', 'target'):
            need(type(link[key]) is str, 'root link path string')
            safe_relative(link[key])
    need(len({link['target'] for link in links}) == len(links), 'unique root link targets')
    return {**value, 'projects': normalized_projects(value['projects']),
            'links': [dict(link) for link in links]}

def normalized_manifest(value):
    need(type(value) is dict and set(value) == {'schema_version', 'source_lock_sha256', 'plan'},
         'exact MaterializedManifest fields')
    need(type(value['schema_version']) is int and value['schema_version'] == 1
         and lower_hex(value['source_lock_sha256'], 64), 'exact manifest schema and source lock')
    return {**value, 'plan': normalized_plan(value['plan'])}

def recovery_branch(actual, expected651, expected652, reconcile_intent, vendor_intent):
    # The expected full plans come from the pinned normal source CLI, not counts.
    actual = normalized_manifest(actual)
    old, new = normalized_manifest(expected651), normalized_manifest(expected652)
    need(len(old['plan']['projects']) == 651 and len(new['plan']['projects']) == 652
         and new['plan']['projects'][:651] == old['plan']['projects']
         and new['plan']['links'] == old['plan']['links']
         and new['plan']['superproject_commit'] == old['plan']['superproject_commit'],
         'exact independent 651 to 652 plan extension')
    need(type(reconcile_intent) is bool and type(vendor_intent) is bool,
         'explicit journal presence observations')
    need(not vendor_intent or reconcile_intent, 'vendor cannot precede source transition')
    if actual == old:
        need(not vendor_intent, 'vendor journal contradicts original 651 manifest')
        if reconcile_intent:
            return 'reconcile-dispatched-manifest-still-651'
        return '651-before-reconcile-dispatch'
    if actual == new:
        need(reconcile_intent, '652 publication lacks this owner transition intent')
        return '652-atomic-manifest-published'
    raise RuntimeError('actual full manifest does not match either pinned normal plan')

def tracked_records(raw):
    result = {}
    for record in raw.split(b'\0'):
        if not record:
            continue
        head, path = record.split(b'\t', 1)
        mode, oid, stage = head.decode('ascii').split()
        name = path.decode('utf-8')
        safe_relative(name)
        need(stage == '0' and mode in ('100644', '100755', '120000', '160000')
             and len(oid) == 40 and all(c in '0123456789abcdef' for c in oid)
             and name not in result, 'unique complete stage-zero Git input')
        result[name] = (mode, oid)
    return result

def tree_records(raw):
    result = {}
    for record in raw.split(b'\0'):
        if not record:
            continue
        head, path = record.split(b'\t', 1)
        mode, kind, oid = head.decode('ascii').split()
        name = path.decode('utf-8')
        safe_relative(name)
        need((kind == 'blob' and mode in ('100644', '100755', '120000'))
             or (kind == 'commit' and mode == '160000'), 'known Git member kind')
        need(name not in result, 'unique committed path')
        result[name] = (mode, oid)
    return result

def canonical_sparse_cones(cones):
    """Git cone list drops children already covered by a selected ancestor.

    Preserve the exact original plan elsewhere. Only its observational cone
    comparison is reduced; index, commit, body and absence checks stay exact.
    Component separators matter: selecting 'lib' does not select 'library'.
    """
    need(type(cones) is list and len(cones) <= 534, 'bounded explicit sparse Vec')
    for cone in cones:
        need(type(cone) is str, 'sparse path must be a string')
        safe_relative(cone)
    need(len(cones) == len(set(cones)), 'unique ordered sparse paths')
    selected = set(cones)
    return sorted(cone for cone in cones
                  if not any(str(parent) in selected
                             for parent in PurePosixPath(cone).parents
                             if str(parent) != '.'))


def cone_requires(path, cones):
    path = PurePosixPath(path)
    if not cones:
        return True
    if len(path.parts) == 1:
        return True
    for value in cones:
        cone = PurePosixPath(value)
        if path == cone or cone in path.parents or path.parent in cone.parents:
            return True
    return False

def git(checkout, args, deadline, guard, commands, committed_attributes_only=False):
    until = min(deadline, time.monotonic() + 120)
    argv = ['/usr/bin/git', '-c', 'core.fsmonitor=false', '-c', 'core.untrackedCache=false',
            '-C', str(checkout), *args]
    env = {**os.environ, 'GIT_OPTIONAL_LOCKS': '0', 'LC_ALL': 'C'}
    if committed_attributes_only:
        need(args[:7] == ['-c', 'core.attributesFile=/dev/null',
             '-c', 'core.packedGitWindowSize=8m', '-c', 'core.packedGitLimit=16m', 'check-attr'],
             'attribute-only query must not execute a content filter')
        need(not any(name in env for name in ('GIT_DIR', 'GIT_COMMON_DIR', 'GIT_WORK_TREE',
             'GIT_INDEX_FILE', 'GIT_ATTR_SOURCE', 'GIT_CONFIG_COUNT', 'GIT_CONFIG_PARAMETERS')),
             'no alternate repository, index or injected attribute configuration')
        env.update(GIT_ATTR_NOSYSTEM='1', GIT_CONFIG_NOSYSTEM='1',
                   GIT_CONFIG_GLOBAL='/dev/null', GIT_NO_REPLACE_OBJECTS='1',
                   GIT_NO_LAZY_FETCH='1')
    child = None
    fd = None
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as error:
        try:
            child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=output,
                                     stderr=error, env=env, start_new_session=True)
            fd = os.pidfd_open(child.pid)
            while child.poll() is None:
                need(time.monotonic() < until, 'original content-query deadline')
                need(os.fstat(output.fileno()).st_size <= 128 * 1024 * 1024
                     and os.fstat(error.fileno()).st_size <= 1024 * 1024, 'bounded Git observation')
                guard()
                try:
                    child.wait(timeout=0.1)
                except subprocess.TimeoutExpired:
                    pass
            need(child.returncode == 0, 'actual Git observation failed: ' + repr(args))
            output.seek(0); raw = output.read(128 * 1024 * 1024 + 1)
            error.seek(0); err = error.read(1024 * 1024 + 1)
            need(len(raw) <= 128 * 1024 * 1024 and len(err) <= 1024 * 1024,
                 'bounded complete Git observation')
            commands.append({'args': args, 'pid': child.pid, 'pidfd_inode': os.fstat(fd).st_ino,
                             'exit_code': child.returncode, 'actual_child_reaped': True,
                             'stdout_bytes': len(raw), 'stdout_sha256': hashlib.sha256(raw).hexdigest(),
                             'stderr_bytes': len(err), 'stderr_sha256': hashlib.sha256(err).hexdigest()})
            return raw
        finally:
            if child is not None and child.returncode is None:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=10)
            if fd is not None:
                os.close(fd)

@contextmanager
def held_git_attribute_metadata(checkout):
    """Hold real Git directories and prove the optional info path stays absent."""
    git_path, info_path = checkout / '.git', checkout / '.git/info'
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    git_fd = os.open(git_path, flags)
    info_fd = None
    try:
        git_identity = f9(os.fstat(git_fd))
        need(stat.S_ISDIR(git_identity[2]) and git_identity == f9(git_path.lstat())
             and git_path.resolve() == git_path, 'real held local Git metadata directory')
        try:
            info_stat = os.stat('info', dir_fd=git_fd, follow_symlinks=False)
        except FileNotFoundError:
            info_stat = None
        if info_stat is not None:
            need(stat.S_ISDIR(info_stat.st_mode), 'real local Git info directory')
            info_fd = os.open('info', flags, dir_fd=git_fd)
            info_identity = f9(os.fstat(info_fd))
            need(info_identity == f9(info_stat) and info_path.resolve() == info_path,
                 'same held local Git info directory')

        def metadata():
            need(git_identity == f9(os.fstat(git_fd)) == f9(git_path.lstat())
                 and git_path.resolve() == git_path, 'held Git parent changed during CRLF comparison')
            rows = [{'path': str(git_path), 'f9': git_identity}]
            if info_fd is None:
                try:
                    os.stat('info', dir_fd=git_fd, follow_symlinks=False)
                except FileNotFoundError:
                    rows.append({'path': str(info_path), 'present': False,
                                 'held_parent_f9': git_identity})
                else:
                    raise RuntimeError('absent Git info directory appeared during CRLF comparison')
            else:
                need(info_identity == f9(os.fstat(info_fd))
                     == f9(os.stat('info', dir_fd=git_fd, follow_symlinks=False))
                     == f9(info_path.lstat()) and info_path.resolve() == info_path,
                     'held Git info directory changed during CRLF comparison')
                rows.append({'path': str(info_path), 'f9': info_identity})
                try:
                    os.stat('attributes', dir_fd=info_fd, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise RuntimeError('local info/attributes override is not permitted for CRLF equivalence')
                need(info_identity == f9(os.fstat(info_fd))
                     == f9(os.stat('info', dir_fd=git_fd, follow_symlinks=False)),
                     'Git info metadata changed while checking attributes absence')
            need(git_identity == f9(os.fstat(git_fd)) == f9(git_path.lstat()),
                 'Git parent metadata changed while checking info absence')
            return rows

        yield metadata
    finally:
        if info_fd is not None:
            os.close(info_fd)
        os.close(git_fd)


def committed_crlf_equivalence(checkout, relative, mode, oid, revision, fd, before,
                               raw_sha256, raw_git_blob, deadline, guard, commands):
    """Verify only Git's explicit committed text/eol=crlf representation.

    No clean/smudge filter, encoding conversion, ident expansion or source write
    is performed. The complete normalized body must still equal the committed
    Git blob. Attribute rules come from the fixed project commit, not mutable
    worktree/index rules; system/global rules and local info overrides cannot
    supply an exception. Raw bytes and their original custody remain recorded.
    """
    need(mode == '100644' and 0 < before[6] <= 8*1024*1024,
         'CRLF conversion is limited to bounded non-executable regular text')
    need(lower_hex(revision, 40) and type(commands) is list,
         'fixed project commit and recorded attribute query required')
    with held_git_attribute_metadata(checkout) as metadata:
        metadata_before = metadata()
        names = ['text', 'eol', 'filter', 'ident', 'working-tree-encoding']
        query = ['-c', 'core.attributesFile=/dev/null',
                 '-c', 'core.packedGitWindowSize=8m', '-c', 'core.packedGitLimit=16m', 'check-attr',
                 '--source='+revision, '-z', *names, '--', relative]
        raw_attributes = git(checkout, query, deadline, guard, commands,
                             committed_attributes_only=True)
        fields = raw_attributes.split(b'\0')
        need(len(raw_attributes) <= 65536 and fields[-1] == b''
             and len(fields) == 3*len(names)+1, 'complete bounded attribute triples')
        attributes = {}
        for i, name in enumerate(names):
            path, attribute, value = fields[3*i:3*i+3]
            need(path.decode('utf-8') == relative and attribute.decode('ascii') == name,
                 'exact path and ordered committed attributes')
            attributes[name] = value.decode('ascii')
        need(attributes['text'] == 'set' and attributes['eol'] == 'crlf'
             and all(attributes[name] in ('unspecified', 'unset')
                     for name in ('filter', 'ident', 'working-tree-encoding')),
             'only explicit committed text/eol=crlf without other content transforms')
        need(before == f9(os.fstat(fd)) == f9((checkout/relative).lstat()),
             'original raw file custody before CRLF comparison')
        os.lseek(fd, 0, os.SEEK_SET)
        chunks, count = [], 0
        while True:
            need(time.monotonic() < deadline, 'fixed CRLF comparison deadline')
            data = os.read(fd, min(1024*1024, before[6]+1-count))
            if not data:
                break
            chunks.append(data); count += len(data)
            need(count <= before[6], 'raw file grew during CRLF comparison')
            guard()
        raw = b''.join(chunks)
        need(count == before[6] and hashlib.sha256(raw).hexdigest() == raw_sha256
             and hashlib.sha1(b'blob '+str(count).encode()+b'\0'+raw).hexdigest() == raw_git_blob,
             'full raw body must equal the original observed bytes')
        crlf_count = raw.count(b'\r\n')
        normalized = raw.replace(b'\r\n', b'\n')
        need(crlf_count > 0 and raw.count(b'\n') == crlf_count
             and b'\0' not in raw and b'\r' not in normalized,
             'only uniform CRLF text; mixed endings, NUL and lone CR are rejected')
        normalized_blob = hashlib.sha1(
            b'blob '+str(len(normalized)).encode()+b'\0'+normalized).hexdigest()
        need(normalized_blob == oid, 'normalized full source content differs from committed Git blob')
        need(before == f9(os.fstat(fd)) == f9((checkout/relative).lstat()),
             'original source inode or bytes changed during CRLF comparison')
        metadata_after = metadata()
        need(metadata_before == metadata_after, 'Git attribute metadata changed during CRLF comparison')
        commands[-1]['committed_CRLF_attribute_metadata'] = {
            'before': metadata_before, 'after': metadata_after,
            'local_info_attributes_absent': True, 'system_and_global_attributes_disabled': True,
            'custom_filters_executed': False, 'source_commit': revision}
        return {'kind': 'explicit-committed-text-eol-crlf', 'source_commit': revision,
                'attributes': attributes, 'normalized_bytes': len(normalized),
                'normalized_sha256': hashlib.sha256(normalized).hexdigest(),
                'normalized_git_blob': normalized_blob, 'CRLF_pairs': crlf_count,
                'custom_filters_executed': False, 'source_mutated': False}


def observe_blob(checkout, relative, mode, oid, sparse_flag, cones, deadline, guard,
                 committed_revision=None, commands=None):
    path = checkout / relative
    need(path.parent.resolve() == path.parent, 'source parent alias')
    if not os.path.lexists(path):
        need(sparse_flag == 'S' and not cone_requires(relative, cones),
             'missing required source body: ' + relative)
        return {'path': relative, 'git_mode': mode, 'git_blob': oid,
                'present': False, 'sparse_skip': True}, None
    before = f9(path.lstat())
    if mode == '160000':
        need(stat.S_ISDIR(before[2]) and not path.is_symlink()
             and not any(path.iterdir()), 'unmaterialized Gitlink must be empty')
        return {'path': relative, 'git_mode': mode, 'git_blob': oid,
                'present': True, 'empty_gitlink': True}, before
    if mode == '120000':
        need(stat.S_ISLNK(before[2]), 'committed symlink kind')
        body = os.fsencode(os.readlink(path))
        need(before == f9(path.lstat()), 'symlink changed while held')
        actual_blob = hashlib.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body).hexdigest()
        need(actual_blob == oid, 'symlink bytes differ from original Git blob')
        return {'path': relative, 'git_mode': mode, 'git_blob': oid, 'present': True,
                'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(),
                'mode': stat.S_IMODE(before[2])}, before
    need(stat.S_ISREG(before[2]) and bool(before[2] & 0o111) == (mode == '100755'),
         'committed regular executable mode')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        need(before == f9(os.fstat(fd)), 'source inode changed before read')
        sha = hashlib.sha256()
        blob = hashlib.sha1(b'blob ' + str(before[6]).encode() + b'\0')
        count = 0
        while True:
            need(time.monotonic() < deadline, 'fixed source bookend deadline')
            data = os.read(fd, 1024 * 1024)
            if not data:
                break
            sha.update(data); blob.update(data); count += len(data)
            if count % (64 * 1024 * 1024) == 0:
                guard()
        need(count == before[6] and before == f9(os.fstat(fd)) == f9(path.lstat()),
             'source inode or bytes changed while read')
        raw_git_blob = blob.hexdigest()
        conversion = None
        if raw_git_blob != oid:
            conversion = committed_crlf_equivalence(checkout, relative, mode, oid,
                committed_revision, fd, before, sha.hexdigest(), raw_git_blob,
                deadline, guard, commands)
        row = {'path': relative, 'git_mode': mode, 'git_blob': oid, 'present': True,
               'bytes': count, 'sha256': sha.hexdigest(), 'mode': stat.S_IMODE(before[2])}
        if conversion is not None:
            row.update(raw_git_blob=raw_git_blob, checkout_conversion=conversion)
        return row, before
    finally:
        os.close(fd)

def snapshot(source, projects, output, deadline, guard):
    source, output = Path(source), Path(output)
    need(source.resolve() == source and source.is_dir() and not os.path.lexists(output),
         'existing source and fresh bookend output')
    projects = normalized_projects(projects)
    summaries = []
    total = hashlib.sha256()
    byte_count = files = absent = 0
    observed_ns = time.time_ns()
    with output.open('xb') as stream:
        for project in projects:
            guard()
            safe_relative(project['path'])
            checkout = source / project['path']
            need(checkout.resolve() == checkout and checkout.is_dir(), 'real project checkout')
            commands = []
            head = git(checkout, ['rev-parse', 'HEAD'], deadline, guard, commands).decode().strip()
            origin = git(checkout, ['remote', 'get-url', 'origin'], deadline, guard, commands).decode().strip()
            need(head == project['commit'] and origin == project['url'], 'original project tuple')
            tree_oid = git(checkout, ['rev-parse', 'HEAD^{tree}'], deadline, guard, commands).decode().strip()
            committed = tree_records(git(checkout, ['ls-tree', '-rz', '--full-tree', 'HEAD'],
                                         deadline, guard, commands))
            index = tracked_records(git(checkout, ['ls-files', '--stage', '-z'], deadline, guard, commands))
            need(index == committed, 'original index differs from actual commit')
            flags = {}
            for record in git(checkout, ['ls-files', '-t', '-z'], deadline, guard, commands).split(b'\0'):
                if record:
                    flag, name = record[:1].decode(), record[2:].decode('utf-8')
                    need(record[1:2] == b' ' and name not in flags and flag in ('H', 'S'),
                         'ordinary tracked/sparse flag only')
                    flags[name] = flag
            need(set(flags) == set(index), 'complete index flag observation')
            cones = project['sparse_paths']
            if cones:
                actual_cones = git(checkout, ['sparse-checkout', 'list'], deadline, guard, commands).decode().splitlines()
                need(len(actual_cones) == len(set(actual_cones))
                     and set(actual_cones) == set(canonical_sparse_cones(cones)),
                     'actual sparse cones differ from canonical original plan')
            else:
                need(set(flags.values()) <= {'H'}, 'complete project cannot omit sparse entries')
            body = hashlib.sha256()
            actual_files = actual_bytes = missing = 0
            for relative, (mode, oid) in sorted(index.items()):
                row, identity = observe_blob(checkout, relative, mode, oid, flags[relative],
                                             cones, deadline, guard, project['commit'], commands)
                line = encoded(row); body.update(line)
                observed = {'project': project['path'], **row, 'f9': identity}
                stream.write(encoded(observed))
                if row['present']:
                    actual_files += 1; actual_bytes += row.get('bytes', 0)
                else:
                    missing += 1
            need(not git(checkout, ['status', '--porcelain=v1', '--untracked-files=all'],
                         deadline, guard, commands), 'project no longer clean after body reads')
            need(git(checkout, ['rev-parse', 'HEAD'], deadline, guard, commands).decode().strip() == head,
                 'original commit changed during full reads')
            stable = {'project': project, 'tree': tree_oid, 'tracked_entries': len(index),
                      'materialized_entries': actual_files, 'materialized_bytes': actual_bytes,
                      'sparse_absent_entries': missing, 'body_sha256': body.hexdigest()}
            total.update(encoded(stable))
            summaries.append({**stable, 'actual_commands': commands})
            files += actual_files; byte_count += actual_bytes; absent += missing
            stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(output, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        first = f9(os.fstat(fd)); h = hashlib.sha256()
        while True:
            data = os.read(fd, 1024 * 1024)
            if not data: break
            h.update(data)
        need(first == f9(os.fstat(fd)) == f9(output.lstat()), 'bookend inventory changed')
    finally:
        os.close(fd)
    return {'schema': 'pocket4-original-materialized-source-content-bookend-v1',
            'observed_ns': observed_ns, 'finished_ns': time.time_ns(), 'projects': summaries,
            'project_count': len(projects), 'materialized_entries': files, 'materialized_bytes': byte_count,
            'sparse_absent_entries': absent, 'content_sha256': total.hexdigest(),
            'inventory': {'path': str(output), 'bytes': first[6], 'sha256': h.hexdigest(), 'identity': first},
            'all_actual_Git_blob_reads_verified': True, 'source_mutations': False}
