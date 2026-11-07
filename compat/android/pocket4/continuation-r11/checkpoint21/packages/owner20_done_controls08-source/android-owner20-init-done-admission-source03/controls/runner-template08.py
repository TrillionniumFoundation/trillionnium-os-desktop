"""Exactly pinned host-only tests; no Android/namespace/Main runtime entry."""
import ast
import base64
import hashlib
import errno
import json
import os
import signal
import stat
import sys
import tempfile
import time
import types

PACKET_BYTES = __PACKET_BYTES__
PACKET_SHA = '__PACKET_SHA__'
PACKET_B64 = '__PACKET_B64__'
TEMP_ROOT = '/tmp/p4-owner20-property-done-controls-08'
NAMES = ('pid', 'pid_for_children', 'mnt', 'cgroup', 'user', 'net',
         'ipc', 'uts', 'time', 'time_for_children')


def need(value, message):
    if not value:
        raise RuntimeError(message)


class FDObservation:
    """Only live /proc/self/fd numbers and fstat identities; never fd contents."""
    def __init__(self, result):
        self.result = result
        self.identities = []
        self.index = {}
        self.snapshots = []
        self.captures = []
        self.owned = []
        self.result['fd_diagnostic'] = {'identity_fields': ['fd','device','inode','mode','uid','gid','rdev'],
            'identity_pool': self.identities, 'snapshots': self.snapshots,
            'first_discrepancy': None, 'capture_cleanup': [],
            'unrelated_ambient_contents_or_targets_read': False, 'only_self_proc_fd_enumerated': True}

    @staticmethod
    def info(fd):
        st = os.fstat(fd)
        return {'fd': fd, 'device': st.st_dev, 'inode': st.st_ino, 'mode': st.st_mode,
                'uid': st.st_uid, 'gid': st.st_gid, 'rdev': st.st_rdev}

    def sample(self, stage, case=None):
        names = os.listdir('/proc/self/fd')
        need(len(names) <= 64 and all(x.isdecimal() for x in names), 'SELF_FD_ENUMERATION_BOUND')
        alive = {}; gone = []
        for fd in sorted(int(x) for x in names):
            try:
                value = self.info(fd)
            except OSError as error:
                if error.errno == errno.EBADF:
                    # listdir closed its own directory fd before returning.
                    # Record every disappeared entry, but never call it live.
                    gone.append(fd); continue
                raise
            key = tuple(value.values())
            if key not in self.index:
                need(len(self.identities) < 256, 'SELF_FD_IDENTITY_POOL_BOUND')
                self.index[key] = len(self.identities)
                self.identities.append(value)
            alive[str(fd)] = self.index[key]
        need(len(self.snapshots) < 96, 'SELF_FD_SNAPSHOT_BOUND')
        index = len(self.snapshots)
        self.snapshots.append({'stage': stage, 'case': case, 'live': alive,
                               'listed_then_EBADF': gone})
        return index

    def equal(self, before, after, stage, case=None):
        a = self.snapshots[before]['live']; b = self.snapshots[after]['live']
        if a == b:
            return True
        detail = {'stage': stage, 'case': case, 'before_snapshot': before, 'after_snapshot': after,
                  'added': sorted(set(b)-set(a), key=int),
                  'removed': sorted(set(a)-set(b), key=int),
                  'changed': sorted((k for k in set(a)&set(b) if a[k] != b[k]), key=int)}
        if self.result['fd_diagnostic']['first_discrepancy'] is None:
            self.result['fd_diagnostic']['first_discrepancy'] = detail
        return False

    def observe_case(self, stage, name, before=None):
        index = self.sample('case_' + stage, name)
        if before is not None:
            need(self.equal(before, index, 'case', name), 'HOST_CASE_LIVE_FD_IDENTITY_CHANGED:' + name)
        return index

    def track_capture(self, capture):
        capture_number = len(self.captures)
        need(capture_number < 64, 'CAPTURE_FIXTURE_COUNT_BOUND')
        self.captures.append(capture)
        original_take = capture._take; original_close = capture._close
        active = {}
        def take(name, fd):
            # Registration is before the original owner can fail. Duplicate
            # aliases to the same still-owned fd keep the same journal entry.
            if fd not in active:
                row = {'capture': capture_number, 'fd': fd, 'identity': None,
                       'close_attempted': False, 'observed_closed': False}
                need(len(self.owned) < 256, 'OWNED_FD_JOURNAL_BOUND')
                self.owned.append(row); active[fd] = row
                row['identity'] = self.info(fd)
            duplicate = name in capture.fds
            if duplicate:
                active[fd]['close_attempted'] = True
            return original_take(name, fd)
        def close(name):
            fd = capture.fds.get(name)
            if fd in active:
                row = active.pop(fd)
                row['close_attempted'] = True
            else:
                row = None
            primary = None
            try:
                return original_close(name)
            except BaseException as error:
                primary = error; raise
            finally:
                if row is not None:
                    try:
                        try:
                            current = self.info(fd)
                        except OSError as error:
                            if error.errno != errno.EBADF: raise
                            row['observed_closed'] = True
                        else:
                            row['observed_closed'] = current != row['identity']
                    except BaseException as observation_error:
                        if primary is None: raise
                        primary.add_note('FD close observation: ' + repr(observation_error)[:160])
        capture._take = take
        capture._close = close

    def cleanup_captures(self):
        errors = []
        for number, capture in enumerate(self.captures):
            for attr in ('child_sock', 'sock'):
                obj = getattr(capture, attr, None)
                if not isinstance(obj, sys.modules['socket'].socket):
                    continue  # Pure Sender seams own no kernel descriptors.
                setattr(capture, attr, None)
                row = {'capture': number, 'kind': attr, 'attempted': True, 'closed': False}
                self.result['fd_diagnostic']['capture_cleanup'].append(row)
                try:
                    obj.close(); row['closed'] = True
                except BaseException as error:
                    row['error'] = repr(error)[:160]; errors.append(row)
            for name in list(capture.fds):
                row = {'capture': number, 'kind': name, 'attempted': True, 'closed': False}
                self.result['fd_diagnostic']['capture_cleanup'].append(row)
                try:
                    capture._close(name); row['closed'] = True
                except BaseException as error:
                    row['error'] = repr(error)[:160]; errors.append(row)
        # A close error is never retried against a possibly reused number.
        # Only descriptors registered before an original _take failure and
        # never subjected to a close attempt may be closed here.
        for entry in self.owned:
            if entry['observed_closed']:
                continue
            try:
                current = self.info(entry['fd'])
            except OSError as error:
                if error.errno == errno.EBADF:
                    entry['observed_closed'] = True; continue
                errors.append({'stage':'journal_fstat','error':repr(error)[:160]}); continue
            if entry['identity'] is not None and current != entry['identity']:
                entry['observed_closed'] = True; continue
            if entry['close_attempted']:
                errors.append({'stage':'ambiguous_original_close_still_live','capture':entry['capture'],
                               'fd':entry['fd']})
                continue
            entry['close_attempted'] = True
            try:
                os.close(entry['fd']); entry['observed_closed'] = True
            except BaseException as error:
                errors.append({'stage':'owned_journal_close','error':repr(error)[:160]})
        self.result['fd_diagnostic']['owned_capture_fds'] = self.owned
        self.result['fd_diagnostic']['capture_cleanup_errors'] = errors
        need(not errors, 'TRACKED_CAPTURE_FD_CLEANUP_FAILED')


