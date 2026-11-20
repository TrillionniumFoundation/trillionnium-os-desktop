#!/usr/bin/python3
"""Read-only partial APEX-provider observations under the caller's custody.

This is never a strict source qualification and never launches a writer. The
controller must retain its original serial lock, retired-child proof, budget
and absolute deadline. Only the four independently fixed original APEX provider blobs
may be S-absent; every other member uses the unchanged strict helper.
"""
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import signal
import stat
import subprocess
import time


SCHEMA = 'p4-r22-incomplete-apex-provider-recovery-diagnostic-v1'
ATTRIBUTES = ('text', 'eol', 'filter', 'ident', 'working-tree-encoding')
CONFIG_PATTERN = r'^(core\.(autocrlf|eol|safecrlf|attributesfile|checkroundtripencoding)|filter\..*\.(clean|smudge|process|required))$'
SCOPE_PATHS = ('/etc/gitconfig', '/home/qq/.gitconfig', '/home/qq/.config/git/config',
               '/etc/gitattributes', '/home/qq/.config/git/attributes')
GIT_OVERRIDES = ('GIT_DIR', 'GIT_COMMON_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE',
                 'GIT_ATTR_SOURCE', 'GIT_CONFIG_COUNT', 'GIT_CONFIG_PARAMETERS',
                 'GIT_CONFIG_GLOBAL', 'GIT_CONFIG_SYSTEM', 'GIT_CONFIG_NOSYSTEM',
                 'GIT_ATTR_NOSYSTEM')


def need(value, message):
    if not value:
        raise RuntimeError(message)


