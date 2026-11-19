#!/usr/bin/env python3
"""Read-only content bookends for the original 651 projects and complete CMake.
Called only by the fixed R12 controller while its original source locks are held.
"""
from pathlib import Path, PurePosixPath
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

def git(checkout, args, deadline, guard, commands):
    until = min(deadline, time.monotonic() + 120)
    argv = ['/usr/bin/git', '-c', 'core.fsmonitor=false', '-c', 'core.untrackedCache=false',
            '-C', str(checkout), *args]
    env = {**os.environ, 'GIT_OPTIONAL_LOCKS': '0', 'LC_ALL': 'C'}
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

def observe_blob(checkout, relative, mode, oid, sparse_flag, cones, deadline, guard):
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
        need(blob.hexdigest() == oid, 'actual source content differs from committed Git blob: ' + relative)
        return {'path': relative, 'git_mode': mode, 'git_blob': oid, 'present': True,
                'bytes': count, 'sha256': sha.hexdigest(), 'mode': stat.S_IMODE(before[2])}, before
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
                need(len(actual_cones) == len(set(actual_cones)) and set(actual_cones) == set(cones),
                     'actual sparse cones differ from original plan')
            else:
                need(set(flags.values()) <= {'H'}, 'complete project cannot omit sparse entries')
            body = hashlib.sha256()
            actual_files = actual_bytes = missing = 0
            for relative, (mode, oid) in sorted(index.items()):
                row, identity = observe_blob(checkout, relative, mode, oid, flags[relative],
                                             cones, deadline, guard)
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
