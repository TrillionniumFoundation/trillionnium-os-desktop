"""Bind the unchanged seven entry FDs to the same Main's actual user namespace."""
import hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
raw=(ROOT/'inputs/main/held_runtime.py').read_bytes()
assert hashlib.sha256(raw).hexdigest()=='72cf33399ca3c280fc0c9288669f7d6c13d387e41b5fb930cf477f2b940f16b4'
s=raw.decode()

def replace(old,new):
    global s
    assert s.count(old)==1,(old[:80],s.count(old))
    s=s.replace(old,new)

replace('import ctypes','import copy\nimport ctypes')
replace('import time','import time\nimport types')
replace('HELPER_SOURCE_SHA = "adf5b08f7854bec061ab8d2a208f3414339701c816218881e6550afde2e6c31c"',
        'HELPER_SOURCE_SHA = "5367f5c9786b9d3795b14c51af6c6bd488782a624b9066ce84e64af7feacf792"')
replace('HELPER_BINARY_SHA = "21ba02ff60ba07667c3b5601c1ff9cb9b2d9cce2fae9290a6f39e47c18126689"',
        'HELPER_BINARY_SHA = "67cfd1c212e9f40ce3f0ff7be856a05f8189c674cbfa270757a672ea596a6c3f"')
replace('    def __init__(self, expected, helper_path, helper_sha256=HELPER_BINARY_SHA):',
        '    def __init__(self, expected, helper_path, helper_sha256=HELPER_BINARY_SHA, *, main_user_namespace):')
replace('        self.expected = expected\n        self.helper_path', '        self.expected = expected\n        self.main_user_namespace = copy.deepcopy(main_user_namespace)\n        self.user_namespace_fd = -1\n        self._mapping_module = load_mapping_module()\n        self.helper_path')
replace('            self._verify_proc()\n            self.record =', '''            self.user_namespace_fd = self._own(os.open('ns/user', os.O_RDONLY | os.O_CLOEXEC,
                                                        dir_fd=self.proc_fd))
            self._verify_proc()
            self.record =''')
replace('    def verify(self):\n        with self._lock:', '''    def _verify_user_namespace(self):
        if self.user_namespace_fd < 0:
            return  # Constructor has not yet acquired all original namespaces.
        m = self._mapping_module
        fixed = self.main_user_namespace
        fact = m.namespace_fact(self.user_namespace_fd)
        require(fact == fixed['user_namespace'], 'held entry user namespace differs from original Main')
        named = os.open('ns/user', os.O_RDONLY | os.O_CLOEXEC, dir_fd=self.proc_fd)
        try:
            require(m.namespace_fact(named) == fact, 'original init changed user namespace')
        finally:
            os.close(named)
        deadline = time.monotonic() + 3
        uid_raw = read_at(self.proc_fd, 'uid_map', 8192, deadline)
        gid_raw = read_at(self.proc_fd, 'gid_map', 8192, deadline)
        require(m.map_row(uid_raw) == fixed['uid_map'] and m.map_row(gid_raw) == fixed['gid_map'],
                'held Main user namespace maps changed')
        status = read_at(self.proc_fd, 'status', 65536, deadline)
        gids = re.findall(rb'^Gid:[ \\t]+([0-9 \\t]+)$', status, re.M)
        require(len(gids) == 1 and [int(x) for x in gids[0].split()] == fixed['root_gids'],
                'held Main root gid changed')
        expected = {'host_pid': self.expected['pid'], 'parent_host_pid': self.expected['ppid'],
                    'start_ticks': int(self.expected['start']),
                    'namespace_pids': [int(x) for x in self.expected['nspid']],
                    'uids': [int(x) for x in self.expected['uid']],
                    'namespaces': {k: self.expected['ns'][k] for k in ('pid', 'mnt')}}
        boot = m.HeldMainUserNamespace._read_boot_id()
        m.validate_observation(fixed, fact, expected, boot)
        host = os.open('/proc/self/ns/user', os.O_RDONLY | os.O_CLOEXEC)
        parent = -1
        try:
            parent = fcntl.ioctl(self.user_namespace_fd, m.NS_GET_PARENT)
            require(m.namespace_fact(parent) == m.namespace_fact(host) == fixed['parent_user_namespace'],
                    'held Main user namespace foreign parent')
        finally:
            if parent >= 0: os.close(parent)
            os.close(host)
        for name, fd in self.namespaces.items():
            owner = fcntl.ioctl(fd, m.NS_GET_USERNS)
            try:
                require(m.namespace_fact(owner) == fact, 'held entry namespace has foreign user owner')
                actual = m.namespace_fact(fd, NS_TYPES[name], name)
                require(actual == fixed['owned_entry_namespaces'][name]['namespace'],
                        'held entry namespace differs from original Main observation')
            finally:
                os.close(owner)
        require(read_at(self.proc_fd, 'uid_map', 8192, deadline) == uid_raw
                and read_at(self.proc_fd, 'gid_map', 8192, deadline) == gid_raw,
                'held entry user maps changed while observed')

    def verify(self):
        with self._lock:''')
replace('        if self.root_fd >= 0:', '        self._verify_user_namespace()\n        if self.root_fd >= 0:')
replace('            argv += ["--", *map(str, command)]', '''            self._verify_user_namespace()
            user = self._mapping_module.namespace_fact(self.user_namespace_fd)
            argv += ['--expected-userns-device=' + str(user['device']),
                     '--expected-userns-inode=' + str(user['inode']),
                     '--expected-init-start-ticks=' + self.expected['start']]
            argv += ["--", *map(str, command)]''')
pin=hashlib.sha256((ROOT/'source/main_user_namespace.py').read_bytes()).hexdigest()
loader='''
MAPPING_PATH='/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1/source/main/main_user_namespace.py'
MAPPING_SHA=__SOURCE_SHA_PLACEHOLDER__
_mapping_module=None

def load_mapping_module():
    global _mapping_module
    if _mapping_module is None:
        fd=os.open(MAPPING_PATH,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:
            before=fd_record(fd)
            require(stat.S_ISREG(before['mode']) and before['nlink']==1 and
                    before['uid']==before['gid']==0 and before['mode']&0o022==0 and
                    0<before['bytes']<=131072,'root-owned pinned mapping source required')
            raw=read_fd(fd,131072,time.monotonic()+3)
            require(len(raw)==before['bytes'] and fd_record(fd)==before and
                    hashlib.sha256(raw).hexdigest()==MAPPING_SHA,'mapping source changed')
        finally:os.close(fd)
        value=types.ModuleType('held_entry_actual_main_mapping');value.__file__=MAPPING_PATH
        exec(compile(raw,MAPPING_PATH,'exec'),value.__dict__);_mapping_module=value
    return _mapping_module

'''.replace('__SOURCE_SHA_PLACEHOLDER__',repr(pin))
s=s.replace('class HeldTarget:',loader+'class HeldTarget:')
compile(s,'held_runtime.py','exec')
(ROOT/'source/held_runtime.py').write_text(s)
print('held_runtime',len(s.encode()),hashlib.sha256(s.encode()).hexdigest())