DEPENDENCY_AUTHORITY = json.loads("{\n  \"schema\": \"owner20-actual-ctypes-import-dependency-v1\",\n  \"actual_stdout\": {\n    \"bytes\": 6285,\n    \"sha256\": \"f3363229acb906a9bb6ae16850afec3c4fd24a484f923774e5964b216ab0febc\",\n    \"git_blob_sha\": \"e060ebe906b767f258207203be80b642aae2679e\",\n    \"job\": \"1a1b00175bd-fc05-6d62\"\n  },\n  \"actual_original_result_success\": false,\n  \"source_sha256\": \"8aa61f8a7a0e79511dc3bb49e4f4f857d7dc40b68a26e431cda0af0629bf56b2\",\n  \"source_line\": 9,\n  \"source_import\": \"ctypes\",\n  \"target\": {\n    \"bytes\": 64184,\n    \"ctime_ns\": 1791083436303902806,\n    \"device\": 66306,\n    \"gid\": 0,\n    \"inode\": 108020388,\n    \"mode\": 33188,\n    \"mtime_ns\": 1774599998000000000,\n    \"nlink\": 1,\n    \"rdev\": 0,\n    \"uid\": 0\n  },\n  \"target_link\": \"/usr/lib/x86_64-linux-gnu/libffi.so.8.2.0\",\n  \"fd_inheritable\": false,\n  \"fdinfo_fields\": {\n    \"flags\": \"02100000\",\n    \"ino\": \"108020388\",\n    \"mnt_id\": \"33\",\n    \"pos\": \"0\"\n  },\n  \"python\": {\n    \"cache_tag\": \"cpython-314\",\n    \"executable\": \"/usr/bin/python3\",\n    \"implementation\": \"cpython\",\n    \"version\": \"3.14.4 (main, Aug 20 2026, 10:41:58) [GCC 15.2.0]\",\n    \"version_info\": [\n      3,\n      14,\n      4,\n      \"final\",\n      0\n    ]\n  },\n  \"modules\": {\n    \"_ctypes\": {\n      \"file\": \"/usr/lib/python3.14/lib-dynload/_ctypes.cpython-314-x86_64-linux-gnu.so\",\n      \"file_body_read\": false\n    },\n    \"ctypes\": {\n      \"file\": \"/usr/lib/python3.14/ctypes/__init__.py\",\n      \"file_body_read\": false\n    }\n  },\n  \"target_body_read\": false,\n  \"matching_installed_libffi_source_proven\": false,\n  \"resource_scope\": \"one actual-observed retained read-only CLOEXEC descriptor created during exact ctypes import; process exit owns final release\"\n}\n")


