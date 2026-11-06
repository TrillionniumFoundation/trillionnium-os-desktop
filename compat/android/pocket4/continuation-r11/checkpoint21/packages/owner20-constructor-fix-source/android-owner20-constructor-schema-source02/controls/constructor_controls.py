"""Actual-shape constructor regressions; every OS/namespace/hash/spawn input is an explicit seam.

These tests execute the production Capture.__init__, _bind_init,
_borrowed_init_current, directory ownership and failure-record paths. They do
not execute the Android accessor, open live init objects, read any property,
enter namespaces, change credentials, or create a child. Synthetic FD numbers
exist only in FakeOS and must never be passed to the host OS.
"""
import ast
import copy
import hashlib
import json
import stat
import types

ORIGINAL_SOURCE_SHA = '8aa61f8a7a0e79511dc3bb49e4f4f857d7dc40b68a26e431cda0af0629bf56b2'
CANDIDATE_SOURCE_SHA = 'e5d993f3bc05cebb4c61c44c84976fca491c10714799a684fed16ef85cd87f8d'
ACTUAL_SAFE_SHA = '46427c74b60af66ba02262d323ec128b32ada64d71489c9541e939216c31b1a8'
ACTUAL_RUNTIME_SHA = 'f3f8afc6f8783b69fe5db48913586dc3f16bda63a4f8820aa1251cffb635bda1'

def require(value, message):
    if not value:
        raise AssertionError(message)

