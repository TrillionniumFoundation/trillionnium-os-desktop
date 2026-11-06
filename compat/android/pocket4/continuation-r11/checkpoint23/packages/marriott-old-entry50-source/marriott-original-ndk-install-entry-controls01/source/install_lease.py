"""One fixed NDK installation lease. Source only; no module-level IO.
Owns one new private source/step directory, the original global action lock,
one own flow lock and one exclusive step lock. It never supplies a Main guard,
installed UID, command runner, instrumentation capability, or retry route.
"""
import errno
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import time

ROOT = Path('/home/alex/work/pocket4-original-ndk-fixture-APK03-install-01')
SOURCE = ROOT/'source'
STEP = ROOT/'steps'/'install-01'
ACTION_LOCK = '/run/lock/android-digitalis-actions.lock'
SOURCE_NAMES = {
    'fixture_contract.py','fixture_context.py','fixture_transport.py',
    'fixture_phases.py','current_discovery.py','install_lease.py','install_worker.py',
}
LOCK_WAIT_SECONDS = 5.0
LOCK_POLL_SECONDS = 0.05
MAX_TRACKED_FDS = 4096


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def identity(fd):
    row = os.fstat(fd)
    return {k:getattr(row, name) for k,name in {
        'device':'st_dev','inode':'st_ino','mode':'st_mode','uid':'st_uid',
        'gid':'st_gid','nlink':'st_nlink','bytes':'st_size',
        'mtime_ns':'st_mtime_ns','ctime_ns':'st_ctime_ns'}.items()}


def public_error(error):
    text = str(error)
    result = {'type':type(error).__name__, 'errno':getattr(error, 'errno', None)}
    if re.fullmatch('[A-Z][A-Z0-9_: ]{0,159}', text):
        result['code'] = text
    else:
        result['message_bytes'] = len(text.encode())
        result['message_sha256'] = sha(text.encode())
    return result