def live_difference(before, after):
    return {'added': sorted(set(after) - set(before), key=int),
            'removed': sorted(set(before) - set(after), key=int),
            'changed': sorted((name for name in set(before) & set(after)
                               if before[name] != after[name]), key=int)}


def dependency_admission(before, after):
    delta = live_difference(before, after)
    need(len(delta['added']) == 1 and not delta['removed'] and not delta['changed'],
         'EXACT_SINGLE_IMPORT_DEPENDENCY_DELTA')
    fd = int(delta['added'][0])
    need(fd > 2, 'DEPENDENCY_MUST_NOT_REPLACE_STANDARD_DESCRIPTOR')
    return fd, delta


def accounted_live_set(before, after, fd, identity_index):
    # The original before snapshot is never mutated or resampled.
    name = str(fd)
    need(name not in before and fd > 2, 'DECLARED_DEPENDENCY_NOT_NEW')
    expected = dict(before)
    expected[name] = identity_index
    need(after == expected, 'UNACCOUNTED_LIVE_FD_DELTA')
    return True


def dependency_python():
    result = {'version': sys.version, 'version_info': list(sys.version_info),
              'executable': sys.executable, 'implementation': sys.implementation.name,
              'cache_tag': sys.implementation.cache_tag}
    modules = {}
    for name in ('ctypes', '_ctypes'):
        module = sys.modules.get(name)
        need(isinstance(module, types.ModuleType), 'EXACT_IMPORTED_MODULE_REQUIRED')
        path = vars(module).get('__file__')
        need(type(path) is str and 0 < len(path.encode()) <= 4096,
             'DEPENDENCY_MODULE_NAME_BOUND')
        modules[name] = {'file': path, 'file_body_read': False}
    return result, modules


def dependency_metadata(fd):
    value = os.fstat(fd)
    return {'device': value.st_dev, 'inode': value.st_ino, 'mode': value.st_mode,
            'uid': value.st_uid, 'gid': value.st_gid, 'rdev': value.st_rdev,
            'nlink': value.st_nlink, 'bytes': value.st_size,
            'mtime_ns': value.st_mtime_ns, 'ctime_ns': value.st_ctime_ns}


def require_dependency_observation(value):
    need(value['target_before'] == value['target_after'] == DEPENDENCY_AUTHORITY['target'],
         'EXACT_ACTUAL_DEPENDENCY_FSTAT_REQUIRED')
    need(value['target_link_before'] == value['target_link_after'] ==
         DEPENDENCY_AUTHORITY['target_link'], 'EXACT_ACTUAL_DEPENDENCY_PATH_REQUIRED')
    need(value['inheritable_before'] is False and value['inheritable_after'] is False,
         'DEPENDENCY_MUST_REMAIN_CLOEXEC')
    need(value['python'] == DEPENDENCY_AUTHORITY['python'] and
         value['modules'] == DEPENDENCY_AUTHORITY['modules'],
         'EXACT_ACTUAL_PYTHON_AND_CTYPES_PROVENANCE_REQUIRED')
    need(value['fdinfo_fields'] == DEPENDENCY_AUTHORITY['fdinfo_fields'] and
         int(value['fdinfo_fields']['flags'], 8) & os.O_ACCMODE == os.O_RDONLY and
         int(value['fdinfo_fields']['flags'], 8) & os.O_CLOEXEC,
         'EXACT_ACTUAL_READONLY_CLOEXEC_FDINFO_REQUIRED')
    need(value['target_file_body_read'] is False and value['dependency_close_attempted'] is False and
         value['owned_fdinfo_closed'] is True and value['first_error'] is None and
         value['secondary_errors'] == [], 'DEPENDENCY_METADATA_COLLECTION_INCOMPLETE')


