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
TEMP_ROOT = '/tmp/p4-owner20-property-host-controls-02'
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
            'ambient_contents_or_targets_read': False, 'only_self_proc_fd_enumerated': True}

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


def main():
    result = {'schema': 1, 'kind': 'owner20-property-host-controls02-run',
        'success': False, 'errors': [], 'first_error': None,
        'Android_executed': False, 'Android_property_reads_or_writes': False,
        'namespace_entry_or_UID_changes': False, 'Main_access': False,
        'normal_runtime_admission_created': False, 'all_fixture_children_reaped': False,
        'all_owned_files_and_fds_closed': False}
    directory = None; directory_identity = None; created = False
    old_temp = tempfile.tempdir; old_alarm = signal.getsignal(signal.SIGALRM)
    before_fds = None; before_ns = None; before_ids = None; watchdog_changed = False
    observed = FDObservation(result)
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
             set(packet['members']) == {'property_visibility.py', 'actor.py', 'baseline_actor.py',
                                       'host_controls.py', 'bind_inputs.py'}, 'EXACT_CONTROL_MEMBERS')
        source = {}
        pins = {}
        for name, row in packet['members'].items():
            need(set(row) == {'text', 'bytes', 'sha256'}, 'MEMBER_SCHEMA')
            body = row['text'].encode('utf-8')
            need(len(body) == row['bytes'] and hashlib.sha256(body).hexdigest() == row['sha256'],
                 'MEMBER_BYTES_SHA')
            compile(body, name, 'exec')
            source[name] = row['text']; pins[name] = {k: row[k] for k in ('bytes', 'sha256')}
        result['source_pins'] = pins
        os.mkdir(TEMP_ROOT, 0o700); created = True
        directory = os.open(TEMP_ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        first = os.fstat(directory)
        need(stat.S_ISDIR(first.st_mode) and stat.S_IMODE(first.st_mode) == 0o700 and
             first.st_uid == first.st_gid == 0, 'NEW_PRIVATE_HOST_FIXTURE_DIRECTORY')
        directory_identity = (first.st_dev, first.st_ino)
        tempfile.tempdir = TEMP_ROOT
        modules_before = observed.sample('before_module_imports')
        subject = types.ModuleType('owner20_property_control_subject')
        exec(compile(source['property_visibility.py'], 'property_visibility.py', 'exec'), subject.__dict__)
        controls = types.ModuleType('owner20_property_controls')
        exec(compile(source['host_controls.py'], 'host_controls.py', 'exec'), controls.__dict__)
        modules_after = observed.sample('after_module_imports')
        need(observed.equal(modules_before, modules_after, 'module_imports'),
             'HOST_MODULE_IMPORT_LIVE_FD_IDENTITY_CHANGED')
        result['controls'] = controls.run(subject, source['actor.py'], source['baseline_actor.py'],
            observed.observe_case, observed.track_capture, control_diagnostics)
        need(result['controls']['success'] is True and result['controls']['count'] == 38,
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
                need(observed.equal(before_fds, final_fds, 'host_final'), 'HOST_OWNED_FD_SET_CHANGED')
                result['all_owned_files_and_fds_closed'] = (
                    result.get('owned_fixture_directory_removed') is True and
                    not result['fd_diagnostic'].get('capture_cleanup_errors'))
                need(result['fd_diagnostic']['first_discrepancy'] is None,
                     'EARLIER_CASE_FD_DISCREPANCY_REMAINS_FAILURE')
        except BaseException as e:
            error('host_final', e)
    result['elapsed_ns'] = time.monotonic_ns() - started
    result['success'] = (not result['errors'] and result.get('controls', {}).get('success') is True and
                         result['all_fixture_children_reaped'] and result['all_owned_files_and_fds_closed'])
    body = (json.dumps(result, sort_keys=True, separators=(',', ':')) + '\n').encode()
    need(len(body) <= 131072, 'HOST_CONTROL_RESULT_BOUND')
    sys.stdout.buffer.write(body); sys.stdout.buffer.flush()
    return 0 if result['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