class InstallLease:
    def __init__(self, scope, source_pin, deadline):
        need(type(scope) is dict and scope.get('phase') == 'install' and
             scope.get('package') == 'com.example.ndk_tests' and
             scope.get('uid') is None and scope.get('user') == 0 and
             scope.get('automatic_retry') is False and
             type(scope.get('attempt_nonce')) is str and
             re.fullmatch('[0-9a-f]{32}', scope['attempt_nonce']) and
             scope['attempt_nonce'] != '0'*32, 'INSTALL_LEASE_SCOPE_REQUIRED')
        need(type(source_pin) is dict and set(source_pin) == {'bytes','sha256'} and
             type(source_pin['bytes']) is int and 0 < source_pin['bytes'] <= 65536 and
             re.fullmatch('[0-9a-f]{64}', source_pin['sha256']),
             'INSTALL_LEASE_EXACT_SOURCE_PIN_REQUIRED')
        need(type(deadline) in (int,float) and math.isfinite(deadline) and
             time.monotonic() < deadline, 'INSTALL_LEASE_FRESH_DEADLINE_REQUIRED')
        self.scope = json.loads(json.dumps(scope))
        self.scope_bytes = canonical(scope)
        self.pin = dict(source_pin)
        self.deadline = deadline
        self.fds = []
        self.names = {}
        self.ancestry = []
        self.locked = []
        self.root_created = False
        self.sources_staged = False
        self.claimed = False
        self.entered = False
        self.closed = False
        self.claim_raw = None
        self.root_identity = None
        self.observation = {
            'schema':1, 'root':str(ROOT), 'step':str(STEP),
            'global_action_lock':ACTION_LOCK, 'root_create_only':True,
            'flow_lock_exclusive':False, 'step_lock_exclusive':False,
            'step_claim_create_only':False, 'global_lock_acquired':False,
            'global_lock_attempts':0, 'global_lock_busy_attempts':0,
            'global_lock_wait_limit_seconds':LOCK_WAIT_SECONDS,
            'automatic_retry':False, 'Android_actions':0,
            'all_tracked_lease_FDs_closed':False,
        }

    def _take(self, fd, label):
        try:
            need(type(fd) is int and fd >= 3 and len(self.fds) < MAX_TRACKED_FDS and
                 not any(x['fd'] == fd and not x['closed'] for x in self.fds),
                 'INSTALL_LEASE_FD_REGISTRATION_REQUIRED')
            row = {'fd':fd, 'label':label, 'closed':False, 'close_error':None}
            self.fds.append(row)
            need(os.get_inheritable(fd) is False, 'LEASE_FD_MUST_BE_CLOEXEC')
            return fd
        except BaseException:
            if not any(x['fd'] == fd and not x['closed'] for x in self.fds):
                os.close(fd)
            raise

    def _close_fd(self, fd):
        matches = [x for x in self.fds if x['fd'] == fd and not x['closed']]
        need(len(matches) == 1, 'EXACT_OWN_LEASE_FD_CLOSE_REQUIRED')
        row = matches[0]
        try:
            os.close(fd)
            row['closed'] = True
        except BaseException as error:
            row['close_error'] = public_error(error)
            # No close retry: a failing close may already have consumed the number.
            row['closed'] = None
            raise

    def _walk_directory(self, path, label):
        path = str(path)
        need(path.startswith('/') and not path.startswith('//') and
             all(x not in ('','.','..') for x in path[1:].split('/')),
             'LEASE_FIXED_ABSOLUTE_DIRECTORY_REQUIRED')
        current = self._take(os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC),
                             label+':slash')
        self._remember_ancestor(None,'/',current)
        for number, part in enumerate(path[1:].split('/')):
            parent = current
            current = self._take(os.open(part,os.O_RDONLY|os.O_DIRECTORY|
                os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent),label+':'+str(number))
            self._remember_ancestor(parent,part,current)
        return current

    def _remember_ancestor(self, parent, name, fd):
        fields = ('device','inode','mode','uid','gid')
        held = identity(fd)
        named = os.stat(name,dir_fd=parent,follow_symlinks=False)
        value = {'device':named.st_dev,'inode':named.st_ino,'mode':named.st_mode,
                 'uid':named.st_uid,'gid':named.st_gid}
        need(stat.S_ISDIR(held['mode']) and
             all(held[k] == value[k] for k in fields), 'LEASE_ANCESTOR_NAME_MISMATCH')
        self.ancestry.append((parent,name,fd,{k:held[k] for k in fields}))

    def _remember_name(self, key, parent, name, fd, directory=False):
        held = identity(fd)
        named = os.stat(name,dir_fd=parent,follow_symlinks=False)
        need((named.st_dev,named.st_ino,named.st_mode,named.st_uid,named.st_gid) ==
             (held['device'],held['inode'],held['mode'],held['uid'],held['gid']),
             'NEW_OWN_LEASE_NAME_MISMATCH')
        if directory:
            need(stat.S_ISDIR(held['mode']) and held['uid'] == held['gid'] == 0 and
                 stat.S_IMODE(held['mode']) == 0o700,
                 'OWN_PRIVATE_ROOT_DIRECTORY_REQUIRED')
        else:
            need(stat.S_ISREG(held['mode']) and held['uid'] == held['gid'] == 0 and
                 held['nlink'] == 1 and not held['mode'] & 0o022,
                 'OWN_LEASE_REGULAR_FILE_REQUIRED')
        self.names[key] = (parent,name,fd,held,directory)
        return held

    def _directory(self, parent, name, key):
        os.mkdir(name,0o700,dir_fd=parent)
        fd = self._take(os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|
                               os.O_CLOEXEC,dir_fd=parent),key)
        # Only a just-created own directory is adjusted; no existing inode is chmod'ed.
        os.fchmod(fd,0o700)
        self._remember_name(key,parent,name,fd,True)
        os.fsync(parent)
        return fd

    def _write_new(self, parent, name, raw, mode=0o400, keep=False):
        need(type(raw) is bytes and len(raw) <= 1048576 and
             type(name) is str and re.fullmatch('[A-Za-z0-9_.-]{1,96}',name),
             'FIXED_OWN_OUTPUT_REQUIRED')
        fd = self._take(os.open(name,os.O_RDWR|os.O_CREAT|os.O_EXCL|
            os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=parent),'write:'+name)
        primary = None
        try:
            count = 0
            while count < len(raw):
                need(time.monotonic() < self.deadline, 'OWN_WRITE_DEADLINE')
                amount = os.write(fd,raw[count:])
                need(amount > 0, 'OWN_WRITE_STALLED')
                count += amount
            os.fchmod(fd,mode)
            os.fsync(fd)
            row = identity(fd)
            need(stat.S_ISREG(row['mode']) and row['nlink'] == 1 and
                 row['uid'] == row['gid'] == 0 and row['bytes'] == len(raw) and
                 stat.S_IMODE(row['mode']) == mode, 'OWN_WRITTEN_FILE_SHAPE')
            os.lseek(fd,0,os.SEEK_SET)
            again = bytearray()
            while True:
                need(time.monotonic() < self.deadline, 'OWN_READBACK_DEADLINE')
                part = os.read(fd,min(65536,len(raw)+1-len(again)))
                if not part:
                    break
                again.extend(part)
                need(len(again) <= len(raw), 'OWN_READBACK_BOUND')
            named = os.stat(name,dir_fd=parent,follow_symlinks=False)
            need(bytes(again) == raw and identity(fd) == row and
                 (named.st_dev,named.st_ino,named.st_mode,named.st_uid,named.st_gid,
                  named.st_nlink,named.st_size,named.st_mtime_ns,named.st_ctime_ns) ==
                 tuple(row[x] for x in ('device','inode','mode','uid','gid','nlink',
                                        'bytes','mtime_ns','ctime_ns')),
                 'OWN_WRITTEN_FILE_OR_NAME_CHANGED')
            os.fsync(parent)
            return fd if keep else {'bytes':len(raw),'sha256':sha(raw)}
        except BaseException as error:
            primary = error
            raise
        finally:
            if not keep or primary is not None:
                try:
                    self._close_fd(fd)
                except BaseException as error:
                    if primary is None:
                        raise
                    primary.add_note('OWN_OUTPUT_CLOSE_FAILED:'+type(error).__name__)

    def create_and_stage(self, sources, manifest_raw):
        need(not self.root_created and not self.closed and os.getuid() == os.geteuid() == 0 and
             os.getgid() == os.getegid() == 0, 'FRESH_ROOT_INSTALL_LEASE_REQUIRED')
        need(type(sources) is dict and set(sources) == SOURCE_NAMES and
             type(manifest_raw) is bytes and
             {'bytes':len(manifest_raw),'sha256':sha(manifest_raw)} == self.pin,
             'EXACT_SEVEN_INSTALL_SOURCES_REQUIRED')
        manifest = json.loads(manifest_raw)
        need(manifest.get('schema') == 'pocket4-original-ndk-fixture-source-v1' and
             set(manifest.get('files',{})) == SOURCE_NAMES, 'SEVEN_SOURCE_MANIFEST_REQUIRED')
        for name,raw in sources.items():
            need(type(raw) is bytes and 0 < len(raw) <= 131072 and
                 manifest['files'][name] == {'bytes':len(raw),'sha256':sha(raw)},
                 'INSTALL_SOURCE_BODY_PIN_CHANGED')
        self.parent = self._walk_directory(ROOT.parent,'fixed-root-parent')
        need(os.fstat(self.parent).st_uid == 1000, 'FIXED_WORK_PARENT_OWNER_REQUIRED')
        # Existing/partial roots are never adopted. mkdir is the atomic once claim.
        os.mkdir(ROOT.name,0o700,dir_fd=self.parent)
        self.root_created = True
        self.root = self._take(os.open(ROOT.name,os.O_RDONLY|os.O_DIRECTORY|
            os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=self.parent),'root')
        os.fchmod(self.root,0o700)
        self.root_identity = self._remember_name('root',self.parent,ROOT.name,self.root,True)
        os.fsync(self.parent)
        self.source = self._directory(self.root,'source','source')
        self.steps = self._directory(self.root,'steps','steps')
        self.step = self._directory(self.steps,'install-01','step')
        for name in sorted(sources):
            self._write_new(self.source,name,sources[name],0o444)
        self._write_new(self.source,'SOURCE_PINS.json',manifest_raw,0o444)
        self.sources_staged = True
        self.observation['root_created'] = True
        self.observation['seven_sources_staged'] = True
        self.observation['source_manifest'] = dict(self.pin)

    def _own_lock(self, parent, name, key):
        fd = self._take(os.open(name,os.O_RDWR|os.O_CREAT|os.O_EXCL|
            os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=parent),key)
        os.fchmod(fd,0o600)
        self._remember_name(key,parent,name,fd)
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.locked.append((key,fd))
        os.fsync(parent)
        return fd

    def acquire_and_claim(self):
        need(self.sources_staged and not self.claimed and not self.closed,
             'NEW_STAGED_INSTALL_STEP_REQUIRED')
        self.flow = self._own_lock(self.root,'flow.lock','flow-lock')
        self.observation['flow_lock_exclusive'] = True
        action_path = Path(ACTION_LOCK)
        self.action_parent = self._walk_directory(action_path.parent,'action-parent')
        self.action = self._take(os.open(action_path.name,
            os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=self.action_parent),'action-lock')
        # The existing global lock is never created, replaced, truncated or chmod'ed.
        self._remember_name('action-lock',self.action_parent,action_path.name,self.action)
        start = time.monotonic()
        end = min(self.deadline,start+LOCK_WAIT_SECONDS)
        first_busy = None
        while True:
            if time.monotonic() >= end:
                if first_busy is not None:
                    raise first_busy
                raise TimeoutError('ACTION_LOCK_ADMISSION_DEADLINE')
            self.observation['global_lock_attempts'] += 1
            try:
                fcntl.flock(self.action,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError as error:
                if error.errno != errno.EAGAIN:
                    raise
                if first_busy is None:
                    first_busy = error
                self.observation['global_lock_busy_attempts'] += 1
                time.sleep(min(LOCK_POLL_SECONDS,max(0,end-time.monotonic())))
                continue
            self.locked.append(('action-lock',self.action))
            self.observation['global_lock_acquired'] = True
            self.observation['global_lock_wait_seconds'] = time.monotonic()-start
            need(time.monotonic() < end, 'ACTION_LOCK_ADMISSION_DEADLINE')
            break
        self.step_lock = self._own_lock(self.step,'step.lock','step-lock')
        self.observation['step_lock_exclusive'] = True
        self.claim_raw = canonical({
            'schema':1,'kind':'pocket4-original-ndk-exclusive-install-step',
            'scope':self.scope,'source_manifest':self.pin,
            'root':str(ROOT),'step':str(STEP),'automatic_retry':False,
            'installed_UID':None,'instrumentation_admitted':False})+b'\n'
        self.claim = self._write_new(self.step,'once.claim.json',self.claim_raw,0o400,True)
        self._remember_name('claim',self.step,'once.claim.json',self.claim)
        self.claimed = True
        self.observation['step_claim_create_only'] = True
        self.observation['claim'] = {'bytes':len(self.claim_raw),'sha256':sha(self.claim_raw)}
        self._verify_objects()

    def _verify_objects(self):
        need(not self.closed, 'INSTALL_LEASE_ALREADY_CLOSED')
        # Shared ancestors are bound by inode/type/ownership, never by mutable
        # directory timestamps. Each held edge is checked against its current name.
        for parent,name,fd,initial in self.ancestry:
            held = identity(fd)
            named = os.stat(name,dir_fd=parent,follow_symlinks=False)
            current = {'device':named.st_dev,'inode':named.st_ino,'mode':named.st_mode,
                       'uid':named.st_uid,'gid':named.st_gid}
            need(all(held[k] == initial[k] == current[k] for k in initial),
                 'LEASE_ANCESTOR_HELD_OR_NAMED_IDENTITY_CHANGED')
            need(os.get_inheritable(fd) is False, 'LEASE_ANCESTOR_FD_BECAME_INHERITABLE')
        for key,(parent,name,fd,initial,directory) in self.names.items():
            held = identity(fd)
            named = os.stat(name,dir_fd=parent,follow_symlinks=False)
            fields = ('device','inode','mode','uid','gid') if directory else tuple(initial)
            current = {'device':named.st_dev,'inode':named.st_ino,'mode':named.st_mode,
                'uid':named.st_uid,'gid':named.st_gid,'nlink':named.st_nlink,
                'bytes':named.st_size,'mtime_ns':named.st_mtime_ns,'ctime_ns':named.st_ctime_ns}
            need(all(held[k] == initial[k] == current[k] for k in fields),
                 'INSTALL_LEASE_HELD_OR_NAMED_IDENTITY_CHANGED')
            need(os.get_inheritable(fd) is False, 'LEASE_FD_BECAME_INHERITABLE')
        if self.claimed:
            raw = os.pread(self.claim,len(self.claim_raw)+1,0)
            need(raw == self.claim_raw, 'EXCLUSIVE_INSTALL_CLAIM_CHANGED')

    def verify_install(self, sources, fixture, scope, step, deadline):
        need(not self.closed and self.claimed and
             len(self.locked) == 3 and {x[0] for x in self.locked} ==
             {'flow-lock','action-lock','step-lock'},
             'ALL_THREE_OWN_INSTALL_LOCKS_REQUIRED')
        fixture.validate_scope(scope)
        need(scope['phase'] == 'install' and scope['uid'] is None and
             canonical(scope) == self.scope_bytes and sources.pin == self.pin and
             str(sources.root) == str(SOURCE) and str(step) == str(STEP) and
             deadline == self.deadline and time.monotonic() < self.deadline,
             'EXACT_LIVE_INSTALL_ADMISSION_REQUIRED')
        self._verify_objects()
        return True

    def enter_install_once(self, sources, fixture, scope, step, deadline):
        self.verify_install(sources,fixture,scope,step,deadline)
        need(not self.entered, 'INSTALL_PHASE_ALREADY_ENTERED_NO_REPLAY')
        self.entered = True
        self.observation['install_phase_entered_once'] = True

    def close(self):
        if self.closed:
            return self.observation
        errors = []
        try:
            self._verify_objects()
        except BaseException as error:
            errors.append({'stage':'lease_final_identity',**public_error(error)})
        for key,fd in reversed(self.locked):
            try:
                fcntl.flock(fd,fcntl.LOCK_UN)
            except BaseException as error:
                errors.append({'stage':'unlock:'+key,**public_error(error)})
        self.locked = []
        for row in reversed(self.fds):
            if row['closed'] is False:
                try:
                    self._close_fd(row['fd'])
                except BaseException as error:
                    errors.append({'stage':'close:'+row['label'],**public_error(error)})
        self.closed = True
        self.observation.update({
            'lease_errors':errors,
            'all_tracked_lease_FDs_closed':all(x['closed'] is True for x in self.fds),
            'tracked_FD_count':len(self.fds),
            'closed_FD_count':sum(x['closed'] is True for x in self.fds),
            'FD_close_failures':[{'label':x['label'],'error':x['close_error']}
                                 for x in self.fds if x['closed'] is not True],
            'global_action_lock_released':self.observation['global_lock_acquired'] and not errors,
            'flow_lock_released':self.observation['flow_lock_exclusive'] and not errors,
            'step_lock_released':self.observation['step_lock_exclusive'] and not errors,
            'private_root_retained':self.root_created,
            'recursive_cleanup':False,
            'global_ambient_FD_equality_asserted':False,
        })
        return self.observation