def observe_dependency(fd, stage, result):
    row = {'stage': stage, 'fd': fd, 'collection_complete': False,
           'target_file_body_read': False, 'dependency_close_attempted': False,
           'owned_fdinfo_opened': False, 'owned_fdinfo_close_attempted': False,
           'owned_fdinfo_closed': False, 'first_error': None, 'secondary_errors': []}
    observations = result['dependency_accounting']['metadata_observations']
    need(len(observations) < 2, 'ONLY_IMPORT_AND_FINAL_DEPENDENCY_OBSERVATIONS')
    observations.append(row)
    info_fd = None
    def error(where, exception):
        item = {'stage': where, 'type': type(exception).__name__,
                'errno': getattr(exception, 'errno', None), 'error': repr(exception)[:512]}
        if row['first_error'] is None:
            row['first_error'] = item
        else:
            row['secondary_errors'].append(item)
    try:
        row['target_before'] = dependency_metadata(fd)
        need(row['target_before'] == DEPENDENCY_AUTHORITY['target'],
             'EXACT_ACTUAL_DEPENDENCY_FSTAT_REQUIRED')
        row['target_link_before'] = os.readlink('/proc/self/fd/' + str(fd))
        row['inheritable_before'] = os.get_inheritable(fd)
        row['python'], row['modules'] = dependency_python()
        need(row['target_link_before'] == DEPENDENCY_AUTHORITY['target_link'] and
             row['inheritable_before'] is False and
             row['python'] == DEPENDENCY_AUTHORITY['python'] and
             row['modules'] == DEPENDENCY_AUTHORITY['modules'],
             'EXACT_ACTUAL_IMPORT_DEPENDENCY_PROVENANCE_REQUIRED')
        info_fd = os.open('/proc/self/fdinfo/' + str(fd),
                          os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        row['owned_fdinfo_opened'] = True
        row['owned_fdinfo_identity'] = FDObservation.info(info_fd)
        chunks = []; count = 0; deadline = time.monotonic() + 1.0
        while True:
            need(time.monotonic() < deadline, 'DEPENDENCY_FDINFO_DEADLINE')
            part = os.read(info_fd, min(1024, 4097 - count))
            if not part:
                break
            count += len(part)
            need(count <= 4096, 'DEPENDENCY_FDINFO_BOUND')
            chunks.append(part)
        raw = b''.join(chunks)
        fields = {}
        for line in raw.decode('ascii', 'strict').splitlines():
            name, separator, value = line.partition(':')
            need(separator and name in ('pos', 'flags', 'mnt_id', 'ino') and
                 name not in fields and value.strip().isdigit(), 'DEPENDENCY_FDINFO_SCHEMA')
            fields[name] = value.strip()
        need(set(fields) == {'pos', 'flags', 'mnt_id', 'ino'}, 'DEPENDENCY_FDINFO_FIELDS')
        row['fdinfo_fields'] = fields
        row['fdinfo_bytes'] = len(raw); row['fdinfo_sha256'] = hashlib.sha256(raw).hexdigest()
        row['target_link_after'] = os.readlink('/proc/self/fd/' + str(fd))
        row['inheritable_after'] = os.get_inheritable(fd)
        row['target_after'] = dependency_metadata(fd)
    except BaseException as exception:
        error('observe_dependency', exception)
    finally:
        if info_fd is not None:
            closing, info_fd = info_fd, None
            row['owned_fdinfo_close_attempted'] = True
            try:
                os.close(closing); row['owned_fdinfo_closed'] = True
            except BaseException as exception:
                error('owned_fdinfo_close', exception)
    try:
        require_dependency_observation(row)
    except BaseException as exception:
        error('dependency_qualification', exception)
    row['collection_complete'] = row['first_error'] is None and row['owned_fdinfo_closed']
    need(row['collection_complete'], 'ACTUAL_IMPORT_DEPENDENCY_NOT_QUALIFIED')
    return row


def dependency_accounting_controls():
    # These are pure metadata fixtures. They do not open or close any real FD.
    def clone(value):
        return json.loads(json.dumps(value))
    cases = []
    before = {'0': 0, '1': 1, '2': 2, '3': 3}
    after = {**before, '7': 4}
    def yes(name, operation):
        operation(); cases.append({'name': name, 'passed': True})
    def no(name, operation, reason):
        try:
            operation()
        except RuntimeError as error:
            need(str(error) == reason, 'DEPENDENCY_CONTROL_WRONG_REJECTION')
        else:
            raise RuntimeError('DEPENDENCY_CONTROL_ACCEPTED_INVALID_STATE:' + name)
        cases.append({'name': name, 'passed': True})
    fixture = {'target_before': clone(DEPENDENCY_AUTHORITY['target']),
               'target_after': clone(DEPENDENCY_AUTHORITY['target']),
               'target_link_before': DEPENDENCY_AUTHORITY['target_link'],
               'target_link_after': DEPENDENCY_AUTHORITY['target_link'],
               'inheritable_before': False, 'inheritable_after': False,
               'python': clone(DEPENDENCY_AUTHORITY['python']),
               'modules': clone(DEPENDENCY_AUTHORITY['modules']),
               'fdinfo_fields': clone(DEPENDENCY_AUTHORITY['fdinfo_fields']),
               'target_file_body_read': False, 'dependency_close_attempted': False,
               'owned_fdinfo_closed': True, 'first_error': None, 'secondary_errors': []}
    def accept():
        fd, delta = dependency_admission(before, after)
        need(fd == 7 and delta == {'added': ['7'], 'removed': [], 'changed': []},
             'DEPENDENCY_CONTROL_DELTA')
        require_dependency_observation(fixture)
        accounted_live_set(before, after, fd, 4)
        need(before == {'0': 0, '1': 1, '2': 2, '3': 3}, 'ORIGINAL_BASELINE_MUTATED')
    yes('exact_single_declared_dependency_preserves_original_baseline', accept)
    no('extra_unrelated_FD_is_not_hidden',
       lambda: accounted_live_set(before, {**after, '8': 5}, 7, 4), 'UNACCOUNTED_LIVE_FD_DELTA')
    no('changed_original_FD_is_not_hidden',
       lambda: accounted_live_set(before, {**after, '1': 9}, 7, 4), 'UNACCOUNTED_LIVE_FD_DELTA')
    no('removed_original_FD_is_not_hidden',
       lambda: accounted_live_set(before, {k:v for k,v in after.items() if k != '0'}, 7, 4),
       'UNACCOUNTED_LIVE_FD_DELTA')
    no('dependency_disappearance_is_not_accepted',
       lambda: accounted_live_set(before, before, 7, 4), 'UNACCOUNTED_LIVE_FD_DELTA')
    no('two_import_added_FDs_cannot_be_registered',
       lambda: dependency_admission(before, {**after, '8': 5}), 'EXACT_SINGLE_IMPORT_DEPENDENCY_DELTA')
    changed = clone(fixture); changed['target_after']['ctime_ns'] += 1
    no('same_named_library_changed_metadata_rejected',
       lambda: require_dependency_observation(changed), 'EXACT_ACTUAL_DEPENDENCY_FSTAT_REQUIRED')
    inherited = clone(fixture); inherited['inheritable_after'] = True
    no('library_FD_becoming_inheritable_rejected',
       lambda: require_dependency_observation(inherited), 'DEPENDENCY_MUST_REMAIN_CLOEXEC')
    need(len(cases) == 8, 'EXACT_DEPENDENCY_ACCOUNTING_CONTROL_COUNT')
    return {'schema': 1, 'scope': 'pure FD ledger metadata fixtures, not kernel execution',
            'all_passed': True, 'count': 8, 'cases': cases,
            'file_bodies_read': 0, 'process_children': 0, 'Main_or_Android_access': False}


def main():
    result = {'schema': 1, 'kind': 'owner20-property-DONE-controls08-run',
        'success': False, 'errors': [], 'first_error': None,
        'Android_executed': False, 'Android_property_reads_or_writes': False,
        'namespace_entry_or_UID_changes': False, 'Main_access': False,
        'normal_runtime_admission_created': False, 'all_fixture_children_reaped': False,
        'all_owned_files_and_fds_closed': False,
        'all_fixture_files_and_fds_closed': False,
        'all_process_lifetime_dependencies_accounted': False,
        'complete_process_retirement_requires_Root_observed_terminal_exit': True,
        'process_exit_already_observed': False,
        'dependency_accounting': {'schema': 1, 'actual_authority': DEPENDENCY_AUTHORITY,
            'declared_resources': [], 'raw_observed_differences': [], 'metadata_observations': [],
            'initial_baseline_moved': False, 'unknown_descriptor_closed': False,
            'dependency_lifetime': 'retained only in this fixed host process; release is by process exit',
            'runtime_authorization_changed': False}}
    directory = None; directory_identity = None; created = False
    old_temp = tempfile.tempdir; old_alarm = signal.getsignal(signal.SIGALRM)
    before_fds = None; before_ns = None; before_ids = None; watchdog_changed = False
    observed = FDObservation(result)
    dependency_fd = None; dependency_identity_index = None
    control_diagnostics = {'controls': [], 'failed_original_run_retained': True,
        'original_stdout_sha256': '0db3e89b04e3c19dec6adcd1868ed2f3ca61da63aadf97df5c575c2a9eada83a'}
    result['controls_progress'] = control_diagnostics
    def error(stage, e):
        row = {'stage': stage, 'type': type(e).__name__, 'error': repr(e)[:1024],
               'errno': getattr(e, 'errno', None)}
        result['errors'].append(row)
        if result['first_error'] is None:
            result['first_error'] = row
    def own_namespaces():
        return {name: [os.stat('/proc/self/ns/' + name).st_dev,
                       os.stat('/proc/self/ns/' + name).st_ino] for name in NAMES}
    def no_children():
        try:
            os.waitid(os.P_ALL, 0, os.WEXITED | os.WNOWAIT | os.WNOHANG)
        except ChildProcessError:
            return True
        return False
    def alarm(signum, frame):
        raise TimeoutError('HOST_CONTROL_WATCHDOG_15_SECONDS')
    started = time.monotonic_ns()
    try:
        need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0,
             'OWNED_HOST_FIXTURES_REQUIRE_ROOT_WITHOUT_CREDENTIAL_CHANGE')
        need(os.uname().machine == 'x86_64' and signal.getsignal(signal.SIGCHLD) == signal.SIG_DFL and
             len(os.listdir('/proc/self/task')) == 1 and no_children(), 'FRESH_HOST_TEST_PROCESS_REQUIRED')
        api = {name: hasattr(os, name) for name in ('fork', 'setns', 'pidfd_open', 'waitid', 'P_PIDFD')}
        api.update({name: hasattr(signal, name) for name in ('pidfd_send_signal', 'setitimer', 'getitimer', 'pthread_sigmask')})
        api['fd_execve'] = os.execve in os.supports_fd
        result['host_Python_API_presence_only'] = api
        need(all(api.values()), 'COLLECTOR_HOST_API_REQUIRED')
        need(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'PREEXISTING_HOST_TIMER')
        before_fds = observed.sample('host_before'); before_ns = own_namespaces()
        before_ids = (os.getresuid(), os.getresgid(), os.getgroups())
        watchdog_changed = True
        signal.signal(signal.SIGALRM, alarm); signal.setitimer(signal.ITIMER_REAL, 15, 0)
        raw = base64.b64decode(PACKET_B64, validate=True)
        need(len(raw) == PACKET_BYTES and hashlib.sha256(raw).hexdigest() == PACKET_SHA,
             'EXACT_CONTROL_PACKET')
        packet = json.loads(raw.decode('utf-8', 'strict'))
        need(set(packet) == {'schema', 'members'} and packet['schema'] == 1 and
             set(packet['members']) == {'property_visibility.py', 'baseline_property_visibility.py',
                                       'import_authority_property.py', 'actor.py', 'baseline_actor.py',
                                       'qualify.py', 'admission_controls.py', 'actual-safe.json'}, 'EXACT_CONTROL_MEMBERS')
        source = {}
        pins = {}
        for name, row in packet['members'].items():
            need(set(row) == {'text', 'bytes', 'sha256'}, 'MEMBER_SCHEMA')
            body = row['text'].encode('utf-8')
            need(len(body) == row['bytes'] and hashlib.sha256(body).hexdigest() == row['sha256'],
                 'MEMBER_BYTES_SHA')
            if name.endswith('.py'):
                compile(body, name, 'exec')
            else:
                json.loads(body.decode('utf-8', 'strict'))
            source[name] = row['text']; pins[name] = {k: row[k] for k in ('bytes', 'sha256')}
        result['source_pins'] = pins
        result['dependency_accounting_controls'] = dependency_accounting_controls()
        os.mkdir(TEMP_ROOT, 0o700); created = True
        directory = os.open(TEMP_ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        first = os.fstat(directory)
        need(stat.S_ISDIR(first.st_mode) and stat.S_IMODE(first.st_mode) == 0o700 and
             first.st_uid == first.st_gid == 0, 'NEW_PRIVATE_HOST_FIXTURE_DIRECTORY')
        directory_identity = (first.st_dev, first.st_ino)
        tempfile.tempdir = TEMP_ROOT
        need('ctypes' not in sys.modules and '_ctypes' not in sys.modules,
             'EXACT_FRESH_IMPORT_DEPENDENCY_BOUNDARY')
        need(pins['import_authority_property.py']['sha256'] == DEPENDENCY_AUTHORITY['source_sha256'] and
             pins['baseline_property_visibility.py']['sha256'] ==
             'e5d993f3bc05cebb4c61c44c84976fca491c10714799a684fed16ef85cd87f8d' and
             pins['property_visibility.py']['sha256'] == '5b6c693f2ace7a873bb5edf62b54ac4ffd2993399989b4091b91a3fab80dd13a',
             'ACTUAL_BASELINE_AND_MINIMAL_CANDIDATE_IMPORT_SOURCE_REQUIRED')
        imports = []
        for name in ('import_authority_property.py', 'baseline_property_visibility.py', 'property_visibility.py'):
            nodes = [node for node in ast.parse(source[name]).body
                     if isinstance(node, (ast.Import, ast.ImportFrom))]
            imports.append(ast.dump(ast.Module(body=nodes, type_ignores=[]), include_attributes=False))
        need(imports[0] == imports[1] == imports[2], 'EXACT_ORIGINAL_IMPORT_LIFECYCLE_REQUIRED')
        modules_before = observed.sample('before_production_module')
        subject = types.ModuleType('owner20_property_control_subject')
        exec(compile(source['property_visibility.py'], 'property_visibility.py', 'exec'), subject.__dict__)
        modules_after = observed.sample('after_production_module')
        try:
            found_fd, delta = dependency_admission(observed.snapshots[modules_before]['live'],
                                                   observed.snapshots[modules_after]['live'])
            result['dependency_accounting']['raw_observed_differences'].append(
                {'stage': 'exact_production_module_import', 'before_snapshot': modules_before,
                 'after_snapshot': modules_after, **delta})
            observation = observe_dependency(found_fd, 'after_exact_production_import', result)
            dependency_fd = found_fd
            dependency_identity_index = observed.snapshots[modules_after]['live'][str(found_fd)]
            result['dependency_accounting']['declared_resources'].append({
                'fd': found_fd, 'identity_index': dependency_identity_index,
                'actual_provenance_stdout_sha256': DEPENDENCY_AUTHORITY['actual_stdout']['sha256'],
                'registered_after_exact_production_import': True,
                'held_by_dependency_not_Capture': True, 'closed_by_this_test': False})
            accounted_live_set(observed.snapshots[modules_before]['live'],
                               observed.snapshots[modules_after]['live'],
                               dependency_fd, dependency_identity_index)
        except BaseException:
            observed.equal(modules_before, modules_after, 'unqualified_module_imports')
            raise
        controls = types.ModuleType('owner20_property_controls')
        exec(compile(source['admission_controls.py'], 'admission_controls.py', 'exec'), controls.__dict__)
        controls_imported = observed.sample('after_controls_module')
        need(observed.equal(modules_after, controls_imported, 'controls_module_import'),
             'UNACCOUNTED_CONTROL_MODULE_LIVE_FD_IDENTITY_CHANGED')
        result['controls'] = controls.run(subject, source,
            observed.observe_case, None, control_diagnostics)
        need(result['controls']['success'] is True and result['controls']['count'] == 31,
             'ALL_PINNED_HOST_CONTROLS_REQUIRED')
    except BaseException as e:
        error('host_controls', e)
    finally:
        if watchdog_changed:
            try: signal.setitimer(signal.ITIMER_REAL, 0, 0)
            except BaseException as e: error('watchdog_disarm', e)
            try: signal.signal(signal.SIGALRM, old_alarm)
            except BaseException as e: error('watchdog_handler_restore', e)
        tempfile.tempdir = old_temp
        try:
            observed.cleanup_captures()
        except BaseException as e:
            error('tracked_capture_cleanup', e)
        try:
            need(no_children(), 'UNREAPED_HOST_FIXTURE_CHILD')
            result['all_fixture_children_reaped'] = True
        except BaseException as e:
            error('children_final', e)
        if directory is not None:
            try:
                now = os.fstat(directory); named = os.stat(TEMP_ROOT, follow_symlinks=False)
                need((now.st_dev, now.st_ino) == directory_identity == (named.st_dev, named.st_ino) and
                     stat.S_ISDIR(named.st_mode) and stat.S_IMODE(named.st_mode) == 0o700 and
                     now.st_uid == now.st_gid == named.st_uid == named.st_gid == 0 and
                     os.listdir(directory) == [], 'OWNED_FIXTURE_DIRECTORY_FINAL')
            except BaseException as e:
                error('fixture_directory_final', e)
            finally:
                fd, directory = directory, None
                try: os.close(fd)
                except BaseException as e: error('fixture_directory_close', e)
        if created and directory_identity is not None:
            try:
                now = os.stat(TEMP_ROOT, follow_symlinks=False)
                need((now.st_dev, now.st_ino) == directory_identity, 'EXACT_OWNED_FIXTURE_DIRECTORY')
                os.rmdir(TEMP_ROOT)
                result['owned_fixture_directory_removed'] = True
            except BaseException as e:
                error('fixture_directory_remove', e)
        try:
            if before_ns is not None:
                need(own_namespaces() == before_ns and
                     (os.getresuid(), os.getresgid(), os.getgroups()) == before_ids, 'HOST_IDENTITY_CHANGED')
                result['host_namespace_and_credentials_unchanged'] = True
            if before_fds is not None:
                final_fds = observed.sample('host_after_cleanup')
                initial_live = observed.snapshots[before_fds]['live']
                final_live = observed.snapshots[final_fds]['live']
                result['original_global_FD_equality'] = initial_live == final_live
                if dependency_fd is None:
                    need(observed.equal(before_fds, final_fds, 'host_final'),
                         'HOST_OWNED_FD_SET_CHANGED_WITHOUT_QUALIFIED_DEPENDENCY')
                    raise RuntimeError('REQUIRED_IMPORT_DEPENDENCY_WAS_NOT_QUALIFIED')
                result['dependency_accounting']['raw_observed_differences'].append(
                    {'stage': 'host_final', 'before_snapshot': before_fds, 'after_snapshot': final_fds,
                     **live_difference(initial_live, final_live)})
                observe_dependency(dependency_fd, 'after_all_fixture_cleanup', result)
                try:
                    accounted_live_set(initial_live, final_live, dependency_fd, dependency_identity_index)
                except BaseException:
                    observed.equal(before_fds, final_fds, 'unaccounted_host_final')
                    raise
                result['all_process_lifetime_dependencies_accounted'] = True
                result['dependency_accounting']['still_live_at_emission'] = [dependency_fd]
                result['dependency_accounting']['requires_actual_process_exit'] = True
                result['dependency_accounting']['target_close_attempts'] = 0
                result['all_fixture_files_and_fds_closed'] = (
                    result.get('owned_fixture_directory_removed') is True and
                    not result['fd_diagnostic'].get('capture_cleanup_errors') and
                    all(row['observed_closed'] for row in observed.owned))
                # The libffi-owned process-lifetime FD is still live here.
                # Do not report every process FD closed before actual exit.
                result['all_owned_files_and_fds_closed'] = False
                need(result['fd_diagnostic']['first_discrepancy'] is None,
                     'EARLIER_CASE_FD_DISCREPANCY_REMAINS_FAILURE')
        except BaseException as e:
            error('host_final', e)
    result['elapsed_ns'] = time.monotonic_ns() - started
    result['success'] = (not result['errors'] and result.get('controls', {}).get('success') is True and
                         result.get('dependency_accounting_controls', {}).get('all_passed') is True and
                         result['all_fixture_children_reaped'] and result['all_fixture_files_and_fds_closed'] and
                         result['all_process_lifetime_dependencies_accounted'])
    result['state'] = ('HOST_CONTROLS_COMPLETE_PROCESS_EXIT_PENDING' if result['success'] else 'FAILED')
    result['success_scope'] = '31 actual actor-loop/child-view controls plus the unchanged 8 dependency-accounting controls; OS/clock/process/file/constructor are explicit seams; original baseline and process-lifetime dependency remain visible; actual process exit is external evidence'
    body = (json.dumps(result, sort_keys=True, separators=(',', ':')) + '\n').encode()
    need(len(body) <= 131072, 'HOST_CONTROL_RESULT_BOUND')
    sys.stdout.buffer.write(body); sys.stdout.buffer.flush()
    return 0 if result['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