def run(P, baseline_text, safe_text, observer, unused_capture_observer, diagnostics, candidate_text):
    rows = diagnostics['controls']
    require(hashlib.sha256(baseline_text.encode()).hexdigest() == ORIGINAL_SOURCE_SHA,
            'exact actual-run baseline required')
    require(hashlib.sha256(safe_text.encode()).hexdigest() == ACTUAL_SAFE_SHA,
            'exact privacy-safe actual projection required')
    safe = json.loads(safe_text)
    require(safe['original_runtime'] == {'bytes': 774912, 'sha256': ACTUAL_RUNTIME_SHA} and
            safe['original_full_hash_and_bytes_verified'] is True and
            safe['raw_init_log_or_crash_packet_exported'] is False,
            'actual external authority differs')
    actor = safe['runtime']['actor_result']
    actual = actor['property_visibility_observation']
    require(actual['first_error']['type'] == 'KeyError' and
            actual['first_error']['error'] == "KeyError('init_current_checks')" and
            actual['first_error']['stage'] == 'initialization' and
            actual['spawn_attempts'] == actual['protocol_packets'] == 0 and
            actual['child_started'] is False and actual['held_fds_closed'] is True,
            'actual failed constructor shape differs')
    old = types.ModuleType('owner20_actual_failed_constructor_baseline')
    exec(compile(baseline_text, 'baseline_property_visibility.py', 'exec'), old.__dict__)
    snapshot = actor['crash_buffer_observation']['init_snapshot']
    audit = actor['latest_status']['relay_lifecycle']
    root_actual = actor['crash_buffer_observation']['init_root']
    domain = actor['crash_buffer_observation']['generation_domain']
    actor_ns = actual['actor_namespaces_after']
    require(len(snapshot['namespaces']) == 10 and snapshot['identity']['uids'] ==
            snapshot['identity']['gids'] == [0, 0, 0, 0],
            'actual init namespace/root identity fixture differs')
    require(domain['path'].endswith('/g-' + audit['nonce'] + '/android'),
            'actual generation domain fixture differs')

    def case(name, function):
        before = observer('before', name)
        primary = None
        details = None
        try:
            details = function()
        except BaseException as error:
            primary = error
        after = None
        try:
            after = observer('after', name, before)
        except BaseException as error:
            if primary is None:
                primary = error
            else:
                primary.add_note('host FD equality: ' + repr(error)[:160])
        row = {'name': name, 'passed': primary is None,
               'scope': 'actual safe shape; real production constructor and init checks; explicit OS/hash/spawn seams',
               'before_fd_snapshot': before, 'after_fd_snapshot': after}
        if details is not None:
            row['details'] = details
        if primary is not None:
            row['error'] = {'type': type(primary).__name__, 'error': repr(primary)[:512]}
        rows.append(row)
        if primary is not None:
            raise primary

    def record_ast(text):
        tree = ast.parse(text)
        capture = next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == 'Capture')
        constructor = next(x for x in capture.body if isinstance(x, ast.FunctionDef) and x.name == '__init__')
        assignments = [x for x in constructor.body if isinstance(x, ast.Assign) and
                       any(isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and
                           t.value.id == 'self' and t.attr == 'record' for t in x.targets)]
        require(len(assignments) == 1 and isinstance(assignments[0].value, ast.Dict),
                'single production constructor record assignment')
        return tree, assignments[0].value

    def only_record_change():
        require(hashlib.sha256(candidate_text.encode()).hexdigest() == CANDIDATE_SOURCE_SHA,
                'candidate production source pin')
        left, left_record = record_ast(baseline_text)
        right, right_record = record_ast(candidate_text)
        matches = [i for i, key in enumerate(right_record.keys)
                   if isinstance(key, ast.Constant) and key.value == 'init_current_checks']
        require(len(matches) == 1 and not any(isinstance(key, ast.Constant) and
                key.value == 'init_current_checks' for key in left_record.keys),
                'only candidate owns the missing field')
        index = matches[0]
        require(isinstance(right_record.values[index], ast.List) and
                not right_record.values[index].elts, 'new list must be fresh empty literal')
        del right_record.keys[index]
        del right_record.values[index]
        require(ast.dump(left, include_attributes=False) == ast.dump(right, include_attributes=False),
                'all remaining production AST unchanged')
        return {'only_new_record_key': 'init_current_checks', 'other_production_AST_unchanged': True}

    class Clock:
        def __init__(self):
            self.now = 1_000_000_000
        def monotonic_ns(self):
            self.now += 1000
            return self.now

    def statrow(meta):
        return types.SimpleNamespace(st_dev=meta['device'], st_ino=meta['inode'],
            st_mode=meta.get('mode', stat.S_IFREG | 0o444), st_uid=meta.get('uid', 0),
            st_gid=meta.get('gid', 0), st_nlink=meta.get('nlink', 1),
            st_size=meta.get('bytes', 0), st_mtime_ns=meta.get('mtime_ns', 0),
            st_ctime_ns=meta.get('ctime_ns', 0))

    def exercise(module, variant='ok', extra_checks=0):
        real_os = module.os
        clock = Clock()
        captures = []
        stats = {'spawn_seam_calls': 0, 'hash_seam_calls': 0, 'init_live_seam_calls': 0,
                 'snapshot_seam_calls': 0, 'synthetic_open_calls': 0, 'synthetic_close_calls': 0}
        init_proc, init_exe = 10001, 10002
        root_meta = dict(root_actual, mode=root_actual['type'] | root_actual['mode'])
        namespace_by_name = dict(zip(module.NAMES, snapshot['namespaces']))
        domain_meta = {'device': domain['device'], 'inode': domain['inode'],
                       'mode': stat.S_IFDIR | 0o755, 'uid': 0, 'gid': 0, 'nlink': 2}
        files = {
            init_proc: {'path': '<borrowed-init-proc>', 'meta': {'device': 26, 'inode': 123}},
            init_exe: {'path': '<borrowed-init-exe>', 'meta': copy.deepcopy(actual['init_source']['metadata'])}}
        borrowed = {init_proc, init_exe}
        closed = set()
        domain_opens = [0]

        class FakeOS:
            def __getattr__(self, name):
                # Constants only. No unlisted host method can be used as fallback.
                if name.startswith('O_') and hasattr(real_os, name):
                    return getattr(real_os, name)
                raise AssertionError('unapproved fake OS member: ' + name)
            def getpid(self):
                return actor['actor_pid']
            def getuid(self): return 0
            def geteuid(self): return 0
            def getgid(self): return 0
            def getegid(self): return 0
            def allocate(self, path, meta):
                fd = 20000 + stats['synthetic_open_calls']
                stats['synthetic_open_calls'] += 1
                require(fd not in files and fd not in closed, 'synthetic FD allocator uniqueness')
                files[fd] = {'path': path, 'meta': copy.deepcopy(meta)}
                return fd
            def fstat(self, fd):
                require(fd in files, 'synthetic fstat on unowned/closed FD')
                return statrow(files[fd]['meta'])
            def stat(self, path, *, dir_fd=None):
                if path.startswith('/proc/self/ns/') and dir_fd is None:
                    name = path[len('/proc/self/ns/'):]
                    require(name in actor_ns, 'fixed actor namespace name')
                    return statrow(actor_ns[name])
                require(dir_fd == init_proc, 'all named init checks use the held fixture proc')
                if path.startswith('ns/'):
                    name = path[3:]
                    require(name in namespace_by_name, 'fixed init namespace name')
                    value = dict(namespace_by_name[name])
                    if variant == 'named_namespace' and name == 'mnt':
                        value['inode'] += 1
                    return statrow(value)
                if path == 'root':
                    value = dict(root_meta)
                    if variant == 'named_root': value['inode'] += 1
                    return statrow(value)
                if path == 'exe':
                    value = dict(actual['init_source']['metadata'])
                    if variant == 'named_executable': value['inode'] += 1
                    return statrow(value)
                raise AssertionError('unexpected named init path: ' + path)
            def open(self, path, flags, mode=0o777, *, dir_fd=None):
                require(flags & real_os.O_CLOEXEC, 'production open keeps CLOEXEC')
                if dir_fd == init_proc and path.startswith('ns/'):
                    name = path[3:]
                    require(name in namespace_by_name, 'fixed opened init namespace')
                    return self.allocate(path, namespace_by_name[name])
                if dir_fd == init_proc and path == 'root':
                    return self.allocate(path, root_meta)
                if path == '/' and dir_fd is None:
                    require(flags & real_os.O_DIRECTORY, 'held directory walk root')
                    return self.allocate('/', {'device': 30, 'inode': 1, 'mode': stat.S_IFDIR | 0o755})
                require(dir_fd in files, 'walk/open parent must be held')
                parent = files[dir_fd]['path']
                if path == 'cgroup.procs':
                    require(parent == domain['path'] and flags & real_os.O_WRONLY and
                            flags & real_os.O_NOFOLLOW, 'exact held generation cgroup.procs seam')
                    return self.allocate(parent + '/' + path, {'device': domain['device'],
                        'inode': domain['inode'] + 101, 'mode': stat.S_IFREG | 0o644})
                require('/' not in path and path not in ('', '.', '..') and
                        flags & real_os.O_DIRECTORY and flags & real_os.O_NOFOLLOW,
                        'bounded nofollow fixed directory component')
                child = parent.rstrip('/') + '/' + path
                require(domain['path'] == child or domain['path'].startswith(child + '/'),
                        'only exact generation directory ancestors')
                meta = {'device': domain['device'], 'inode': 200 + len(child),
                        'mode': stat.S_IFDIR | 0o755, 'uid': 0, 'gid': 0}
                if child == domain['path']:
                    domain_opens[0] += 1
                    meta = dict(domain_meta)
                    if variant == 'named_domain' and domain_opens[0] > 1:
                        meta['inode'] += 1
                return self.allocate(child, meta)
            def close(self, fd):
                require(fd in files and fd not in borrowed and fd not in closed,
                        'synthetic close exactly once, never borrowed')
                del files[fd]
                closed.add(fd)
                stats['synthetic_close_calls'] += 1

        fake = FakeOS()
        class Init:
            proc = init_proc
            exe = init_exe
            def snapshot(self):
                stats['snapshot_seam_calls'] += 1
                return copy.deepcopy(snapshot)
            def live(self):
                stats['init_live_seam_calls'] += 1
                if variant == 'deadline' and stats['init_live_seam_calls'] == 1:
                    clock.now = captures[0].deadline

        def bounded(fd, path, maximum):
            require(fd == init_proc and path in ('status', 'cgroup'), 'fixed held init input seam')
            if path == 'cgroup':
                data = ('0::' + domain['path'][len('/sys/fs/cgroup'):] + '/init-bootstrap\n').encode()
            else:
                uid = 1069 if variant == 'current_uid' else 0
                data = ('Pid:\t%d\nUid:\t%d\t%d\t%d\t%d\nGid:\t0\t0\t0\t0\n' %
                        (snapshot['process']['pid'], uid, uid, uid, uid)).encode()
            require(len(data) <= maximum, 'bounded metadata seam')
            return data

        def require_cgroup2(fd):
            require(fd in files and files[fd]['path'] == domain['path'] and
                    files[fd]['meta']['device'] == domain['device'], 'exact cgroup2 seam')
        owned = types.SimpleNamespace(NAMES=module.NAMES, bounded=bounded, require_cgroup2=require_cgroup2)
        def bind_helper(self, ignored_fd):
            captures.append(self)
            self.helper_meta = copy.deepcopy(actual['helper']['metadata'])
            self.helper_path = '/fixed-fixture/sdk-visibility'
            self._take('helper', fake.allocate('<helper-fixture>', self.helper_meta))
            self.record['helper'] = copy.deepcopy(actual['helper'])
        def hash_init(self, fd, maximum, during_observation=True):
            require(fd == init_exe and maximum == 16 * 1024 * 1024 and during_observation,
                    'only init hash seam used')
            stats['hash_seam_calls'] += 1
            return b'EXPLICIT-HASH-SEAM-NOT-ACTUAL-ELF', copy.deepcopy(actual['init_source'])
        def spawn(self):
            require(self.record['init_current_checks'] and self.pid is None and
                    self.record['spawn_attempts'] == self.record['protocol_packets'] == 0,
                    'real constructor reached spawn seam only after current init proof')
            stats['spawn_seam_calls'] += 1
        saved = {'os': module.os, 'time': module.time, 'filesystem_type': module.filesystem_type,
                 '_bind_helper': module.Capture._bind_helper, '_hash': module.Capture._hash,
                 '_spawn': module.Capture._spawn}
        result = None
        try:
            module.os = fake
            module.time = clock
            module.filesystem_type = lambda fd: module.ROOT_TMPFS if files[fd]['path'] == 'root' else -1
            module.Capture._bind_helper = bind_helper
            module.Capture._hash = hash_init
            module.Capture._spawn = spawn
            plan = {'attempt_nonce': actual['attempt_nonce'],
                    'spec': {'pressure_relay': {'cgroup_parent':
                        domain['path'].rsplit('/g-', 1)[0]}}}
            c = module.Capture(Init(), copy.deepcopy(audit), plan, {}, -1, None, owned, 30.0)
            require(c in captures, 'real constructor was used')
            if extra_checks:
                require(c.record['first_error'] is None, 'repeat begins from successful constructor')
                for unused in range(extra_checks):
                    c._borrowed_init_current()
            result = {'record': c.record, 'stats': stats}
        finally:
            primary = None
            for c in captures:
                for name in list(c.fds):
                    try:
                        c._close(name)
                    except BaseException as error:
                        if primary is None: primary = error
            module.os = saved['os']
            module.time = saved['time']
            module.filesystem_type = saved['filesystem_type']
            module.Capture._bind_helper = saved['_bind_helper']
            module.Capture._hash = saved['_hash']
            module.Capture._spawn = saved['_spawn']
            require(set(files) == borrowed, 'every synthetic owned FD closed; borrowed retained')
            require(stats['synthetic_open_calls'] == stats['synthetic_close_calls'],
                    'complete synthetic acquisition/close ledger')
            if primary is not None:
                raise primary
        require(result is not None, 'constructor result retained')
        require(all(row['closed'] and row['close_attempted_once']
                    for row in result['record']['fd_close_records']), 'production close records retained')
        return result

    def brief(value):
        r = value['record']
        return {'first_error': r['first_error'], 'current_checks': len(r.get('init_current_checks', [])),
                'spawn_seam_calls': value['stats']['spawn_seam_calls'],
                'actual_child_started': r['child_started'], 'source_qualified': r['source_qualified_before_reads'],
                'synthetic_open_calls': value['stats']['synthetic_open_calls'],
                'synthetic_close_calls': value['stats']['synthetic_close_calls']}

    def baseline_fails():
        value = exercise(old)
        row = value['record']
        require(row['first_error'] == actual['first_error'] and value['stats']['spawn_seam_calls'] == 0 and
                'init_current_checks' not in row and row['secondary_errors'] == [],
                'actual old constructor KeyError must reproduce, without helper spawn')
        return brief(value)

    def candidate_passes():
        value = exercise(P)
        r = value['record']
        require(r['first_error'] is None and r['secondary_errors'] == [] and
                value['stats']['spawn_seam_calls'] == 1 and len(r['init_current_checks']) == 1,
                'fixed production constructor must append before its spawn seam')
        check = r['init_current_checks'][0]
        require(r['started_monotonic_ns'] <= check['before_ns'] <= check['after_ns'] <
                r['deadline_monotonic_ns'] and all(v is True for k, v in check.items()
                if k not in ('before_ns', 'after_ns')), 'complete current proof bounds')
        return brief(value)

    def repeated_checks():
        value = exercise(P, extra_checks=2)
        require(value['record']['first_error'] is None and
                len(value['record']['init_current_checks']) == 3 and
                value['stats']['spawn_seam_calls'] == 1, 'three current checks, one constructor')
        return brief(value)

    def separate_lists():
        left, right = exercise(P), exercise(P)
        a, b = left['record']['init_current_checks'], right['record']['init_current_checks']
        require(a is not b and len(a) == len(b) == 1, 'each constructor owns a separate fresh list')
        a.append({'fixture_only': True})
        require(len(b) == 1, 'no cross-generation mutable list alias')
        return {'distinct_constructor_owned_lists': True}

    def negative(variant, reason):
        value = exercise(P, variant)
        row = value['record']
        require(row['first_error'] is not None and reason in row['first_error']['error'] and
                row['first_error']['stage'] == 'initialization' and
                value['stats']['spawn_seam_calls'] == 0 and row['init_current_checks'] == [] and
                not row['child_started'] and not row['source_qualified_before_reads'] and
                row['start_token_attempts'] == row['finish_token_attempts'] == row['protocol_packets'] == 0,
                'negative identity/deadline gate must remain before helper spawn or token')
        return brief(value)

    case('only-fresh-constructor-list-field-changes-production-AST', only_record_change)
    case('old-actual-constructor-shape-reproduces-init-current-checks-KeyError', baseline_fails)
    case('corrected-real-constructor-record-and-current-init-proof', candidate_passes)
    case('same-constructor-repeated-current-init-proofs-append', repeated_checks)
    case('independent-constructors-have-independent-proof-lists', separate_lists)
    case('changed-named-init-namespace-blocks-spawn', lambda: negative('named_namespace', 'SDK_INIT_NAMED_NAMESPACE_CHANGED'))
    case('changed-named-init-root-blocks-spawn', lambda: negative('named_root', 'SDK_INIT_NAMED_ROOT_CHANGED'))
    case('changed-current-init-UID-blocks-spawn', lambda: negative('current_uid', 'SDK_INIT_CURRENT_IDS'))
    case('changed-current-init-executable-blocks-spawn', lambda: negative('named_executable', 'SDK_INIT_CURRENT_EXECUTABLE_CHANGED'))
    case('changed-named-generation-domain-blocks-spawn', lambda: negative('named_domain', 'SDK_DOMAIN_NAMED_CHANGED'))
    case('original-two-second-deadline-still-blocks-spawn', lambda: negative('deadline', 'SDK_SHARED_TWO_SECOND_DEADLINE'))
    require(len(rows) == 11, 'fixed constructor regression count')
    return {'schema': 1, 'kind': 'owner20-constructor-init-checks-regressions01',
            'success': True, 'controls': rows, 'count': len(rows),
            'actual_original_source_sha256': ORIGINAL_SOURCE_SHA,
            'candidate_source_sha256': CANDIDATE_SOURCE_SHA,
            'actual_safe_projection_sha256': ACTUAL_SAFE_SHA,
            'Android_executed': False, 'Main_access': False,
            'actual_namespace_or_credential_changes': False, 'property_reads_or_writes': False,
            'real_child_spawned': False, 'real_init_or_bionic_qualified': False,
            'root_warmed_cache_limitation_remains': True}
