"""Read-only binding of an adopted native leaf release to its current owner.

The root-owned detached manifest pairs an already reviewed source selection
with a final CI executable.  It grants no Android or application acceptance.
Source preparation never supplies a binary hash and never opens this lease.
"""
import datetime
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import select
import stat
import time

CURRENT = Path('/home/alex/work/pocket4-android-final/CONTINUATION_CURRENT.json')
RELEASE_ROOT = Path('/etc/droidloom/native-application-leaves')
CLI = Path('/usr/bin/droidloom-applications')
PROTOCOL = 'droidloom-gallery-image-custody-v1'
MANIFEST_SCHEMA = 'pocket4-native-application-leaf-release-v1'
MAX_LEAF_SECONDS = 1530
LOCKS = [
    (CURRENT.parent/'.CONTINUATION_CURRENT.lock', [66306,41719172,33152,0,0,1,0,1794130437217307659,1794130437217307659]),
    (CURRENT.parent/'.qpr1-kernel-control-8b88.lock', [66306,41719533,33152,0,0,1,0,1794178693266232511,1794178693266232511]),
]
META = ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
OWNER_KEYS = {'acquisition','acquisition_id','active_until_utc','generation','name','scope'}
MANIFEST_KEYS = {'schema','protocol','binary','selection','catalog','foreground_owner',
                 'owner_expires_unix_seconds','before_current','before_current_copy',
                 'source_tree','ci_commit','ci_run_id','runtime_qualified','production_ready'}


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def exact(value, keys, reason):
    need(type(value) is dict and set(value) == set(keys), reason)


def integer(value, low=0, high=2**64-1):
    return type(value) is int and low <= value <= high


def digest(value, size=64):
    return type(value) is str and re.fullmatch('[0-9a-f]{'+str(size)+'}', value) is not None


def file_pin(value, maximum):
    exact(value, {'path','bytes','sha256'}, 'EXACT_RELEASE_FILE_PIN')
    need(type(value['path']) is str and Path(value['path']).is_absolute()
         and '\x00' not in value['path'] and integer(value['bytes'],1,maximum)
         and digest(value['sha256']), 'BOUNDED_TYPED_RELEASE_FILE_PIN')
    return value


def parse(raw):
    def pairs(values):
        out = {}
        for key, value in values:
            need(key not in out, 'DUPLICATE_RELEASE_JSON_KEY')
            out[key] = value
        return out
    def nonfinite(value):
        raise RuntimeError('NONFINITE_RELEASE_JSON_NUMBER')
    return json.loads(raw.decode('utf-8','strict'), object_pairs_hook=pairs, parse_constant=nonfinite)


def f9(info):
    return [getattr(info,key) for key in META]


def owner(value):
    exact(value, OWNER_KEYS, 'EXACT_FOREGROUND_OWNER_FIELDS')
    need(all(type(v) is str and 0 < len(v) <= 4096 for v in value.values()), 'TYPED_FOREGROUND_OWNER')
    need(all(re.fullmatch('[A-Za-z0-9_.-]{1,256}',value[key]) is not None
             for key in ('name','generation','acquisition_id')), 'BOUNDED_OWNER_GENERATION_AND_ACQUISITION')
    need(re.fullmatch('[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:Z|\\+00:00)',
                      value['active_until_utc']) is not None, 'EXACT_UTC_OWNER_EXPIRY_GRAMMAR')
    expiry = datetime.datetime.fromisoformat(value['active_until_utc'])
    need(expiry.tzinfo is not None and expiry.utcoffset() == datetime.timedelta(0), 'UTC_OWNER_EXPIRY_REQUIRED')
    return int(expiry.timestamp())


