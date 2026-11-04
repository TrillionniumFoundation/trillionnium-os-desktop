#!/usr/bin/env python3
"""Actual local old/new owned-child exec control; no namespaces or services."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'factory-diagnostic03-runtime02-freeze-01/controller.py'
NEW = HERE / 'controller.py'
PINS = {
    str(OLD): '2db9c643b177a61989d5fd3c860caba8a40b4abc7b8009db408b08d93caf99f2',
    str(NEW): 'e76e35332951ba72e68bc59e7d4849ec05c06233c5db95d8d50d74ecfefe0628',
}

def load(path):
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PINS[str(path)]
    scope = {'__name__': 'owned_local_capdrop_control', '__file__': str(path)}
    exec(compile(raw, str(path), 'exec'), scope)
    return scope

def caps():
    values = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    return {name: int(values[name].strip(), 16) for name in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb')}

assert os.geteuid() == 0
old, new = load(OLD), load(NEW)
parent_before = caps()
fds_before = sorted(os.listdir('/proc/self/fd'))
python = Path(sys.executable).resolve(strict=True)
elf = os.open(python, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
info = os.fstat(elf)
assert stat.S_ISREG(info.st_mode) and info.st_mode & 0o6000 == 0
python_sha = hashlib.sha256(python.read_bytes()).hexdigest()
probe = '''import ctypes,json,os
from pathlib import Path
rows=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
libc=ctypes.CDLL(None,use_errno=True)
death=ctypes.c_int()
rc=libc.prctl(2,ctypes.byref(death),0,0,0)
print(json.dumps({'uids':list(os.getresuid()),'gids':list(os.getresgid()),'groups':os.getgroups(),
 'caps':{name:int(rows[name].strip(),16) for name in ('CapInh','CapPrm','CapEff','CapAmb')},
 'pdeathsig_rc':rc,'pdeathsig':death.value}))
'''
rows = []
try:
    for label, module in (('original_retains_inheritable', old), ('repaired_clears_all_sets', new)):
        def child_body(parent_fd):
            header = new['CapabilityHeader'](0x20080522, 0)
            data = (new['CapabilityData'] * 2)()
            new['checked'](new['libc'].capget(ctypes.byref(header), data), 'local initial capget')
            # CAP_NET_BIND_SERVICE is already permitted in this owned local
            # child; seed only that existing permission into inheritable.
            assert data[0].permitted & (1 << 10)
            data[0].inheritable |= 1 << 10
            new['checked'](new['libc'].capset(ctypes.byref(header), data), 'seed existing permitted bit')
            module['child_exec'](elf, [str(python), '-I', '-c', probe], 61171)(parent_fd)
            raise AssertionError('exec returned')
        child = module['spawn'](label, child_body, [elf])
        try:
            result = child.join(6)
            assert result['returncode'] == 0 and not result['stderr'] and not result['forced_kill']
            observation = json.loads(result['stdout'])
            assert observation['uids'] == observation['gids'] == [61171] * 3
            assert observation['groups'] == []
            assert observation['pdeathsig_rc'] == 0 and observation['pdeathsig'] == 9
            assert observation['caps']['CapEff'] == observation['caps']['CapPrm'] == observation['caps']['CapAmb'] == 0
            assert observation['caps']['CapInh'] == ((parent_before['CapInh'] | (1 << 10)) if module is old else 0)
            rows.append({'label': label, 'pass': True, 'actual_child': result, 'observed_after_exec': observation})
        finally:
            if child.returncode is None: child.retire()
            assert child.close_streams() == []
            os.close(child.pidfd)
finally:
    os.close(elf)
parent_after = caps()
fds_after = sorted(os.listdir('/proc/self/fd'))
assert parent_after == parent_before and fds_after == fds_before
report = {'schema':1, 'scope':'actual local child setuid/capset/exec; host factory and Android not executed',
          'source_pins':PINS, 'python':{'path':str(python),'sha256':python_sha},
          'cases':rows, 'parent_capabilities_unchanged':True, 'parent_fd_set_restored':True,
          'owned_children_reaped':2, 'namespace_actions':0, 'service_actions':0,
          'production_guard_changed':False, 'whole_app_production_ready':False}
raw = (json.dumps(report,indent=2) + '\n').encode()
with (HERE/'capdrop-control-result.json').open('xb') as stream: stream.write(raw)
print(json.dumps({'pass':True,'cases':2,'result_sha256':hashlib.sha256(raw).hexdigest(),
                  'original_inheritable':rows[0]['observed_after_exec']['caps']['CapInh'],
                  'repaired_inheritable':rows[1]['observed_after_exec']['caps']['CapInh']}))