def f9(s):
    return [s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def fingerprint(path, *, optional=False, maximum=128 * 1024 * 1024):
    """Read only the exact ordinary path; EACCES is never treated as absence."""
    path = Path(path)
    need(path.is_absolute() and path.parent.resolve() == path.parent, 'canonical metadata parent')
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        need(optional, 'required Git metadata is absent: ' + str(path))
        return {'path': str(path), 'errno': 2}
    try:
        first = f9(os.fstat(fd))
        need(stat.S_ISREG(first[2]) and first[5] == 1 and first[6] <= maximum,
             'bounded ordinary single-link metadata')
        digest = hashlib.sha256(); count = 0
        while True:
            block = os.read(fd, 1024 * 1024)
            if not block:
                break
            digest.update(block); count += len(block)
            need(count <= maximum, 'metadata exceeded the bound while reading')
        need(count == first[6] and first == f9(os.fstat(fd)) == f9(path.lstat()),
             'held metadata changed during full read')
        return {'path': str(path), 'identity': first, 'bytes': count, 'sha256': digest.hexdigest()}
    finally:
        os.close(fd)


def write_bytes(path, body):
    path = Path(path)
    need(path.parent.resolve() == path.parent, 'canonical diagnostic output parent')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        view = memoryview(body)
        while view:
            count = os.write(fd, view)
            need(count > 0, 'complete create-only diagnostic output')
            view = view[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    return fingerprint(path, maximum=max(len(body), 1))


def _no_git_locks(checkout):
    for name in ('index.lock', 'config.lock', 'config.worktree.lock', 'HEAD.lock',
                 'packed-refs.lock', 'shallow.lock', 'info/sparse-checkout.lock'):
        path = checkout / '.git' / name
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        raise RuntimeError('original Git mutation lock remains: ' + str(path))


def _metadata(checkout, names):
    git = checkout / '.git'
    status = git.lstat()
    need(stat.S_ISDIR(status.st_mode) and git.resolve() == git, 'ordinary real Git metadata directory')
    _no_git_locks(checkout)
    refs = []
    for name in ('index', 'HEAD', 'config', 'config.worktree', 'info/sparse-checkout', 'info/attributes'):
        refs.append(fingerprint(git / name, optional=name not in ('index', 'HEAD', 'config')))
    # Git reads attributes in every ancestor, including an untracked file that
    # was previously absent. Freeze those absences before the filter query too.
    # A set deduplicates common parents; work is linear in path components.
    attributes = set()
    for name in names:
        for parent in PurePosixPath(name).parents:
            attributes.add(str(parent / '.gitattributes'))
    for name in sorted(attributes):
        refs.append(fingerprint(checkout / name, optional=True, maximum=8 * 1024 * 1024))
    return refs


def _scope(admission):
    refs = admission['conversion_scope']
    for ref in refs:
        actual = fingerprint(ref['path'], optional='errno' in ref, maximum=8 * 1024 * 1024)
        need(actual == ref, 'original effective Git configuration/attributes scope changed')
    return refs


def _production_admission(admission):
    need(not any(key in os.environ for key in GIT_OVERRIDES), 'no hidden Git configuration or repository override')
    need(type(admission) is dict and set(admission) == {
        'schema', 'conversion_scope', 'expected_conversion_stdout_hex'}
        and admission['schema'] == 'p4-r20-frozen-git-conversion-admission-v1'
        and type(admission['conversion_scope']) is list
        and [row['path'] for row in admission['conversion_scope']] == list(SCOPE_PATHS)
        and type(admission['expected_conversion_stdout_hex']) is str
        and 0 < len(admission['expected_conversion_stdout_hex']) <= 131072,
        'complete original five-path conversion scope and bounded actual configuration')
    bytes.fromhex(admission['expected_conversion_stdout_hex'])
    for ref in admission['conversion_scope']:
        if 'identity' in ref:
            need(set(ref) == {'path', 'identity', 'bytes', 'sha256'}
                 and type(ref['identity']) is list and len(ref['identity']) == 9
                 and all(type(value) is int for value in ref['identity'])
                 and type(ref['bytes']) is int and ref['bytes'] == ref['identity'][6]
                 and type(ref['sha256']) is str and len(ref['sha256']) == 64,
                 'complete actual present conversion-scope reference')
        else:
            need(set(ref) == {'path', 'errno'} and type(ref['errno']) is int and ref['errno'] == 2,
                 'only actual ENOENT can identify an absent conversion scope')


def _capture_query(bookends, checkout, args, deadline, guard, commands, captures, directory,
                   *, committed=False):
    before = len(commands)
    raw = bookends.git(checkout, args, deadline, guard, commands,
                       committed_attributes_only=committed)
    need(len(commands) == before + 1, 'one actual read-only Git child')
    command = commands[-1]
    need(command['actual_child_reaped'] is True and command['exit_code'] == 0
         and command['stderr_bytes'] == 0, 'complete quiet read-only attribute/configuration query')
    index = len(captures)
    out = write_bytes(directory / ('query-%04d.stdout' % index), raw)
    err = write_bytes(directory / ('query-%04d.stderr' % index), b'')
    need(out['bytes'] == command['stdout_bytes'] and out['sha256'] == command['stdout_sha256']
         and err['sha256'] == command['stderr_sha256'], 'captured original Git query output')
    captures.append({'command': command, 'stdout': out, 'stderr': err})
    return raw


def _configuration(bookends, checkout, deadline, guard, commands, captures, directory, admission):
    _scope(admission)
    # The unchanged helper injects core.fsmonitor=false for its own queries.
    # --get-regexp returns all original values as well, so no configured hook
    # can be hidden behind that command-line false value before normal resume.
    raw = _capture_query(bookends, checkout,
        ['config', '--show-origin', '--show-scope', '--null', '--get-regexp', r'^core\.fsmonitor$'],
        deadline, guard, commands, captures, directory)
    parts = raw.split(b'\0')
    need(parts[-1] == b'' and (len(parts) - 1) % 3 == 0, 'complete fsmonitor configuration triples')
    values = []
    for offset in range(0, len(parts) - 1, 3):
        scope, origin, pair = parts[offset:offset + 3]
        key, value = pair.split(b'\n', 1)
        need(key == b'core.fsmonitor' and value.lower() in (b'false', b'0', b'no', b'off'),
             'effective executable/builtin fsmonitor is not admitted')
        values.append({'scope': scope.decode(), 'origin': origin.decode(), 'value': value.decode()})
    need(values, 'actual fixed helper fsmonitor false must be observed')
    config = _capture_query(bookends, checkout,
        ['config', '--show-origin', '--show-scope', '--null', '--get-regexp', CONFIG_PATTERN],
        deadline, guard, commands, captures, directory)
    need(config.hex() == admission['expected_conversion_stdout_hex'],
         'effective conversion configuration differs from the frozen original scope')
    _scope(admission)
    return {'fsmonitor_values': values, 'conversion_stdout_bytes': len(config),
            'conversion_stdout_sha256': hashlib.sha256(config).hexdigest()}


def _all_tracked_filters(checkout, names, deadline, guard, directory, commands):
    """Exactly one stdin query; never alter Git filter configuration or run one."""
    until = min(deadline, time.monotonic() + 120)
    body = b''.join(name.encode('utf-8') + b'\0' for name in names)
    need(len(body) <= 128 * 1024 * 1024, 'bounded complete tracked path input')
    stdin_ref = write_bytes(directory / 'tracked-filter.stdin', body)
    argv = ['/usr/bin/git', '-c', 'core.fsmonitor=false', '-c', 'core.untrackedCache=false',
            '-C', str(checkout), 'check-attr', '-z', '--stdin', 'filter']
    env = {**os.environ, 'GIT_OPTIONAL_LOCKS': '0', 'GIT_NO_LAZY_FETCH': '1',
           'GIT_NO_REPLACE_OBJECTS': '1', 'LC_ALL': 'C'}
    child = pidfd = None
    error = None
    row = {'argv': argv, 'started_ns': time.time_ns(), 'stdin': stdin_ref,
           'actual_child_reaped': False, 'original_pidfd_held_until_reaped': False}
    out_path, err_path = directory / 'tracked-filter.stdout', directory / 'tracked-filter.stderr'
    with open(stdin_ref['path'], 'rb') as inp, out_path.open('xb') as output, err_path.open('xb') as err:
        try:
            child = subprocess.Popen(argv, stdin=inp, stdout=output, stderr=err,
                                     env=env, start_new_session=True, close_fds=True)
            row['pid'] = child.pid
            pidfd = os.pidfd_open(child.pid)
            row['pidfd_inode'] = os.fstat(pidfd).st_ino
            while child.poll() is None:
                need(time.monotonic() < until, 'original partial diagnostic query deadline')
                need(os.fstat(output.fileno()).st_size <= 256 * 1024 * 1024
                     and os.fstat(err.fileno()).st_size <= 1024 * 1024, 'bounded complete filter observation')
                guard()
                try:
                    child.wait(timeout=0.1)
                except subprocess.TimeoutExpired:
                    pass
            need(child.returncode == 0, 'actual tracked-filter query failed')
        except BaseException as failure:
            error = repr(failure)
        finally:
            if child is not None and child.returncode is None:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait(timeout=10)
            row.update(exit_code=None if child is None else child.returncode,
                       actual_child_reaped=child is not None and child.returncode is not None,
                       original_pidfd_held_until_reaped=pidfd is not None and child is not None
                           and child.returncode is not None,
                       finished_ns=time.time_ns(), error=error)
            if pidfd is not None:
                os.close(pidfd)
            output.flush(); err.flush()
            os.fsync(output.fileno()); os.fsync(err.fileno())
    row['stdout'] = fingerprint(out_path, maximum=256 * 1024 * 1024)
    row['stderr'] = fingerprint(err_path, maximum=1024 * 1024)
    need(fingerprint(stdin_ref['path']) == stdin_ref, 'original tracked path query input unchanged')
    commands.append(row)
    need(error is None and row['exit_code'] == 0 and row['actual_child_reaped']
         and row['original_pidfd_held_until_reaped'] and row['stderr']['bytes'] == 0,
         'complete retired tracked-filter observation required')
    counts = {'unspecified': 0, 'unset': 0}
    with out_path.open('rb') as stream:
        pending = bytearray()
        def field():
            while True:
                index = pending.find(0)
                if index >= 0:
                    value = bytes(pending[:index]); del pending[:index + 1]
                    return value
                block = stream.read(65536)
                need(block, 'truncated tracked-filter attribute output')
                pending.extend(block)
                need(len(pending) <= 1024 * 1024, 'bounded tracked-filter output field')
        for number, name in enumerate(names):
            path, attribute, value = field(), field(), field()
            need(path == name.encode() and attribute == b'filter', 'complete ordered tracked-filter roster')
            need(value in (b'unspecified', b'unset'), 'a named executable content filter is not admitted')
            counts[value.decode()] += 1
            if number % 8192 == 0:
                guard()
        need(not pending and stream.read(1) == b'', 'extra tracked-filter output or member')
    need(fingerprint(out_path, maximum=256 * 1024 * 1024) == row['stdout'],
         'tracked-filter output unchanged after complete parsing')
    return {'tracked_paths': len(names), 'path_roster': stdin_ref, 'command': row,
            'attributes': counts, 'all_tracked_filters_unspecified_or_unset': True,
            'configuration_changed': False, 'custom_filters_executed': False}


def _provider_attributes(bookends, core, project, checkout, deadline, guard, commands, captures, directory):
    names = sorted(path for provider, path in core.CANDIDATES if provider == project)
    need(len(names) == 2, 'both files of this original provider')
    observations = []
    for committed in (True, False):
        args = (['-c', 'core.attributesFile=/dev/null', '-c', 'core.packedGitWindowSize=8m',
                 '-c', 'core.packedGitLimit=16m', 'check-attr', '--source=' + core.PROVIDERS[project]['commit']]
                if committed else ['check-attr'])
        args += ['-z', *ATTRIBUTES, '--', *names]
        raw = _capture_query(bookends, checkout, args, deadline, guard, commands, captures, directory,
                             committed=committed)
        parts = raw.split(b'\0')
        need(parts[-1] == b'' and len(parts) == len(names) * 15 + 1, 'complete provider attribute triples')
        values = {}
        for index, name in enumerate(names):
            one = {}
            for j, attr in enumerate(ATTRIBUTES):
                path, key, value = parts[index * 15 + j * 3:index * 15 + j * 3 + 3]
                need(path.decode() == name and key.decode() == attr, 'exact original provider attribute order')
                one[attr] = value.decode()
            need(one == {attr: 'unspecified' for attr in ATTRIBUTES},
                 'new provider members require unchanged raw checkout bytes and no content transformations')
            values[name] = one
        observations.append({'committed': committed, 'values': values, 'stdout': captures[-1]['stdout']})
    need(observations[0]['values'] == observations[1]['values'], 'committed and effective provider attributes differ')
    return observations


def candidate_checkout_rules(bookends, core, source, directory, deadline, guard, config_admission):
    _production_admission(config_admission)
    source, directory = Path(source), Path(directory)
    need(source.resolve() == source and source.is_dir(), 'original source root')
    need(directory.is_absolute() and directory.parent.resolve() == directory.parent
         and source != directory and source not in directory.parents,
         'provider rule observations must be outside source')
    directory.mkdir(mode=0o700)
    result = {}
    for number, project in enumerate(sorted(core.PROVIDERS)):
        result[project] = _candidate_checkout_rules(
            bookends, core, project, source / project, directory / ('provider-%02d' % number),
            deadline, guard, config_admission)
    need(set(result) == set(core.PROVIDERS), 'both original provider rule observations')
    return {'schema': 'p4-r22-four-original-apex-provider-checkout-rules-v1',
            'providers': result, 'candidate_count': 4,
            'all_five_attributes_unspecified': True, 'committed_effective_equal': True,
            'custom_filters_executed': False, 'source_mutations': False,
            'source_recovery_complete': False, 'runtime_qualified': False, 'production_ready': False}


def _candidate_checkout_rules(bookends, core, project, checkout, directory, deadline, guard, config_admission):
    """Same exact attribute parser for the initial reconcile and a single resume.

    This query does not claim that the candidates are absent, that all source
    bodies are complete, or that a writer may be dispatched. Those gates remain
    with the controller's original full before/partial evidence and custody.
    """
    checkout, directory = Path(checkout), Path(directory)
    need(time.monotonic() < deadline and checkout.resolve() == checkout and checkout.is_dir(),
         'original checkout and original query deadline')
    need(directory.is_absolute() and directory.parent.resolve() == directory.parent
         and checkout != directory and checkout not in directory.parents,
         'diagnostic evidence must be outside the original project')
    directory.mkdir(mode=0o700)
    commands = []; captures = []
    try:
        _no_git_locks(checkout); guard()
        base_metadata = _metadata(checkout, [])
        configuration = _configuration(bookends, checkout, deadline, guard, commands,
                                        captures, directory, config_admission)
        head = bookends.git(checkout, ['rev-parse', 'HEAD'], deadline, guard, commands).decode().strip()
        origin = bookends.git(checkout, ['remote', 'get-url', 'origin'], deadline, guard, commands).decode().strip()
        need(head == core.PROVIDERS[project]['commit'] and origin == core.PROVIDERS[project]['url'],
             'rules belong to this exact original APEX provider')
        attr_names = {'.gitattributes'}
        for provider, name in core.CANDIDATES:
            if provider != project:
                continue
            for parent in PurePosixPath(name).parents:
                attr_names.add(str(parent / '.gitattributes'))
        metadata = _metadata(checkout, sorted(attr_names))
        need(metadata[:len(base_metadata)] == base_metadata,
             'original local configuration changed around its effective query')
        need(not os.path.lexists(checkout / '.git/info/attributes'), 'no local attribute override for providers')
        observations = _provider_attributes(bookends, core, project, checkout, deadline, guard, commands, captures, directory)
        need(_metadata(checkout, sorted(attr_names)) == metadata, 'original provider-rule metadata remains unchanged')
        _scope(config_admission); guard()
        return {'schema': 'p4-r22-original-apex-project-checkout-rules-v1',
                'HEAD': head, 'origin': origin, 'project': project, 'candidate_count': 2,
                'attributes': observations, 'configuration': configuration,
                'commands': commands, 'query_captures': captures,
                'Git_metadata_before_after': metadata,
                'conversion_scope': config_admission['conversion_scope'],
                'all_five_attributes_unspecified': True, 'committed_effective_equal': True,
                'custom_filters_executed': False, 'source_mutations': False,
                'source_recovery_complete': False, 'runtime_qualified': False, 'production_ready': False}
    except BaseException as error:
        write_bytes(directory / 'FAILURE.json', (json.dumps({
            'schema': 'p4-r22-original-apex-project-checkout-rules-failure-v1',
            'error': repr(error), 'commands': commands, 'query_captures': captures,
            'source_mutations': False, 'source_recovery_complete': False,
            'runtime_qualified': False, 'production_ready': False,
        }, sort_keys=True, indent=2) + '\n').encode())
        raise


def _snapshot_projects(bookends, core, source, old_projects, new_projects, output, deadline, guard,
                       admission):
    """Internal fixture seam; production callers must use partial_snapshot."""
    source, output = Path(source), Path(output)
    need(source.resolve() == source and source.is_dir() and not os.path.lexists(output),
         'original real source and fresh partial diagnostic output')
    need(output.is_absolute() and output.parent.resolve() == output.parent
         and source != output and source not in output.parents,
         'partial diagnostic evidence must be outside the original source')
    old_projects, new_projects = map(bookends.normalized_projects, (old_projects, new_projects))
    need(len(old_projects) == len(new_projects), 'same ordered partial source project roster')
    queries = output.with_name(output.name + '.queries')
    queries.mkdir(mode=0o700)
    total = hashlib.sha256(); summaries = []
    total_files = total_bytes = total_absent = 0
    observed_ns = time.time_ns(); provider_profiles = {}; provider_attributes = {}
    active = {}
    try:
        with output.open('xb') as stream:
            for number, (old, new) in enumerate(zip(old_projects, new_projects)):
                need(time.monotonic() < deadline, 'original partial source diagnostic deadline')
                guard(); _scope(admission)
                need(old['path'] == new['path'], 'ordered original project identity')
                provider = core.PROVIDERS.get(old['path'])
                is_provider = provider is not None
                need((new == {**old, 'sparse_paths': old['sparse_paths'] + [provider['cone']]})
                     if is_provider else old == new,
                     'only both complete original provider directories may expand')
                checkout = source / old['path']
                need(checkout.resolve() == checkout and checkout.is_dir(), 'real original checkout')
                _no_git_locks(checkout)
                directory = queries / ('project-%04d' % number); directory.mkdir(mode=0o700)
                commands = []; captures = []
                active = {'project': old['path'], 'actual_commands': commands, 'query_captures': captures}
                base_metadata = _metadata(checkout, [])
                config = _configuration(bookends, checkout, deadline, guard, commands, captures, directory, admission)
                head = bookends.git(checkout, ['rev-parse', 'HEAD'], deadline, guard, commands).decode().strip()
                origin = bookends.git(checkout, ['remote', 'get-url', 'origin'], deadline, guard, commands).decode().strip()
                need(head == old['commit'] and origin == old['url'], 'exact original project HEAD and origin')
                tree = bookends.git(checkout, ['rev-parse', 'HEAD^{tree}'], deadline, guard, commands).decode().strip()
                committed = bookends.tree_records(bookends.git(checkout, ['ls-tree', '-rz', '--full-tree', 'HEAD'],
                                                                deadline, guard, commands))
                index = bookends.tracked_records(bookends.git(checkout, ['ls-files', '--stage', '-z'],
                                                              deadline, guard, commands))
                need(index == committed, 'original index differs from fixed HEAD')
                names = sorted(index)
                metadata = _metadata(checkout, names)
                need(metadata[:len(base_metadata)] == base_metadata,
                     'original local configuration changed around its effective query')
                metadata_ref = write_bytes(directory / 'git-metadata-before.ndjson',
                    b''.join(bookends.encoded(row) for row in metadata))
                flags = {}
                for record in bookends.git(checkout, ['ls-files', '-t', '-z'], deadline, guard, commands).split(b'\0'):
                    if record:
                        flag, name = record[:1].decode(), record[2:].decode()
                        need(record[1:2] == b' ' and name not in flags and flag in ('H', 'S'),
                             'ordinary complete index flags only')
                        flags[name] = flag
                need(set(flags) == set(index), 'complete original index flags')
                selected = old
                if old['sparse_paths']:
                    cones = bookends.git(checkout, ['sparse-checkout', 'list'], deadline, guard, commands).decode().splitlines()
                    need(len(cones) == len(set(cones)), 'unique actual sparse cones')
                    if set(cones) == set(bookends.canonical_sparse_cones(old['sparse_paths'])):
                        if is_provider:
                            provider_profiles[old['path']] = 'old'
                    else:
                        need(is_provider and set(cones) == set(bookends.canonical_sparse_cones(new['sparse_paths'])),
                             'actual sparse cones match neither fixed provider scope')
                        selected = new; provider_profiles[old['path']] = 'new'
                else:
                    need(set(flags.values()) <= {'H'}, 'complete original project cannot omit sparse entries')
                    cones = []
                all_filters = _all_tracked_filters(checkout, names, deadline, guard, directory, commands)
                if is_provider:
                    need(not os.path.lexists(checkout / '.git/info/attributes'), 'no local attribute override for providers')
                    provider_attributes[old['path']] = _provider_attributes(
                        bookends, core, old['path'], checkout, deadline, guard, commands, captures, directory)
                body = hashlib.sha256(); files = size = absent = 0
                for relative, (mode, oid) in sorted(index.items()):
                    # Only these four entries use the old cone requirement when
                    # the actual sparse list has already reached the new scope.
                    # observe_blob still rejects every missing H and every byte
                    # or mode mismatch; _candidate additionally forbids conversion.
                    candidate_key = (old['path'], relative)
                    candidate = candidate_key in core.CANDIDATES
                    required_cones = old['sparse_paths'] if candidate else selected['sparse_paths']
                    # lexists() in the old helper is not an EACCES classifier.
                    # Probe the original path first, accepting only ENOENT as
                    # absence so a denied S entry cannot look like a sparse one.
                    try:
                        (checkout / relative).lstat()
                    except FileNotFoundError:
                        pass
                    row, identity = bookends.observe_blob(checkout, relative, mode, oid, flags[relative],
                        required_cones, deadline, guard, old['commit'], commands)
                    observed = {'project': old['path'], **row, 'f9': identity}
                    if candidate:
                        core._candidate(observed, candidate_key, True)
                    body.update(bookends.encoded(row)); stream.write(bookends.encoded(observed))
                    if row['present']:
                        files += 1; size += row.get('bytes', 0)
                    else:
                        absent += 1
                need(_metadata(checkout, names) == metadata, 'original Git/configuration/attribute inputs changed')
                _scope(admission)
                need(not bookends.git(checkout, ['status', '--porcelain=v1', '--untracked-files=all'],
                                       deadline, guard, commands), 'partial source has dirty or untracked members')
                need(bookends.git(checkout, ['rev-parse', 'HEAD'], deadline, guard, commands).decode().strip() == head,
                     'original HEAD changed during partial body reads')
                need(_metadata(checkout, names) == metadata, 'original Git metadata changed after status')
                _scope(admission)
                stable = {'project': selected, 'tree': tree, 'tracked_entries': len(index),
                          'materialized_entries': files, 'materialized_bytes': size,
                          'sparse_absent_entries': absent, 'body_sha256': body.hexdigest()}
                total.update(bookends.encoded(stable))
                summaries.append({**stable, 'actual_commands': commands, 'query_captures': captures,
                                  'Git_metadata_before_after': {'entries': len(metadata), 'inventory': metadata_ref},
                                  'configuration': config,
                                  'actual_sparse_cones': cones, 'all_tracked_filter_observation': all_filters})
                total_files += files; total_bytes += size; total_absent += absent
                stream.flush()
            os.fsync(stream.fileno())
        need(set(provider_profiles) == set(provider_attributes) == set(core.PROVIDERS)
             and all(state in ('old', 'new') for state in provider_profiles.values()),
             'both actual original provider scopes and all four attribute observations')
        _scope(admission); guard()
        return {'schema': SCHEMA, 'observed_ns': observed_ns, 'finished_ns': time.time_ns(),
                'projects': summaries, 'project_count': len(summaries),
                'materialized_entries': total_files, 'materialized_bytes': total_bytes,
                'sparse_absent_entries': total_absent, 'content_sha256': total.hexdigest(),
                'inventory': fingerprint(output, maximum=1024 * 1024 * 1024),
                'actual_provider_cone_profiles': provider_profiles, 'provider_checkout_attributes': provider_attributes,
                'all_actual_Git_blob_reads_verified': True, 'all_tracked_filter_queries_complete': True,
                'conversion_scope': admission['conversion_scope'],
                'strict_complete_source_verified': False, 'recovery_admission_only': True,
                'source_mutations': False, 'custom_filters_executed': False,
                'profile_contract_validated': False, 'source_recovery_complete': False,
                'runtime_qualified': False, 'production_ready': False}
    except BaseException as error:
        failure = {'schema': SCHEMA + '-failure', 'observed_ns': observed_ns, 'finished_ns': time.time_ns(),
                   'error': repr(error), 'completed_projects': summaries, 'active_project': active,
                   'strict_complete_source_verified': False, 'source_recovery_complete': False,
                   'source_mutations': False, 'runtime_qualified': False, 'production_ready': False}
        write_bytes(output.with_name(output.name + '.failure.json'),
                    (json.dumps(failure, sort_keys=True, indent=2) + '\n').encode())
        raise


def partial_snapshot(bookends, core, source, old, new, output, deadline, guard,
                     config_admission, old_manifest_ref):
    old, new = core.validate_profiles(bookends, old, new)
    need(type(deadline) in (int, float) and time.monotonic() < deadline,
         'original caller deadline still active')
    _production_admission(config_admission)
    source = Path(source)
    manifest = source / '.droidloom-source-manifest.json'
    need(str(manifest) == old_manifest_ref['path'] and fingerprint(manifest) == old_manifest_ref,
         'exact old manifest before conditional resume diagnosis')
    fd = os.open(manifest, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        need(f9(os.fstat(fd)) == old_manifest_ref['identity'] and old_manifest_ref['bytes'] <= 16 * 1024 * 1024,
             'bounded same original old manifest inode')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(16 * 1024 * 1024 + 1)
        need(len(raw) == old_manifest_ref['bytes'] and hashlib.sha256(raw).hexdigest() == old_manifest_ref['sha256']
             and f9(os.fstat(fd)) == f9(manifest.lstat()) == old_manifest_ref['identity'],
             'old manifest complete held body')
        need(bookends.normalized_manifest(bookends.strict_json(raw)) == old,
             'partial diagnosis requires the original complete old manifest')
    finally:
        os.close(fd)
    result = _snapshot_projects(bookends, core, source, old['plan']['projects'], new['plan']['projects'],
        output, deadline, guard, config_admission)
    need(fingerprint(manifest) == old_manifest_ref, 'original old manifest remains unchanged')
    result.update(profile_contract_validated=True, original_manifest=old_manifest_ref,
                  old_manifest_semantic_sha256=hashlib.sha256(bookends.encoded(old)).hexdigest(),
                  new_manifest_semantic_sha256=hashlib.sha256(bookends.encoded(new)).hexdigest())
    return result