def manifest(value):
    exact(value, MANIFEST_KEYS, 'EXACT_DETACHED_RELEASE_MANIFEST')
    need(value['schema'] == MANIFEST_SCHEMA and value['protocol'] == PROTOCOL
         and value['runtime_qualified'] is False and value['production_ready'] is False,
         'SOURCE_BINARY_PAIRING_CONFERS_NO_RUNTIME_ACCEPTANCE')
    file_pin(value['binary'],64*1024*1024)
    need(value['binary']['path'] == str(CLI), 'ONLY_CANONICAL_APPLICATIONS_EXECUTABLE')
    file_pin(value['selection'],1024*1024); file_pin(value['catalog'],65536)
    file_pin(value['before_current_copy'],2*1024*1024)
    need(value['catalog']['path'] == str(RELEASE_ROOT/'catalogs'/(value['catalog']['sha256']+'.json'))
         and value['before_current_copy']['path'] == str(RELEASE_ROOT/'current-preimages'/
             (value['before_current_copy']['sha256']+'.json')), 'ROOT_OWNED_CONTENT_ADDRESSED_RELEASE_INPUTS')
    previous = value['before_current']
    exact(previous, {'path','bytes','sha256','f9'}, 'EXACT_ACTUAL_PRE_CAS_CURRENT_PROOF')
    file_pin({k:previous[k] for k in ('path','bytes','sha256')},2*1024*1024)
    need(previous['path'] == str(CURRENT) and type(previous['f9']) is list
         and len(previous['f9']) == 9 and all(integer(x) for x in previous['f9'])
         and previous['f9'][2:6] == [stat.S_IFREG|0o600,1000,1000,1]
         and previous['f9'][6] == previous['bytes']
         and previous['bytes'] == value['before_current_copy']['bytes']
         and previous['sha256'] == value['before_current_copy']['sha256'],
         'ORIGINAL_WHOLE_CURRENT_COPY_MUST_RETAIN_ITS_REAL_PREIMAGE')
    expiry = owner(value['foreground_owner'])
    need(integer(value['owner_expires_unix_seconds'],1,2**63-1)
         and value['owner_expires_unix_seconds'] == expiry
         and digest(value['source_tree'],40) and digest(value['ci_commit'],40)
         and integer(value['ci_run_id'],1), 'TYPED_CURRENT_RELEASE_BUILD_AND_OWNER')
    return value


class ReleaseLease:
    """Owned read descriptors and the original two shared lock OFDs."""
    def __init__(self, release_ref, preparation_ref):
        need(os.getuid() == os.geteuid() == 0, 'ORIGINAL_ROOT_LEAF_CONTROLLER_REQUIRED')
        file_pin(release_ref,65536); file_pin(preparation_ref,1024*1024)
        need(release_ref['path'] == str(RELEASE_ROOT/'releases'/(release_ref['sha256']+'.json')),
             'ONLY_ADOPTED_ROOT_OWNED_DETACHED_RELEASE_PATH')
        self.pid = os.getpid(); self.closed = False
        self.directories = {}; self.files = []; self.lock_fds = []
        self.resource_scope = None
        self.release_ref = dict(release_ref); self.preparation_ref = dict(preparation_ref)
        try:
            for path, expected in LOCKS:
                parent = self._directory(path.parent, root_owned=False)
                fd = os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
                try:
                    need(f9(os.fstat(fd)) == expected == f9(os.stat(path.name,dir_fd=parent,
                          follow_symlinks=False)), 'ORIGINAL_LOCK_INODE_AND_COMPLETE_METADATA_REQUIRED')
                    fcntl.flock(fd,fcntl.LOCK_SH|fcntl.LOCK_NB)
                except BaseException:
                    os.close(fd); raise
                self.lock_fds.append(fd)
            raw = self._file(CURRENT,None,2*1024*1024,root_owned=False)
            self.current = parse(raw)
            need(type(self.current) is dict and self.current.get('native_application_leaf_release') == release_ref,
                 'DETACHED_RELEASE_IS_NOT_IN_CANONICAL_CURRENT')
            self.release = manifest(parse(self._file(Path(release_ref['path']),release_ref,65536,root_owned=True)))
            need(self.release['owner_expires_unix_seconds'] > int(time.time()) + MAX_LEAF_SECONDS + 60,
                 'ORIGINAL_OWNER_WINDOW_MUST_COVER_COMPLETE_LEAF_AND_RETIREMENT')
            need(self.current.get('foreground_owner') == self.release['foreground_owner']
                 and self.current.get('application_qualification_preparations') == self.release['selection'],
                 'CURRENT_OWNER_AND_COMPLETE_SELECTED_SOURCE_MUST_MATCH_RELEASE')
            before_raw = self._file(Path(self.release['before_current_copy']['path']),
                self.release['before_current_copy'],2*1024*1024,root_owned=True)
            before = parse(before_raw)
            need(type(before) is dict and before.get('foreground_owner') == self.release['foreground_owner']
                 and before.get('application_qualification_preparations') == self.release['selection'],
                 'ACTUAL_PRESERVED_PRE_CAS_CURRENT_OWNER_AND_SELECTION_DIFFER')
            # Prove the sole authorized forward transition from the actual
            # preserved raw preimage. Never delete a postimage field to invent
            # historical bytes; JSON encoding preserves bool versus number.
            allowed_post = copy.deepcopy(before)
            allowed_post['native_application_leaf_release'] = release_ref
            need(json.dumps(allowed_post,sort_keys=True,separators=(',',':'),allow_nan=False)
                 == json.dumps(self.current,sort_keys=True,separators=(',',':'),allow_nan=False),
                 'CURRENT_IS_NOT_THE_EXACT_SINGLE_FIELD_RELEASE_ADOPTION_SUCCESSOR')
            selection = parse(self._file(Path(self.release['selection']['path']),
                self.release['selection'],1024*1024,root_owned=False))
            catalog = parse(self._file(Path(self.release['catalog']['path']),self.release['catalog'],65536,root_owned=True))
            need(type(catalog) is list and len(catalog) == 13, 'COMPLETE_RELEASE_SOURCE_CATALOG')
            for index,row in enumerate(catalog):
                exact(row,{'index','preparation','entry'},'EXACT_RELEASE_SOURCE_CATALOG_ROW')
                need(integer(row['index'],index,index),'ORDERED_UNIQUE_RELEASE_SOURCE_CATALOG')
                file_pin(row['preparation'],1024*1024); file_pin(row['entry'],262144)
            need(type(selection) is dict and selection.get('schema') == 'current-application-preparation-selection-v1'
                 and selection.get('selection_only') is True
                 and all(type(selection.get(key)) is int and selection[key] == 0 for key in
                         ('Android_actions','Main_actions','CURRENT_writes','new_runtime_acceptance_count'))
                 and selection.get('full_Main_execute_or_full_runtime_seed_executed') is False
                 and selection.get('historical_runtime_credit_transferred') is False
                 and selection.get('selected_preparations') == [row['preparation'] for row in catalog],
                 'EXACT_THIRTEEN_SOURCE_ONLY_PREPARATIONS_REQUIRED')
            selected = [row for row in catalog[1:2] if row['preparation'] == preparation_ref]
            need(len(selected) == 1, 'THIS_GALLERY_PREPARATION_MUST_BE_SELECTED_BY_THE_ADOPTED_RELEASE')
            self._file(Path(preparation_ref['path']),preparation_ref,1024*1024,root_owned=False)
            self._file(Path(selected[0]['entry']['path']),selected[0]['entry'],262144,root_owned=False)
            self.cli_reference = dict(self.release['binary'])
            self._file(CLI,self.cli_reference,64*1024*1024,root_owned=True,executable=True)
            self.guard()
        except BaseException:
            self.close(); raise

    def _directory(self,path,root_owned):
        path = Path(path)
        if str(path) in self.directories:
            fd,identity,parent,name,required = self.directories[str(path)]
            if root_owned:
                need(identity[3:5] == [0,0] and identity[2] & 0o022 == 0, 'ROOT_RELEASE_PARENT_NOT_PRIVATE')
                self.directories[str(path)] = (fd,identity,parent,name,True)
            return fd
        if path == Path('/'):
            parent = name = None
            fd = os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        else:
            parent = self._directory(path.parent,root_owned); name = path.name
            need(name not in ('.','..'), 'CANONICAL_RELEASE_PARENT')
            fd = os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
        try:
            identity = f9(os.fstat(fd))[:6]
            need(stat.S_ISDIR(identity[2]) and identity == f9(path.lstat())[:6], 'HELD_RELEASE_DIRECTORY_IDENTITY')
            if root_owned:
                need(identity[3:5] == [0,0] and identity[2] & 0o022 == 0, 'ROOT_RELEASE_PARENT_NOT_PRIVATE')
            self.directories[str(path)] = (fd,identity,parent,name,root_owned)
            return fd
        except BaseException:
            os.close(fd); raise

    def _file(self,path,reference,maximum,root_owned,executable=False):
        need(path.is_absolute() and path.resolve() == path, 'CANONICAL_RELEASE_FILE')
        parent = self._directory(path.parent,root_owned)
        fd = os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
        try:
            identity = f9(os.fstat(fd))
            need(stat.S_ISREG(identity[2]) and identity[5] == 1 and 0 < identity[6] <= maximum,
                 'BOUNDED_SINGLE_LINK_HELD_RELEASE_FILE')
            if root_owned:
                need(identity[3:5] == [0,0] and identity[2] & 0o022 == 0, 'ROOT_OWNED_RELEASE_FILE_REQUIRED')
            if path == CURRENT:
                need(identity[2:6] == [stat.S_IFREG|0o600,1000,1000,1], 'ORIGINAL_CURRENT_CUSTODY_REQUIRED')
            if executable:
                need(identity[2] & 0o111 != 0 and identity[2] & 0o6000 == 0, 'ORDINARY_INSTALLED_NATIVE_EXECUTABLE')
            raw = self._body(fd,identity[6])
            actual = {'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
            need(reference is None or actual == reference, 'FULL_HELD_RELEASE_FILE_HASH_DIFFERS')
            need(identity == f9(os.fstat(fd)) == f9(os.stat(path.name,dir_fd=parent,follow_symlinks=False)),
                 'RELEASE_FILE_CHANGED_DURING_READ')
            self.files.append((fd,identity,parent,path.name,actual))
            return raw
        except BaseException:
            os.close(fd); raise

    @staticmethod
    def _body(fd,size):
        result = bytearray(); offset = 0
        while offset < size:
            raw = os.pread(fd,min(65536,size-offset),offset)
            need(raw,'SHORT_RELEASE_FILE_BODY'); result.extend(raw); offset += len(raw)
        need(os.pread(fd,1,size) == b'','LONG_RELEASE_FILE_BODY')
        return bytes(result)

    def guard(self):
        need(not self.closed and os.getpid() == self.pid, 'SAME_PROCESS_LIVE_RELEASE_LEASE_REQUIRED')
        need(self.release['owner_expires_unix_seconds'] > int(time.time()) + 30, 'ORIGINAL_FOREGROUND_OWNER_EXPIRED')
        for path,(fd,identity,parent,name,required) in self.directories.items():
            need(f9(os.fstat(fd))[:6] == identity == f9(os.lstat(path))[:6], 'RELEASE_PARENT_IDENTITY_CHANGED')
            if parent is not None:
                need(f9(os.stat(name,dir_fd=parent,follow_symlinks=False))[:6] == identity,
                     'RELEASE_PARENT_LINK_CHANGED')
        for (path,expected),fd in zip(LOCKS,self.lock_fds):
            need(f9(os.fstat(fd)) == expected == f9(path.lstat()), 'ORIGINAL_RELEASE_LOCK_CHANGED')
        for fd,identity,parent,name,reference in self.files:
            need(f9(os.fstat(fd)) == identity == f9(os.stat(name,dir_fd=parent,follow_symlinks=False)),
                 'HELD_CURRENT_RELEASE_OR_SOURCE_METADATA_CHANGED')
            need(hashlib.sha256(self._body(fd,identity[6])).hexdigest() == reference['sha256'],
                 'HELD_CURRENT_RELEASE_OR_SOURCE_BODY_CHANGED')
            need(f9(os.fstat(fd)) == identity == f9(os.stat(name,dir_fd=parent,follow_symlinks=False)),
                 'RELEASE_CHANGED_DURING_BOOKEND')
        if self.resource_scope is not None:
            self.resource_scope.report()
        return dict(self.cli_reference)

    def admit_owned_leaf_resources(self):
        """Bind only this real native parent's newly created descendant group.

        A nonempty cgroup v2 parent need not expose local memory controls in
        its child. The parent's held, numeric hard bounds cover the complete
        descendant tree, including this child and its nested commands. No
        shared ancestor is altered and no sibling can escape job retirement.
        """
        self.guard()
        need(self.resource_scope is None, 'NATIVE_RESOURCE_SCOPE_ALREADY_BOUND')
        cli_identity = next(identity for _,identity,_,_,ref in self.files
                            if ref['path'] == str(CLI))
        self.resource_scope = OwnedLeafResources(self.cli_reference,cli_identity)
        self.resource_scope.report()
        return self.resource_scope

    def close(self):
        if self.closed:
            return
        if self.resource_scope is not None:
            self.resource_scope.close()
        for fd, *_ in reversed(self.files):
            os.close(fd)
        for fd in reversed(self.lock_fds):
            # flock belongs to the open file description. A forked child may
            # close its inherited copy, but must not unlock the parent's OFD.
            os.close(fd)
        for fd, *_ in reversed(list(self.directories.values())):
            os.close(fd)
        self.closed = True

    def __enter__(self):
        self.guard(); return self

    def __exit__(self,*unused):
        self.close()


def bind_release(release_ref,preparation_ref):
    return ReleaseLease(release_ref,preparation_ref)


class OwnedLeafResources:
    """Held effective limits, actual parent executable and nested ownership.

    This object is created only by a live release lease. A report is freshly
    measured evidence, never an admission input supplied in a JSON request.
    """
    def __init__(self,cli_reference,cli_identity):
        self.pid = os.getpid(); self.ppid = os.getppid(); self.closed = False
        self.fds = []; self.dirs = []; self.controls = []
        self.cli_reference = dict(cli_reference); self.cli_identity = cli_identity
        try:
            self.proc = self._directory(Path('/proc')/str(self.ppid))
            self.start = self._process_identity()
            self.pidfd = os.pidfd_open(self.ppid,0); self.fds.append(self.pidfd)
            self.poller = select.poll(); self.poller.register(self.pidfd,select.POLLIN)
            # /proc/<held native parent>/exe is the one deliberate kernel
            # magic-link open. Its actual OFD must equal the adopted binary.
            self.exe = os.open('exe',os.O_RDONLY|os.O_CLOEXEC,dir_fd=self.proc)
            self.fds.append(self.exe)
            need(f9(os.fstat(self.exe)) == self.cli_identity,
                 'ACTUAL_NATIVE_PARENT_EXECUTABLE_DIFFERS_FROM_RELEASE')
            self.membership = self._membership(Path('/proc/self/cgroup').read_bytes())
            self.parent_membership = self._membership(self._read(self.proc,'cgroup'))
            self.path = Path('/sys/fs/cgroup')/self.membership.lstrip('/')
            self.parent_path = Path('/sys/fs/cgroup')/self.parent_membership.lstrip('/')
            need(self.parent_path != Path('/sys/fs/cgroup')
                 and self.path.parent == self.parent_path
                 and re.fullmatch('droidloom-app-calendar-reminder-leaf-'+str(self.ppid)+'-[0-9]+',
                                  self.path.name) is not None,
                 'ONLY_NATIVE_CREATED_NESTED_GALLERY_CGROUP')
            self.parent = self._directory(self.parent_path)
            self.child = self._directory(self.path)
            self.limits = {}
            for key in ('cpu.max','memory.max','memory.swap.max','pids.max'):
                fd = self._control(self.parent,key)
                self.limits[key] = self._text(fd)
            self._limits(self.limits)
            self.events = self._control(self.parent,'memory.events')
            self.swap = self._control(self.parent,'memory.swap.current')
            self.peak = self._control(self.parent,'memory.peak')
            self.procs = self._control(self.child,'cgroup.procs')
            for metric in ('cpu.stat','memory.current','pids.current'):
                self._control(self.parent,metric)
            # Present child limits may only further restrict the effective
            # ancestor limits. Their exact values are held across bookends.
            self.child_limits = {}
            for key in ('cpu.max','memory.max','memory.swap.max','pids.max'):
                try:
                    fd = self._control(self.child,key)
                except FileNotFoundError:
                    continue
                self.child_limits[key] = self._text(fd)
            self.report()
        except BaseException:
            self.close(); raise

    @staticmethod
    def _membership(raw):
        rows = raw.decode('ascii','strict').splitlines()
        need(len(rows) == 1 and rows[0].startswith('0::/'), 'ONE_REAL_CGROUP2_MEMBERSHIP')
        value = rows[0][3:]
        need(value != '/' and all(part not in ('','.','..') for part in value[1:].split('/')),
             'NONROOT_CANONICAL_NATIVE_RESOURCE_GROUP')
        return value

    @staticmethod
    def _read(parent,name):
        fd = os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
        try:
            raw = os.read(fd,65537)
            need(len(raw) <= 65536, 'BOUNDED_NATIVE_KERNEL_METADATA')
            return raw
        finally:
            os.close(fd)

    @staticmethod
    def _text(fd):
        raw = os.pread(fd,65537,0)
        need(len(raw) <= 65536, 'BOUNDED_HELD_RESOURCE_CONTROL')
        return raw.decode('ascii','strict').strip()

    def _directory(self,path):
        need(path.is_absolute() and path.resolve() == path, 'CANONICAL_NATIVE_RESOURCE_DIRECTORY')
        fd = os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        self.fds.append(fd)
        identity = f9(os.fstat(fd))[:5]
        need(identity == f9(path.lstat())[:5] and identity[3:5] == [0,0]
             and identity[2] & 0o022 == 0, 'HELD_ROOT_NATIVE_RESOURCE_DIRECTORY')
        self.dirs.append((fd,path,identity))
        return fd

    def _control(self,parent,name):
        fd = os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
        self.fds.append(fd)
        identity = f9(os.fstat(fd))[:6]
        need(identity == f9(os.stat(name,dir_fd=parent,follow_symlinks=False))[:6]
             and stat.S_ISREG(identity[2]) and identity[3:5] == [0,0]
             and identity[2] & 0o022 == 0, 'HELD_ROOT_NATIVE_RESOURCE_CONTROL')
        self.controls.append((fd,parent,name,identity))
        return fd

    def _process_identity(self):
        raw = self._read(self.proc,'stat').decode('ascii','strict')
        head,tail = raw.rsplit(') ',1); fields = tail.split()
        pid = int(head.split(' (',1)[0])
        need(pid == self.ppid and len(fields) >= 20, 'ACTUAL_NATIVE_PARENT_PROCESS')
        status = self._read(self.proc,'status').decode('ascii','strict').splitlines()
        uids = [row.split()[1:] for row in status if row.startswith('Uid:')]
        need(uids == [['0','0','0','0']], 'ORIGINAL_ROOT_NATIVE_PARENT_CREDENTIALS')
        return (pid,int(fields[19]))

    @staticmethod
    def _limits(values):
        cpu = values['cpu.max'].split()
        need(len(cpu) == 2 and all(x.isdigit() for x in cpu)
             and 0 < 2*int(cpu[0]) <= int(cpu[1]) and int(cpu[1]) > 0
             and values['memory.max'] == '536870912'
             and values['memory.swap.max'] == '0' and values['pids.max'] == '64',
             'HELD_ANCESTOR_MUST_PROVE_ORIGINAL_CPU_MEMORY_SWAP_PID_HARD_LIMITS')

    def report(self):
        need(not self.closed and os.getpid() == self.pid and os.getppid() == self.ppid
             and not self.poller.poll(0) and self._process_identity() == self.start,
             'ORIGINAL_NATIVE_PARENT_EXITED_OR_CHANGED')
        actual_exe = os.open('exe',os.O_RDONLY|os.O_CLOEXEC,dir_fd=self.proc)
        try:
            need(f9(os.fstat(actual_exe)) == self.cli_identity,
                 'NATIVE_PARENT_EXECUTED_A_DIFFERENT_BINARY')
        finally:
            os.close(actual_exe)
        need(f9(os.fstat(self.exe)) == self.cli_identity
             and hashlib.sha256(ReleaseLease._body(self.exe,self.cli_identity[6])).hexdigest()
                 == self.cli_reference['sha256']
             and f9(os.fstat(self.exe)) == self.cli_identity,
             'ACTUAL_HELD_NATIVE_PARENT_BINARY_CHANGED')
        need(self._membership(Path('/proc/self/cgroup').read_bytes()) == self.membership
             and self._membership(self._read(self.proc,'cgroup')) == self.parent_membership,
             'NATIVE_PARENT_OR_OWNED_CHILD_CHANGED_CGROUP')
        for fd,path,identity in self.dirs:
            need(f9(os.fstat(fd))[:5] == identity == f9(path.lstat())[:5],
                 'HELD_NATIVE_RESOURCE_DIRECTORY_REPLACED')
        for fd,parent,name,identity in self.controls:
            need(f9(os.fstat(fd))[:6] == identity ==
                 f9(os.stat(name,dir_fd=parent,follow_symlinks=False))[:6],
                 'HELD_NATIVE_RESOURCE_CONTROL_REPLACED')
            expected = self.limits if parent == self.parent else self.child_limits
            if name in expected:
                need(self._text(fd) == expected[name], 'PINNED_RESOURCE_LIMIT_CHANGED')
        self._limits(self.limits)
        events = {}
        for line in self._text(self.events).splitlines():
            pair = line.split()
            need(len(pair) == 2 and pair[0] not in events and pair[1].isdigit(),
                 'EXACT_REAL_ANCESTOR_MEMORY_EVENTS')
            events[pair[0]] = int(pair[1])
        need(all(events.get(key) == 0 for key in ('oom','oom_kill','oom_group_kill'))
             and self._text(self.swap) == '0', 'OWNED_RESOURCE_ANCESTOR_OOM_OR_SWAP')
        need(str(self.pid) in self._text(self.procs).splitlines(),
             'THIS_PROCESS_NOT_IN_ITS_NATIVE_OWNED_GROUP')
        affinity = os.sched_getaffinity(0)
        need(bool(affinity) and affinity <= {20,21}
             and resource.getrlimit(resource.RLIMIT_CORE) == (0,0),
             'ORIGINAL_LEAF_AFFINITY_AND_CORE_LIMITS_REQUIRED')
        peak = self._text(self.peak)
        need(peak.isdigit(), 'REAL_ANCESTOR_MEMORY_PEAK_REQUIRED')
        need(not self.poller.poll(0) and self._process_identity() == self.start
             and self._membership(Path('/proc/self/cgroup').read_bytes()) == self.membership
             and self._membership(self._read(self.proc,'cgroup')) == self.parent_membership,
             'NATIVE_RESOURCE_IDENTITY_CHANGED_DURING_BOOKEND')
        result = {'schema':'pocket4-held-effective-calendar-resources-v1',
            'cgroup':'0::'+self.membership,'limiting_ancestor':'0::'+self.parent_membership,
            'limits':dict(self.limits),'child_local_limits':dict(self.child_limits),
            'affinity':sorted(affinity),'memory_events':events,
            'memory_peak_bytes':int(peak),'swap_current_bytes':0,
            'native_parent_pid':self.ppid,'native_parent_start_ticks':self.start[1],
            'hierarchy_is_within_original_native_retirement_scope':True}
        required = ('cpu.max','cpu.stat','memory.max','memory.current','memory.peak',
                    'memory.events','memory.swap.max','memory.swap.current','pids.current')
        metrics = {name:self._text(fd) for fd,parent,name,_ in self.controls
                   if parent == self.parent and name in required}
        need(set(metrics) == set(required), 'COMPLETE_REAL_HELD_CALENDAR_RESOURCE_METRICS')
        need(metrics['cpu.max'] == self.limits['cpu.max']
             and metrics['memory.max'] == self.limits['memory.max']
             and metrics['memory.swap.max'] == '0' and metrics['memory.swap.current'] == '0'
             and all(metrics[key].isdigit() for key in ('memory.current','memory.peak','pids.current')),
             'HELD_CALENDAR_RESOURCE_METRICS_CHANGED')
        measured = {}
        for row in metrics['memory.events'].splitlines():
            key,value = row.split()
            need(key not in measured and value.isdigit(), 'EXACT_REAL_CALENDAR_MEMORY_EVENTS')
            measured[key] = int(value)
        need(all(measured.get(key) == 0 for key in ('oom','oom_kill','oom_group_kill')),
             'CALENDAR_RESOURCE_ANCESTOR_OOM')
        result['memory_events'] = measured
        result['memory_peak_bytes'] = int(metrics['memory.peak'])
        result['ancestor_files'] = metrics
        return result

    def close(self):
        if self.closed:
            return
        self.closed = True
        for fd in reversed(self.fds):
            os.close(fd)


def bind_current(preparation_ref):
    """Discover only the selected root manifest; the lease re-reads under locks.

    This first bounded read grants no authority. ReleaseLease independently
    opens both original lock OFDs and validates the complete actual chain.
    """
    fd = os.open(CURRENT,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        metadata = f9(os.fstat(fd))
        need(metadata[2:6] == [stat.S_IFREG|0o600,1000,1000,1]
             and 0 < metadata[6] < 2*1024*1024, 'ORIGINAL_BOUNDED_CURRENT_DISCOVERY')
        current = parse(ReleaseLease._body(fd,metadata[6]))
        need(metadata == f9(os.fstat(fd)) == f9(CURRENT.lstat()), 'CURRENT_DISCOVERY_CHANGED')
        need(type(current) is dict, 'COMPLETE_CURRENT_DISCOVERY_REQUIRED')
        release_ref = current.get('native_application_leaf_release')
        file_pin(release_ref,65536)
    finally:
        os.close(fd)
    return ReleaseLease(release_ref,preparation_ref)
